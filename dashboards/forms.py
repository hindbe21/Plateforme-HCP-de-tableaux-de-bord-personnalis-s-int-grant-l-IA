from __future__ import annotations

from typing import Any

import pandas as pd
from django import forms

from datasets.models import JeuDonnees
from datasets.services import charger_dataframe_postgresql

from .models import (
    Filtre,
    FiltreWidget,
    TableauBord,
    Widget,
)


AGREGATIONS = (
    ("NOMBRE", "Nombre d’observations"),
    (
        "NOMBRE_DISTINCT",
        "Nombre de valeurs distinctes",
    ),
    ("SOMME", "Somme"),
    ("MOYENNE", "Moyenne"),
    ("MEDIANE", "Médiane"),
    ("MINIMUM", "Minimum"),
    ("MAXIMUM", "Maximum"),
)

ORDRES_TRI = (
    ("NATUREL", "Ordre naturel"),
    ("CROISSANT", "Croissant"),
    ("DECROISSANT", "Décroissant"),
)


def est_administrateur(utilisateur):
    return bool(
        utilisateur.is_superuser
        or utilisateur.is_staff
        or getattr(
            utilisateur,
            "est_administrateur",
            False,
        )
        or getattr(
            utilisateur,
            "role",
            "",
        )
        == "ADMIN"
    )


def nom_champ_proprietaire(modele):
    champs = {
        champ.name
        for champ in modele._meta.get_fields()
    }

    for nom in (
        "proprietaire",
        "utilisateur_metier",
        "utilisateur",
        "createur",
    ):
        if nom in champs:
            return nom

    return None


def normaliser_serie(serie):
    return serie.apply(
        lambda valeur: (
            pd.NA
            if isinstance(
                valeur,
                str,
            )
            and not valeur.strip()
            else valeur
        )
    )


def construire_profils_colonnes(
    jeu_donnees,
) -> dict[str, dict[str, Any]]:
    dataframe = charger_dataframe_postgresql(
        jeu_donnees
    )

    profils = {}

    for colonne in dataframe.columns:
        nom = str(colonne)

        serie = normaliser_serie(
            dataframe[colonne]
        )

        valeurs = serie.dropna()

        numerique = pd.to_numeric(
            valeurs,
            errors="coerce",
        )

        ratio_numerique = (
            float(
                numerique.notna().mean()
            )
            if not valeurs.empty
            else 0
        )

        dates = pd.to_datetime(
            valeurs,
            errors="coerce",
            dayfirst=True,
        )

        ratio_date = (
            float(
                dates.notna().mean()
            )
            if not valeurs.empty
            else 0
        )

        if ratio_numerique >= 0.90:
            type_colonne = "NUMÉRIQUE"

        elif ratio_date >= 0.90:
            type_colonne = "DATE"

        else:
            type_colonne = "TEXTE"

        exemples = []

        for valeur in (
            valeurs
            .astype(str)
            .drop_duplicates()
            .head(3)
        ):
            texte = valeur.strip()

            if len(texte) > 30:
                texte = (
                    texte[:27]
                    + "..."
                )

            exemples.append(
                texte
            )

        nombre_uniques = int(
            valeurs.nunique()
        )

        ratio_uniques = (
            nombre_uniques
            / len(valeurs)
            if len(valeurs)
            else 0
        )

        nom_normalise = (
            nom.lower()
            .replace(" ", "_")
            .replace("-", "_")
        )

        semble_identifiant = (
            nom_normalise
            in {
                "id",
                "identifiant",
                "code",
                "numero",
                "numéro",
                "cin",
                "cne",
            }
            or nom_normalise.startswith(
                (
                    "id_",
                    "code_",
                    "numero_",
                    "numéro_",
                )
            )
            or (
                ratio_uniques >= 0.95
                and type_colonne
                in {
                    "NUMÉRIQUE",
                    "TEXTE",
                }
            )
        )

        profils[nom] = {
            "nom": nom,
            "type": type_colonne,
            "exemples": exemples,
            "nombre_manquantes": int(
                serie.isna().sum()
            ),
            "nombre_uniques": (
                nombre_uniques
            ),
            "ratio_uniques": round(
                ratio_uniques,
                4,
            ),
            "semble_identifiant": (
                semble_identifiant
            ),
        }

    return profils


def libelle_colonne(profil):
    exemples = ", ".join(
        profil["exemples"]
    ) or "aucun exemple"

    return (
        f'{profil["nom"]} — '
        f'{profil["type"].lower()} — '
        f'Ex. : {exemples}'
    )


def choix_colonnes(
    profils,
    *,
    seulement_numeriques=False,
):
    choix = [
        (
            "",
            "Sélectionner une colonne",
        )
    ]

    for nom, profil in profils.items():
        if (
            seulement_numeriques
            and profil["type"]
            != "NUMÉRIQUE"
        ):
            continue

        choix.append(
            (
                nom,
                libelle_colonne(
                    profil
                ),
            )
        )

    return choix


class TableauBordForm(forms.ModelForm):
    class Meta:
        model = TableauBord

        fields = (
            "titre",
            "description",
            "jeu_donnees",
        )

        widgets = {
            "titre": forms.TextInput(
                attrs={
                    "class":
                    "form-control",

                    "placeholder": (
                        "Exemple : Analyse "
                        "démographique 2026"
                    ),
                }
            ),

            "description":
            forms.Textarea(
                attrs={
                    "class":
                    "form-control",

                    "rows": 3,
                }
            ),

            "jeu_donnees":
            forms.Select(
                attrs={
                    "class":
                    "form-select",
                }
            ),
        }

    def __init__(
        self,
        *args,
        utilisateur,
        **kwargs,
    ):
        super().__init__(
            *args,
            **kwargs,
        )

        queryset = (
            JeuDonnees.objects.all()
        )

        champ_proprietaire = (
            nom_champ_proprietaire(
                JeuDonnees
            )
        )

        if (
            champ_proprietaire
            and not est_administrateur(
                utilisateur
            )
        ):
            queryset = queryset.filter(
                **{
                    champ_proprietaire:
                    utilisateur
                }
            )

        noms_champs = {
            champ.name
            for champ
            in JeuDonnees._meta.get_fields()
        }

        if "type_version" in noms_champs:
            nettoyes = queryset.filter(
                type_version="NETTOYEE"
            )

            if nettoyes.exists():
                queryset = nettoyes

        ordre = (
            "-date_importation"
            if "date_importation"
            in noms_champs
            else "-pk"
        )

        self.fields[
            "jeu_donnees"
        ].queryset = queryset.order_by(
            ordre
        )


class WidgetForm(forms.ModelForm):
    colonne_categorie = (
        forms.ChoiceField(
            label="Dimension / axe X",
            required=False,
            choices=(),
            widget=forms.Select(
                attrs={
                    "class":
                    "form-select",
                }
            ),
        )
    )

    colonne_serie = (
        forms.ChoiceField(
            label="Série / légende",
            required=False,
            choices=(),
            widget=forms.Select(
                attrs={
                    "class":
                    "form-select",
                }
            ),
        )
    )

    colonne_mesure = (
        forms.ChoiceField(
            label="Variable à agréger / axe Y",
            required=False,
            choices=(),
            widget=forms.Select(
                attrs={
                    "class":
                    "form-select",
                }
            ),
        )
    )

    agregation = forms.ChoiceField(
        label="Fonction d’agrégation",
        choices=AGREGATIONS,
        initial="NOMBRE",
        widget=forms.Select(
            attrs={
                "class":
                "form-select",
            }
        ),
    )

    ordre_tri = forms.ChoiceField(
        label="Ordre de tri",
        choices=ORDRES_TRI,
        initial="DECROISSANT",
        widget=forms.Select(
            attrs={
                "class":
                "form-select",
            }
        ),
    )

    nombre_classes = (
        forms.IntegerField(
            label="Nombre de classes",
            min_value=3,
            max_value=50,
            initial=10,
            required=False,
            widget=forms.NumberInput(
                attrs={
                    "class":
                    "form-control",
                }
            ),
        )
    )

    inclure_manquantes = (
        forms.BooleanField(
            label=(
                "Inclure les valeurs "
                "manquantes"
            ),
            required=False,
            widget=forms.CheckboxInput(
                attrs={
                    "class":
                    "form-check-input",
                }
            ),
        )
    )

    class Meta:
        model = Widget

        fields = (
            "titre",
            "type_widget",
            "colonne_categorie",
            "limite_resultats",
        )

        labels = {
            "titre":
            "Titre du widget",

            "type_widget":
            "Type de visualisation",

            "limite_resultats":
            "Nombre maximal de résultats",
        }

        widgets = {
            "titre":
            forms.TextInput(
                attrs={
                    "class":
                    "form-control",

                    "placeholder": (
                        "Exemple : "
                        "Population par région"
                    ),
                }
            ),

            "type_widget":
            forms.Select(
                attrs={
                    "class":
                    "form-select",
                }
            ),

            "limite_resultats":
            forms.NumberInput(
                attrs={
                    "class":
                    "form-control",

                    "min": 1,
                    "max": 500,
                }
            ),
        }

    def __init__(
        self,
        *args,
        tableau_bord,
        **kwargs,
    ):
        super().__init__(
            *args,
            **kwargs,
        )

        self.tableau_bord = (
            tableau_bord
        )

        # Associe immédiatement l’instance au tableau
        # de bord, notamment lors d’une création
        # effectuée par l’assistant.
        self.instance.tableau_bord = (
            tableau_bord
        )

        self.profils_colonnes = (
            construire_profils_colonnes(
                tableau_bord.jeu_donnees
            )
        )

        self.fields[
            "colonne_categorie"
        ].choices = choix_colonnes(
            self.profils_colonnes
        )

        # Toutes les colonnes sont proposées ici.
        # La validation et le JavaScript adaptent ensuite
        # les choix selon l’agrégation.
        self.fields[
            "colonne_mesure"
        ].choices = choix_colonnes(
            self.profils_colonnes
        )

        self.fields[
            "colonne_serie"
        ].choices = choix_colonnes(
            self.profils_colonnes
        )

        configuration = {}

        if (
            self.instance
            and self.instance.pk
        ):
            configuration = (
                self.instance.configuration
                or {}
            )

        self.fields[
            "colonne_mesure"
        ].initial = configuration.get(
            "colonne_mesure",
            "",
        )

        self.fields[
            "colonne_serie"
        ].initial = configuration.get(
            "colonne_serie",
            "",
        )

        self.fields[
            "agregation"
        ].initial = configuration.get(
            "agregation",
            "NOMBRE",
        )

        self.fields[
            "ordre_tri"
        ].initial = configuration.get(
            "ordre_tri",
            "DECROISSANT",
        )

        self.fields[
            "nombre_classes"
        ].initial = configuration.get(
            "nombre_classes",
            10,
        )

        self.fields[
            "inclure_manquantes"
        ].initial = configuration.get(
            "inclure_manquantes",
            False,
        )

    def clean(self):
        cleaned_data = (
            super().clean()
        )

        type_widget = cleaned_data.get(
            "type_widget"
        )

        dimension = cleaned_data.get(
            "colonne_categorie"
        )

        mesure = cleaned_data.get(
            "colonne_mesure"
        )

        serie = cleaned_data.get(
            "colonne_serie"
        )

        agregation = cleaned_data.get(
            "agregation"
        )

        graphiques_groupes = {
            "BARRES",
            "BARRES_HORIZONTALES",
            "CLASSEMENT",
            "CAMEMBERT",
            "ANNEAU",
            "COURBE",
            "AIRES",
        }

        agregations_numeriques = {
            "SOMME",
            "MOYENNE",
            "MEDIANE",
            "MINIMUM",
            "MAXIMUM",
        }

        if serie:
            if type_widget not in {
                "BARRES",
                "BARRES_HORIZONTALES",
                "COURBE",
                "AIRES",
                "TABLEAU_CROISE",
            }:
                self.add_error(
                    "colonne_serie",
                    (
                        "Une série est disponible "
                        "uniquement pour les barres, "
                        "les courbes, les aires et "
                        "les tableaux croisés."
                    ),
                )

            if serie == dimension:
                self.add_error(
                    "colonne_serie",
                    (
                        "La série doit être différente "
                        "de la dimension de l’axe X."
                    ),
                )

            if serie == mesure:
                self.add_error(
                    "colonne_serie",
                    (
                        "La série doit être différente "
                        "de la mesure de l’axe Y."
                    ),
                )

        if (
            type_widget
            in graphiques_groupes
            and not dimension
        ):
            self.add_error(
                "colonne_categorie",
                (
                    "Sélectionnez la "
                    "dimension utilisée "
                    "sur l’axe X."
                ),
            )

        if (
            type_widget
            in graphiques_groupes
            and agregation
            == "NOMBRE_DISTINCT"
            and not mesure
        ):
            self.add_error(
                "colonne_mesure",
                (
                    "Sélectionnez la variable "
                    "dont les valeurs distinctes "
                    "doivent être comptées."
                ),
            )

        if (
            type_widget
            in graphiques_groupes
            and agregation
            in agregations_numeriques
            and not mesure
        ):
            self.add_error(
                "colonne_mesure",
                (
                    "Cette agrégation nécessite "
                    "une variable numérique."
                ),
            )

        if (
            type_widget
            == "INDICATEUR"
            and agregation
            == "NOMBRE_DISTINCT"
            and not mesure
        ):
            self.add_error(
                "colonne_mesure",
                (
                    "Sélectionnez la variable "
                    "dont les valeurs distinctes "
                    "doivent être comptées."
                ),
            )

        if (
            type_widget
            == "INDICATEUR"
            and agregation
            in agregations_numeriques
            and not mesure
        ):
            self.add_error(
                "colonne_mesure",
                (
                    "Sélectionnez la mesure "
                    "de l’indicateur."
                ),
            )

        if (
            mesure
            and agregation
            in agregations_numeriques
        ):
            type_mesure = (
                self.profils_colonnes
                .get(
                    mesure,
                    {},
                )
                .get("type")
            )

            if (
                type_mesure
                != "NUMÉRIQUE"
            ):
                self.add_error(
                    "colonne_mesure",
                    (
                        "Somme, moyenne, médiane, "
                        "minimum et maximum "
                        "nécessitent une colonne "
                        "numérique."
                    ),
                )

        if type_widget == "TABLEAU_CROISE":
            if not dimension or not serie:
                raise forms.ValidationError(
                    "Un tableau croisé nécessite une dimension en lignes et une série en colonnes."
                )
            if dimension == serie:
                self.add_error(
                    "colonne_serie",
                    "La série doit être différente de la dimension.",
                )
            if agregation in agregations_numeriques and not mesure:
                self.add_error(
                    "colonne_mesure",
                    "Cette agrégation nécessite une mesure numérique.",
                )

        if type_widget == "STATISTIQUES_DESCRIPTIVES":
            colonne_statistique = mesure or dimension
            if not colonne_statistique:
                raise forms.ValidationError(
                    "Sélectionnez une colonne numérique à décrire."
                )
            if self.profils_colonnes.get(colonne_statistique, {}).get("type") != "NUMÉRIQUE":
                raise forms.ValidationError(
                    "Les statistiques descriptives nécessitent une colonne numérique."
                )

        if (
            type_widget
            == "HISTOGRAMME"
        ):
            if not dimension:
                self.add_error(
                    "colonne_categorie",
                    (
                        "Sélectionnez la "
                        "variable numérique "
                        "à analyser."
                    ),
                )

            elif (
                self.profils_colonnes
                .get(
                    dimension,
                    {},
                )
                .get("type")
                != "NUMÉRIQUE"
            ):
                self.add_error(
                    "colonne_categorie",
                    (
                        "Un histogramme "
                        "nécessite une "
                        "variable numérique."
                    ),
                )

        if (
            type_widget
            == "NUAGE_POINTS"
        ):
            if (
                not dimension
                or not mesure
            ):
                raise forms.ValidationError(
                    (
                        "Un nuage de points "
                        "nécessite deux "
                        "variables numériques."
                    )
                )

            if dimension == mesure:
                raise forms.ValidationError(
                    (
                        "Les axes X et Y "
                        "doivent utiliser "
                        "deux colonnes "
                        "différentes."
                    )
                )

            for champ, colonne in (
                (
                    "colonne_categorie",
                    dimension,
                ),
                (
                    "colonne_mesure",
                    mesure,
                ),
            ):
                type_colonne = (
                    self.profils_colonnes
                    .get(
                        colonne,
                        {},
                    )
                    .get("type")
                )

                if (
                    type_colonne
                    != "NUMÉRIQUE"
                ):
                    self.add_error(
                        champ,
                        (
                            "Sélectionnez une "
                            "colonne numérique."
                        ),
                    )

        if (
            type_widget
            == "TABLEAU"
            and not dimension
            and not mesure
        ):
            raise forms.ValidationError(
                (
                    "Sélectionnez au moins "
                    "une colonne à afficher."
                )
            )

        return cleaned_data

    def save(
        self,
        commit=True,
    ):
        widget = super().save(
            commit=False
        )

        widget.configuration = {
            "colonne_mesure":
            self.cleaned_data.get(
                "colonne_mesure",
                "",
            ),

            "colonne_serie":
            self.cleaned_data.get(
                "colonne_serie",
                "",
            ),

            "agregation":
            self.cleaned_data.get(
                "agregation",
                "NOMBRE",
            ),

            "ordre_tri":
            self.cleaned_data.get(
                "ordre_tri",
                "DECROISSANT",
            ),

            "nombre_classes":
            self.cleaned_data.get(
                "nombre_classes"
            )
            or 10,

            "inclure_manquantes":
            bool(
                self.cleaned_data.get(
                    "inclure_manquantes"
                )
            ),
        }

        if commit:
            widget.save()

        return widget


class BaseFiltreForm:
    def initialiser_colonnes(
        self,
        source_donnees,
    ):
        self.profils_colonnes = (
            construire_profils_colonnes(
                source_donnees
            )
        )

        self.fields[
            "colonne"
        ].choices = [
            (
                nom,
                libelle_colonne(
                    profil
                ),
            )
            for nom, profil
            in self.profils_colonnes.items()
        ]

    def valider_filtre(self):
        cleaned_data = (
            super().clean()
        )

        operateur = cleaned_data.get(
            "operateur"
        )

        valeur = str(
            cleaned_data.get(
                "valeur"
            )
            or ""
        ).strip()

        if (
            operateur
            not in {
                "VIDE",
                "NON_VIDE",
            }
            and not valeur
        ):
            self.add_error(
                "valeur",
                (
                    "Saisissez la "
                    "valeur du filtre."
                ),
            )

        if operateur == "ENTRE":
            morceaux = [
                element.strip()
                for element
                in valeur.split(";")
                if element.strip()
            ]

            if len(morceaux) != 2:
                self.add_error(
                    "valeur",
                    (
                        "Utilisez le format : "
                        "minimum ; maximum."
                    ),
                )

        return cleaned_data


class FiltreForm(
    BaseFiltreForm,
    forms.ModelForm,
):
    colonne = forms.ChoiceField(
        label="Colonne à filtrer",
        choices=(),
        widget=forms.Select(
            attrs={
                "class":
                "form-select",
            }
        ),
    )

    class Meta:
        model = Filtre

        fields = (
            "colonne",
            "operateur",
            "valeur",
        )

        widgets = {
            "operateur":
            forms.Select(
                attrs={
                    "class":
                    "form-select",
                }
            ),

            "valeur":
            forms.TextInput(
                attrs={
                    "class":
                    "form-control",

                    "placeholder": (
                        "Pour Entre : "
                        "minimum ; maximum"
                    ),
                }
            ),
        }

    def __init__(
        self,
        *args,
        tableau_bord,
        **kwargs,
    ):
        super().__init__(
            *args,
            **kwargs,
        )

        self.initialiser_colonnes(
            tableau_bord.jeu_donnees
        )

    def clean(self):
        return self.valider_filtre()


class FiltreWidgetForm(
    BaseFiltreForm,
    forms.ModelForm,
):
    colonne = forms.ChoiceField(
        label="Colonne à filtrer",
        choices=(),
        widget=forms.Select(
            attrs={
                "class":
                "form-select",
            }
        ),
    )

    class Meta:
        model = FiltreWidget

        fields = (
            "colonne",
            "operateur",
            "valeur",
        )

        widgets = {
            "operateur":
            forms.Select(
                attrs={
                    "class":
                    "form-select",
                }
            ),

            "valeur":
            forms.TextInput(
                attrs={
                    "class":
                    "form-control",

                    "placeholder": (
                        "Pour Entre : "
                        "minimum ; maximum"
                    ),
                }
            ),
        }

    def __init__(
        self,
        *args,
        widget,
        **kwargs,
    ):
        super().__init__(
            *args,
            **kwargs,
        )

        self.initialiser_colonnes(
            widget.tableau_bord.jeu_donnees
        )

    def clean(self):
        return self.valider_filtre()
