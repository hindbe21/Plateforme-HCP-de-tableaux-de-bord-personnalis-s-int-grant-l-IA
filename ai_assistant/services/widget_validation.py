from __future__ import annotations

import re

from .column_matching import (
    colonnes_mentionnees,
    normaliser_texte,
    resoudre_colonne,
)


TYPES_WIDGETS = {
    "INDICATEUR", "BARRES", "BARRES_HORIZONTALES", "CLASSEMENT",
    "CAMEMBERT", "ANNEAU", "COURBE", "AIRES", "HISTOGRAMME",
    "NUAGE_POINTS", "TABLEAU", "TABLEAU_CROISE",
    "STATISTIQUES_DESCRIPTIVES",
}

AGREGATIONS = {
    "NOMBRE",
    "NOMBRE_DISTINCT",
    "SOMME",
    "MOYENNE",
    "MEDIANE",
    "MINIMUM",
    "MAXIMUM",
}

ORDRES = {
    "CROISSANT",
    "DECROISSANT",
}

CATEGORIES = {
    "INDICATEURS_CLES",
    "COMPARAISONS",
    "EVOLUTIONS_TEMPORELLES",
    "REPARTITIONS",
    "RELATIONS_VARIABLES",
    "TABLEAUX_DETAILLES",
}

PERTINENCES = {
    "FORTEMENT_RECOMMANDE",
    "RECOMMANDE",
    "OPTIONNEL",
}

CATEGORIE_LIBELLES = {
    "INDICATEURS_CLES": "Indicateurs clés",
    "COMPARAISONS": "Comparaisons",
    "EVOLUTIONS_TEMPORELLES": "Évolutions temporelles",
    "REPARTITIONS": "Répartitions et distributions",
    "RELATIONS_VARIABLES": "Relations entre variables",
    "TABLEAUX_DETAILLES": "Tableaux détaillés",
}

PERTINENCE_LIBELLES = {
    "FORTEMENT_RECOMMANDE": "Fortement recommandé",
    "RECOMMANDE": "Recommandé",
    "OPTIONNEL": "Optionnel",
}

REPRESENTATION_LIBELLES = {
    "INDICATEUR": "Carte KPI", "BARRES": "Graphique en barres",
    "BARRES_HORIZONTALES": "Barres horizontales", "CLASSEMENT": "Classement",
    "CAMEMBERT": "Graphique circulaire", "ANNEAU": "Graphique en anneau",
    "COURBE": "Graphique en courbes", "AIRES": "Graphique en aires",
    "HISTOGRAMME": "Histogramme", "NUAGE_POINTS": "Nuage de points",
    "TABLEAU": "Tableau simple", "TABLEAU_CROISE": "Tableau croisé",
    "STATISTIQUES_DESCRIPTIVES": "Statistiques descriptives",
}

MAP_TYPES = {
    "bar": "BARRES",
    "bars": "BARRES",
    "barres": "BARRES",
    "line": "COURBE",
    "courbe": "COURBE",
    "area": "AIRES", "aire": "AIRES", "aires": "AIRES",
    "horizontal_bar": "BARRES_HORIZONTALES",
    "barres_horizontales": "BARRES_HORIZONTALES",
    "ranking": "CLASSEMENT", "classement": "CLASSEMENT",
    "pie": "CAMEMBERT", "doughnut": "ANNEAU", "donut": "ANNEAU", "anneau": "ANNEAU",
    "camembert": "CAMEMBERT",
    "kpi": "INDICATEUR",
    "indicator": "INDICATEUR",
    "indicateur": "INDICATEUR",
    "histogram": "HISTOGRAMME",
    "histogramme": "HISTOGRAMME",
    "scatter": "NUAGE_POINTS",
    "nuage_points": "NUAGE_POINTS",
    "table": "TABLEAU", "tableau": "TABLEAU",
    "pivot": "TABLEAU_CROISE", "tableau_croise": "TABLEAU_CROISE",
    "descriptive": "STATISTIQUES_DESCRIPTIVES",
    "statistiques_descriptives": "STATISTIQUES_DESCRIPTIVES",
}

MAP_AGREGATIONS = {
    "count": "NOMBRE",
    "nombre": "NOMBRE",
    "count_distinct": "NOMBRE_DISTINCT",
    "distinct": "NOMBRE_DISTINCT",
    "sum": "SOMME",
    "somme": "SOMME",
    "mean": "MOYENNE",
    "average": "MOYENNE",
    "moyenne": "MOYENNE",
    "median": "MEDIANE",
    "mediane": "MEDIANE",
    "min": "MINIMUM",
    "minimum": "MINIMUM",
    "max": "MAXIMUM",
    "maximum": "MAXIMUM",
}


class ConfigurationWidgetInvalide(ValueError):
    pass


def extraire(configuration, *cles, defaut=""):
    for cle in cles:
        if cle in configuration:
            return configuration.get(cle)
    return defaut


def nettoyer_texte(valeur, limite=500):
    return str(valeur or "").strip()[:limite]


def normaliser_alternatives(valeur):
    resultat = []

    for element in list(valeur or [])[:5]:
        if isinstance(element, str):
            libelle = nettoyer_texte(element, 120)
            if libelle:
                resultat.append({
                    "libelle": libelle,
                    "raison": "",
                })
            continue

        if not isinstance(element, dict):
            continue

        libelle = nettoyer_texte(
            element.get("libelle")
            or element.get("type")
            or element.get("nom"),
            120,
        )
        raison = nettoyer_texte(
            element.get("raison")
            or element.get("note"),
            300,
        )
        if libelle:
            resultat.append({
                "libelle": libelle,
                "raison": raison,
            })

    return resultat


def normaliser_filtres_recommandes(valeur, colonnes):
    resultat = []

    for element in list(valeur or [])[:6]:
        if isinstance(element, str):
            colonne = resoudre_colonne(
                element,
                colonnes,
            )
            raison = ""
        elif isinstance(element, dict):
            colonne = resoudre_colonne(
                element.get("colonne")
                or element.get("column"),
                colonnes,
            )
            raison = nettoyer_texte(
                element.get("raison")
                or element.get("reason"),
                300,
            )
        else:
            continue

        if colonne and colonne in colonnes:
            resultat.append({
                "colonne": colonne,
                "raison": raison,
            })

    uniques = []
    vus = set()
    for element in resultat:
        if element["colonne"] in vus:
            continue
        vus.add(element["colonne"])
        uniques.append(element)

    return uniques


def normaliser_configuration(configuration, analyse):
    configuration = dict(configuration or {})
    schema = analyse.schema or {}
    profils = schema.get("profils", {})
    colonnes = list(profils.keys())

    type_brut = str(extraire(
        configuration,
        "type_widget",
        "widget",
        "type",
        defaut="BARRES",
    ) or "BARRES").strip()
    type_widget = MAP_TYPES.get(
        type_brut.lower(),
        type_brut.upper(),
    )

    aggregation_brute = str(extraire(
        configuration,
        "agregation",
        "aggregation",
        "aggregate",
        defaut="NOMBRE",
    ) or "NOMBRE").strip()
    agregation = MAP_AGREGATIONS.get(
        aggregation_brute.lower(),
        aggregation_brute.upper(),
    )

    dimension = resoudre_colonne(
        extraire(
            configuration,
            "colonne_categorie",
            "x_axis",
            "dimension",
        ),
        colonnes,
    )
    mesure = resoudre_colonne(
        extraire(
            configuration,
            "colonne_mesure",
            "y_axis",
            "measure",
            "mesure",
        ),
        colonnes,
    )
    serie = resoudre_colonne(
        extraire(
            configuration,
            "colonne_serie",
            "series",
            "serie",
            "legend",
        ),
        colonnes,
    )

    try:
        limite = int(extraire(
            configuration,
            "limite_resultats",
            "limit",
            defaut=10,
        ) or 10)
    except (TypeError, ValueError):
        limite = 10

    try:
        classes = int(extraire(
            configuration,
            "nombre_classes",
            "bins",
            defaut=10,
        ) or 10)
    except (TypeError, ValueError):
        classes = 10

    try:
        score = float(extraire(
            configuration,
            "score",
            defaut=0,
        ) or 0)
    except (TypeError, ValueError):
        score = 0.0

    try:
        selection_rang = int(extraire(
            configuration,
            "selection_rang",
            defaut=0,
        ) or 0)
    except (TypeError, ValueError):
        selection_rang = 0

    ordre = str(extraire(
        configuration,
        "ordre_tri",
        "sort",
        defaut="DECROISSANT",
    ) or "DECROISSANT").upper()
    if ordre in {"ASC", "ASCENDING"}:
        ordre = "CROISSANT"
    if ordre in {"DESC", "DESCENDING"}:
        ordre = "DECROISSANT"

    categorie = str(extraire(
        configuration,
        "categorie",
        defaut="COMPARAISONS",
    ) or "COMPARAISONS").upper()
    if categorie not in CATEGORIES:
        categorie = "COMPARAISONS"

    pertinence = str(extraire(
        configuration,
        "pertinence",
        defaut="RECOMMANDE",
    ) or "RECOMMANDE").upper()
    if pertinence not in PERTINENCES:
        pertinence = "RECOMMANDE"

    filtres = []
    for filtre in list(extraire(
        configuration,
        "filtres",
        "filters",
        defaut=[],
    ) or [])[:3]:
        if not isinstance(filtre, dict):
            continue
        colonne_filtre = resoudre_colonne(
            filtre.get("colonne")
            or filtre.get("column"),
            colonnes,
        )
        operateur = str(
            filtre.get("operateur")
            or filtre.get("operator")
            or "EGAL"
        ).upper()
        filtres.append({
            "colonne": colonne_filtre,
            "operateur": operateur,
            "valeur": str(
                filtre.get("valeur")
                or filtre.get("value")
                or ""
            ),
        })

    return {
        "titre": nettoyer_texte(
            extraire(
                configuration,
                "titre",
                "title",
                defaut="Widget proposé",
            ) or "Widget proposé",
            200,
        ),
        "type_widget": type_widget,
        "representation": nettoyer_texte(
            extraire(
                configuration,
                "representation",
                "representation_label",
                defaut=REPRESENTATION_LIBELLES.get(type_widget, type_widget),
            ),
            120,
        ),
        "colonne_categorie": dimension,
        "colonne_mesure": mesure,
        "colonne_serie": serie,
        "agregation": agregation,
        "agregation_affichee": nettoyer_texte(
            extraire(
                configuration,
                "agregation_affichee",
                defaut=agregation,
            ),
            160,
        ),
        "ordre_tri": ordre,
        "limite_resultats": max(1, min(500, limite)),
        "nombre_classes": max(3, min(50, classes)),
        "inclure_manquantes": bool(extraire(
            configuration,
            "inclure_manquantes",
            defaut=False,
        )),
        "filtres": filtres,
        "filtres_recommandes": normaliser_filtres_recommandes(
            extraire(
                configuration,
                "filtres_recommandes",
                "recommended_filters",
                defaut=[],
            ),
            colonnes,
        ),
        "categorie": categorie,
        "categorie_libelle": nettoyer_texte(
            extraire(
                configuration,
                "categorie_libelle",
                defaut=CATEGORIE_LIBELLES.get(categorie, categorie),
            ) or CATEGORIE_LIBELLES.get(categorie, categorie),
            120,
        ),
        "pertinence": pertinence,
        "pertinence_libelle": nettoyer_texte(
            extraire(
                configuration,
                "pertinence_libelle",
                defaut=PERTINENCE_LIBELLES.get(pertinence, pertinence),
            ) or PERTINENCE_LIBELLES.get(pertinence, pertinence),
            120,
        ),
        "score": round(max(0.0, min(100.0, score)), 2),
        "objectif": nettoyer_texte(
            extraire(
                configuration,
                "objectif",
                "objective",
                defaut="",
            ),
            500,
        ),
        "raison": nettoyer_texte(
            extraire(
                configuration,
                "raison",
                "reason",
                defaut="",
            ),
            700,
        ),
        "alternatives": normaliser_alternatives(
            extraire(
                configuration,
                "alternatives",
                defaut=[],
            )
        ),
        "selection_equilibree": bool(extraire(
            configuration,
            "selection_equilibree",
            defaut=False,
        )),
        "selection_rang": selection_rang,
    }


def corriger_selon_demande(configuration, demande, analyse):
    configuration = normaliser_configuration(
        configuration,
        analyse,
    )
    schema = analyse.schema or {}
    profils = schema.get("profils", {})
    colonnes = list(profils.keys())
    mentionnees = colonnes_mentionnees(
        demande,
        colonnes,
    )
    texte = normaliser_texte(demande)

    intention_evolution = any(
        mot in texte
        for mot in (
            "evolution",
            "tendance",
            "progression",
            "variation",
            "au fil",
            "dans le temps",
        )
    )
    mention_temps = any(
        mot in texte.split()
        for mot in (
            "annee",
            "annees",
            "year",
            "years",
            "date",
            "mois",
            "month",
            "temps",
            "periode",
            "trimestre",
        )
    )

    temporelles = [
        nom for nom in mentionnees
        if profils.get(nom, {}).get("type") == "TEMPORELLE"
    ]
    numeriques = [
        nom for nom in mentionnees
        if profils.get(nom, {}).get("type") == "NUMERIQUE"
    ]
    categories = [
        nom for nom in mentionnees
        if profils.get(nom, {}).get("type") == "CATEGORIELLE"
    ]

    if intention_evolution:
        if not temporelles and mention_temps:
            disponibles = schema.get("temporelles", [])
            if len(disponibles) == 1:
                temporelles = [disponibles[0]]
        if temporelles:
            configuration["type_widget"] = "COURBE"
            configuration["representation"] = "Graphique en courbes"
            configuration["categorie"] = "EVOLUTIONS_TEMPORELLES"
            configuration["categorie_libelle"] = "Évolutions temporelles"
            configuration["colonne_categorie"] = temporelles[0]
            configuration["ordre_tri"] = "CROISSANT"
            if numeriques:
                configuration["colonne_mesure"] = numeriques[0]
                configuration["colonne_serie"] = categories[0] if categories else ""
                configuration["agregation"] = profils[numeriques[0]].get(
                    "aggregation_recommandee",
                    "MOYENNE",
                )
            elif categories:
                configuration["colonne_mesure"] = ""
                configuration["colonne_serie"] = categories[0]
                configuration["agregation"] = "NOMBRE"

    top_match = re.search(
        r"\b(?:top|dix|10)\s*(\d+)?",
        texte,
    )
    if top_match:
        valeur = top_match.group(1)
        configuration["limite_resultats"] = int(
            valeur or 10
        )

    return configuration


def valider_configuration(configuration, analyse):
    configuration = normaliser_configuration(
        configuration,
        analyse,
    )
    profils = (
        analyse.schema
        or {}
    ).get("profils", {})
    colonnes = set(profils.keys())

    type_widget = configuration["type_widget"]
    agregation = configuration["agregation"]
    dimension = configuration["colonne_categorie"]
    mesure = configuration["colonne_mesure"]
    serie = configuration["colonne_serie"]

    if type_widget not in TYPES_WIDGETS:
        raise ConfigurationWidgetInvalide(
            "Le type de widget proposé n’est pas autorisé."
        )
    if agregation not in AGREGATIONS:
        raise ConfigurationWidgetInvalide(
            "L’agrégation proposée n’est pas autorisée."
        )
    if configuration["ordre_tri"] not in ORDRES:
        raise ConfigurationWidgetInvalide(
            "L’ordre de tri proposé n’est pas autorisé."
        )

    for libelle, colonne in (
        ("dimension", dimension),
        ("mesure", mesure),
        ("série", serie),
    ):
        if colonne and colonne not in colonnes:
            raise ConfigurationWidgetInvalide(
                f"La {libelle} « {colonne} » n’existe pas dans le jeu de données."
            )

    groupes = {
        "BARRES", "BARRES_HORIZONTALES", "CLASSEMENT",
        "CAMEMBERT", "ANNEAU", "COURBE", "AIRES",
    }
    agregations_numeriques = {
        "SOMME",
        "MOYENNE",
        "MEDIANE",
        "MINIMUM",
        "MAXIMUM",
    }

    if type_widget in groupes and not dimension:
        raise ConfigurationWidgetInvalide(
            "Une dimension est obligatoire pour ce graphique."
        )
    if agregation in agregations_numeriques:
        if not mesure:
            raise ConfigurationWidgetInvalide(
                "Cette agrégation nécessite une mesure numérique."
            )
        if profils[mesure]["type"] != "NUMERIQUE":
            raise ConfigurationWidgetInvalide(
                "La mesure doit être une colonne numérique."
            )
    if agregation == "NOMBRE_DISTINCT" and not mesure:
        raise ConfigurationWidgetInvalide(
            "Le nombre distinct nécessite une colonne de mesure."
        )

    if type_widget == "TABLEAU_CROISE":
        if not dimension or not serie:
            raise ConfigurationWidgetInvalide(
                "Un tableau croisé nécessite une dimension et une série."
            )
        if dimension == serie:
            raise ConfigurationWidgetInvalide(
                "La dimension et la série doivent être différentes."
            )

    if type_widget == "STATISTIQUES_DESCRIPTIVES":
        colonne = mesure or dimension
        if not colonne or profils[colonne]["type"] != "NUMERIQUE":
            raise ConfigurationWidgetInvalide(
                "Les statistiques descriptives nécessitent une colonne numérique."
            )
        configuration["colonne_categorie"] = colonne
        configuration["colonne_mesure"] = ""
        configuration["colonne_serie"] = ""

    if type_widget == "HISTOGRAMME":
        if (
            not dimension
            or profils[dimension]["type"] != "NUMERIQUE"
        ):
            raise ConfigurationWidgetInvalide(
                "Un histogramme nécessite une colonne numérique."
            )
        configuration["colonne_mesure"] = ""
        configuration["colonne_serie"] = ""

    if type_widget == "NUAGE_POINTS":
        if not dimension or not mesure:
            raise ConfigurationWidgetInvalide(
                "Un nuage de points nécessite deux colonnes numériques."
            )
        if (
            profils[dimension]["type"] != "NUMERIQUE"
            or profils[mesure]["type"] != "NUMERIQUE"
        ):
            raise ConfigurationWidgetInvalide(
                "Les deux axes du nuage de points doivent être numériques."
            )
        if dimension == mesure:
            raise ConfigurationWidgetInvalide(
                "Les deux axes doivent utiliser des colonnes différentes."
            )
        configuration["colonne_serie"] = ""

    if serie:
        if type_widget not in {
            "BARRES", "BARRES_HORIZONTALES", "COURBE", "AIRES", "TABLEAU_CROISE"
        }:
            raise ConfigurationWidgetInvalide(
                "Une série est disponible uniquement pour les barres, les courbes, les aires et les tableaux croisés."
            )
        if serie in {dimension, mesure}:
            raise ConfigurationWidgetInvalide(
                "La série doit être différente des axes."
            )

    if type_widget == "INDICATEUR":
        configuration["colonne_categorie"] = ""
        configuration["colonne_serie"] = ""
        if agregation == "NOMBRE":
            configuration["colonne_mesure"] = ""

    operateurs_autorises = {
        "EGAL",
        "DIFFERENT",
        "CONTIENT",
        "NE_CONTIENT_PAS",
        "SUPERIEUR",
        "SUPERIEUR_EGAL",
        "INFERIEUR",
        "INFERIEUR_EGAL",
        "ENTRE",
        "VIDE",
        "NON_VIDE",
    }
    for filtre in configuration.get("filtres", []):
        if filtre.get("colonne") not in colonnes:
            raise ConfigurationWidgetInvalide(
                "Une colonne proposée pour un filtre n’existe pas."
            )
        if filtre.get("operateur") not in operateurs_autorises:
            raise ConfigurationWidgetInvalide(
                "Un opérateur de filtre proposé n’est pas autorisé."
            )
        if (
            filtre.get("operateur") not in {"VIDE", "NON_VIDE"}
            and not str(filtre.get("valeur", "")).strip()
        ):
            raise ConfigurationWidgetInvalide(
                "Un filtre proposé nécessite une valeur."
            )

    return configuration
