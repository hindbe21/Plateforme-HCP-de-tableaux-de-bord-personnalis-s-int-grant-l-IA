from __future__ import annotations

from typing import Any

import pandas as pd
from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from .services import charger_dataframe_postgresql
from .views import recuperer_jeu_donnees_autorise


MOTS_IDENTIFIANT = {
    "id",
    "identifiant",
    "code",
    "numero",
    "numéro",
    "cin",
    "cne",
}


def _normaliser_vides(dataframe: pd.DataFrame) -> pd.DataFrame:
    resultat = dataframe.copy()

    for colonne in resultat.select_dtypes(include="object").columns:
        resultat[colonne] = resultat[colonne].apply(
            lambda valeur: (
                pd.NA
                if isinstance(valeur, str) and not valeur.strip()
                else valeur
            )
        )

    return resultat


def _format_nombre(valeur: Any, decimales: int = 2) -> str:
    if valeur is None or pd.isna(valeur):
        return "—"

    try:
        nombre = float(valeur)
    except (TypeError, ValueError):
        return str(valeur)

    if nombre.is_integer():
        return f"{int(nombre):,}".replace(",", " ")

    return f"{nombre:,.{decimales}f}".replace(",", " ")


def _nom_normalise(nom: str) -> str:
    return (
        nom.strip()
        .lower()
        .replace("-", "_")
        .replace(" ", "_")
    )


def _semble_identifiant(nom: str, ratio_uniques: float) -> bool:
    nom_normalise = _nom_normalise(nom)

    return bool(
        nom_normalise in MOTS_IDENTIFIANT
        or nom_normalise.startswith(
            ("id_", "code_", "numero_", "numéro_")
        )
        or ratio_uniques >= 0.98
    )


def _profil_colonne(
    nom: str,
    serie: pd.Series,
    nombre_lignes: int,
) -> dict[str, Any]:
    valeurs = serie.dropna()
    nombre_manquantes = int(serie.isna().sum())
    nombre_uniques = int(valeurs.nunique(dropna=True))
    ratio_uniques = (
        nombre_uniques / max(len(valeurs), 1)
    )

    numerique = pd.to_numeric(valeurs, errors="coerce")
    ratio_numerique = (
        float(numerique.notna().mean())
        if not valeurs.empty
        else 0.0
    )

    dates = pd.to_datetime(
        valeurs,
        errors="coerce",
        dayfirst=True,
    )
    ratio_date = (
        float(dates.notna().mean())
        if not valeurs.empty
        else 0.0
    )

    exemples = [
        str(valeur)[:55]
        for valeur in valeurs.astype(str).drop_duplicates().head(3)
    ]

    profil: dict[str, Any] = {
        "nom": nom,
        "nombre_manquantes": nombre_manquantes,
        "taux_manquantes": round(
            100 * nombre_manquantes / max(nombre_lignes, 1),
            1,
        ),
        "nombre_uniques": nombre_uniques,
        "exemples": exemples,
        "statistiques": [],
        "modalites": [],
    }

    identifiant = _semble_identifiant(
        nom,
        ratio_uniques,
    )

    if ratio_numerique >= 0.90 and not identifiant:
        valeurs_numeriques = pd.to_numeric(
            serie,
            errors="coerce",
        ).dropna()

        profil["type"] = "Numérique"
        profil["type_code"] = "NUMERIQUE"
        profil["recommandation"] = (
            "Indicateur, histogramme ou mesure d’un graphique."
        )

        if not valeurs_numeriques.empty:
            profil["statistiques"] = [
                ("Minimum", _format_nombre(valeurs_numeriques.min())),
                ("Maximum", _format_nombre(valeurs_numeriques.max())),
                ("Moyenne", _format_nombre(valeurs_numeriques.mean())),
                ("Médiane", _format_nombre(valeurs_numeriques.median())),
                ("Écart-type", _format_nombre(valeurs_numeriques.std())),
                ("1er quartile", _format_nombre(valeurs_numeriques.quantile(0.25))),
                ("3e quartile", _format_nombre(valeurs_numeriques.quantile(0.75))),
            ]

    elif ratio_date >= 0.90 and nombre_uniques > 1:
        dates_valides = pd.to_datetime(
            serie,
            errors="coerce",
            dayfirst=True,
        ).dropna()

        profil["type"] = "Date"
        profil["type_code"] = "DATE"
        profil["recommandation"] = (
            "Courbe chronologique ou filtre par période."
        )

        if not dates_valides.empty:
            profil["statistiques"] = [
                ("Première date", dates_valides.min().strftime("%d/%m/%Y")),
                ("Dernière date", dates_valides.max().strftime("%d/%m/%Y")),
            ]

    else:
        profil["type"] = "Identifiant" if identifiant else "Texte / catégorie"
        profil["type_code"] = "IDENTIFIANT" if identifiant else "TEXTE"

        if identifiant:
            profil["recommandation"] = (
                "À conserver pour identifier les lignes, mais à éviter comme axe principal."
            )
        elif nombre_uniques <= 12:
            profil["recommandation"] = (
                "Barres, anneau ou filtre catégoriel."
            )
        elif nombre_uniques <= 50:
            profil["recommandation"] = (
                "Barres avec limite de résultats ou tableau."
            )
        else:
            profil["recommandation"] = (
                "Tableau détaillé, recherche ou filtre."
            )

        effectifs = valeurs.astype(str).value_counts().head(5)
        profil["modalites"] = [
            {
                "valeur": str(valeur)[:60],
                "effectif": int(effectif),
                "pourcentage": round(
                    100 * int(effectif) / max(len(valeurs), 1),
                    1,
                ),
            }
            for valeur, effectif in effectifs.items()
        ]

    return profil


def _correlations(dataframe: pd.DataFrame) -> list[dict[str, Any]]:
    colonnes_numeriques: dict[str, pd.Series] = {}

    for colonne in dataframe.columns:
        serie = pd.to_numeric(
            dataframe[colonne],
            errors="coerce",
        )

        if serie.notna().mean() >= 0.90 and serie.nunique() > 1:
            colonnes_numeriques[str(colonne)] = serie

    if len(colonnes_numeriques) < 2:
        return []

    matrice = pd.DataFrame(colonnes_numeriques).corr()
    resultats = []
    deja_vus = set()

    for colonne_a in matrice.columns:
        for colonne_b in matrice.columns:
            if colonne_a == colonne_b:
                continue

            paire = tuple(sorted((str(colonne_a), str(colonne_b))))

            if paire in deja_vus:
                continue

            deja_vus.add(paire)
            valeur = matrice.loc[colonne_a, colonne_b]

            if pd.isna(valeur):
                continue

            resultats.append(
                {
                    "colonne_a": colonne_a,
                    "colonne_b": colonne_b,
                    "valeur": round(float(valeur), 3),
                    "force": abs(float(valeur)),
                }
            )

    return sorted(
        resultats,
        key=lambda element: element["force"],
        reverse=True,
    )[:8]


def _constats(
    profils: list[dict[str, Any]],
    doublons: int,
    taux_manquantes: float,
) -> list[str]:
    resultats = []

    if doublons:
        resultats.append(
            f"{doublons} ligne(s) dupliquée(s) ont été détectée(s)."
        )
    else:
        resultats.append(
            "Aucune ligne entièrement dupliquée n’a été détectée."
        )

    if taux_manquantes >= 10:
        resultats.append(
            f"Les valeurs manquantes représentent {taux_manquantes:.1f} % des cellules."
        )
    elif taux_manquantes > 0:
        resultats.append(
            f"Le taux global de valeurs manquantes reste limité à {taux_manquantes:.1f} %."
        )
    else:
        resultats.append(
            "Le jeu de données ne contient aucune valeur manquante."
        )

    colonnes_tres_incompletes = [
        profil["nom"]
        for profil in profils
        if profil["taux_manquantes"] >= 40
    ]

    if colonnes_tres_incompletes:
        resultats.append(
            "Colonnes très incomplètes à examiner : "
            + ", ".join(colonnes_tres_incompletes[:5])
            + "."
        )

    return resultats


@login_required
def rapport_statistique(request, pk):
    """Rapport complet calculé directement sur les données PostgreSQL."""

    jeu_donnees = recuperer_jeu_donnees_autorise(
        request.user,
        pk,
    )

    dataframe = _normaliser_vides(
        charger_dataframe_postgresql(jeu_donnees)
    )

    nombre_lignes = int(dataframe.shape[0])
    nombre_colonnes = int(dataframe.shape[1])
    nombre_cellules = nombre_lignes * nombre_colonnes
    valeurs_manquantes = int(dataframe.isna().sum().sum())
    taux_manquantes = (
        100 * valeurs_manquantes / max(nombre_cellules, 1)
    )
    doublons = int(dataframe.duplicated().sum())
    lignes_completes = int(dataframe.notna().all(axis=1).sum())
    lignes_vides = int(dataframe.isna().all(axis=1).sum())

    profils = [
        _profil_colonne(
            str(colonne),
            dataframe[colonne],
            nombre_lignes,
        )
        for colonne in dataframe.columns
    ]

    repartition_types: dict[str, int] = {}

    for profil in profils:
        libelle = profil["type"]
        repartition_types[libelle] = (
            repartition_types.get(libelle, 0) + 1
        )

    return render(
        request,
        "datasets/rapport_statistique.html",
        {
            "jeu_donnees": jeu_donnees,
            "resume": {
                "lignes": nombre_lignes,
                "colonnes": nombre_colonnes,
                "cellules": nombre_cellules,
                "valeurs_manquantes": valeurs_manquantes,
                "taux_manquantes": round(taux_manquantes, 1),
                "doublons": doublons,
                "lignes_completes": lignes_completes,
                "lignes_vides": lignes_vides,
            },
            "profils": profils,
            "repartition_types": repartition_types,
            "correlations": _correlations(dataframe),
            "constats": _constats(
                profils,
                doublons,
                taux_manquantes,
            ),
        },
    )
