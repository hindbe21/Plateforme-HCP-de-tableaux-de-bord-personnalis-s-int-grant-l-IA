from __future__ import annotations

import hashlib
import json
import math
import re
from typing import Any

import numpy as np
import pandas as pd

from datasets.services import charger_dataframe_postgresql

from ..models import AnalyseJeuDonnees


MOTS_IDENTIFIANTS = {
    "id", "identifiant", "identifier", "code", "numero", "numéro",
    "cin", "cne", "uuid", "reference", "référence", "ref",
}

MOTS_TEMPORELS = {
    "date", "dates", "annee", "annees", "année", "années",
    "year", "years", "mois", "month", "jour", "jours", "day",
    "trimestre", "trimestres", "quarter", "periode", "période", "time",
}

MOTS_SOMME = {
    "total", "montant", "amount", "revenue", "revenu", "sales",
    "vente", "ventes", "population", "effectif", "count", "nombre",
    "income", "expenditure", "salary", "salaries", "wages",
}

MOTS_MOYENNE = {
    "moyenne", "mean", "average", "taux", "rate", "ratio", "score",
    "index", "indice", "price", "prix", "value", "valeur",
}

MOTS_GEOGRAPHIQUES = {
    "pays", "country", "region", "région", "province", "prefecture",
    "préfecture", "ville", "city", "commune", "district", "territoire",
    "continent", "latitude", "longitude", "lat", "lon", "lng",
}

MOTS_POURCENTAGE = {
    "pourcentage", "percentage", "percent", "pct", "taux", "rate",
    "ratio", "part", "share", "proportion",
}

MOTS_CIBLES = {
    "objectif", "target", "cible", "budget", "capacity", "capacite",
    "capacité", "seuil", "threshold", "maximum", "max",
}

CATEGORIES_WIDGETS = (
    ("INDICATEURS_CLES", "Indicateurs clés"),
    ("COMPARAISONS", "Comparaisons"),
    ("EVOLUTIONS_TEMPORELLES", "Évolutions temporelles"),
    ("REPARTITIONS", "Répartitions et distributions"),
    ("RELATIONS_VARIABLES", "Relations entre variables"),
    ("TABLEAUX_DETAILLES", "Tableaux détaillés"),
)


def valeur_json(valeur):
    if valeur is None:
        return None
    try:
        if pd.isna(valeur):
            return None
    except Exception:
        pass
    if isinstance(valeur, (np.integer,)):
        return int(valeur)
    if isinstance(valeur, (np.floating,)):
        nombre = float(valeur)
        return nombre if math.isfinite(nombre) else None
    if isinstance(valeur, (pd.Timestamp,)):
        return valeur.isoformat()
    if isinstance(valeur, (str, int, float, bool)):
        return valeur
    return str(valeur)


def normaliser_nom(nom) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(nom).lower()).strip()


def convertir_numerique(serie: pd.Series):
    if pd.api.types.is_numeric_dtype(serie):
        return pd.to_numeric(serie, errors="coerce"), 1.0

    texte = serie.astype("string").str.strip()
    texte = texte.str.replace("\u00a0", "", regex=False)
    texte = texte.str.replace(" ", "", regex=False)
    texte = texte.str.replace(",", ".", regex=False)
    convertie = pd.to_numeric(texte, errors="coerce")
    valides = int(serie.notna().sum())
    ratio = float(convertie.notna().sum() / valides) if valides else 0.0
    return convertie, ratio


def convertir_temporelle(serie: pd.Series, nom_colonne: str):
    if pd.api.types.is_datetime64_any_dtype(serie):
        return pd.to_datetime(serie, errors="coerce"), 1.0

    nom_tokens = set(normaliser_nom(nom_colonne).split())
    numerique, ratio_num = convertir_numerique(serie)
    if ratio_num >= 0.80 and nom_tokens & {"annee", "year"}:
        masque = numerique.dropna().between(1800, 2200)
        if len(masque) and float(masque.mean()) >= 0.80:
            dates = pd.to_datetime(
                numerique.round().astype("Int64").astype("string"),
                format="%Y",
                errors="coerce",
            )
            return dates, float(dates.notna().sum() / max(1, serie.notna().sum()))

    if not (nom_tokens & MOTS_TEMPORELS):
        return None, 0.0

    dates = pd.to_datetime(serie, errors="coerce", dayfirst=True)
    valides = int(serie.notna().sum())
    ratio = float(dates.notna().sum() / valides) if valides else 0.0
    return dates, ratio


def aggregation_recommandee(nom_colonne: str) -> str:
    mots = set(normaliser_nom(nom_colonne).split())
    if mots & MOTS_SOMME:
        return "SOMME"
    if mots & MOTS_MOYENNE:
        return "MOYENNE"
    return "MOYENNE"


def empreinte_jeu_donnees(jeu_donnees) -> str:
    contenu = {
        "pk": jeu_donnees.pk,
        "lignes": int(getattr(jeu_donnees, "nombre_lignes", 0) or 0),
        "colonnes": list(getattr(jeu_donnees, "colonnes", []) or []),
        "types": dict(getattr(jeu_donnees, "types_colonnes", {}) or {}),
        "version": int(getattr(jeu_donnees, "numero_version", 1) or 1),
    }
    texte = json.dumps(contenu, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(texte.encode("utf-8")).hexdigest()


def est_colonne_geographique(nom_colonne: str) -> bool:
    return bool(set(normaliser_nom(nom_colonne).split()) & MOTS_GEOGRAPHIQUES)


def est_mesure_pourcentage(nom_colonne: str, valeurs: pd.Series) -> bool:
    mots = set(normaliser_nom(nom_colonne).split())
    if mots & MOTS_POURCENTAGE:
        return True
    valeurs = valeurs.dropna()
    if len(valeurs) < 3:
        return False
    ratio_0_1 = float(valeurs.between(0, 1).mean())
    return ratio_0_1 >= 0.95


def est_colonne_cible(nom_colonne: str) -> bool:
    return bool(set(normaliser_nom(nom_colonne).split()) & MOTS_CIBLES)


def construire_filtres_recommandes(profils: dict[str, Any]) -> list[dict[str, Any]]:
    filtres = []
    for nom, profil in profils.items():
        type_colonne = profil.get("type")
        uniques = int(profil.get("nombre_uniques", 0) or 0)
        taux_manquantes = float(profil.get("taux_manquantes", 0) or 0)
        if taux_manquantes >= 95:
            continue

        if type_colonne == "TEMPORELLE":
            filtres.append({
                "colonne": nom,
                "type": "TEMPOREL",
                "raison": "Permet de limiter l’analyse à une période précise.",
                "operateurs": ["ENTRE", "SUPERIEUR_EGAL", "INFERIEUR_EGAL"],
                "pertinence": "FORTEMENT_RECOMMANDE",
            })
        elif type_colonne == "CATEGORIELLE" and 2 <= uniques <= 30:
            filtres.append({
                "colonne": nom,
                "type": "CATEGORIEL",
                "raison": "Permet de comparer ou d’isoler des catégories métier.",
                "operateurs": ["EGAL", "DIFFERENT", "CONTIENT"],
                "pertinence": (
                    "FORTEMENT_RECOMMANDE"
                    if profil.get("est_geographique")
                    else "RECOMMANDE"
                ),
            })

    ordre = {"FORTEMENT_RECOMMANDE": 0, "RECOMMANDE": 1, "OPTIONNEL": 2}
    filtres.sort(key=lambda element: (
        ordre.get(element.get("pertinence"), 9),
        element.get("colonne", ""),
    ))
    return filtres[:12]


def construire_widgets_non_disponibles(
    profils: dict[str, Any],
    dimensions: list[str],
    mesures: list[str],
    temporelles: list[str],
    geographiques: list[str],
    pourcentages: list[str],
    cibles: list[str],
) -> list[dict[str, Any]]:
    categories = [
        nom for nom in dimensions
        if profils.get(nom, {}).get("type") == "CATEGORIELLE"
    ]
    resultat = []

    if geographiques:
        resultat.append({
            "widget": "Carte géographique",
            "cause": "PLATEFORME",
            "raison": (
                "Le fichier contient une colonne géographique "
                f"({', '.join(geographiques[:3])}), mais le composant cartographique "
                "n’est pas encore intégré au moteur de widgets."
            ),
            "conditions": "Une colonne géographique reconnue et un composant de carte.",
            "alternative": "Utiliser un graphique en barres par zone géographique.",
        })
    else:
        resultat.append({
            "widget": "Carte géographique",
            "cause": "DONNEES",
            "raison": "Aucune colonne de pays, région, ville, latitude ou longitude n’a été détectée.",
            "conditions": "Une colonne géographique ou des coordonnées.",
            "alternative": "Aucune carte fiable ne peut être proposée avec ce fichier.",
        })

    if len(categories) >= 2 and mesures:
        resultat.append({
            "widget": "Tableau croisé dynamique",
            "cause": "PLATEFORME",
            "raison": (
                "Le fichier possède les dimensions et mesures nécessaires, "
                "mais le widget de tableau croisé n’est pas encore pris en charge."
            ),
            "conditions": "Deux dimensions catégorielles et une mesure.",
            "alternative": "Créer un tableau simple ou deux graphiques comparatifs.",
        })
    else:
        resultat.append({
            "widget": "Tableau croisé dynamique",
            "cause": "DONNEES",
            "raison": "Il faut au moins deux dimensions catégorielles et une mesure numérique.",
            "conditions": "Deux dimensions catégorielles et une mesure.",
            "alternative": "Utiliser un tableau simple avec les colonnes disponibles.",
        })

    if temporelles and len(mesures) >= 2:
        resultat.append({
            "widget": "Graphique combiné",
            "cause": "PLATEFORME",
            "raison": (
                "Les données permettraient de combiner plusieurs mesures dans le temps, "
                "mais le formulaire actuel ne gère qu’une mesure principale par widget."
            ),
            "conditions": "Une dimension temporelle et au moins deux mesures numériques.",
            "alternative": "Créer plusieurs courbes séparées ou une courbe avec une série.",
        })
    else:
        resultat.append({
            "widget": "Graphique combiné",
            "cause": "DONNEES",
            "raison": "Une dimension temporelle et au moins deux mesures numériques sont nécessaires.",
            "conditions": "Une dimension temporelle et deux mesures.",
            "alternative": "Créer les graphiques pris en charge séparément.",
        })

    if pourcentages or cibles:
        resultat.append({
            "widget": "Jauge ou progression",
            "cause": "PLATEFORME",
            "raison": (
                "Une mesure de taux ou de cible a été détectée, mais les jauges et barres "
                "de progression ne sont pas encore intégrées au moteur de rendu."
            ),
            "conditions": "Une valeur actuelle et une cible ou un maximum fiable.",
            "alternative": "Utiliser une carte KPI avec la moyenne ou la valeur agrégée.",
        })
    else:
        resultat.append({
            "widget": "Jauge ou progression",
            "cause": "DONNEES",
            "raison": "Aucune mesure de pourcentage, de cible ou de capacité n’a été détectée.",
            "conditions": "Une valeur actuelle et une cible ou un maximum.",
            "alternative": "Une carte KPI simple reste possible pour les mesures numériques.",
        })

    return resultat


def analyser_dataframe(dataframe: pd.DataFrame) -> dict[str, Any]:
    nombre_lignes = int(len(dataframe))
    profils = {}
    statistiques_numeriques = {}
    statistiques_categorielles = {}
    statistiques_temporelles = {}

    marqueurs_vides = {
        "", "manquante", "manquant", "na", "n/a", "null",
        "none", "nan", "missing", "vide", "-", "--",
    }

    dataframe = dataframe.copy()
    for nom in dataframe.columns:
        if pd.api.types.is_object_dtype(dataframe[nom]) or pd.api.types.is_string_dtype(dataframe[nom]):
            dataframe[nom] = dataframe[nom].apply(
                lambda valeur: (
                    pd.NA
                    if isinstance(valeur, str)
                    and valeur.strip().lower() in marqueurs_vides
                    else valeur
                )
            )

    for nom in dataframe.columns:
        serie = dataframe[nom]
        non_nulles = serie.dropna()
        uniques = int(non_nulles.nunique(dropna=True))
        ratio_uniques = float(uniques / len(non_nulles)) if len(non_nulles) else 0.0
        nom_normalise = normaliser_nom(nom)
        mots_nom = set(nom_normalise.split())

        date_serie, ratio_date = convertir_temporelle(serie, str(nom))
        numerique, ratio_numerique = convertir_numerique(serie)

        nom_compact = "_".join(nom_normalise.split())
        identifiant_nom_fort = (
            nom_compact in {
                "id", "identifiant", "identifier", "uuid",
                "cin", "cne", "numero", "numéro",
            }
            or nom_compact.startswith(("id_", "uuid_", "identifiant_"))
            or nom_compact.endswith(("_id", "_uuid", "_identifiant"))
        )
        identifiant_code = (
            bool(mots_nom & {"code", "reference", "référence", "ref"})
            and ratio_uniques >= 0.80
        )
        identifiant_sequentiel = False
        if ratio_numerique >= 0.95 and ratio_uniques >= 0.97:
            valeurs_uniques = numerique.dropna().drop_duplicates().sort_values()
            if len(valeurs_uniques) >= 5:
                ecarts = valeurs_uniques.diff().dropna()
                identifiant_sequentiel = bool(
                    len(ecarts)
                    and float((ecarts == 1).mean()) >= 0.90
                )

        if date_serie is not None and ratio_date >= 0.80:
            type_colonne = "TEMPORELLE"
        elif identifiant_nom_fort or identifiant_code or identifiant_sequentiel:
            type_colonne = "IDENTIFIANT"
        elif ratio_numerique >= 0.80:
            type_colonne = "NUMERIQUE"
        else:
            type_colonne = "CATEGORIELLE"

        exemples = [
            str(valeur_json(valeur))[:80]
            for valeur in non_nulles.drop_duplicates().head(3).tolist()
        ]

        est_geographique = est_colonne_geographique(str(nom))
        est_pourcentage = False
        est_cible = est_colonne_cible(str(nom))
        if type_colonne == "NUMERIQUE":
            est_pourcentage = est_mesure_pourcentage(str(nom), numerique)

        taux_manquantes = round(float(serie.isna().mean() * 100), 2)
        profil = {
            "nom": str(nom),
            "type": type_colonne,
            "exemples": exemples,
            "nombre_manquantes": int(serie.isna().sum()),
            "taux_manquantes": taux_manquantes,
            "nombre_uniques": uniques,
            "ratio_uniques": round(ratio_uniques, 4),
            "est_identifiant": type_colonne == "IDENTIFIANT",
            "est_geographique": est_geographique,
            "est_pourcentage": est_pourcentage,
            "est_cible": est_cible,
            "utilisable_dimension": (
                type_colonne in {"CATEGORIELLE", "TEMPORELLE"}
                and uniques >= 2
                and taux_manquantes < 95
            ),
            "utilisable_mesure": (
                type_colonne == "NUMERIQUE"
                and taux_manquantes < 95
            ),
        }

        if type_colonne == "NUMERIQUE":
            valeurs = numerique.dropna()
            profil["aggregation_recommandee"] = aggregation_recommandee(str(nom))
            if len(valeurs):
                statistiques_numeriques[str(nom)] = {
                    "nombre": int(valeurs.count()),
                    "somme": valeur_json(valeurs.sum()),
                    "moyenne": valeur_json(valeurs.mean()),
                    "mediane": valeur_json(valeurs.median()),
                    "minimum": valeur_json(valeurs.min()),
                    "maximum": valeur_json(valeurs.max()),
                    "ecart_type": valeur_json(valeurs.std(ddof=1)),
                }
        elif type_colonne == "CATEGORIELLE":
            top = non_nulles.astype("string").value_counts().head(10)
            statistiques_categorielles[str(nom)] = {
                "modalites_principales": [
                    {"valeur": str(index)[:100], "effectif": int(valeur)}
                    for index, valeur in top.items()
                ]
            }
        elif type_colonne == "TEMPORELLE":
            dates = date_serie.dropna()
            if len(dates):
                statistiques_temporelles[str(nom)] = {
                    "minimum": valeur_json(dates.min()),
                    "maximum": valeur_json(dates.max()),
                    "nombre_periodes": int(dates.nunique()),
                }

        profils[str(nom)] = profil

    dimensions = [
        nom for nom, profil in profils.items()
        if profil["utilisable_dimension"]
    ]
    mesures = [
        nom for nom, profil in profils.items()
        if profil["utilisable_mesure"]
    ]
    temporelles = [
        nom for nom, profil in profils.items()
        if profil["type"] == "TEMPORELLE"
    ]
    identifiants = [
        nom for nom, profil in profils.items()
        if profil["type"] == "IDENTIFIANT"
    ]
    geographiques = [
        nom for nom, profil in profils.items()
        if profil.get("est_geographique")
    ]
    pourcentages = [
        nom for nom, profil in profils.items()
        if profil.get("est_pourcentage")
    ]
    cibles = [
        nom for nom, profil in profils.items()
        if profil.get("est_cible")
    ]

    relations = []

    for temps in temporelles[:5]:
        for mesure in mesures[:10]:
            relations.append({
                "nature": "EVOLUTION_TEMPORELLE",
                "dimension": temps,
                "mesure": mesure,
                "serie": "",
                "agregation": profils[mesure].get("aggregation_recommandee", "MOYENNE"),
                "widget": "COURBE",
                "score": 0.95,
            })

    categories = [
        nom for nom in dimensions
        if profils[nom]["type"] == "CATEGORIELLE"
        and 2 <= profils[nom]["nombre_uniques"] <= 50
    ]

    for categorie in categories[:12]:
        uniques = int(profils[categorie]["nombre_uniques"] or 0)
        for mesure in mesures[:8]:
            relations.append({
                "nature": (
                    "CLASSEMENT"
                    if uniques > 12
                    else "COMPARAISON_CATEGORIES"
                ),
                "dimension": categorie,
                "mesure": mesure,
                "serie": "",
                "agregation": profils[mesure].get("aggregation_recommandee", "MOYENNE"),
                "widget": "BARRES",
                "score": 0.90 if uniques <= 12 else 0.84,
            })

        if uniques <= 20:
            relations.append({
                "nature": "REPARTITION_CATEGORIES",
                "dimension": categorie,
                "mesure": "",
                "serie": "",
                "agregation": "NOMBRE",
                "widget": "CAMEMBERT" if uniques <= 6 else "BARRES",
                "score": 0.86 if uniques <= 8 else 0.78,
            })

    for mesure in mesures[:12]:
        relations.append({
            "nature": "DISTRIBUTION_NUMERIQUE",
            "dimension": mesure,
            "mesure": "",
            "serie": "",
            "agregation": "NOMBRE",
            "widget": "HISTOGRAMME",
            "score": 0.80,
        })

    correlations = []
    colonnes_correlation = mesures[:15]
    if len(colonnes_correlation) >= 2:
        donnees_num = pd.DataFrame({
            nom: convertir_numerique(dataframe[nom])[0]
            for nom in colonnes_correlation
        })
        matrice = donnees_num.corr(min_periods=5)
        for i, gauche in enumerate(colonnes_correlation):
            for droite in colonnes_correlation[i + 1:]:
                valeur = matrice.loc[gauche, droite]
                if pd.notna(valeur) and abs(float(valeur)) >= 0.30:
                    correlations.append({
                        "nature": "CORRELATION",
                        "dimension": gauche,
                        "mesure": droite,
                        "serie": "",
                        "agregation": "NOMBRE",
                        "widget": "NUAGE_POINTS",
                        "coefficient": round(float(valeur), 4),
                        "score": round(min(0.98, 0.60 + abs(float(valeur)) / 3), 3),
                    })
    correlations.sort(key=lambda element: abs(element.get("coefficient", 0)), reverse=True)
    relations.extend(correlations[:12])

    indicateurs = [{
        "colonne": "",
        "agregation": "NOMBRE",
        "titre": "Nombre total d’observations",
        "score": 0.96,
    }]
    for mesure in mesures[:12]:
        agregation = profils[mesure].get("aggregation_recommandee", "MOYENNE")
        indicateurs.append({
            "colonne": mesure,
            "agregation": agregation,
            "titre": f"{agregation.title()} de {str(mesure).replace('_', ' ')}",
            "score": 0.92 if agregation == "SOMME" else 0.86,
        })

    filtres_recommandes = construire_filtres_recommandes(profils)
    widgets_non_disponibles = construire_widgets_non_disponibles(
        profils,
        dimensions,
        mesures,
        temporelles,
        geographiques,
        pourcentages,
        cibles,
    )

    schema = {
        "nombre_lignes": nombre_lignes,
        "nombre_colonnes": int(len(dataframe.columns)),
        "profils": profils,
        "dimensions": dimensions,
        "mesures": mesures,
        "temporelles": temporelles,
        "identifiants": identifiants,
        "geographiques": geographiques,
        "pourcentages": pourcentages,
        "cibles": cibles,
        "filtres_recommandes": filtres_recommandes,
        "widgets_non_disponibles": widgets_non_disponibles,
        "categories_widgets": [
            {"code": code, "libelle": libelle}
            for code, libelle in CATEGORIES_WIDGETS
        ],
    }

    statistiques = {
        "qualite": {
            "valeurs_manquantes": int(dataframe.isna().sum().sum()),
            "doublons": int(dataframe.duplicated().sum()),
            "lignes_entierement_vides": int(dataframe.isna().all(axis=1).sum()),
        },
        "numeriques": statistiques_numeriques,
        "categorielles": statistiques_categorielles,
        "temporelles": statistiques_temporelles,
    }

    return {
        "schema": schema,
        "statistiques": statistiques,
        "relations": relations,
        "indicateurs": indicateurs,
    }


def analyser_et_enregistrer(jeu_donnees, force=False):
    empreinte = empreinte_jeu_donnees(jeu_donnees)
    existante = AnalyseJeuDonnees.objects.filter(
        jeu_donnees=jeu_donnees,
    ).first()

    if (
        existante
        and not force
        and existante.empreinte == empreinte
        and existante.statut == AnalyseJeuDonnees.Statut.PRETE
    ):
        return existante

    try:
        dataframe = charger_dataframe_postgresql(jeu_donnees)
        resultat = analyser_dataframe(dataframe)
        analyse, _ = AnalyseJeuDonnees.objects.update_or_create(
            jeu_donnees=jeu_donnees,
            defaults={
                "empreinte": empreinte,
                "schema": resultat["schema"],
                "statistiques": resultat["statistiques"],
                "relations": resultat["relations"],
                "indicateurs": resultat["indicateurs"],
                "statut": AnalyseJeuDonnees.Statut.PRETE,
                "message_erreur": "",
            },
        )
        return analyse
    except Exception as erreur:
        analyse, _ = AnalyseJeuDonnees.objects.update_or_create(
            jeu_donnees=jeu_donnees,
            defaults={
                "empreinte": empreinte,
                "schema": {},
                "statistiques": {},
                "relations": [],
                "indicateurs": [],
                "statut": AnalyseJeuDonnees.Statut.ERREUR,
                "message_erreur": str(erreur),
            },
        )
        raise
