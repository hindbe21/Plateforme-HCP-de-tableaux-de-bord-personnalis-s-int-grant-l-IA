from django import forms

from dashboards.models import Widget

from .services.widget_validation import (
    ConfigurationWidgetInvalide,
    valider_configuration,
)


AGREGATIONS = (
    ("NOMBRE", "Nombre d’observations"),
    ("NOMBRE_DISTINCT", "Nombre de valeurs distinctes"),
    ("SOMME", "Somme"),
    ("MOYENNE", "Moyenne"),
    ("MEDIANE", "Médiane"),
    ("MINIMUM", "Minimum"),
    ("MAXIMUM", "Maximum"),
)

ORDRES = (
    ("CROISSANT", "Croissant"),
    ("DECROISSANT", "Décroissant"),
)


class MessageAssistantForm(forms.Form):
    message = forms.CharField(
        label="Votre demande",
        max_length=1500,
        widget=forms.Textarea(attrs={
            "class": "form-control",
            "rows": 3,
            "placeholder": (
                "Exemple : Montre-moi l’évolution des ventes "
                "par année et propose le graphique le plus pertinent."
            ),
        }),
    )


class SuggestionWidgetForm(forms.Form):
    PERTINENCES = (
        ("FORTEMENT_RECOMMANDE", "Fortement recommandé"),
        ("RECOMMANDE", "Recommandé"),
        ("OPTIONNEL", "Optionnel"),
    )

    OPERATEURS = (
        ("", "Aucun opérateur"),
        ("EGAL", "Égal à"),
        ("DIFFERENT", "Différent de"),
        ("CONTIENT", "Contient"),
        ("NE_CONTIENT_PAS", "Ne contient pas"),
        ("SUPERIEUR", "Supérieur à"),
        ("SUPERIEUR_EGAL", "Supérieur ou égal à"),
        ("INFERIEUR", "Inférieur à"),
        ("INFERIEUR_EGAL", "Inférieur ou égal à"),
        ("ENTRE", "Entre deux valeurs"),
        ("VIDE", "Valeur manquante"),
        ("NON_VIDE", "Valeur renseignée"),
    )

    titre = forms.CharField(
        label="Titre",
        max_length=200,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    objectif = forms.CharField(
        label="Objectif du widget",
        required=False,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 3}),
    )
    pertinence = forms.ChoiceField(
        label="Niveau de pertinence",
        choices=PERTINENCES,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    type_widget = forms.ChoiceField(
        label="Type de visualisation",
        choices=Widget.TYPE_WIDGET_CHOICES,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    colonne_categorie = forms.ChoiceField(
        label="Dimension / axe X",
        required=False,
        choices=(),
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    colonne_mesure = forms.ChoiceField(
        label="Mesure / axe Y",
        required=False,
        choices=(),
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    colonne_serie = forms.ChoiceField(
        label="Série / légende",
        required=False,
        choices=(),
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    agregation = forms.ChoiceField(
        label="Agrégation",
        choices=AGREGATIONS,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    ordre_tri = forms.ChoiceField(
        label="Ordre de tri",
        choices=ORDRES,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    limite_resultats = forms.IntegerField(
        label="Nombre maximal de résultats",
        min_value=1,
        max_value=500,
        widget=forms.NumberInput(attrs={"class": "form-control"}),
    )
    nombre_classes = forms.IntegerField(
        label="Nombre de classes de l’histogramme",
        min_value=3,
        max_value=50,
        required=False,
        widget=forms.NumberInput(attrs={"class": "form-control"}),
    )
    inclure_manquantes = forms.BooleanField(
        label="Inclure les valeurs manquantes",
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )
    justification = forms.CharField(
        label="Justification",
        required=False,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 4}),
    )

    for numero in range(1, 4):
        locals()[f"filtre_{numero}_colonne"] = forms.ChoiceField(
            label=f"Filtre {numero} — colonne",
            required=False,
            choices=(),
            widget=forms.Select(attrs={"class": "form-select"}),
        )
        locals()[f"filtre_{numero}_operateur"] = forms.ChoiceField(
            label=f"Filtre {numero} — opérateur",
            required=False,
            choices=OPERATEURS,
            widget=forms.Select(attrs={"class": "form-select"}),
        )
        locals()[f"filtre_{numero}_valeur"] = forms.CharField(
            label=f"Filtre {numero} — valeur",
            required=False,
            widget=forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Exemple : 2024 ou Rabat",
            }),
        )

    def __init__(self, *args, analyse, initial=None, **kwargs):
        self.analyse = analyse
        self.configuration_originale = dict(initial or {})
        super().__init__(*args, initial=initial, **kwargs)

        colonnes = list((analyse.schema or {}).get("profils", {}).keys())
        choix = [("", "Aucune")] + [(nom, nom) for nom in colonnes]
        self.fields["colonne_categorie"].choices = choix
        self.fields["colonne_mesure"].choices = choix
        self.fields["colonne_serie"].choices = choix

        for numero in range(1, 4):
            self.fields[f"filtre_{numero}_colonne"].choices = choix

        for numero, filtre in enumerate(
            list(self.configuration_originale.get("filtres", []) or [])[:3],
            start=1,
        ):
            self.fields[f"filtre_{numero}_colonne"].initial = filtre.get("colonne", "")
            self.fields[f"filtre_{numero}_operateur"].initial = filtre.get("operateur", "")
            self.fields[f"filtre_{numero}_valeur"].initial = filtre.get("valeur", "")

    def clean(self):
        donnees = super().clean()
        if self.errors:
            return donnees

        filtres = []
        for numero in range(1, 4):
            colonne = donnees.get(f"filtre_{numero}_colonne") or ""
            operateur = donnees.get(f"filtre_{numero}_operateur") or ""
            valeur = str(donnees.get(f"filtre_{numero}_valeur") or "").strip()

            if not colonne and not operateur and not valeur:
                continue
            if not colonne:
                self.add_error(
                    f"filtre_{numero}_colonne",
                    "Sélectionnez une colonne pour ce filtre.",
                )
                continue
            if not operateur:
                self.add_error(
                    f"filtre_{numero}_operateur",
                    "Sélectionnez un opérateur pour ce filtre.",
                )
                continue
            if operateur not in {"VIDE", "NON_VIDE"} and not valeur:
                self.add_error(
                    f"filtre_{numero}_valeur",
                    "Cette opération nécessite une valeur.",
                )
                continue

            filtres.append({
                "colonne": colonne,
                "operateur": operateur,
                "valeur": valeur,
            })

        if self.errors:
            return donnees

        configuration = dict(self.configuration_originale)
        configuration.update({
            "titre": donnees.get("titre"),
            "objectif": donnees.get("objectif"),
            "raison": (
                donnees.get("justification")
                or self.configuration_originale.get("raison", "")
            ),
            "pertinence": donnees.get("pertinence"),
            "type_widget": donnees.get("type_widget"),
            "colonne_categorie": donnees.get("colonne_categorie"),
            "colonne_mesure": donnees.get("colonne_mesure"),
            "colonne_serie": donnees.get("colonne_serie"),
            "agregation": donnees.get("agregation"),
            "ordre_tri": donnees.get("ordre_tri"),
            "limite_resultats": donnees.get("limite_resultats"),
            "nombre_classes": donnees.get("nombre_classes") or 10,
            "inclure_manquantes": donnees.get("inclure_manquantes", False),
            "filtres": filtres,
        })

        try:
            self.configuration_validee = valider_configuration(
                configuration,
                self.analyse,
            )
        except ConfigurationWidgetInvalide as erreur:
            raise forms.ValidationError(str(erreur)) from erreur
        return donnees

from copy import deepcopy


def lignes_vers_liste(valeur):
    return [
        ligne.strip()
        for ligne in str(valeur or "").splitlines()
        if ligne.strip()
    ]


class RapportEditionForm(forms.Form):
    resume_executif = forms.CharField(
        label="Résumé exécutif",
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 5}),
    )
    synthese_ia = forms.CharField(
        label="Synthèse complémentaire",
        required=False,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 4}),
    )
    constatations = forms.CharField(
        label="Principales constatations",
        required=False,
        help_text="Une constatation par ligne.",
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 7}),
    )
    comparaisons = forms.CharField(
        label="Comparaisons entre widgets",
        required=False,
        help_text="Une comparaison par ligne.",
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 5}),
    )
    recommandations = forms.CharField(
        label="Recommandations",
        required=False,
        help_text="Une recommandation par ligne.",
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 6}),
    )
    limites = forms.CharField(
        label="Limites de l’analyse",
        required=False,
        help_text="Une limite par ligne.",
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 6}),
    )
    conclusion = forms.CharField(
        label="Conclusion générale",
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 5}),
    )

    def __init__(self, *args, contenu, **kwargs):
        self.contenu_original = deepcopy(contenu or {})
        initial = {
            "resume_executif": self.contenu_original.get("resume_executif", ""),
            "synthese_ia": self.contenu_original.get("synthese_ia", ""),
            "constatations": "\n".join(self.contenu_original.get("constatations", []) or []),
            "comparaisons": "\n".join(self.contenu_original.get("comparaisons", []) or []),
            "recommandations": "\n".join(self.contenu_original.get("recommandations", []) or []),
            "limites": "\n".join(self.contenu_original.get("limites", []) or []),
            "conclusion": self.contenu_original.get("conclusion", ""),
        }
        super().__init__(*args, initial=initial, **kwargs)
        self.groupes_widgets = []

        for index, widget in enumerate(self.contenu_original.get("analyses_widgets", []) or []):
            interpretation = f"widget_{index}_interpretation"
            commentaire = f"widget_{index}_commentaire"
            prudence = f"widget_{index}_prudence"

            self.fields[interpretation] = forms.CharField(
                label="Interprétation",
                widget=forms.Textarea(attrs={"class": "form-control", "rows": 5}),
                initial=widget.get("interpretation", ""),
            )
            self.fields[commentaire] = forms.CharField(
                label="Commentaire complémentaire",
                required=False,
                widget=forms.Textarea(attrs={"class": "form-control", "rows": 4}),
                initial=widget.get("commentaire_ia", ""),
            )
            self.fields[prudence] = forms.CharField(
                label="Prudence",
                widget=forms.Textarea(attrs={"class": "form-control", "rows": 3}),
                initial=widget.get("prudence", ""),
            )
            self.groupes_widgets.append({
                "index": index,
                "titre": widget.get("titre", f"Widget {index + 1}"),
                "type_widget": widget.get("type_widget", ""),
                "interpretation_name": interpretation,
                "commentaire_name": commentaire,
                "prudence_name": prudence,
            })

    def groupes_widgets_lies(self):
        return [
            {
                **groupe,
                "interpretation": self[groupe["interpretation_name"]],
                "commentaire": self[groupe["commentaire_name"]],
                "prudence": self[groupe["prudence_name"]],
            }
            for groupe in self.groupes_widgets
        ]

    def construire_contenu(self):
        contenu = deepcopy(self.contenu_original)
        contenu["resume_executif"] = self.cleaned_data["resume_executif"].strip()
        contenu["synthese_ia"] = self.cleaned_data.get("synthese_ia", "").strip()
        contenu["constatations"] = lignes_vers_liste(self.cleaned_data.get("constatations"))
        contenu["comparaisons"] = lignes_vers_liste(self.cleaned_data.get("comparaisons"))
        contenu["recommandations"] = lignes_vers_liste(self.cleaned_data.get("recommandations"))
        contenu["limites"] = lignes_vers_liste(self.cleaned_data.get("limites"))
        contenu["conclusion"] = self.cleaned_data["conclusion"].strip()

        widgets = list(contenu.get("analyses_widgets", []) or [])
        for groupe in self.groupes_widgets:
            index = groupe["index"]
            if index >= len(widgets):
                continue
            widgets[index]["interpretation"] = self.cleaned_data[
                groupe["interpretation_name"]
            ].strip()
            widgets[index]["commentaire_ia"] = self.cleaned_data.get(
                groupe["commentaire_name"], ""
            ).strip()
            widgets[index]["prudence"] = self.cleaned_data[
                groupe["prudence_name"]
            ].strip()
        contenu["analyses_widgets"] = widgets
        return contenu


class RapportJeuDonneesEditionForm(forms.Form):
    resume_executif=forms.CharField(label="Résumé exécutif",widget=forms.Textarea(attrs={"class":"form-control","rows":5}))
    constatations=forms.CharField(label="Principales constatations",required=False,help_text="Une constatation par ligne.",widget=forms.Textarea(attrs={"class":"form-control","rows":7}))
    recommandations=forms.CharField(label="Recommandations",required=False,help_text="Une recommandation par ligne.",widget=forms.Textarea(attrs={"class":"form-control","rows":7}))
    limites=forms.CharField(label="Limites",required=False,help_text="Une limite par ligne.",widget=forms.Textarea(attrs={"class":"form-control","rows":6}))
    conclusion=forms.CharField(label="Conclusion",widget=forms.Textarea(attrs={"class":"form-control","rows":5}))
    def __init__(self,*args,contenu,**kwargs):
        self.contenu_original=deepcopy(contenu or {})
        initial={"resume_executif":self.contenu_original.get("resume_executif",""),"constatations":"\n".join(self.contenu_original.get("constatations",[]) or []),"recommandations":"\n".join(self.contenu_original.get("recommandations",[]) or []),"limites":"\n".join(self.contenu_original.get("limites",[]) or []),"conclusion":self.contenu_original.get("conclusion","")}
        super().__init__(*args,initial=initial,**kwargs)
    def construire_contenu(self):
        contenu=deepcopy(self.contenu_original)
        contenu["resume_executif"]=self.cleaned_data["resume_executif"].strip()
        contenu["constatations"]=lignes_vers_liste(self.cleaned_data.get("constatations"))
        contenu["recommandations"]=lignes_vers_liste(self.cleaned_data.get("recommandations"))
        contenu["limites"]=lignes_vers_liste(self.cleaned_data.get("limites"))
        contenu["conclusion"]=self.cleaned_data["conclusion"].strip()
        return contenu
