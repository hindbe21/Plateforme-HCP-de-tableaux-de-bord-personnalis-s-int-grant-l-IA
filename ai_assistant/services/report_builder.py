from __future__ import annotations

import json
from typing import Any

import pandas as pd

from datasets.services import (
    charger_dataframe_postgresql,
)
from dashboards.models import (
    Filtre,
    Widget,
)
from dashboards.views import (
    appliquer_filtres,
    preparer_widget,
)


LIBELLES_WIDGETS = {
    "INDICATEUR": "Indicateur",
    "BARRES": "Diagramme en barres",
    "CAMEMBERT": "Diagramme circulaire",
    "COURBE": "Graphique en courbes",
    "HISTOGRAMME": "Histogramme",
    "NUAGE_POINTS": "Nuage de points",
    "TABLEAU": "Tableau statistique",
}


def est_nombre(valeur):
    return (
        isinstance(valeur, (int, float))
        and not isinstance(valeur, bool)
        and pd.notna(valeur)
    )


def nombre_affichable(valeur):
    if not est_nombre(valeur):
        return valeur

    nombre = float(valeur)

    if nombre.is_integer():
        return int(nombre)

    return round(nombre, 4)


def resume_chart_config(texte_json):
    """
    Extrait uniquement les résultats déjà préparés
    par Django pour le widget.

    Les données sont limitées avant l'envoi à Ollama,
    mais les calculs déterministes utilisent toutes
    les valeurs présentes dans la configuration.
    """

    if not texte_json:
        return {}

    try:
        configuration = json.loads(
            texte_json
        )
    except (
        TypeError,
        json.JSONDecodeError,
    ):
        return {}

    data = configuration.get(
        "data",
        {},
    )

    labels = list(
        data.get(
            "labels",
            [],
        )
        or []
    )

    datasets = []

    for dataset in list(
        data.get(
            "datasets",
            [],
        )
        or []
    ):
        datasets.append(
            {
                "label":
                dataset.get(
                    "label",
                    "Série",
                ),

                "data":
                list(
                    dataset.get(
                        "data",
                        [],
                    )
                    or []
                ),
            }
        )

    return {
        "type":
        configuration.get("type"),

        "labels":
        labels,

        "datasets":
        datasets,
    }


def analyser_serie_graphique(
    labels,
    dataset,
    type_widget,
):
    nom_serie = str(
        dataset.get(
            "label",
            "Série",
        )
        or "Série"
    )

    valeurs_brutes = list(
        dataset.get(
            "data",
            [],
        )
        or []
    )

    resultat = {
        "nom":
        nom_serie,

        "nombre_points":
        len(valeurs_brutes),

        "details":
        [],
    }

    # Cas d'un nuage de points Chart.js :
    # [{"x": 10, "y": 20}, ...]
    points = []

    for valeur in valeurs_brutes:
        if (
            isinstance(valeur, dict)
            and est_nombre(
                valeur.get("x")
            )
            and est_nombre(
                valeur.get("y")
            )
        ):
            points.append(
                (
                    float(valeur["x"]),
                    float(valeur["y"]),
                )
            )

    if points:
        serie_x = pd.Series(
            [
                point[0]
                for point in points
            ],
            dtype="float64",
        )

        serie_y = pd.Series(
            [
                point[1]
                for point in points
            ],
            dtype="float64",
        )

        correlation = (
            float(
                serie_x.corr(
                    serie_y
                )
            )
            if len(points) >= 2
            else None
        )

        resultat.update(
            {
                "type_analyse":
                "CORRELATION",

                "correlation":
                (
                    round(
                        correlation,
                        4,
                    )
                    if (
                        correlation is not None
                        and pd.notna(
                            correlation
                        )
                    )
                    else None
                ),

                "minimum_x":
                nombre_affichable(
                    serie_x.min()
                ),

                "maximum_x":
                nombre_affichable(
                    serie_x.max()
                ),

                "minimum_y":
                nombre_affichable(
                    serie_y.min()
                ),

                "maximum_y":
                nombre_affichable(
                    serie_y.max()
                ),
            }
        )

        resultat["details"].append(
            (
                f"{len(points)} point(s) "
                "ont été analysés."
            )
        )

        if resultat["correlation"] is not None:
            resultat["details"].append(
                (
                    "Corrélation linéaire calculée : "
                    f"{resultat['correlation']}."
                )
            )

        return resultat

    paires = []

    for index, valeur in enumerate(
        valeurs_brutes
    ):
        if not est_nombre(valeur):
            continue

        etiquette = (
            labels[index]
            if index < len(labels)
            else str(index + 1)
        )

        paires.append(
            (
                str(etiquette),
                float(valeur),
            )
        )

    if not paires:
        resultat["type_analyse"] = (
            "AUCUNE_VALEUR_NUMERIQUE"
        )

        resultat["details"].append(
            (
                "Aucune valeur numérique "
                "exploitable n'a été détectée."
            )
        )

        return resultat

    valeurs = [
        valeur
        for _, valeur
        in paires
    ]

    maximum = max(
        paires,
        key=lambda element: element[1],
    )

    minimum = min(
        paires,
        key=lambda element: element[1],
    )

    somme = float(
        sum(valeurs)
    )

    moyenne = (
        somme
        / len(valeurs)
    )

    resultat.update(
        {
            "type_analyse":
            "SERIE",

            "maximum":
            {
                "etiquette":
                maximum[0],

                "valeur":
                nombre_affichable(
                    maximum[1]
                ),
            },

            "minimum":
            {
                "etiquette":
                minimum[0],

                "valeur":
                nombre_affichable(
                    minimum[1]
                ),
            },

            "somme":
            nombre_affichable(
                somme
            ),

            "moyenne":
            nombre_affichable(
                moyenne
            ),

            "nombre_valeurs":
            len(valeurs),
        }
    )

    resultat["details"].extend(
        [
            (
                "Valeur la plus élevée : "
                f"{maximum[0]} "
                f"({nombre_affichable(maximum[1])})."
            ),
            (
                "Valeur la plus faible : "
                f"{minimum[0]} "
                f"({nombre_affichable(minimum[1])})."
            ),
        ]
    )

    if type_widget == "COURBE" and len(
        paires
    ) >= 2:
        premier = paires[0]
        dernier = paires[-1]

        variation = (
            dernier[1]
            - premier[1]
        )

        taux = None

        if premier[1] != 0:
            taux = (
                variation
                / abs(
                    premier[1]
                )
                * 100
            )

        resultat["evolution"] = {
            "debut":
            {
                "etiquette":
                premier[0],

                "valeur":
                nombre_affichable(
                    premier[1]
                ),
            },

            "fin":
            {
                "etiquette":
                dernier[0],

                "valeur":
                nombre_affichable(
                    dernier[1]
                ),
            },

            "variation":
            nombre_affichable(
                variation
            ),

            "taux":
            (
                round(
                    taux,
                    2,
                )
                if taux is not None
                else None
            ),
        }

        sens = (
            "hausse"
            if variation > 0
            else (
                "baisse"
                if variation < 0
                else "stabilité"
            )
        )

        texte_evolution = (
            f"Entre {premier[0]} et "
            f"{dernier[0]}, la série "
            f"présente une {sens} de "
            f"{nombre_affichable(abs(variation))}"
        )

        if taux is not None:
            texte_evolution += (
                f" ({abs(taux):.2f} %)"
            )

        resultat["details"].append(
            texte_evolution + "."
        )

    return resultat


def analyser_graphique(
    graphique,
    type_widget,
):
    labels = list(
        graphique.get(
            "labels",
            [],
        )
        or []
    )

    datasets = list(
        graphique.get(
            "datasets",
            [],
        )
        or []
    )

    series = [
        analyser_serie_graphique(
            labels,
            dataset,
            type_widget,
        )
        for dataset in datasets
    ]

    details = [
        (
            f"{len(labels)} catégorie(s) "
            f"et {len(series)} série(s) "
            "sont représentées."
        )
    ]

    for serie in series[:8]:
        nom = serie.get(
            "nom",
            "Série",
        )

        for texte in serie.get(
            "details",
            [],
        )[:4]:
            prefixe = (
                f"{nom} : "
                if len(series) > 1
                else ""
            )

            details.append(
                prefixe + texte
            )

    return {
        "nombre_categories":
        len(labels),

        "nombre_series":
        len(series),

        "series":
        series,

        "details":
        details,
    }


def analyser_tableau(
    dataframe,
    colonnes,
):
    colonnes_valides = [
        colonne
        for colonne in colonnes
        if colonne in dataframe.columns
    ]

    details = [
        (
            f"{len(dataframe)} ligne(s) "
            f"et {len(colonnes_valides)} "
            "colonne(s) sont analysées."
        )
    ]

    colonnes_resumees = []

    for colonne in colonnes_valides[:12]:
        serie = dataframe[colonne]

        nombre_manquantes = int(
            serie.isna().sum()
        )

        serie_numerique = pd.to_numeric(
            serie,
            errors="coerce",
        )

        ratio_numerique = float(
            serie_numerique.notna().mean()
        )

        resume = {
            "nom":
            colonne,

            "nombre_manquantes":
            nombre_manquantes,

            "nombre_distinctes":
            int(
                serie.nunique(
                    dropna=True
                )
            ),
        }

        if ratio_numerique >= 0.8:
            valeurs = (
                serie_numerique
                .dropna()
            )

            resume["type"] = "NUMERIQUE"

            if not valeurs.empty:
                resume.update(
                    {
                        "minimum":
                        nombre_affichable(
                            valeurs.min()
                        ),

                        "maximum":
                        nombre_affichable(
                            valeurs.max()
                        ),

                        "moyenne":
                        nombre_affichable(
                            valeurs.mean()
                        ),

                        "mediane":
                        nombre_affichable(
                            valeurs.median()
                        ),
                    }
                )

                details.append(
                    (
                        f"{colonne} : minimum "
                        f"{resume['minimum']}, maximum "
                        f"{resume['maximum']}, moyenne "
                        f"{resume['moyenne']}."
                    )
                )

        else:
            resume["type"] = "CATEGORIELLE"

            modalites = (
                serie
                .dropna()
                .astype(str)
                .value_counts()
                .head(3)
            )

            resume["modalites_principales"] = [
                {
                    "valeur":
                    str(index),

                    "effectif":
                    int(effectif),
                }
                for index, effectif
                in modalites.items()
            ]

            if (
                resume[
                    "modalites_principales"
                ]
            ):
                texte_modalites = ", ".join(
                    (
                        f"{element['valeur']} "
                        f"({element['effectif']})"
                    )
                    for element
                    in resume[
                        "modalites_principales"
                    ]
                )

                details.append(
                    (
                        f"{colonne} : modalités "
                        f"principales {texte_modalites}."
                    )
                )

        if nombre_manquantes:
            details.append(
                (
                    f"{colonne} contient "
                    f"{nombre_manquantes} "
                    "valeur(s) manquante(s)."
                )
            )

        colonnes_resumees.append(
            resume
        )

    return {
        "nombre_lignes":
        int(
            len(dataframe)
        ),

        "nombre_colonnes":
        len(colonnes_valides),

        "colonnes":
        colonnes_resumees,

        "details":
        details,
    }


def construire_interpretation(
    widget,
    element,
    analyse_calculee,
):
    configuration = (
        widget.configuration
        or {}
    )

    mesure = str(
        configuration.get(
            "colonne_mesure",
            "",
        )
        or ""
    )

    agregation = str(
        configuration.get(
            "agregation",
            "NOMBRE",
        )
        or "NOMBRE"
    )

    if element.get("erreur"):
        return (
            "Le widget n'a pas pu être calculé : "
            + str(
                element["erreur"]
            ),
            (
                "Vérifiez les colonnes, les filtres "
                "et l'agrégation du widget."
            ),
        )

    if widget.type_widget == "INDICATEUR":
        valeur = element.get(
            "valeur_indicateur"
        )

        if mesure:
            interpretation = (
                f"L'indicateur affiche "
                f"{valeur} pour la mesure "
                f"« {mesure} » avec "
                f"l'agrégation {agregation}."
            )
        else:
            interpretation = (
                f"L'indicateur affiche "
                f"{valeur} avec "
                f"l'agrégation {agregation}."
            )

        return (
            interpretation,
            (
                "Cette valeur dépend des filtres "
                "actifs et du périmètre du widget."
            ),
        )

    if widget.type_widget == "TABLEAU":
        interpretation = (
            "Le tableau fournit une vue détaillée "
            f"de {analyse_calculee.get('nombre_lignes', 0)} "
            "ligne(s) après application des filtres."
        )

        return (
            interpretation,
            (
                "L'affichage visuel peut être limité "
                "à un aperçu, mais les calculs du rapport "
                "utilisent toutes les lignes filtrées."
            ),
        )

    series = analyse_calculee.get(
        "series",
        [],
    )

    if not series:
        return (
            (
                "Le graphique a été calculé, "
                "mais aucune série numérique "
                "exploitable n'a été détectée."
            ),
            (
                "Vérifiez la mesure et "
                "l'agrégation du widget."
            ),
        )

    premiere = series[0]

    if (
        premiere.get(
            "type_analyse"
        )
        == "CORRELATION"
    ):
        correlation = premiere.get(
            "correlation"
        )

        if correlation is None:
            interpretation = (
                "Le nuage de points contient "
                "trop peu de valeurs pour calculer "
                "une corrélation fiable."
            )
        else:
            force = abs(
                float(correlation)
            )

            if force >= 0.7:
                niveau = "forte"
            elif force >= 0.4:
                niveau = "modérée"
            else:
                niveau = "faible"

            sens = (
                "positive"
                if correlation > 0
                else (
                    "négative"
                    if correlation < 0
                    else "nulle"
                )
            )

            interpretation = (
                "La relation linéaire observée est "
                f"{niveau} et {sens} "
                f"(corrélation {correlation})."
            )

        return (
            interpretation,
            (
                "Une corrélation ne démontre "
                "pas une relation de causalité."
            ),
        )

    maximum = premiere.get(
        "maximum",
        {},
    )

    minimum = premiere.get(
        "minimum",
        {},
    )

    interpretation = (
        "La valeur la plus élevée est associée "
        f"à « {maximum.get('etiquette', '—')} » "
        f"({maximum.get('valeur', '—')}), "
        "tandis que la plus faible est associée "
        f"à « {minimum.get('etiquette', '—')} » "
        f"({minimum.get('valeur', '—')})."
    )

    if (
        widget.type_widget == "COURBE"
        and premiere.get(
            "evolution"
        )
    ):
        evolution = premiere[
            "evolution"
        ]

        variation = evolution.get(
            "variation",
            0,
        )

        sens = (
            "une hausse"
            if (
                isinstance(
                    variation,
                    (int, float),
                )
                and variation > 0
            )
            else (
                "une baisse"
                if (
                    isinstance(
                        variation,
                        (int, float),
                    )
                    and variation < 0
                )
                else "une stabilité"
            )
        )

        interpretation += (
            " Entre "
            f"{evolution['debut']['etiquette']} "
            "et "
            f"{evolution['fin']['etiquette']}, "
            f"la série présente {sens}."
        )

    prudence = (
        "L'interprétation dépend de "
        f"l'agrégation {agregation}, "
        "des filtres et du contexte métier."
    )

    return (
        interpretation,
        prudence,
    )


def comparer_widgets(
    resultats_widgets,
):
    comparaisons = []

    for index, premier in enumerate(
        resultats_widgets
    ):
        for second in resultats_widgets[
            index + 1:
        ]:
            meme_mesure = (
                premier.get("mesure")
                and premier.get("mesure")
                == second.get("mesure")
            )

            meme_agregation = (
                premier.get("agregation")
                == second.get("agregation")
            )

            dimensions_differentes = (
                premier.get("dimension")
                != second.get("dimension")
            )

            if (
                meme_mesure
                and meme_agregation
                and dimensions_differentes
            ):
                comparaisons.append(
                    (
                        f"« {premier['titre']} » et "
                        f"« {second['titre']} » utilisent "
                        f"la même mesure "
                        f"« {premier['mesure']} » avec "
                        f"l'agrégation "
                        f"{premier['agregation']}, "
                        "mais selon des dimensions "
                        "différentes."
                    )
                )

    return comparaisons[:8]


def calculer_resultats_tableau_bord(
    tableau_bord,
):
    """
    Calcule toutes les informations du rapport.

    Ollama ne reçoit jamais le DataFrame. Il reçoit
    uniquement la structure JSON retournée ici.
    """

    dataframe = (
        charger_dataframe_postgresql(
            tableau_bord.jeu_donnees
        )
    )

    filtres_globaux = list(
        Filtre.objects.filter(
            tableau_bord=tableau_bord,
            actif=True,
        ).order_by(
            "ordre",
            "date_creation",
        )
    )

    dataframe_global = appliquer_filtres(
        dataframe,
        filtres_globaux,
    )

    widgets = list(
        Widget.objects.filter(
            tableau_bord=tableau_bord,
        ).prefetch_related(
            "filtres_locaux"
        ).order_by(
            "ordre",
            "date_creation",
        )
    )

    resultats_widgets = []
    constatations = []

    for position, widget in enumerate(
        widgets,
        start=1,
    ):
        filtres_locaux = list(
            widget.filtres_locaux.filter(
                actif=True,
            ).order_by(
                "ordre",
                "date_creation",
            )
        )

        dataframe_widget = appliquer_filtres(
            dataframe_global,
            filtres_locaux,
        )

        element = preparer_widget(
            widget,
            dataframe_widget,
        )

        configuration = (
            widget.configuration
            or {}
        )

        mesure = str(
            configuration.get(
                "colonne_mesure",
                "",
            )
            or ""
        )

        serie = str(
            configuration.get(
                "colonne_serie",
                "",
            )
            or ""
        )

        agregation = str(
            configuration.get(
                "agregation",
                "NOMBRE",
            )
            or "NOMBRE"
        )

        analyse_calculee: dict[str, Any]

        if widget.type_widget == "INDICATEUR":
            analyse_calculee = {
                "valeur":
                element.get(
                    "valeur_indicateur"
                ),

                "details":
                [
                    (
                        "Valeur calculée : "
                        f"{element.get('valeur_indicateur')}."
                    )
                ],
            }

        elif widget.type_widget == "TABLEAU":
            colonnes = list(
                element.get(
                    "colonnes_tableau",
                    [],
                )
                or []
            )

            analyse_calculee = analyser_tableau(
                dataframe_widget,
                colonnes,
            )

        else:
            graphique = resume_chart_config(
                element.get(
                    "chart_config_json"
                )
            )

            analyse_calculee = analyser_graphique(
                graphique,
                widget.type_widget,
            )

        (
            interpretation,
            prudence,
        ) = construire_interpretation(
            widget,
            element,
            analyse_calculee,
        )

        resultat = {
            "position":
            position,

            "titre":
            widget.titre,

            "type_widget":
            widget.type_widget,

            "type_widget_libelle":
            LIBELLES_WIDGETS.get(
                widget.type_widget,
                widget.type_widget,
            ),

            "dimension":
            widget.colonne_categorie,

            "mesure":
            mesure,

            "serie":
            serie,

            "agregation":
            agregation,

            "ordre_tri":
            str(
                configuration.get(
                    "ordre_tri",
                    "",
                )
                or ""
            ),

            "nombre_lignes_utilisees":
            int(
                len(dataframe_widget)
            ),

            "filtres_locaux":
            [
                str(filtre)
                for filtre
                in filtres_locaux
            ],

            "erreur":
            str(
                element.get(
                    "erreur",
                    "",
                )
                or ""
            ),

            "analyse_calculee":
            analyse_calculee,

            "details_calcules":
            list(
                analyse_calculee.get(
                    "details",
                    [],
                )
                or []
            ),

            "interpretation_calculee":
            interpretation,

            "prudence_calculee":
            prudence,
        }

        resultats_widgets.append(
            resultat
        )

        if not resultat["erreur"]:
            constatations.append(
                (
                    f"{widget.titre} : "
                    f"{interpretation}"
                )
            )

    comparaisons = comparer_widgets(
        resultats_widgets
    )

    limites = [
        (
            "Les résultats décrivent uniquement "
            "les widgets présents dans ce tableau "
            "de bord."
        ),
        (
            "Les filtres globaux et locaux ainsi "
            "que les agrégations modifient le "
            "périmètre de l'analyse."
        ),
        (
            "Une association statistique ou une "
            "corrélation ne suffit pas à établir "
            "une causalité."
        ),
        (
            "L'interprétation métier doit être "
            "validée par un utilisateur connaissant "
            "le contexte du jeu de données."
        ),
    ]

    tableau_resume = {
        "titre":
        tableau_bord.titre,

        "description":
        tableau_bord.description,

        "jeu_donnees":
        tableau_bord.jeu_donnees.nom,

        "nombre_lignes_total":
        int(
            len(dataframe)
        ),

        "nombre_lignes_apres_filtres":
        int(
            len(dataframe_global)
        ),

        "filtres_globaux":
        [
            str(filtre)
            for filtre
            in filtres_globaux
        ],

        "nombre_filtres_globaux":
        len(
            filtres_globaux
        ),

        "nombre_widgets":
        len(
            widgets
        ),
    }

    return {
        "tableau_bord":
        tableau_resume,

        "widgets":
        resultats_widgets,

        "constatations_calculees":
        constatations,

        "comparaisons_calculees":
        comparaisons,

        "limites_calculees":
        limites,
    }
