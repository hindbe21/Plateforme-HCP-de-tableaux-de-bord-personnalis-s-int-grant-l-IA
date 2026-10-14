from __future__ import annotations

from collections import defaultdict

from ..models import SuggestionWidget
from .widget_validation import valider_configuration


CATEGORIES_SUGGESTIONS = (
    ("INDICATEURS_CLES", "Indicateurs clés"),
    ("COMPARAISONS", "Comparaisons"),
    ("EVOLUTIONS_TEMPORELLES", "Évolutions temporelles"),
    ("REPARTITIONS", "Répartitions et distributions"),
    ("RELATIONS_VARIABLES", "Relations entre variables"),
    ("TABLEAUX_DETAILLES", "Tableaux détaillés"),
)

PERTINENCE_LIBELLES = {
    "FORTEMENT_RECOMMANDE": "Fortement recommandé",
    "RECOMMANDE": "Recommandé",
    "OPTIONNEL": "Optionnel",
}

REPRESENTATIONS = {
    "INDICATEUR": "Carte KPI", "BARRES": "Graphique en barres",
    "BARRES_HORIZONTALES": "Barres horizontales", "CLASSEMENT": "Classement",
    "CAMEMBERT": "Graphique circulaire", "ANNEAU": "Graphique en anneau",
    "COURBE": "Graphique en courbes", "AIRES": "Graphique en aires",
    "HISTOGRAMME": "Histogramme", "NUAGE_POINTS": "Nuage de points",
    "TABLEAU": "Tableau simple", "TABLEAU_CROISE": "Tableau croisé",
    "STATISTIQUES_DESCRIPTIVES": "Statistiques descriptives",
}


class CatalogueSuggestions:
    def __init__(self, analyse, limite=80):
        self.analyse = analyse
        self.limite = max(1, int(limite or 40))
        self.schema = analyse.schema or {}
        self.profils = self.schema.get("profils", {})
        self.relations = sorted(
            analyse.relations or [],
            key=lambda element: element.get("score", 0),
            reverse=True,
        )
        self.configurations = []
        self.cles = set()
        self.compteurs_categories = defaultdict(int)

    def titre_colonne(self, nom):
        return str(nom).replace("_", " ").strip().capitalize()

    def pertinence(self, score):
        if score >= 88:
            return "FORTEMENT_RECOMMANDE"
        if score >= 72:
            return "RECOMMANDE"
        return "OPTIONNEL"

    def filtres_pour(self, colonnes_utilisees=None, limite=4):
        colonnes_utilisees = set(colonnes_utilisees or [])
        resultat = []
        for element in self.schema.get("filtres_recommandes", []) or []:
            colonne = element.get("colonne")
            if not colonne or colonne in colonnes_utilisees:
                continue
            resultat.append({
                "colonne": colonne,
                "raison": element.get("raison", ""),
            })
            if len(resultat) >= limite:
                break
        return resultat

    def ajouter(
        self,
        configuration,
        *,
        categorie,
        score,
        objectif,
        raison,
        alternatives=None,
        filtres_recommandes=None,
        representation=None,
        agregation_affichee=None,
    ):
        if len(self.configurations) >= self.limite:
            return

        categorie_libelle = dict(CATEGORIES_SUGGESTIONS).get(
            categorie,
            categorie,
        )
        pertinence = self.pertinence(score)

        configuration = {
            **configuration,
            "categorie": categorie,
            "categorie_libelle": categorie_libelle,
            "pertinence": pertinence,
            "pertinence_libelle": PERTINENCE_LIBELLES[pertinence],
            "score": round(float(score), 2),
            "objectif": objectif,
            "raison": raison,
            "alternatives": alternatives or [],
            "filtres_recommandes": filtres_recommandes or [],
            "representation": (
                representation
                or REPRESENTATIONS.get(
                    configuration.get("type_widget"),
                    configuration.get("type_widget", "Widget"),
                )
            ),
            "agregation_affichee": (
                agregation_affichee
                or configuration.get("agregation", "NOMBRE")
            ),
            "selection_equilibree": False,
            "selection_rang": 0,
            "filtres": list(configuration.get("filtres", []) or []),
        }

        configuration = valider_configuration(
            configuration,
            self.analyse,
        )

        cle = (
            configuration["type_widget"],
            configuration["colonne_categorie"],
            configuration["colonne_mesure"],
            configuration["colonne_serie"],
            configuration["agregation"],
            configuration["limite_resultats"],
        )
        if cle in self.cles:
            return

        self.cles.add(cle)
        self.configurations.append((configuration, raison))
        self.compteurs_categories[categorie] += 1

    def generer_indicateurs(self):
        indicateurs = list(self.analyse.indicateurs or [])

        for index, indicateur in enumerate(indicateurs[:10]):
            colonne = indicateur.get("colonne", "")
            agregation = indicateur.get("agregation", "NOMBRE")
            score = float(indicateur.get("score", 0.84) or 0.84) * 100

            if colonne:
                objectif = (
                    f"Suivre la valeur agrégée de « {colonne} » "
                    "en un coup d’œil."
                )
                raison = (
                    f"« {colonne} » est une mesure numérique. Une carte KPI "
                    f"résume sa {agregation.lower()} sans surcharger le tableau de bord."
                )
                filtres = self.filtres_pour([colonne])
            else:
                objectif = "Afficher le volume total d’enregistrements analysés."
                raison = (
                    "Le nombre total de lignes constitue un repère simple pour "
                    "comprendre le périmètre du tableau de bord."
                )
                filtres = self.filtres_pour([])

            self.ajouter(
                {
                    "titre": indicateur.get("titre") or "Indicateur clé",
                    "type_widget": "INDICATEUR",
                    "colonne_categorie": "",
                    "colonne_mesure": colonne,
                    "colonne_serie": "",
                    "agregation": agregation,
                    "ordre_tri": "DECROISSANT",
                    "limite_resultats": 10,
                    "nombre_classes": 10,
                    "inclure_manquantes": False,
                },
                categorie="INDICATEURS_CLES",
                score=score - index,
                objectif=objectif,
                raison=raison,
                alternatives=[
                    {
                        "libelle": "Tableau statistique",
                        "raison": "À utiliser lorsqu’un détail vérifiable est nécessaire.",
                    }
                ],
                filtres_recommandes=filtres,
                representation="Carte KPI",
            )

    def generer_relations(self):
        for relation in self.relations:
            nature = relation.get("nature")
            dimension = relation.get("dimension", "")
            mesure = relation.get("mesure", "")
            agregation = relation.get("agregation", "NOMBRE")
            score = float(relation.get("score", 0.70) or 0.70) * 100
            profil_dimension = self.profils.get(dimension, {})
            uniques = int(profil_dimension.get("nombre_uniques", 0) or 0)

            if nature == "EVOLUTION_TEMPORELLE":
                titre = f"Évolution de {self.titre_colonne(mesure)}"
                objectif = f"Observer l’évolution de « {mesure} » selon « {dimension} »."
                raison = (
                    f"« {dimension} » est temporelle et « {mesure} » est numérique. "
                    "La courbe respecte l’ordre du temps et met en évidence les tendances."
                )
                alternatives = [
                    {
                        "libelle": "Graphique en aires",
                        "raison": "Variante utile pour insister sur le volume cumulé.",
                    },
                    {
                        "libelle": "Graphique en barres",
                        "raison": "Plus lisible lorsqu’il existe peu de périodes.",
                    },
                ]
                self.ajouter(
                    {
                        "titre": titre,
                        "type_widget": "COURBE",
                        "colonne_categorie": dimension,
                        "colonne_mesure": mesure,
                        "colonne_serie": relation.get("serie", ""),
                        "agregation": agregation,
                        "ordre_tri": "CROISSANT",
                        "limite_resultats": 100,
                        "nombre_classes": 10,
                        "inclure_manquantes": False,
                    },
                    categorie="EVOLUTIONS_TEMPORELLES",
                    score=score,
                    objectif=objectif,
                    raison=raison,
                    alternatives=alternatives,
                    filtres_recommandes=self.filtres_pour([dimension, mesure]),
                    representation="Graphique en courbes",
                )

            elif nature in {"COMPARAISON_CATEGORIES", "CLASSEMENT"}:
                classement = nature == "CLASSEMENT"
                titre = (
                    f"Classement de {self.titre_colonne(mesure)} "
                    f"par {self.titre_colonne(dimension)}"
                    if classement
                    else (
                        f"{self.titre_colonne(mesure)} "
                        f"par {self.titre_colonne(dimension)}"
                    )
                )
                objectif = (
                    f"Classer les principales catégories de « {dimension} » selon « {mesure} »."
                    if classement
                    else f"Comparer « {mesure} » entre les catégories de « {dimension} »."
                )
                raison = (
                    f"« {dimension} » contient {uniques} catégorie(s) et « {mesure} » "
                    "est numérique. Les barres permettent une comparaison directe des valeurs."
                )
                alternatives = [
                    {
                        "libelle": "Tableau simple",
                        "raison": "Préférable pour consulter les valeurs exactes.",
                    }
                ]
                if 2 <= uniques <= 6:
                    alternatives.append({
                        "libelle": "Graphique circulaire",
                        "raison": "Possible si l’objectif porte sur la part de chaque catégorie.",
                    })

                self.ajouter(
                    {
                        "titre": titre,
                        "type_widget": "BARRES",
                        "colonne_categorie": dimension,
                        "colonne_mesure": mesure,
                        "colonne_serie": relation.get("serie", ""),
                        "agregation": agregation,
                        "ordre_tri": "DECROISSANT",
                        "limite_resultats": 10 if classement else min(30, max(10, uniques)),
                        "nombre_classes": 10,
                        "inclure_manquantes": False,
                    },
                    categorie="COMPARAISONS",
                    score=score,
                    objectif=objectif,
                    raison=raison,
                    alternatives=alternatives,
                    filtres_recommandes=self.filtres_pour([dimension, mesure]),
                    representation=(
                        "Classement en barres"
                        if classement
                        else "Graphique en barres"
                    ),
                )

            elif nature == "REPARTITION_CATEGORIES":
                type_widget = relation.get("widget", "BARRES")
                representation = (
                    "Graphique circulaire"
                    if type_widget == "CAMEMBERT"
                    else "Graphique en barres"
                )
                titre = f"Répartition par {self.titre_colonne(dimension)}"
                objectif = (
                    f"Mesurer la part des observations dans chaque catégorie de « {dimension} »."
                )
                raison = (
                    f"« {dimension} » comporte {uniques} catégorie(s). "
                    + (
                        "Le graphique circulaire permet de lire les parts lorsque leur nombre reste limité."
                        if type_widget == "CAMEMBERT"
                        else "Les barres restent plus lisibles qu’un cercle avec plusieurs catégories."
                    )
                )
                alternatives = [
                    {
                        "libelle": "Diagramme en anneau",
                        "raison": "Variante visuelle du graphique circulaire.",
                    },
                    {
                        "libelle": "Tableau simple",
                        "raison": "À utiliser pour afficher les effectifs exacts.",
                    },
                ]
                if type_widget == "CAMEMBERT":
                    alternatives.append({
                        "libelle": "Graphique en barres",
                        "raison": "Plus précis pour comparer des parts proches.",
                    })

                self.ajouter(
                    {
                        "titre": titre,
                        "type_widget": type_widget,
                        "colonne_categorie": dimension,
                        "colonne_mesure": "",
                        "colonne_serie": "",
                        "agregation": "NOMBRE",
                        "ordre_tri": "DECROISSANT",
                        "limite_resultats": min(20, max(6, uniques)),
                        "nombre_classes": 10,
                        "inclure_manquantes": False,
                    },
                    categorie="REPARTITIONS",
                    score=score,
                    objectif=objectif,
                    raison=raison,
                    alternatives=alternatives,
                    filtres_recommandes=self.filtres_pour([dimension]),
                    representation=representation,
                    agregation_affichee="Nombre d’observations et part en pourcentage",
                )

            elif nature == "DISTRIBUTION_NUMERIQUE":
                titre = f"Distribution de {self.titre_colonne(dimension)}"
                objectif = (
                    f"Observer la dispersion et la concentration des valeurs de « {dimension} »."
                )
                raison = (
                    f"« {dimension} » est numérique. L’histogramme regroupe ses valeurs "
                    "en classes afin de révéler la forme de la distribution."
                )
                self.ajouter(
                    {
                        "titre": titre,
                        "type_widget": "HISTOGRAMME",
                        "colonne_categorie": dimension,
                        "colonne_mesure": "",
                        "colonne_serie": "",
                        "agregation": "NOMBRE",
                        "ordre_tri": "CROISSANT",
                        "limite_resultats": 20,
                        "nombre_classes": 10,
                        "inclure_manquantes": False,
                    },
                    categorie="REPARTITIONS",
                    score=score,
                    objectif=objectif,
                    raison=raison,
                    alternatives=[
                        {
                            "libelle": "Tableau statistique",
                            "raison": "Complète l’histogramme avec minimum, maximum, moyenne et médiane.",
                        }
                    ],
                    filtres_recommandes=self.filtres_pour([dimension]),
                    representation="Histogramme",
                )

            elif nature == "CORRELATION":
                coefficient = relation.get("coefficient")
                titre = (
                    f"Relation entre {self.titre_colonne(dimension)} "
                    f"et {self.titre_colonne(mesure)}"
                )
                objectif = (
                    f"Examiner l’association entre « {dimension} » et « {mesure} »."
                )
                raison = (
                    f"Les deux colonnes sont numériques et leur corrélation simple calculée "
                    f"par Pandas vaut {coefficient}. Le nuage de points montre la relation "
                    "sans supposer de causalité."
                )
                self.ajouter(
                    {
                        "titre": titre,
                        "type_widget": "NUAGE_POINTS",
                        "colonne_categorie": dimension,
                        "colonne_mesure": mesure,
                        "colonne_serie": "",
                        "agregation": "NOMBRE",
                        "ordre_tri": "CROISSANT",
                        "limite_resultats": 500,
                        "nombre_classes": 10,
                        "inclure_manquantes": False,
                    },
                    categorie="RELATIONS_VARIABLES",
                    score=score,
                    objectif=objectif,
                    raison=raison,
                    alternatives=[
                        {
                            "libelle": "Tableau des deux variables",
                            "raison": "Permet de vérifier les valeurs exactes avant interprétation.",
                        }
                    ],
                    filtres_recommandes=self.filtres_pour([dimension, mesure]),
                    representation="Nuage de points",
                )

    def generer_visualisations_avancees(self):
        dimensions = list(self.schema.get("dimensions", []) or [])
        mesures = list(self.schema.get("mesures", []) or [])
        temporelles = set(self.schema.get("temporelles", []) or [])

        # Alternatives temporelles en aires.
        for relation in self.relations[:20]:
            if relation.get("nature") != "EVOLUTION_TEMPORELLE":
                continue
            dimension = relation.get("dimension", "")
            mesure = relation.get("mesure", "")
            if not dimension or not mesure:
                continue
            self.ajouter(
                {
                    "titre": f"Aire de {self.titre_colonne(mesure)}",
                    "type_widget": "AIRES",
                    "colonne_categorie": dimension,
                    "colonne_mesure": mesure,
                    "colonne_serie": relation.get("serie", ""),
                    "agregation": relation.get("agregation", "SOMME"),
                    "ordre_tri": "CROISSANT", "limite_resultats": 100,
                    "nombre_classes": 10, "inclure_manquantes": False,
                },
                categorie="EVOLUTIONS_TEMPORELLES", score=76,
                objectif="Observer l’évolution et le volume dans le temps.",
                raison="Le graphique en aires complète la courbe lorsque le volume global est utile.",
                alternatives=[{"libelle":"Graphique en courbes","raison":"Plus précis pour lire les variations."}],
                filtres_recommandes=self.filtres_pour([dimension, mesure]),
            )

        categories = [
            c for c in dimensions
            if self.profils.get(c, {}).get("type") == "CATEGORIELLE"
        ]
        for dimension in categories[:8]:
            uniques = int(self.profils.get(dimension, {}).get("nombre_uniques", 0) or 0)
            if 2 <= uniques <= 8:
                self.ajouter(
                    {
                        "titre": f"Répartition en anneau de {self.titre_colonne(dimension)}",
                        "type_widget": "ANNEAU", "colonne_categorie": dimension,
                        "colonne_mesure": "", "colonne_serie": "", "agregation": "NOMBRE",
                        "ordre_tri": "DECROISSANT", "limite_resultats": uniques,
                        "nombre_classes": 10, "inclure_manquantes": False,
                    },
                    categorie="REPARTITIONS", score=74,
                    objectif="Comparer les parts relatives d’un petit nombre de catégories.",
                    raison="Un anneau reste lisible lorsque la variable contient au maximum huit catégories.",
                    alternatives=[{"libelle":"Graphique en barres","raison":"Plus précis lorsque les parts sont proches."}],
                    filtres_recommandes=self.filtres_pour([dimension]),
                )

            mesure = mesures[0] if mesures else ""
            self.ajouter(
                {
                    "titre": f"Classement par {self.titre_colonne(dimension)}",
                    "type_widget": "BARRES_HORIZONTALES" if uniques > 8 else "CLASSEMENT",
                    "colonne_categorie": dimension, "colonne_mesure": mesure,
                    "colonne_serie": "", "agregation": "SOMME" if mesure else "NOMBRE",
                    "ordre_tri": "DECROISSANT", "limite_resultats": min(15, max(5, uniques)),
                    "nombre_classes": 10, "inclure_manquantes": False,
                },
                categorie="COMPARAISONS", score=80,
                objectif="Identifier rapidement les catégories les plus importantes.",
                raison="Un classement trié ou des barres horizontales conviennent aux libellés longs.",
                alternatives=[{"libelle":"Graphique en barres","raison":"Alternative compacte pour peu de catégories."}],
                filtres_recommandes=self.filtres_pour([dimension, mesure]),
            )

        for mesure in mesures[:6]:
            self.ajouter(
                {
                    "titre": f"Statistiques de {self.titre_colonne(mesure)}",
                    "type_widget": "STATISTIQUES_DESCRIPTIVES",
                    "colonne_categorie": mesure, "colonne_mesure": "", "colonne_serie": "",
                    "agregation": "NOMBRE", "ordre_tri": "CROISSANT", "limite_resultats": 20,
                    "nombre_classes": 10, "inclure_manquantes": False,
                },
                categorie="TABLEAUX_DETAILLES", score=78,
                objectif="Consulter le minimum, le maximum, la moyenne, la médiane, l’écart-type et les quartiles.",
                raison=f"« {mesure} » est numérique ; un résumé descriptif complète les graphiques.",
                alternatives=[{"libelle":"Histogramme","raison":"Montre la forme de la distribution."}],
                filtres_recommandes=self.filtres_pour([mesure]),
            )

        if len(categories) >= 2:
            ligne, colonne = categories[:2]
            self.ajouter(
                {
                    "titre": f"Tableau croisé {self.titre_colonne(ligne)} × {self.titre_colonne(colonne)}",
                    "type_widget": "TABLEAU_CROISE", "colonne_categorie": ligne,
                    "colonne_mesure": "", "colonne_serie": colonne, "agregation": "NOMBRE",
                    "ordre_tri": "DECROISSANT", "limite_resultats": 30,
                    "nombre_classes": 10, "inclure_manquantes": False,
                },
                categorie="TABLEAUX_DETAILLES", score=82,
                objectif="Croiser deux dimensions et comparer leurs effectifs.",
                raison="Un tableau croisé permet une lecture simultanée de deux variables catégorielles.",
                alternatives=[{"libelle":"Barres avec séries","raison":"Plus visuel lorsque les catégories sont peu nombreuses."}],
                filtres_recommandes=self.filtres_pour([ligne, colonne]),
            )

    def generer_tableaux(self):
        dimensions = list(self.schema.get("dimensions", []) or [])
        mesures = list(self.schema.get("mesures", []) or [])

        if not dimensions and not mesures:
            return

        dimension = dimensions[0] if dimensions else ""
        mesure = mesures[0] if mesures else ""
        colonnes = [colonne for colonne in (dimension, mesure) if colonne]

        self.ajouter(
            {
                "titre": "Aperçu détaillé des données",
                "type_widget": "TABLEAU",
                "colonne_categorie": dimension,
                "colonne_mesure": mesure,
                "colonne_serie": "",
                "agregation": "NOMBRE",
                "ordre_tri": "DECROISSANT",
                "limite_resultats": 50,
                "nombre_classes": 10,
                "inclure_manquantes": False,
            },
            categorie="TABLEAUX_DETAILLES",
            score=76,
            objectif="Consulter les valeurs exactes utilisées par les visualisations.",
            raison=(
                "Un tableau simple complète les graphiques avec une vue détaillée, "
                "vérifiable et exportable des colonnes sélectionnées."
            ),
            alternatives=[
                {
                    "libelle": "Tableau croisé dynamique",
                    "raison": "Non disponible actuellement dans le moteur de widgets.",
                }
            ],
            filtres_recommandes=self.filtres_pour(colonnes),
            representation="Tableau simple",
        )

    def marquer_selection_equilibree(self, maximum=6):
        priorites = [
            "INDICATEURS_CLES",
            "EVOLUTIONS_TEMPORELLES",
            "COMPARAISONS",
            "REPARTITIONS",
            "RELATIONS_VARIABLES",
            "TABLEAUX_DETAILLES",
        ]

        par_categorie = defaultdict(list)
        for index, (configuration, _) in enumerate(self.configurations):
            par_categorie[configuration["categorie"]].append((index, configuration))

        selection = []
        signatures = set()

        for categorie in priorites:
            candidats = sorted(
                par_categorie.get(categorie, []),
                key=lambda element: element[1].get("score", 0),
                reverse=True,
            )
            for index, configuration in candidats:
                signature = (
                    configuration.get("colonne_categorie"),
                    configuration.get("colonne_mesure"),
                )
                if signature in signatures and categorie not in {
                    "INDICATEURS_CLES",
                    "TABLEAUX_DETAILLES",
                }:
                    continue
                selection.append(index)
                signatures.add(signature)
                break
            if len(selection) >= maximum:
                break

        if len(selection) < maximum:
            restants = sorted(
                [
                    (index, configuration)
                    for index, (configuration, _) in enumerate(self.configurations)
                    if index not in selection
                ],
                key=lambda element: element[1].get("score", 0),
                reverse=True,
            )
            for index, configuration in restants:
                if configuration.get("pertinence") == "OPTIONNEL":
                    continue
                selection.append(index)
                if len(selection) >= maximum:
                    break

        for rang, index in enumerate(selection, start=1):
            self.configurations[index][0]["selection_equilibree"] = True
            self.configurations[index][0]["selection_rang"] = rang

    def construire(self):
        self.generer_indicateurs()
        self.generer_relations()
        self.generer_visualisations_avancees()
        self.generer_tableaux()
        self.marquer_selection_equilibree()

        return sorted(
            self.configurations,
            key=lambda element: (
                element[0].get("selection_rang", 999) or 999,
                -element[0].get("score", 0),
                element[0].get("titre", ""),
            ),
        )


def generer_configurations(analyse, limite=80):
    return CatalogueSuggestions(
        analyse,
        limite=limite,
    ).construire()


def enregistrer_suggestions_automatiques(
    tableau_bord,
    analyse,
    remplacer=True,
):
    if remplacer:
        SuggestionWidget.objects.filter(
            tableau_bord=tableau_bord,
            source=SuggestionWidget.Source.AUTOMATIQUE,
            statut=SuggestionWidget.Statut.PROPOSEE,
        ).update(
            statut=SuggestionWidget.Statut.SUPPRIMEE
        )

    objets = []
    for configuration, justification in generer_configurations(analyse):
        objets.append(
            SuggestionWidget.objects.create(
                tableau_bord=tableau_bord,
                analyse=analyse,
                source=SuggestionWidget.Source.AUTOMATIQUE,
                configuration=configuration,
                justification=justification,
            )
        )
    return objets
