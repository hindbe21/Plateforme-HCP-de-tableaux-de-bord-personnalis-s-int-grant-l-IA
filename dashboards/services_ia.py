from __future__ import annotations

import json
import logging
import re
import unicodedata
from difflib import SequenceMatcher
from typing import Any

from django.conf import settings
from django.db import transaction
from django.db.models import Max

from .forms import (
    AGREGATIONS,
    ORDRES_TRI,
    WidgetForm,
    construire_profils_colonnes,
)
from .models import (
    Filtre,
    FiltreWidget,
    Widget,
)


logger = logging.getLogger(
    __name__
)


class ErreurAssistantIA(Exception):
    """Erreur contrôlée de l’assistant IA."""


TYPES_WIDGETS_AUTORISES = {
    valeur
    for valeur, _
    in Widget.TYPE_WIDGET_CHOICES
}

AGREGATIONS_AUTORISEES = {
    valeur
    for valeur, _
    in AGREGATIONS
}

ORDRES_AUTORISES = {
    valeur
    for valeur, _
    in ORDRES_TRI
}

OPERATEURS_AUTORISES = {
    valeur
    for valeur, _
    in Filtre.Operateur.choices
}


SCHEMA_CONFIGURATION_WIDGET = {
    "type": "object",

    "properties": {
        "titre": {
            "type": "string",
        },

        "explication": {
            "type": "string",
        },

        "type_widget": {
            "type": "string",
            "enum": sorted(
                TYPES_WIDGETS_AUTORISES
            ),
        },

        "colonne_categorie": {
            "type": "string",
        },

        "colonne_mesure": {
            "type": "string",
        },

        "colonne_serie": {
            "type": "string",
        },

        "agregation": {
            "type": "string",
            "enum": sorted(
                AGREGATIONS_AUTORISEES
            ),
        },

        "ordre_tri": {
            "type": "string",
            "enum": sorted(
                ORDRES_AUTORISES
            ),
        },

        "limite_resultats": {
            "type": "integer",
            "minimum": 1,
            "maximum": 100,
        },

        "nombre_classes": {
            "type": "integer",
            "minimum": 3,
            "maximum": 50,
        },

        "inclure_manquantes": {
            "type": "boolean",
        },

        "filtres": {
            "type": "array",
            "maxItems": 3,

            "items": {
                "type": "object",

                "properties": {
                    "colonne": {
                        "type": "string",
                    },

                    "operateur": {
                        "type": "string",
                        "enum": sorted(
                            OPERATEURS_AUTORISES
                        ),
                    },

                    "valeur": {
                        "type": "string",
                    },
                },

                "required": [
                    "colonne",
                    "operateur",
                    "valeur",
                ],

                "additionalProperties":
                False,
            },
        },
    },

    "required": [
        "titre",
        "explication",
        "type_widget",
        "colonne_categorie",
        "colonne_mesure",
        "colonne_serie",
        "agregation",
        "ordre_tri",
        "limite_resultats",
        "nombre_classes",
        "inclure_manquantes",
        "filtres",
    ],

    "additionalProperties":
    False,
}


INSTRUCTIONS_ASSISTANT = """
Tu es un assistant spécialisé dans la création
de visualisations statistiques pour une plateforme
du Haut-Commissariat au Plan.

Ta tâche consiste à transformer une demande en français
en configuration de widget.

Règles obligatoires :

1. Utilise uniquement les noms exacts des colonnes
   fournis dans le contexte.

2. N’invente aucune colonne, aucune valeur statistique
   et aucun résultat.

3. Pour NOMBRE :
   - aucune colonne de mesure n’est nécessaire ;
   - utilise une dimension pour BARRES, CAMEMBERT
     ou COURBE ;
   - pour un INDICATEUR, laisse la dimension
     et la mesure vides.

4. Pour NOMBRE_DISTINCT :
   - une colonne de mesure est obligatoire ;
   - elle peut être numérique, textuelle ou temporelle.

5. Pour SOMME, MOYENNE, MEDIANE, MINIMUM et MAXIMUM :
   - la colonne de mesure doit être numérique.

6. HISTOGRAMME :
   - colonne_categorie doit être numérique ;
   - colonne_mesure doit être vide ;
   - nombre_classes doit être compris entre 3 et 50.

7. NUAGE_POINTS :
   - colonne_categorie et colonne_mesure doivent être
     deux colonnes numériques différentes.

8. TABLEAU :
   - utilise colonne_categorie et éventuellement
     colonne_mesure pour choisir les colonnes affichées.

9. COURBE :
   - privilégie une dimension temporelle ou ordonnée ;
   - pour suivre une catégorie textuelle au fil du temps,
     utilise la colonne temporelle comme colonne_categorie,
     la catégorie comme colonne_serie, laisse
     colonne_mesure vide et utilise NOMBRE.

10. colonne_serie :
   - facultative ;
   - uniquement pour BARRES ou COURBE ;
   - permet de produire une ligne ou une barre par catégorie.

11. N’ajoute un filtre que si la demande de l’utilisateur
    le formule clairement.

12. Pour ENTRE, écris les deux bornes dans valeur
    séparées par un point-virgule, par exemple :
    2009;2012

13. VIDE et NON_VIDE utilisent une valeur vide.

14. L’explication doit être courte, claire et prudente.

15. La proposition sera vérifiée par Django avant toute
    création. L’utilisateur doit toujours confirmer.
""".strip()


def normaliser_texte(
    valeur,
) -> str:
    texte = str(
        valeur
        or ""
    ).lower()

    texte = unicodedata.normalize(
        "NFKD",
        texte,
    )

    texte = "".join(
        caractere
        for caractere in texte
        if not unicodedata.combining(
            caractere
        )
    )

    texte = texte.replace(
        "_",
        " ",
    )

    texte = re.sub(
        r"[^a-z0-9]+",
        " ",
        texte,
    )

    texte = re.sub(
        r"\bfct\b",
        "fonction",
        texte,
    )

    return re.sub(
        r"\s+",
        " ",
        texte,
    ).strip()


EQUIVALENCES_ANALYTIQUES_GENERIQUES = {
    # Termes généraux fréquents dans les fichiers statistiques.
    # Cette table ne dépend d’aucun jeu de données particulier.
    "annee": "year",
    "annees": "year",
    "years": "year",
    "mois": "month",
    "months": "month",
    "jour": "day",
    "jours": "day",
    "days": "day",
    "nom": "name",
    "noms": "name",
    "libelle": "name",
    "libelles": "name",
    "valeur": "value",
    "valeurs": "value",
    "values": "value",
    "code": "code",
    "codes": "code",
    "categorie": "category",
    "categories": "category",
    "groupe": "group",
    "groupes": "group",
    "groups": "group",
    "unite": "unit",
    "unites": "unit",
    "units": "unit",
    "nombre": "number",
    "nombres": "number",
    "montant": "amount",
    "montants": "amount",
    "date": "date",
    "dates": "date",
}


MOTS_IGNORES_NOMS_COLONNES = {
    "la",
    "le",
    "les",
    "un",
    "une",
    "de",
    "du",
    "des",
    "d",
    "l",
    "colonne",
    "colonnes",
    "column",
    "columns",
    "champ",
    "champs",
    "field",
    "fields",
}


def racine_token_generique(
    token,
):
    """
    Normalise légèrement les pluriels sans connaître
    à l’avance les noms des colonnes du fichier.
    """

    token = EQUIVALENCES_ANALYTIQUES_GENERIQUES.get(
        token,
        token,
    )

    if len(token) > 4 and token.endswith("ies"):
        token = token[:-3] + "y"

    elif len(token) > 4 and token.endswith("es"):
        token = token[:-2]

    elif len(token) > 3 and token.endswith("s"):
        token = token[:-1]

    return token


def tokens_nom_colonne(
    valeur,
):
    """
    Découpe aussi bien les noms techniques que les
    formulations libres : snake_case, tirets, pluriels,
    ordre différent et fautes légères.
    """

    tokens = []

    for token in normaliser_texte(
        valeur
    ).split():
        token = racine_token_generique(
            token
        )

        if (
            token
            and token
            not in MOTS_IGNORES_NOMS_COLONNES
        ):
            tokens.append(token)

    return tokens


def similarite_token(
    premier,
    second,
):
    if premier == second:
        return 1.0

    return SequenceMatcher(
        None,
        premier,
        second,
    ).ratio()


def score_couverture_tokens(
    source,
    cible,
):
    """
    Compare chaque mot au mot le plus proche.
    Cette mesure fonctionne pour n’importe quel nom de
    colonne, sans dictionnaire spécifique au fichier.
    """

    if not source or not cible:
        return 0.0

    scores = []

    for token_source in source:
        scores.append(
            max(
                similarite_token(
                    token_source,
                    token_cible,
                )
                for token_cible in cible
            )
        )

    return sum(scores) / len(scores)


def score_ressemblance_colonne(
    expression,
    colonne,
):
    tokens_expression = tokens_nom_colonne(
        expression
    )

    tokens_colonne = tokens_nom_colonne(
        colonne
    )

    if not tokens_expression or not tokens_colonne:
        return 0.0

    texte_expression = " ".join(
        tokens_expression
    )

    texte_colonne = " ".join(
        tokens_colonne
    )

    texte_expression_trie = " ".join(
        sorted(tokens_expression)
    )

    texte_colonne_trie = " ".join(
        sorted(tokens_colonne)
    )

    ratio_ordre = SequenceMatcher(
        None,
        texte_expression,
        texte_colonne,
    ).ratio()

    ratio_sans_ordre = SequenceMatcher(
        None,
        texte_expression_trie,
        texte_colonne_trie,
    ).ratio()

    couverture_expression = score_couverture_tokens(
        tokens_expression,
        tokens_colonne,
    )

    couverture_colonne = score_couverture_tokens(
        tokens_colonne,
        tokens_expression,
    )

    score_bidirectionnel = (
        0.55 * couverture_expression
        + 0.45 * couverture_colonne
    )

    return max(
        ratio_ordre,
        ratio_sans_ordre,
        score_bidirectionnel,
    )


def classer_colonnes_proches(
    nom_propose,
    colonnes,
):
    candidats = [
        (
            score_ressemblance_colonne(
                nom_propose,
                colonne,
            ),
            colonne,
        )
        for colonne in colonnes
    ]

    candidats.sort(
        key=lambda element: (
            -element[0],
            str(element[1]),
        )
    )

    return candidats


def resoudre_nom_colonne(
    nom_propose,
    colonnes,
    *,
    seuil=None,
):
    """
    Résout dynamiquement un nom approximatif vers un nom
    exact. Aucune colonne n’est codée en dur.
    """

    nom_propose = str(
        nom_propose or ""
    ).strip()

    if not nom_propose:
        return ""

    if nom_propose in colonnes:
        return nom_propose

    nom_normalise = normaliser_texte(
        nom_propose
    )

    for colonne in colonnes:
        if normaliser_texte(colonne) == nom_normalise:
            return colonne

    candidats = classer_colonnes_proches(
        nom_propose,
        colonnes,
    )

    if not candidats:
        return nom_propose

    meilleur_score, meilleure_colonne = candidats[0]
    deuxieme_score = (
        candidats[1][0]
        if len(candidats) > 1
        else 0.0
    )

    nombre_tokens = len(
        tokens_nom_colonne(nom_propose)
    )

    if seuil is None:
        seuil = 0.88 if nombre_tokens <= 1 else 0.76

    # On corrige seulement lorsque le résultat est fiable.
    if (
        meilleur_score >= seuil
        and (
            meilleur_score - deuxieme_score >= 0.05
            or meilleur_score >= 0.95
        )
    ):
        return meilleure_colonne

    return nom_propose


def rechercher_colonnes_approximatives(
    demande,
    colonnes,
):
    """
    Cherche dans toute la phrase les passages ressemblant
    aux colonnes réelles du fichier. Le mécanisme est créé
    à partir de la liste reçue et fonctionne donc avec
    n’importe quel CSV ou Excel.
    """

    tokens_demande = tokens_nom_colonne(
        demande
    )

    if not tokens_demande:
        return []

    propositions = []

    for colonne in colonnes:
        tokens_colonne = tokens_nom_colonne(
            colonne
        )

        if not tokens_colonne:
            continue

        longueur = len(tokens_colonne)
        tailles = {
            max(1, longueur - 1),
            longueur,
            longueur + 1,
        }

        meilleur_score = 0.0
        meilleure_position = 0

        for taille in sorted(tailles):
            if taille > len(tokens_demande):
                continue

            for position in range(
                len(tokens_demande) - taille + 1
            ):
                morceau = " ".join(
                    tokens_demande[
                        position:
                        position + taille
                    ]
                )

                score = score_ressemblance_colonne(
                    morceau,
                    colonne,
                )

                if score > meilleur_score:
                    meilleur_score = score
                    meilleure_position = position

        seuil = 0.90 if longueur <= 1 else 0.77

        if meilleur_score >= seuil:
            propositions.append(
                (
                    meilleure_position,
                    -meilleur_score,
                    colonne,
                )
            )

    propositions.sort()

    resultat = []

    for _, _, colonne in propositions:
        if colonne not in resultat:
            resultat.append(colonne)

    return resultat


def colonnes_mentionnees(
    demande,
    colonnes,
):
    demande_normalisee = normaliser_texte(
        demande
    )

    resultat = []

    # Correspondance exacte d’abord.
    for colonne in colonnes:
        nom_normalise = normaliser_texte(
            colonne
        )

        if (
            nom_normalise
            and re.search(
                (
                    r"(?<![a-z0-9])"
                    + re.escape(nom_normalise)
                    + r"(?![a-z0-9])"
                ),
                demande_normalisee,
            )
        ):
            resultat.append(
                (
                    demande_normalisee.find(
                        nom_normalise
                    ),
                    colonne,
                )
            )

    resultat.sort()

    colonnes_uniques = [
        colonne
        for _, colonne in resultat
    ]

    # Puis correspondance dynamique et approximative.
    for colonne in rechercher_colonnes_approximatives(
        demande,
        colonnes,
    ):
        if colonne not in colonnes_uniques:
            colonnes_uniques.append(colonne)

    return colonnes_uniques


def construire_schema_sortie_ollama(
    colonnes,
):
    """
    Contraint Ollama à retourner uniquement un nom exact
    présent dans le fichier. Il ne peut plus inventer
    « name_industry » lorsqu’une autre colonne existe.
    """

    schema = json.loads(
        json.dumps(
            SCHEMA_CONFIGURATION_WIDGET
        )
    )

    choix_colonnes = [
        "",
        *list(colonnes),
    ]

    for champ in (
        "colonne_categorie",
        "colonne_mesure",
        "colonne_serie",
    ):
        schema["properties"][champ] = {
            "type": "string",
            "enum": choix_colonnes,
        }

    schema[
        "properties"
    ][
        "filtres"
    ][
        "items"
    ][
        "properties"
    ][
        "colonne"
    ] = {
        "type": "string",
        "enum": list(colonnes),
    }

    return schema


def colonne_apres_expression(
    demande,
    colonnes,
    expressions,
):
    demande_normalisee = normaliser_texte(
        demande
    )

    meilleure = None

    for expression in expressions:
        expression_normalisee = (
            normaliser_texte(
                expression
            )
        )

        position_expression = (
            demande_normalisee
            .find(
                expression_normalisee
            )
        )

        if position_expression < 0:
            continue

        debut = (
            position_expression
            + len(
                expression_normalisee
            )
        )

        for colonne in colonnes:
            nom_normalise = normaliser_texte(
                colonne
            )

            position_colonne = (
                demande_normalisee
                .find(
                    nom_normalise,
                    debut,
                )
            )

            if position_colonne < 0:
                continue

            candidat = (
                position_colonne,
                colonne,
            )

            if (
                meilleure is None
                or candidat[0]
                < meilleure[0]
            ):
                meilleure = candidat

    return (
        meilleure[1]
        if meilleure
        else ""
    )



def resoudre_colonne_temporelle(
    demande,
    colonnes,
    profils,
):
    """
    Résout une expression temporelle même lorsqu'elle
    contient une faute légère ou une formulation libre.

    Exemples reconnus : année, années, annes, year,
    date, mois, trimestre, période et temps.
    """

    texte = normaliser_texte(
        demande
    )

    tokens_demande = texte.split()

    termes_temporels = {
        "annee",
        "annees",
        "year",
        "years",
        "date",
        "dates",
        "mois",
        "month",
        "months",
        "trimestre",
        "quarter",
        "quarters",
        "periode",
        "periodes",
        "temps",
        "temporel",
        "temporelle",
    }

    def token_temporel(token):
        if len(token) < 3:
            return False

        return any(
            SequenceMatcher(
                None,
                token,
                terme,
            ).ratio()
            >= 0.78
            for terme in termes_temporels
        )

    demande_temporelle = any(
        token_temporel(token)
        for token in tokens_demande
    )

    candidats = []

    for colonne in colonnes:
        nom = normaliser_texte(
            colonne
        )

        profil = profils.get(
            colonne,
            {},
        )

        score = 0

        tokens_colonne = nom.split()

        if nom in {
            "year",
            "years",
            "annee",
            "annees",
            "date",
        }:
            score += 100

        if any(
            token_temporel(token)
            for token in tokens_colonne
        ):
            score += 60

        if profil.get("type") == "DATE":
            score += 50

        exemples = [
            str(valeur)
            for valeur in (
                profil.get(
                    "exemples",
                    [],
                )
                or []
            )
        ]

        if exemples and all(
            re.fullmatch(
                r"(?:19|20)\d{2}(?:\.0)?",
                valeur.strip(),
            )
            for valeur in exemples
        ):
            score += 40

        nombre_uniques = int(
            profil.get(
                "nombre_uniques",
                0,
            )
            or 0
        )

        # Une colonne numérique de quatre chiffres,
        # contenant peu de valeurs différentes, est
        # probablement une année.
        if (
            exemples
            and nombre_uniques
            and nombre_uniques <= 200
            and all(
                re.fullmatch(
                    r"(?:19|20)\d{2}(?:\.0)?",
                    valeur.strip(),
                )
                for valeur in exemples
            )
        ):
            score += 20

        if score:
            candidats.append(
                (
                    score,
                    colonne,
                )
            )

    if not candidats:
        return ""

    candidats.sort(
        key=lambda element: (
            -element[0],
            str(element[1]),
        )
    )

    meilleur_score, meilleure_colonne = (
        candidats[0]
    )

    deuxieme_score = (
        candidats[1][0]
        if len(candidats) > 1
        else 0
    )

    # Si l'utilisateur évoque le temps, on accepte le
    # meilleur candidat. Pour une demande d'évolution,
    # on peut également inférer une colonne temporelle
    # unique et très évidente, même si le mot est très
    # mal orthographié.
    demande_evolution = any(
        expression in texte
        for expression in (
            "evolution",
            "evluation",
            "evoluation",
            "variation",
            "tendance",
            "progression",
        )
    )

    candidat_evident = (
        meilleur_score >= 100
        and (
            meilleur_score - deuxieme_score >= 30
            or len(candidats) == 1
        )
    )

    if demande_temporelle or (
        demande_evolution
        and candidat_evident
    ):
        return meilleure_colonne

    return ""


def construire_proposition_rapide(
    tableau_bord,
    demande,
    profils_colonnes=None,
):
    """
    Interprète immédiatement les demandes courantes.

    Cette étape ne lance pas Ollama. Elle rend les cas
    simples presque instantanés et laisse le modèle local
    uniquement pour les demandes ambiguës.
    """

    colonnes = list(
        tableau_bord
        .jeu_donnees
        .colonnes
        or []
    )

    texte = normaliser_texte(
        demande
    )

    profils = profils_colonnes or {}

    if not profils:
        try:
            profils = construire_profils_colonnes(
                tableau_bord.jeu_donnees
            )
        except Exception:
            profils = {}

    mentionnees = colonnes_mentionnees(
        demande,
        colonnes,
    )

    colonne_temporelle = (
        resoudre_colonne_temporelle(
            demande,
            colonnes,
            profils,
        )
    )

    if (
        colonne_temporelle
        and colonne_temporelle
        not in mentionnees
    ):
        mentionnees.append(
            colonne_temporelle
        )

    relation_en_fonction = bool(
        re.search(
            (
                r"\b(?:en\s+)?fonction\b"
                r"|\bselon\b"
                r"|\bpar\s+rapport\s+a\b"
            ),
            texte,
        )
    )

    demande_evolution = any(
        expression in texte
        for expression in (
            "evolution",
            "evluation",
            "evoluation",
            "variation",
            "tendance",
            "progression",
        )
    )

    # Cas métier important : évolution d’une catégorie
    # textuelle au fil du temps. La catégorie devient
    # une série/légende et l’axe Y représente l’effectif.
    if demande_evolution and colonne_temporelle:
        cible = next(
            (
                colonne
                for colonne in mentionnees
                if colonne
                != colonne_temporelle
            ),
            "",
        )

        if cible:
            type_cible = (
                profils.get(
                    cible,
                    {},
                )
                .get("type")
            )

            titre = str(
                demande
            ).strip()

            if len(titre) > 100:
                titre = (
                    titre[:97].rstrip()
                    + "..."
                )

            if type_cible == "TEXTE":
                proposition = {
                    "titre":
                    titre,

                    "explication":
                    (
                        "Chaque courbe représente une "
                        f"valeur de {cible}. L’axe X utilise "
                        f"{colonne_temporelle} et l’axe Y "
                        "affiche le nombre d’observations."
                    ),

                    "type_widget":
                    "COURBE",

                    "colonne_categorie":
                    colonne_temporelle,

                    "colonne_mesure":
                    "",

                    "colonne_serie":
                    cible,

                    "agregation":
                    "NOMBRE",

                    "ordre_tri":
                    "CROISSANT",

                    "limite_resultats":
                    50,

                    "nombre_classes":
                    10,

                    "inclure_manquantes":
                    False,

                    "filtres":
                    [],
                }

                return valider_proposition_widget_ia(
                    tableau_bord,
                    proposition,
                )

            if type_cible == "NUMÉRIQUE":
                proposition = {
                    "titre":
                    titre,

                    "explication":
                    (
                        f"La courbe affiche la moyenne de {cible} "
                        f"pour chaque valeur de {colonne_temporelle}."
                    ),

                    "type_widget":
                    "COURBE",

                    "colonne_categorie":
                    colonne_temporelle,

                    "colonne_mesure":
                    cible,

                    "colonne_serie":
                    "",

                    "agregation":
                    "MOYENNE",

                    "ordre_tri":
                    "CROISSANT",

                    "limite_resultats":
                    50,

                    "nombre_classes":
                    10,

                    "inclure_manquantes":
                    False,

                    "filtres":
                    [],
                }

                return valider_proposition_widget_ia(
                    tableau_bord,
                    proposition,
                )

    # Une demande d'évolution sans axe temporel ne doit
    # jamais être transformée silencieusement en courbe
    # par catégorie. Il vaut mieux demander une précision
    # que proposer une configuration statistiquement fausse.
    if demande_evolution and not colonne_temporelle:
        raise ErreurAssistantIA(
            (
                "Je n’ai pas identifié avec certitude "
                "la colonne temporelle. Mentionnez son "
                "nom ou utilisez une formulation comme "
                "« en fonction de l’année »."
            )
        )

    colonne_relation_x = ""
    colonne_relation_y = ""

    if relation_en_fonction:
        colonne_relation_x = (
            colonne_temporelle
            or colonne_apres_expression(
                demande,
                colonnes,
                [
                    "en fonction de",
                    "en fonction des",
                    "en fonction du",
                ],
            )
        )

        colonne_relation_y = next(
            (
                colonne
                for colonne in mentionnees
                if colonne
                != colonne_relation_x
            ),
            "",
        )

    profil_x = profils.get(
        colonne_relation_x,
        {},
    )

    profil_y = profils.get(
        colonne_relation_y,
        {},
    )

    nom_x_normalise = normaliser_texte(
        colonne_relation_x
    )

    categorie_temporelle = (
        profil_x.get("type") == "DATE"
        or any(
            mot in nom_x_normalise.split()
            for mot in (
                "date",
                "annee",
                "year",
                "mois",
                "month",
                "trimestre",
                "quarter",
            )
        )
    )

    relation_numerique = (
        profil_x.get("type")
        == "NUMÉRIQUE"
        and profil_y.get("type")
        == "NUMÉRIQUE"
    )

    # Les demandes explicites d’indicateur sont
    # prioritaires. Cela évite que l’expression
    # « nombre total de lignes » soit confondue
    # avec un graphique en ligne.
    if (
        "indicateur" in texte
        or re.search(
            r"\bkpi\b",
            texte,
        )
        or (
            "nombre total de lignes"
            in texte
        )
        or (
            "nombre de lignes"
            in texte
            and " par "
            not in f" {texte} "
        )
    ):
        type_widget = "INDICATEUR"

    elif (
        "nuage" in texte
        or "scatter" in texte
        or "correlation" in texte
    ):
        type_widget = "NUAGE_POINTS"

    elif "histogramme" in texte:
        type_widget = "HISTOGRAMME"

    elif (
        "camembert" in texte
        or "secteur" in texte
        or "circulaire" in texte
    ):
        type_widget = "CAMEMBERT"

    elif (
        "barre" in texte
        or "barres" in texte
    ):
        type_widget = "BARRES"

    elif (
        "courbe" in texte
        or demande_evolution
        or re.search(
            (
                r"\b(?:graphique|diagramme)"
                r"s? en lignes?\b"
            ),
            texte,
        )
    ):
        type_widget = "COURBE"

    elif relation_en_fonction:
        if categorie_temporelle:
            type_widget = "COURBE"
        elif relation_numerique:
            type_widget = "NUAGE_POINTS"
        else:
            type_widget = "BARRES"

    elif (
        "tableau" in texte
        or "table " in f"{texte} "
    ):
        type_widget = "TABLEAU"

    elif " par " in f" {texte} ":
        type_widget = "BARRES"

    else:
        type_widget = "INDICATEUR"

    if (
        "nombre distinct" in texte
        or "distinct" in texte
    ):
        agregation = "NOMBRE_DISTINCT"

    elif "moyenne" in texte:
        agregation = "MOYENNE"

    elif "mediane" in texte:
        agregation = "MEDIANE"

    elif (
        "minimum" in texte
        or re.search(
            r"\bmin\b",
            texte,
        )
    ):
        agregation = "MINIMUM"

    elif (
        "maximum" in texte
        or re.search(
            r"\bmax\b",
            texte,
        )
    ):
        agregation = "MAXIMUM"

    elif (
        "somme" in texte
        or (
            "total de" in texte
            and "nombre total" not in texte
        )
    ):
        agregation = "SOMME"

    else:
        agregation = "NOMBRE"

    colonne_par = colonne_apres_expression(
        demande,
        colonnes,
        [
            "par",
            "selon",
            "en fonction de",
        ],
    )

    colonne_mesure = (
        colonne_apres_expression(
            demande,
            colonnes,
            [
                "moyenne de",
                "mediane de",
                "somme de",
                "minimum de",
                "maximum de",
                "nombre distinct de",
                "distinct de",
            ],
        )
    )

    colonne_categorie = ""
    mesure = ""
    serie = ""

    # Dans « évolution de X en fonction de Y »,
    # Y est l’axe X et X est l’axe Y.
    if (
        relation_en_fonction
        and colonne_relation_x
        and colonne_relation_y
    ):
        colonne_categorie = colonne_relation_x
        mesure = colonne_relation_y

        if type_widget == "NUAGE_POINTS":
            agregation = "NOMBRE"
        elif agregation == "NOMBRE":
            agregation = "MOYENNE"

    elif (
        demande_evolution
        and len(mentionnees) >= 2
    ):
        colonne_categorie = (
            colonne_par or mentionnees[-1]
        )
        mesure = next(
            (
                colonne
                for colonne in mentionnees
                if colonne != colonne_categorie
            ),
            "",
        )

        if mesure and agregation == "NOMBRE":
            agregation = "MOYENNE"

    elif type_widget == "HISTOGRAMME":
        colonne_categorie = (
            mentionnees[0]
            if mentionnees
            else ""
        )

        agregation = "NOMBRE"

    elif type_widget == "NUAGE_POINTS":
        if len(mentionnees) >= 2:
            colonne_categorie = (
                mentionnees[0]
            )

            mesure = mentionnees[1]

        else:
            return None

    elif agregation == "NOMBRE":
        if type_widget == "INDICATEUR":
            colonne_categorie = ""
            mesure = ""

        else:
            colonne_categorie = (
                colonne_par
                or (
                    mentionnees[0]
                    if mentionnees
                    else ""
                )
            )

    elif agregation == "NOMBRE_DISTINCT":
        mesure = (
            colonne_mesure
            or (
                mentionnees[0]
                if mentionnees
                else ""
            )
        )

        if (
            type_widget
            != "INDICATEUR"
        ):
            colonne_categorie = (
                colonne_par
                or next(
                    (
                        colonne
                        for colonne
                        in mentionnees
                        if colonne != mesure
                    ),
                    "",
                )
            )

    else:
        mesure = (
            colonne_mesure
            or (
                mentionnees[0]
                if mentionnees
                else ""
            )
        )

        if (
            type_widget
            != "INDICATEUR"
        ):
            colonne_categorie = (
                colonne_par
                or next(
                    (
                        colonne
                        for colonne
                        in mentionnees
                        if colonne != mesure
                    ),
                    "",
                )
            )

    if (
        type_widget
        in {
            "BARRES",
            "CAMEMBERT",
            "COURBE",
        }
        and not colonne_categorie
    ):
        return None

    if (
        agregation
        != "NOMBRE"
        and not mesure
    ):
        return None

    limite = 10

    correspondance_limite = re.search(
        (
            r"\b(?:top|premiers?|premieres?)"
            r"\s*(\d{1,3})\b"
        ),
        texte,
    )

    if not correspondance_limite:
        correspondance_limite = re.search(
            (
                r"\b(\d{1,3})\s*"
                r"(?:premiers?|premieres?)\b"
            ),
            texte,
        )

    if correspondance_limite:
        limite = min(
            100,
            max(
                1,
                int(
                    correspondance_limite.group(
                        1
                    )
                ),
            ),
        )

    ordre = (
        "CROISSANT"
        if (
            "croissant" in texte
            or "ascendant" in texte
        )
        else "DECROISSANT"
    )

    titre = str(
        demande
    ).strip()

    if len(titre) > 100:
        titre = (
            titre[:97].rstrip()
            + "..."
        )

    proposition = {
        "titre":
        titre,

        "explication":
        (
            "Configuration interprétée "
            "automatiquement à partir de "
            "la demande."
        ),

        "type_widget":
        type_widget,

        "colonne_categorie":
        colonne_categorie,

        "colonne_mesure":
        mesure,

        "colonne_serie":
        serie,

        "agregation":
        agregation,

        "ordre_tri":
        ordre,

        "limite_resultats":
        limite,

        "nombre_classes":
        10,

        "inclure_manquantes":
        False,

        "filtres":
        [],
    }

    try:
        return valider_proposition_widget_ia(
            tableau_bord,
            proposition,
        )

    except ErreurAssistantIA as erreur:
        demande_explicite = any(
            expression in texte
            for expression in (
                "indicateur",
                "kpi",
                "histogramme",
                "camembert",
                "secteur",
                "barre",
                "barres",
                "courbe",
                "nuage",
                "scatter",
                "tableau",
                "nombre total de lignes",
                "nombre de lignes",
            )
        )

        if demande_explicite:
            raise ErreurAssistantIA(
                (
                    "La demande a été comprise, "
                    "mais la configuration a été "
                    f"refusée : {erreur}"
                )
            ) from erreur

        # Une demande réellement ambiguë peut encore
        # être confiée au petit modèle Ollama.
        return None


def construire_contexte_ia(
    tableau_bord,
    profils_colonnes=None,
) -> dict[str, Any]:
    """Construit un contexte compact sans envoyer les lignes."""

    profils = profils_colonnes

    if profils is None:
        try:
            profils = construire_profils_colonnes(
                tableau_bord.jeu_donnees
            )
        except Exception:
            profils = {}

    colonnes = []

    for nom, profil in list(profils.items())[:50]:
        colonnes.append(
            {
                "nom": nom,
                "type": profil.get("type", "INCONNU"),
                "exemples": list(
                    profil.get("exemples", []) or []
                )[:3],
                "nombre_distinctes": int(
                    profil.get("nombre_uniques", 0) or 0
                ),
                "nombre_manquantes": int(
                    profil.get("nombre_manquantes", 0) or 0
                ),
                "identifiant_probable": bool(
                    profil.get("semble_identifiant", False)
                ),
            }
        )

    if not colonnes:
        colonnes = [
            {"nom": str(nom)}
            for nom in list(
                tableau_bord.jeu_donnees.colonnes or []
            )[:50]
        ]

    return {
        "jeu_donnees": tableau_bord.jeu_donnees.nom,
        "nombre_lignes": int(
            getattr(
                tableau_bord.jeu_donnees,
                "nombre_lignes",
                0,
            ) or 0
        ),
        "colonnes": colonnes,
    }


def generer_proposition_widget_ia(
    tableau_bord,
    demande: str,
    profils_colonnes=None,
) -> dict[str, Any]:
    """
    Utilise d’abord un interpréteur local instantané,
    puis Ollama uniquement lorsque la demande reste
    ambiguë.
    """

    proposition_rapide = (
        construire_proposition_rapide(
            tableau_bord,
            demande,
            profils_colonnes=profils_colonnes,
        )
    )

    if proposition_rapide is not None:
        return proposition_rapide

    import urllib.error
    import urllib.request

    adresse = str(
        getattr(
            settings,
            "OLLAMA_BASE_URL",
            "http://127.0.0.1:11434",
        )
        or "http://127.0.0.1:11434"
    ).rstrip("/")

    modele = str(
        getattr(
            settings,
            "OLLAMA_MODEL",
            "qwen2.5:0.5b-instruct",
        )
        or "qwen2.5:0.5b-instruct"
    ).strip()

    timeout = int(
        getattr(
            settings,
            "OLLAMA_TIMEOUT",
            90,
        )
        or 90
    )

    contexte = construire_contexte_ia(
        tableau_bord,
        profils_colonnes=profils_colonnes,
    )

    colonnes_exactes = list(
        tableau_bord.jeu_donnees.colonnes
        or []
    )

    colonnes_probables = (
        colonnes_mentionnees(
            demande,
            colonnes_exactes,
        )
    )

    schema_sortie = (
        construire_schema_sortie_ollama(
            colonnes_exactes
        )
    )

    format_attendu = {
        "titre":
        "Titre court",

        "explication":
        "Phrase courte",

        "type_widget":
        (
            "INDICATEUR|BARRES|CAMEMBERT|COURBE|"
            "HISTOGRAMME|NUAGE_POINTS|TABLEAU"
        ),

        "colonne_categorie":
        "nom exact ou chaîne vide",

        "colonne_mesure":
        "nom exact ou chaîne vide",

        "colonne_serie":
        "nom exact ou chaîne vide",

        "agregation":
        (
            "NOMBRE|NOMBRE_DISTINCT|SOMME|MOYENNE|"
            "MEDIANE|MINIMUM|MAXIMUM"
        ),

        "ordre_tri":
        "CROISSANT|DECROISSANT",

        "limite_resultats":
        10,

        "nombre_classes":
        10,

        "inclure_manquantes":
        False,

        "filtres":
        [],
    }

    prompt = (
        "Crée une configuration JSON de widget.\n"
        "Utilise uniquement les noms exacts autorisés par le schéma.\n"
        "Associe les formulations approximatives aux colonnes réelles.\n"
        "Appuie-toi sur leurs types et exemples.\n"
        "Pour X en fonction de Y, Y est l’axe X et X est l’axe Y.\n"
        "Une évolution utilise généralement une COURBE.\n"
        "Deux variables numériques sans temps utilisent généralement "
        "un NUAGE_POINTS.\n"
        "Ne calcule aucune statistique.\n"
        "Réponds uniquement avec un objet JSON.\n\n"
        f"Demande : {demande}\n"
        f"Colonnes probablement mentionnées : "
        f"{json.dumps(colonnes_probables, ensure_ascii=False)}\n"
        f"Contexte : "
        f"{json.dumps(contexte, ensure_ascii=False)}\n"
        f"Format : "
        f"{json.dumps(format_attendu, ensure_ascii=False)}"
    )

    charge_utile = {
        "model":
        modele,

        "stream":
        False,

        "format":
        schema_sortie,

        "keep_alive":
        "30m",

        "messages": [
            {
                "role":
                "system",

                "content":
                (
                    "Tu transformes une demande en "
                    "configuration de visualisation. "
                    "Tu réponds uniquement en JSON."
                ),
            },

            {
                "role":
                "user",

                "content":
                prompt,
            },
        ],

        "options": {
            "temperature":
            0,

            "seed":
            42,

            "num_ctx":
            2048,

            "num_predict":
            220,
        },
    }

    requete = urllib.request.Request(
        f"{adresse}/api/chat",

        data=json.dumps(
            charge_utile,
            ensure_ascii=False,
        ).encode("utf-8"),

        headers={
            "Content-Type":
            "application/json",
        },

        method="POST",
    )

    try:
        with urllib.request.urlopen(
            requete,
            timeout=timeout,
        ) as reponse:
            corps = reponse.read().decode(
                "utf-8"
            )

        resultat_ollama = json.loads(
            corps
        )

        logger.info(
            (
                "Ollama : total=%s, chargement=%s, "
                "tokens_entree=%s, tokens_sortie=%s"
            ),
            resultat_ollama.get(
                "total_duration"
            ),
            resultat_ollama.get(
                "load_duration"
            ),
            resultat_ollama.get(
                "prompt_eval_count"
            ),
            resultat_ollama.get(
                "eval_count"
            ),
        )

        texte = str(
            resultat_ollama
            .get(
                "message",
                {},
            )
            .get(
                "content",
                "",
            )
            or ""
        ).strip()

        if not texte:
            raise ErreurAssistantIA(
                (
                    "Le modèle local n’a retourné "
                    "aucune proposition."
                )
            )

        proposition = json.loads(
            texte
        )

    except urllib.error.HTTPError as erreur:
        detail = ""

        try:
            detail = erreur.read().decode(
                "utf-8",
                errors="ignore",
            )

        except Exception:
            pass

        if erreur.code == 404:
            raise ErreurAssistantIA(
                (
                    f"Le modèle « {modele} » "
                    "n’est pas installé. Exécutez : "
                    f"ollama pull {modele}"
                )
            ) from erreur

        raise ErreurAssistantIA(
            (
                "Ollama a refusé la requête. "
                f"Détail : {detail[:300]}"
            )
        ) from erreur

    except urllib.error.URLError as erreur:
        raise ErreurAssistantIA(
            (
                "Ollama n’est pas accessible. "
                "Vérifiez qu’il est lancé."
            )
        ) from erreur

    except TimeoutError as erreur:
        raise ErreurAssistantIA(
            (
                "Le modèle local reste trop lent. "
                "Utilisez une demande contenant le "
                "type de graphique et les noms exacts "
                "des colonnes."
            )
        ) from erreur

    except json.JSONDecodeError as erreur:
        raise ErreurAssistantIA(
            (
                "La réponse du modèle local n’a pas "
                "pu être interprétée."
            )
        ) from erreur

    except ErreurAssistantIA:
        raise

    except Exception as erreur:
        logger.exception(
            "Erreur inattendue Ollama."
        )

        raise ErreurAssistantIA(
            (
                "Une erreur est survenue pendant "
                "l’utilisation du modèle local."
            )
        ) from erreur

    return valider_proposition_widget_ia(
        tableau_bord,
        proposition,
    )

def construire_donnees_widget_form(
    proposition,
):
    inclure_manquantes = bool(
        proposition.get(
            "inclure_manquantes",
            False,
        )
    )

    donnees = {
        "titre":
        proposition.get(
            "titre",
            "",
        ),

        "type_widget":
        proposition.get(
            "type_widget",
            "",
        ),

        "colonne_categorie":
        proposition.get(
            "colonne_categorie",
            "",
        ),

        "colonne_mesure":
        proposition.get(
            "colonne_mesure",
            "",
        ),

        "colonne_serie":
        proposition.get(
            "colonne_serie",
            "",
        ),

        "agregation":
        proposition.get(
            "agregation",
            "NOMBRE",
        ),

        "ordre_tri":
        proposition.get(
            "ordre_tri",
            "DECROISSANT",
        ),

        "limite_resultats":
        proposition.get(
            "limite_resultats",
            10,
        ),

        "nombre_classes":
        proposition.get(
            "nombre_classes",
            10,
        ),
    }

    if inclure_manquantes:
        donnees[
            "inclure_manquantes"
        ] = "on"

    return donnees


def formater_erreurs_formulaire(
    form,
) -> str:
    erreurs = []

    for champ, messages in (
        form.errors.items()
    ):
        libelle = (
            form.fields[
                champ
            ].label
            if champ in form.fields
            else "Configuration"
        )

        for message in messages:
            erreurs.append(
                f"{libelle} : {message}"
            )

    return " ".join(
        erreurs
    )


def valider_proposition_widget_ia(
    tableau_bord,
    proposition,
) -> dict[str, Any]:
    """
    Ne fait jamais confiance directement
    à la réponse du modèle.
    """

    if not isinstance(
        proposition,
        dict,
    ):
        raise ErreurAssistantIA(
            "La proposition IA est invalide."
        )

    colonnes = set(
        tableau_bord.jeu_donnees.colonnes
        or []
    )

    titre = str(
        proposition.get(
            "titre",
            "",
        )
        or ""
    ).strip()

    if not titre:
        raise ErreurAssistantIA(
            (
                "L’assistant n’a pas proposé "
                "de titre."
            )
        )

    if len(titre) > 200:
        titre = titre[:200].strip()

    dimension = resoudre_nom_colonne(
        proposition.get(
            "colonne_categorie",
            "",
        ),
        colonnes,
    )

    mesure = resoudre_nom_colonne(
        proposition.get(
            "colonne_mesure",
            "",
        ),
        colonnes,
    )

    serie = resoudre_nom_colonne(
        proposition.get(
            "colonne_serie",
            "",
        ),
        colonnes,
    )

    for libelle, colonne in (
        ("dimension", dimension),
        ("mesure", mesure),
        ("série", serie),
    ):
        if (
            colonne
            and colonne not in colonnes
        ):
            raise ErreurAssistantIA(
                (
                    f"La {libelle} « {colonne} » "
                    "n’existe pas dans ce jeu de données."
                )
            )

    type_widget = str(
        proposition.get(
            "type_widget",
            "",
        )
        or ""
    ).strip()

    agregation = str(
        proposition.get(
            "agregation",
            "NOMBRE",
        )
        or "NOMBRE"
    ).strip()

    ordre_tri = str(
        proposition.get(
            "ordre_tri",
            "DECROISSANT",
        )
        or "DECROISSANT"
    ).strip()

    if (
        type_widget
        not in TYPES_WIDGETS_AUTORISES
    ):
        raise ErreurAssistantIA(
            (
                "Le type de visualisation "
                "proposé n’est pas autorisé."
            )
        )

    if serie:
        if type_widget not in {
            "BARRES",
            "COURBE",
        }:
            raise ErreurAssistantIA(
                (
                    "Une série est autorisée uniquement "
                    "pour les barres et les courbes."
                )
            )

        if serie in {
            dimension,
            mesure,
        }:
            raise ErreurAssistantIA(
                (
                    "La colonne de série doit être "
                    "différente des axes X et Y."
                )
            )

    if (
        agregation
        not in AGREGATIONS_AUTORISEES
    ):
        raise ErreurAssistantIA(
            (
                "La fonction d’agrégation "
                "proposée n’est pas autorisée."
            )
        )

    if ordre_tri not in ORDRES_AUTORISES:
        raise ErreurAssistantIA(
            (
                "L’ordre de tri proposé "
                "n’est pas autorisé."
            )
        )

    try:
        limite_resultats = int(
            proposition.get(
                "limite_resultats",
                10,
            )
            or 10
        )

    except (
        TypeError,
        ValueError,
    ):
        limite_resultats = 10

    limite_resultats = min(
        100,
        max(
            1,
            limite_resultats,
        ),
    )

    try:
        nombre_classes = int(
            proposition.get(
                "nombre_classes",
                10,
            )
            or 10
        )

    except (
        TypeError,
        ValueError,
    ):
        nombre_classes = 10

    nombre_classes = min(
        50,
        max(
            3,
            nombre_classes,
        ),
    )

    proposition_normalisee = {
        "titre":
        titre,

        "explication":
        str(
            proposition.get(
                "explication",
                "",
            )
            or ""
        ).strip(),

        "type_widget":
        type_widget,

        "colonne_categorie":
        dimension,

        "colonne_mesure":
        mesure,

        "colonne_serie":
        serie,

        "agregation":
        agregation,

        "ordre_tri":
        ordre_tri,

        "limite_resultats":
        limite_resultats,

        "nombre_classes":
        nombre_classes,

        "inclure_manquantes":
        bool(
            proposition.get(
                "inclure_manquantes",
                False,
            )
        ),

        "filtres":
        [],
    }

    formulaire_widget = WidgetForm(
        construire_donnees_widget_form(
            proposition_normalisee
        ),
        tableau_bord=tableau_bord,
    )

    if not formulaire_widget.is_valid():
        raise ErreurAssistantIA(
            (
                "La proposition n’est pas compatible "
                "avec les règles statistiques : "
                f"{formater_erreurs_formulaire(formulaire_widget)}"
            )
        )

    filtres = proposition.get(
        "filtres",
        [],
    )

    if not isinstance(
        filtres,
        list,
    ):
        raise ErreurAssistantIA(
            (
                "La liste des filtres "
                "proposés est invalide."
            )
        )

    for filtre in filtres[:3]:
        if not isinstance(
            filtre,
            dict,
        ):
            continue

        colonne = resoudre_nom_colonne(
            filtre.get(
                "colonne",
                "",
            ),
            colonnes,
        )

        operateur = str(
            filtre.get(
                "operateur",
                "",
            )
            or ""
        ).strip()

        valeur = str(
            filtre.get(
                "valeur",
                "",
            )
            or ""
        ).strip()

        if colonne not in colonnes:
            raise ErreurAssistantIA(
                (
                    f"La colonne de filtre « {colonne} » "
                    "n’existe pas."
                )
            )

        if (
            operateur
            not in OPERATEURS_AUTORISES
        ):
            raise ErreurAssistantIA(
                (
                    "Un opérateur de filtre "
                    "proposé n’est pas autorisé."
                )
            )

        sans_valeur = {
            Filtre.Operateur.VIDE,
            Filtre.Operateur.NON_VIDE,
        }

        if (
            operateur not in sans_valeur
            and not valeur
        ):
            raise ErreurAssistantIA(
                (
                    f"Le filtre sur « {colonne} » "
                    "nécessite une valeur."
                )
            )

        if (
            operateur
            == Filtre.Operateur.ENTRE
            and len(
                [
                    element
                    for element
                    in valeur.split(";")
                    if element.strip()
                ]
            )
            != 2
        ):
            raise ErreurAssistantIA(
                (
                    "Un filtre « Entre deux valeurs » "
                    "doit utiliser deux bornes séparées "
                    "par un point-virgule."
                )
            )

        if operateur in sans_valeur:
            valeur = ""

        proposition_normalisee[
            "filtres"
        ].append(
            {
                "colonne":
                colonne,

                "operateur":
                operateur,

                "valeur":
                valeur,
            }
        )

    return proposition_normalisee


@transaction.atomic
def creer_widget_depuis_proposition(
    tableau_bord,
    proposition,
):
    """
    Crée le widget uniquement après confirmation
    de l’utilisateur et après une seconde validation.
    """

    proposition = (
        valider_proposition_widget_ia(
            tableau_bord,
            proposition,
        )
    )

    formulaire = WidgetForm(
        construire_donnees_widget_form(
            proposition
        ),
        tableau_bord=tableau_bord,
    )

    if not formulaire.is_valid():
        raise ErreurAssistantIA(
            (
                "La proposition n’est plus valide : "
                f"{formater_erreurs_formulaire(formulaire)}"
            )
        )

    widget = formulaire.save(
        commit=False
    )

    widget.tableau_bord = (
        tableau_bord
    )

    ordre_max = (
        Widget.objects
        .filter(
            tableau_bord=tableau_bord
        )
        .aggregate(
            valeur=Max(
                "ordre"
            )
        )[
            "valeur"
        ]
        or 0
    )

    widget.ordre = (
        ordre_max + 1
    )

    widget.save()

    for index, filtre in enumerate(
        proposition.get(
            "filtres",
            [],
        ),
        start=1,
    ):
        objet_filtre = FiltreWidget(
            widget=widget,

            colonne=filtre[
                "colonne"
            ],

            operateur=filtre[
                "operateur"
            ],

            valeur=filtre[
                "valeur"
            ],

            actif=True,

            ordre=index,
        )

        objet_filtre.full_clean()
        objet_filtre.save()

    return widget
