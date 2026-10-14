from __future__ import annotations

import json
import urllib.error
import urllib.request

from django.conf import settings

from .widget_recommender import generer_configurations
from .widget_validation import (
    ConfigurationWidgetInvalide,
    corriger_selon_demande,
    valider_configuration,
)


class ErreurOllama(Exception):
    pass


def parametres_ollama():
    base_url = str(getattr(settings, "OLLAMA_BASE_URL", "http://127.0.0.1:11434")).rstrip("/")
    modele = str(getattr(settings, "OLLAMA_MODEL", "llama3.1:8b"))
    timeout = int(getattr(settings, "OLLAMA_TIMEOUT", 90))
    return base_url, modele, timeout


def appeler_ollama(messages, temperature=0.1):
    base_url, modele, timeout = parametres_ollama()
    requete = urllib.request.Request(
        f"{base_url}/api/chat",
        data=json.dumps({
            "model": modele,
            "stream": False,
            "format": "json",
            "messages": messages,
            "options": {"temperature": temperature},
        }, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(requete, timeout=timeout) as reponse:
            resultat = json.loads(reponse.read().decode("utf-8"))
    except urllib.error.HTTPError as erreur:
        detail = erreur.read().decode("utf-8", errors="ignore")
        raise ErreurOllama(f"Ollama a refusé la requête : {detail[:300]}") from erreur
    except urllib.error.URLError as erreur:
        raise ErreurOllama("Ollama n’est pas accessible. Vérifiez qu’il est lancé.") from erreur
    except TimeoutError as erreur:
        raise ErreurOllama("Ollama n’a pas répondu dans le délai prévu.") from erreur

    contenu = str(resultat.get("message", {}).get("content", "") or "").strip()
    if not contenu:
        raise ErreurOllama("Ollama n’a retourné aucune réponse.")
    try:
        return json.loads(contenu), modele
    except json.JSONDecodeError as erreur:
        raise ErreurOllama("La réponse d’Ollama n’est pas un JSON valide.") from erreur


def contexte_compact(analyse, tableau_bord):
    schema = analyse.schema or {}
    profils = schema.get("profils", {})
    statistiques = analyse.statistiques or {}

    colonnes = []
    for nom, profil in profils.items():
        element = {
            "nom": nom,
            "type": profil.get("type"),
            "exemples": list(profil.get("exemples", []))[:3],
            "nombre_uniques": profil.get("nombre_uniques"),
            "taux_manquantes": profil.get("taux_manquantes"),
            "utilisable_dimension": profil.get("utilisable_dimension"),
            "utilisable_mesure": profil.get("utilisable_mesure"),
            "est_geographique": profil.get("est_geographique", False),
            "est_pourcentage": profil.get("est_pourcentage", False),
        }
        if nom in statistiques.get("numeriques", {}):
            element["statistiques"] = statistiques["numeriques"][nom]
        if nom in statistiques.get("temporelles", {}):
            element["periode"] = statistiques["temporelles"][nom]
        if nom in statistiques.get("categorielles", {}):
            element["modalites_principales"] = statistiques["categorielles"][nom].get(
                "modalites_principales", []
            )[:5]
        colonnes.append(element)

    widgets_actuels = [
        {
            "titre": widget.titre,
            "type_widget": widget.type_widget,
            "colonne_categorie": widget.colonne_categorie,
            "configuration": widget.configuration or {},
        }
        for widget in tableau_bord.widgets.all().order_by("ordre", "date_creation")
    ]

    catalogue = []
    for configuration, _ in generer_configurations(analyse, limite=20):
        catalogue.append({
            "titre": configuration.get("titre"),
            "categorie": configuration.get("categorie"),
            "pertinence": configuration.get("pertinence"),
            "type_widget": configuration.get("type_widget"),
            "dimension": configuration.get("colonne_categorie"),
            "mesure": configuration.get("colonne_mesure"),
            "serie": configuration.get("colonne_serie"),
            "agregation": configuration.get("agregation"),
            "objectif": configuration.get("objectif"),
            "raison": configuration.get("raison"),
        })

    return {
        "jeu_donnees": tableau_bord.jeu_donnees.nom,
        "nombre_lignes": schema.get("nombre_lignes"),
        "colonnes": colonnes,
        "relations_possibles": list(analyse.relations or [])[:30],
        "indicateurs_calculables": list(analyse.indicateurs or [])[:12],
        "filtres_recommandes": list(schema.get("filtres_recommandes", []) or [])[:12],
        "widgets_non_disponibles": list(schema.get("widgets_non_disponibles", []) or []),
        "catalogue_automatique": catalogue,
        "widgets_actuels": widgets_actuels,
    }


def demande_catalogue_global(demande):
    texte = str(demande or "").lower()
    expressions = (
        "tous les widgets",
        "toutes les suggestions",
        "tous les graphiques",
        "widgets possibles",
        "autres suggestions",
        "tableau de bord equilibre",
        "tableau de bord équilibré",
    )
    return any(expression in texte for expression in expressions)


def traiter_message(demande, analyse, tableau_bord):
    contexte = contexte_compact(analyse, tableau_bord)

    if demande_catalogue_global(demande):
        nombre = len(contexte.get("catalogue_automatique", []))
        return {
            "action": "REPONDRE",
            "message": (
                f"L’analyse automatique a déjà préparé {nombre} proposition(s) "
                "classées par indicateurs, comparaisons, évolutions, répartitions, "
                "relations et tableaux. La sélection équilibrée indique les widgets "
                "les plus importants. Les autres propositions restent disponibles "
                "et modifiables dans chaque catégorie."
            ),
            "suggestions": [],
            "modele": "Règles Python/Pandas",
        }

    instructions = """
Tu es l’assistant de création de tableaux de bord de la plateforme HCP.
Tu n’as jamais accès aux lignes du fichier. Tu reçois uniquement le schéma,
les types, des statistiques calculées par Pandas, les relations détectées,
un catalogue automatique et les widgets impossibles.

Tu peux proposer de 0 à 6 widgets. Réponds par un JSON strict :
{
  "action": "PROPOSER_WIDGETS" | "REPONDRE" | "CLARIFIER",
  "message": "réponse claire en français",
  "suggestions": [
    {
      "titre": "...",
      "type_widget": "INDICATEUR|BARRES|CAMEMBERT|COURBE|HISTOGRAMME|NUAGE_POINTS|TABLEAU",
      "colonne_categorie": "nom exact ou chaîne vide",
      "colonne_mesure": "nom exact ou chaîne vide",
      "colonne_serie": "nom exact ou chaîne vide",
      "agregation": "NOMBRE|NOMBRE_DISTINCT|SOMME|MOYENNE|MEDIANE|MINIMUM|MAXIMUM",
      "ordre_tri": "CROISSANT|DECROISSANT",
      "limite_resultats": 10,
      "nombre_classes": 10,
      "inclure_manquantes": false,
      "categorie": "INDICATEURS_CLES|COMPARAISONS|EVOLUTIONS_TEMPORELLES|REPARTITIONS|RELATIONS_VARIABLES|TABLEAUX_DETAILLES",
      "pertinence": "FORTEMENT_RECOMMANDE|RECOMMANDE|OPTIONNEL",
      "objectif": "information recherchée",
      "raison": "raison statistique et métier",
      "alternatives": [
        {"libelle": "autre représentation", "raison": "quand la choisir"}
      ],
      "filtres_recommandes": [
        {"colonne": "nom exact", "raison": "utilité du filtre"}
      ]
    }
  ]
}

Règles obligatoires :
- Utilise uniquement les noms exacts des colonnes du contexte.
- N’invente aucune colonne, valeur, statistique ou donnée.
- Ne propose pas un widget seulement parce qu’il est techniquement possible.
- Une évolution exige une colonne temporelle et utilise généralement une COURBE.
- Une comparaison de catégories utilise généralement des BARRES.
- Une répartition circulaire convient uniquement à un petit nombre de catégories.
- Deux variables numériques peuvent utiliser un NUAGE_POINTS.
- Un histogramme exige une colonne numérique.
- Un KPI correspond à une valeur agrégée unique.
- Les types non autorisés comme carte, jauge, graphique combiné ou tableau croisé
  ne doivent pas être placés dans suggestions. Explique leur impossibilité dans message
  en utilisant la section widgets_non_disponibles.
- Lorsque plusieurs représentations sont possibles, choisis la meilleure et place
  les autres dans alternatives.
- Chaque suggestion doit avoir un objectif, une raison et un niveau de pertinence.
- Le widget ne sera jamais créé sans confirmation de l’utilisateur.
- Si la demande est ambiguë, utilise CLARIFIER.
""".strip()

    resultat, modele = appeler_ollama([
        {"role": "system", "content": instructions},
        {
            "role": "user",
            "content": (
                "Contexte analysé par Pandas :\n"
                + json.dumps(contexte, ensure_ascii=False, default=str)
                + "\n\nDemande utilisateur :\n"
                + str(demande)
            ),
        },
    ])

    action = str(resultat.get("action", "REPONDRE") or "REPONDRE").upper()
    if action == "PROPOSER_WIDGET":
        action = "PROPOSER_WIDGETS"
    message = str(resultat.get("message", "") or "").strip()
    suggestions_brutes = resultat.get("suggestions", [])

    if not suggestions_brutes and isinstance(resultat.get("suggestion"), dict):
        suggestions_brutes = [resultat["suggestion"]]

    suggestions = []
    erreurs = []

    if action == "PROPOSER_WIDGETS":
        if not isinstance(suggestions_brutes, list):
            raise ErreurOllama("Ollama n’a pas fourni une liste de suggestions valide.")

        for proposition in suggestions_brutes[:6]:
            if not isinstance(proposition, dict):
                continue
            try:
                proposition = corriger_selon_demande(
                    proposition,
                    demande,
                    analyse,
                )
                proposition = valider_configuration(
                    proposition,
                    analyse,
                )
            except ConfigurationWidgetInvalide as erreur:
                erreurs.append(str(erreur))
                continue
            suggestions.append(proposition)

        if not suggestions:
            detail = erreurs[0] if erreurs else "Aucune configuration exploitable n’a été fournie."
            return {
                "action": "CLARIFIER",
                "message": (
                    "La demande n’a pas permis de préparer un widget valide. "
                    + detail
                ),
                "suggestions": [],
                "modele": modele,
            }

    return {
        "action": action,
        "message": message or (
            "Proposition préparée à partir de l’analyse du jeu de données."
            if suggestions
            else "Réponse préparée à partir de l’analyse disponible."
        ),
        "suggestions": suggestions if action == "PROPOSER_WIDGETS" else [],
        "modele": modele,
    }


def normaliser_placeholder(valeur):
    texte = str(valeur or "").strip().lower()
    remplacements = str.maketrans({
        "é": "e", "è": "e", "ê": "e", "ë": "e",
        "à": "a", "â": "a", "ä": "a",
        "î": "i", "ï": "i", "ô": "o", "ö": "o",
        "ù": "u", "û": "u", "ü": "u", "ç": "c", "’": "'",
    })
    return " ".join(texte.translate(remplacements).split())


def nettoyer_texte_ia(valeur, *, longueur_minimale=25):
    if valeur is None or isinstance(valeur, (dict, list)):
        return ""
    texte = str(valeur).strip()
    if not texte:
        return ""
    normalise = normaliser_placeholder(texte)
    if normalise in PLACEHOLDERS_IA:
        return ""
    if any(p in normalise for p in PLACEHOLDERS_IA if len(p) >= 12):
        return ""
    if texte.startswith(("{", "[")) or texte.endswith("}"):
        return ""
    if len(texte) < longueur_minimale:
        return ""
    if any(t in normalise for t in {"tableau_bord", "dataframe", "dictionnaire python", "json strict"}):
        return ""
    return texte


def liste_textes_valides(valeur):
    if not isinstance(valeur, list):
        return []
    resultat = []
    for element in valeur:
        texte = ""
        if isinstance(element, str):
            texte = nettoyer_texte_ia(element)
        elif isinstance(element, dict):
            for cle in ("texte", "constatation", "comparaison", "recommandation", "limite", "message"):
                texte = nettoyer_texte_ia(element.get(cle))
                if texte:
                    break
        if texte and texte not in resultat:
            resultat.append(texte)
    return resultat


def rapport_deterministe(donnees_calculees):
    tableau = donnees_calculees.get("tableau_bord", {})
    widgets = list(donnees_calculees.get("widgets", []) or [])
    nombre_widgets = int(tableau.get("nombre_widgets", len(widgets)) or 0)
    nombre_a_revoir = int(tableau.get("nombre_widgets_a_revoir", 0) or 0)
    nombre_attention = int(tableau.get("nombre_widgets_attention", 0) or 0)
    lignes_total = int(tableau.get("nombre_lignes_total", 0) or 0)
    lignes_filtrees = int(tableau.get("nombre_lignes_apres_filtres", lignes_total) or 0)

    resume = (
        f"Le tableau de bord « {tableau.get('titre', '')} » analyse le jeu de données "
        f"« {tableau.get('jeu_donnees', '')} » à travers {nombre_widgets} widget(s). "
        f"Les calculs portent sur {lignes_filtrees} ligne(s) après filtres, "
        f"sur {lignes_total} ligne(s) disponibles."
    )
    if nombre_a_revoir:
        resume += f" {nombre_a_revoir} widget(s) présentent une configuration à revoir."
    elif nombre_attention:
        resume += f" {nombre_attention} widget(s) nécessitent une attention particulière."

    analyses = []
    for widget in widgets:
        calculee = widget.get("analyse_calculee", {}) or {}
        analyses.append({
            "position": widget.get("position"),
            "titre": str(widget.get("titre", "Widget") or "Widget"),
            "type_widget": str(widget.get("type_widget_libelle", widget.get("type_widget", "")) or ""),
            "dimension": str(widget.get("dimension", "") or "Aucune"),
            "dimension_type": str(widget.get("dimension_type", "") or "Aucune"),
            "mesure": str(widget.get("mesure", "") or "Aucune"),
            "mesure_type": str(widget.get("mesure_type", "") or "Aucune"),
            "serie": str(widget.get("serie", "") or "Aucune"),
            "agregation": str(widget.get("agregation", "NOMBRE") or "NOMBRE"),
            "nombre_lignes_utilisees": int(widget.get("nombre_lignes_utilisees", 0) or 0),
            "interpretation": str(widget.get("interpretation_calculee", "") or "Le widget a été calculé à partir des données filtrées."),
            "prudence": str(widget.get("prudence_calculee", "") or "Les résultats dépendent des filtres et agrégations."),
            "details": list(widget.get("details_calcules", []) or [])[:16],
            "classement": list(calculee.get("classement", []) or [])[:5],
            "colonnes_statistiques": list(calculee.get("colonnes", []) or [])[:20],
            "series_resumees": list(calculee.get("series", []) or [])[:8],
            "qualite": dict(widget.get("qualite", {}) or {}),
            "commentaire_ia": "",
        })

    conclusion = (
        "Le tableau de bord fournit plusieurs résultats utiles, mais certaines visualisations "
        "doivent être corrigées avant une interprétation métier. Les alertes présentées dans "
        "chaque widget indiquent les améliorations prioritaires."
        if nombre_a_revoir
        else
        "Les widgets fournissent une lecture synthétique du jeu de données dans le périmètre "
        "défini par les filtres et les agrégations. Les résultats doivent être rapprochés du "
        "contexte métier avant toute décision."
    )

    return {
        "resume_executif": resume,
        "synthese_ia": "",
        "analyses_widgets": analyses,
        "comparaisons": list(donnees_calculees.get("comparaisons_calculees", []) or []),
        "constatations": list(donnees_calculees.get("constatations_calculees", []) or []),
        "recommandations": list(donnees_calculees.get("recommandations_calculees", []) or []),
        "limites": list(donnees_calculees.get("limites_calculees", []) or []),
        "conclusion": conclusion,
    }


def fusionner_commentaires_ollama(rapport_base, resultat_ollama):
    if not isinstance(resultat_ollama, dict):
        return rapport_base

    synthese = nettoyer_texte_ia(resultat_ollama.get("synthese"), longueur_minimale=70)
    if synthese:
        rapport_base["synthese_ia"] = synthese

    commentaires_par_titre = {}
    commentaires = resultat_ollama.get("commentaires_widgets", [])
    if isinstance(commentaires, list):
        for element in commentaires:
            if not isinstance(element, dict):
                continue
            titre = str(element.get("titre", "") or "").strip()
            commentaire = nettoyer_texte_ia(element.get("commentaire"), longueur_minimale=45)
            if titre and commentaire:
                commentaires_par_titre[titre] = commentaire

    for analyse in rapport_base["analyses_widgets"]:
        commentaire = commentaires_par_titre.get(analyse["titre"], "")
        if commentaire and commentaire not in {analyse["interpretation"], analyse["prudence"]}:
            analyse["commentaire_ia"] = commentaire

    for cle in ("comparaisons", "recommandations", "limites"):
        for texte in liste_textes_valides(resultat_ollama.get(cle, [])):
            if texte not in rapport_base[cle]:
                rapport_base[cle].append(texte)
    return rapport_base


def rediger_rapport(donnees_calculees):
    rapport_base = rapport_deterministe(donnees_calculees)
    contexte = {
        "tableau_bord": donnees_calculees.get("tableau_bord", {}),
        "widgets": [
            {
                "titre": widget.get("titre"),
                "type": widget.get("type_widget_libelle"),
                "dimension": widget.get("dimension"),
                "mesure": widget.get("mesure"),
                "agregation": widget.get("agregation"),
                "interpretation_calculee": widget.get("interpretation_calculee"),
                "qualite": widget.get("qualite"),
                "details_calcules": list(widget.get("details_calcules", []) or [])[:8],
            }
            for widget in donnees_calculees.get("widgets", [])
        ],
    }

    instructions = """
Tu rédiges uniquement des commentaires complémentaires à partir de résultats déjà
calculés par Django et Pandas. Tu ne calcules et n'inventes aucune valeur.

Interdictions :
- inventer une catégorie, un pays, un secteur ou une causalité ;
- modifier le titre d'un widget ;
- copier les exemples du schéma JSON ;
- répondre par « chaînes uniquement », « un paragraphe clair et court »,
  « commentaire complémentaire » ou les noms des champs ;
- employer les termes internes tableau_bord, DataFrame ou dictionnaire.

Réponds par un JSON strict :
{
  "synthese": "synthèse réelle de 3 à 5 phrases",
  "commentaires_widgets": [
    {"titre": "titre exact du widget", "commentaire": "commentaire réellement rédigé"}
  ],
  "comparaisons": ["phrases réellement rédigées"],
  "recommandations": ["phrases réellement rédigées"],
  "limites": ["phrases réellement rédigées"]
}
Les tableaux doivent contenir uniquement des phrases réellement rédigées.
""".strip()

    try:
        resultat, modele = appeler_ollama(
            [
                {"role": "system", "content": instructions},
                {
                    "role": "user",
                    "content": "Résultats autorisés :\n" + json.dumps(
                        contexte, ensure_ascii=False, default=str
                    ),
                },
            ],
            temperature=0.05,
        )
    except ErreurOllama:
        return rapport_base, "Django/Pandas — mode sécurisé"

    return fusionner_commentaires_ollama(rapport_base, resultat), modele
