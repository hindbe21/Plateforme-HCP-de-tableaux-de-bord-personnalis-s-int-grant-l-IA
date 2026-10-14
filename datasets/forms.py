from pathlib import Path

from django import forms

from .models import JeuDonnees


TYPES_NUMERIQUES = {
    "nombre",
    "entier",
    "numerique",
    "numérique",
    "float",
    "integer",
    "decimal",
}


def est_type_numerique(type_colonne):
    return str(type_colonne or "").strip().lower() in TYPES_NUMERIQUES


def marquer_recommandation(choix, action_recommandee):
    resultat = []

    for valeur, libelle in choix:
        if valeur == action_recommandee:
            libelle = f"{libelle} — recommandé"

        resultat.append((valeur, libelle))

    return tuple(resultat)


class JeuDonneesImportForm(forms.ModelForm):
    """Importe un fichier sans le sauvegarder localement."""

    TAILLE_MAXIMALE = 10 * 1024 * 1024
    EXTENSIONS_AUTORISEES = {
        ".csv",
        ".xlsx",
    }

    fichier = forms.FileField(
        label="Fichier CSV ou Excel",
        widget=forms.ClearableFileInput(
            attrs={
                "class": "form-control",
                "accept": ".csv,.xlsx",
            }
        ),
    )

    class Meta:
        model = JeuDonnees

        fields = [
            "nom",
            "description",
        ]

        widgets = {
            "nom": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Exemple : Population par région",
                }
            ),
            "description": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 4,
                    "placeholder": (
                        "Décrivez brièvement le contenu "
                        "du jeu de données."
                    ),
                }
            ),
        }

    def clean_fichier(self):
        fichier = self.cleaned_data.get("fichier")

        if not fichier:
            raise forms.ValidationError(
                "Veuillez sélectionner un fichier."
            )

        extension = Path(fichier.name).suffix.lower()

        if extension not in self.EXTENSIONS_AUTORISEES:
            raise forms.ValidationError(
                "Format non autorisé. "
                "Utilisez un fichier CSV ou XLSX."
            )

        if fichier.size > self.TAILLE_MAXIMALE:
            raise forms.ValidationError(
                "Le fichier dépasse la taille maximale de 10 Mo."
            )

        return fichier
class JeuDonneesModificationForm(forms.ModelForm):
    """Permet de modifier le nom et la description."""

    class Meta:
        model = JeuDonnees

        fields = [
            "nom",
            "description",
        ]

        widgets = {
            "nom": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Nom du jeu de données",
                }
            ),
            "description": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 4,
                    "placeholder": "Description du jeu de données",
                }
            ),
        }

class NettoyageDonneesForm(forms.Form):
    """
    Formulaire guidé de nettoyage.

    Il traite séparément :
    - la forme générale des données ;
    - les colonnes vides, presque vides, constantes ou dupliquées ;
    - les lignes vides et les doublons ;
    - les valeurs manquantes ;
    - les valeurs inhabituelles.
    """

    nom_version = forms.CharField(
        label="Nom de la nouvelle version",
        max_length=255,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Exemple : Données — version nettoyée",
            }
        ),
    )

    nettoyer_textes = forms.BooleanField(
        label="Supprimer les espaces inutiles dans les textes",
        required=False,
        initial=True,
        widget=forms.CheckboxInput(
            attrs={"class": "form-check-input"}
        ),
    )

    convertir_nombres = forms.BooleanField(
        label="Convertir les nombres enregistrés comme texte",
        required=False,
        initial=True,
        widget=forms.CheckboxInput(
            attrs={"class": "form-check-input"}
        ),
    )

    convertir_dates = forms.BooleanField(
        label="Convertir les dates enregistrées comme texte",
        required=False,
        initial=True,
        widget=forms.CheckboxInput(
            attrs={"class": "form-check-input"}
        ),
    )

    supprimer_lignes_vides = forms.ChoiceField(
        label="Lignes entièrement vides",
        choices=(
            ("OUI", "Supprimer les lignes entièrement vides"),
            ("NON", "Conserver ces lignes"),
        ),
        initial="OUI",
        widget=forms.RadioSelect(),
    )

    action_doublons = forms.ChoiceField(
        label="Traitement des doublons",
        choices=(
            (
                "SUPPRIMER",
                "Supprimer les répétitions et garder la première ligne",
            ),
            ("CONSERVER", "Conserver toutes les lignes"),
        ),
        initial="SUPPRIMER",
        widget=forms.RadioSelect(),
    )

    mode_doublons = forms.ChoiceField(
        label="Méthode de comparaison",
        choices=(
            ("TOUTES", "Comparer toutes les colonnes"),
            ("COLONNES", "Comparer seulement certaines colonnes"),
        ),
        initial="TOUTES",
        widget=forms.RadioSelect(),
    )

    colonnes_doublons = forms.MultipleChoiceField(
        label="Colonnes utilisées pour la comparaison",
        required=False,
        widget=forms.CheckboxSelectMultiple(),
    )

    def __init__(
        self,
        *args,
        jeu_donnees,
        diagnostic,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)

        self.jeu_donnees = jeu_donnees
        self.diagnostic = diagnostic

        self.fields["nom_version"].initial = (
            f"{jeu_donnees.nom} — version nettoyée"
        )

        toutes_colonnes = [
            str(colonne)
            for colonne in jeu_donnees.colonnes
        ]

        self.fields["colonnes_doublons"].choices = [
            (colonne, colonne)
            for colonne in toutes_colonnes
        ]

        self.champs_structurels = []
        self.champs_manquants = []
        self.champs_aberrants = []

        colonnes_entierement_vides = {
            information["nom"]
            for information in diagnostic.get(
                "colonnes_structurelles",
                [],
            )
            if information.get("vide")
        }

        # -----------------------------------------------------
        # Colonnes structurelles problématiques
        # -----------------------------------------------------
        for index, information in enumerate(
            diagnostic.get(
                "colonnes_structurelles",
                [],
            )
        ):
            colonne = information["nom"]
            nom_action = f"structure_{index}"
            nom_cible = f"cible_structure_{index}"

            autoriser_fusion = bool(
                information.get("presque_vide")
                and not information.get("vide")
                and not information.get("dupliquee_de")
            )

            choix = [
                ("CONSERVER", "Conserver la colonne"),
                ("SUPPRIMER", "Supprimer la colonne"),
            ]

            if autoriser_fusion:
                choix.append(
                    (
                        "FUSIONNER_SUPPRIMER",
                        (
                            "Déplacer ses valeurs vers une autre "
                            "colonne, puis la supprimer"
                        ),
                    )
                )

            action_recommandee = information.get(
                "recommandation_action",
                "CONSERVER",
            )

            valeurs_actions = {
                valeur
                for valeur, _ in choix
            }

            if action_recommandee not in valeurs_actions:
                action_recommandee = "CONSERVER"

            self.fields[nom_action] = forms.ChoiceField(
                label=f"Traitement de {colonne}",
                choices=marquer_recommandation(
                    tuple(choix),
                    action_recommandee,
                ),
                initial=action_recommandee,
                widget=forms.Select(
                    attrs={
                        "class": "form-select structure-action",
                    }
                ),
            )

            cibles = [
                ("", "Sélectionner la colonne de destination")
            ]

            cibles.extend(
                (
                    autre_colonne,
                    autre_colonne,
                )
                for autre_colonne in toutes_colonnes
                if (
                    autre_colonne != colonne
                    and autre_colonne
                    not in colonnes_entierement_vides
                )
            )

            self.fields[nom_cible] = forms.ChoiceField(
                label="Colonne de destination",
                required=False,
                choices=cibles,
                initial=information.get(
                    "cible_recommandee",
                    "",
                ),
                widget=forms.Select(
                    attrs={
                        "class": "form-select",
                    }
                ),
            )

            self.champs_structurels.append(
                {
                    "colonne": colonne,
                    "nom_action": nom_action,
                    "nom_cible": nom_cible,
                }
            )

        colonnes_structurelles = {
            information["colonne"]
            for information in self.champs_structurels
        }

        # -----------------------------------------------------
        # Valeurs manquantes
        # -----------------------------------------------------
        for index, information in enumerate(
            diagnostic.get("colonnes", [])
        ):
            nombre_manquant = information.get(
                "manquantes",
                0,
            )

            if nombre_manquant <= 0:
                continue

            colonne = information["nom"]

            # Une colonne remplie à moins de 5 % est traitée dans
            # la section structurelle. L'imputer automatiquement
            # déformerait trop fortement les données.
            if (
                colonne in colonnes_structurelles
                and information.get("pourcentage", 0) >= 95
            ):
                continue

            type_colonne = str(
                information.get(
                    "type",
                    "texte",
                )
            ).strip().lower()

            nom_action = f"manquante_{index}"
            nom_valeur = f"valeur_manquante_{index}"

            if est_type_numerique(type_colonne):
                choix = (
                    ("AUCUNE", "Ne rien faire"),
                    ("MOYENNE", "Remplacer par la moyenne"),
                    ("MEDIANE", "Remplacer par la médiane"),
                    ("MODE", "Remplacer par la valeur la plus fréquente"),
                    ("VALEUR", "Utiliser une valeur personnalisée"),
                    ("SUPPRIMER", "Supprimer les lignes concernées"),
                )
                choix_initial = information.get(
                    "recommandation_action",
                    "MEDIANE",
                )
            else:
                choix = (
                    ("AUCUNE", "Ne rien faire"),
                    ("MODE", "Remplacer par la valeur la plus fréquente"),
                    (
                        "NON_RENSEIGNE",
                        'Remplacer par « Non renseigné »',
                    ),
                    ("VALEUR", "Utiliser une autre valeur"),
                    ("SUPPRIMER", "Supprimer les lignes concernées"),
                )
                choix_initial = information.get(
                    "recommandation_action",
                    "NON_RENSEIGNE",
                )

            valeurs_autorisees = {
                valeur
                for valeur, _ in choix
            }

            if choix_initial not in valeurs_autorisees:
                choix_initial = "AUCUNE"

            self.fields[nom_action] = forms.ChoiceField(
                label=f"Traitement de {colonne}",
                choices=marquer_recommandation(
                    choix,
                    choix_initial,
                ),
                initial=choix_initial,
                widget=forms.Select(
                    attrs={
                        "class": "form-select missing-action",
                    }
                ),
            )

            self.fields[nom_valeur] = forms.CharField(
                label="Valeur personnalisée",
                required=False,
                widget=forms.TextInput(
                    attrs={
                        "class": "form-control",
                        "placeholder": (
                            "Saisissez la valeur de remplacement"
                        ),
                    }
                ),
            )

            self.champs_manquants.append(
                {
                    "colonne": colonne,
                    "type": type_colonne,
                    "nom_action": nom_action,
                    "nom_valeur": nom_valeur,
                }
            )

        # -----------------------------------------------------
        # Valeurs inhabituelles
        # -----------------------------------------------------
        for index, information in enumerate(
            diagnostic.get("valeurs_aberrantes", [])
        ):
            colonne = information["colonne"]

            if colonne in colonnes_structurelles:
                continue

            nom_action = f"aberrante_{index}"

            choix_aberrants = (
                ("AUCUNE", "Conserver les valeurs"),
                ("MEDIANE", "Remplacer par la médiane"),
                ("MOYENNE", "Remplacer par la moyenne"),
                ("BORNER", "Limiter aux bornes habituelles"),
                ("SUPPRIMER", "Supprimer les lignes concernées"),
            )

            action_recommandee = information.get(
                "recommandation_action",
                "AUCUNE",
            )

            self.fields[nom_action] = forms.ChoiceField(
                label=f"Traitement de {colonne}",
                choices=marquer_recommandation(
                    choix_aberrants,
                    action_recommandee,
                ),
                initial=action_recommandee,
                widget=forms.Select(
                    attrs={
                        "class": "form-select",
                    }
                ),
            )

            self.champs_aberrants.append(
                {
                    "colonne": colonne,
                    "nom_action": nom_action,
                }
            )

    def clean(self):
        cleaned_data = super().clean()

        if (
            cleaned_data.get("action_doublons")
            == "SUPPRIMER"
            and cleaned_data.get("mode_doublons")
            == "COLONNES"
            and not cleaned_data.get("colonnes_doublons")
        ):
            self.add_error(
                "colonnes_doublons",
                (
                    "Sélectionnez au moins une colonne "
                    "ou choisissez « Comparer toutes les colonnes »."
                ),
            )

        actions_structurelles = {}

        for information in self.champs_structurels:
            source = information["colonne"]
            nom_action = information["nom_action"]
            nom_cible = information["nom_cible"]
            action = cleaned_data.get(
                nom_action,
                "CONSERVER",
            )
            cible = cleaned_data.get(
                nom_cible,
                "",
            )

            actions_structurelles[source] = action

            if action != "FUSIONNER_SUPPRIMER":
                continue

            if not cible:
                self.add_error(
                    nom_cible,
                    "Sélectionnez une colonne de destination.",
                )
            elif cible == source:
                self.add_error(
                    nom_cible,
                    (
                        "La colonne source et la colonne de "
                        "destination doivent être différentes."
                    ),
                )

        # La cible d'une fusion doit rester dans la version finale.
        for information in self.champs_structurels:
            action = cleaned_data.get(
                information["nom_action"],
                "CONSERVER",
            )

            if action != "FUSIONNER_SUPPRIMER":
                continue

            cible = cleaned_data.get(
                information["nom_cible"],
                "",
            )

            if actions_structurelles.get(cible) in {
                "SUPPRIMER",
                "FUSIONNER_SUPPRIMER",
            }:
                self.add_error(
                    information["nom_cible"],
                    (
                        "La colonne de destination doit être conservée."
                    ),
                )

        colonnes_supprimees = {
            information["colonne"]
            for information in self.champs_structurels
            if cleaned_data.get(
                information["nom_action"]
            ) in {
                "SUPPRIMER",
                "FUSIONNER_SUPPRIMER",
            }
        }

        colonnes_restantes = set(
            str(colonne)
            for colonne in self.jeu_donnees.colonnes
        ) - colonnes_supprimees

        if not colonnes_restantes:
            raise forms.ValidationError(
                "Le nettoyage ne peut pas supprimer toutes les colonnes."
            )

        for information in self.champs_manquants:
            action = cleaned_data.get(
                information["nom_action"]
            )

            if action != "VALEUR":
                continue

            nom_valeur = information["nom_valeur"]
            valeur = cleaned_data.get(nom_valeur)

            if valeur is None or str(valeur).strip() == "":
                self.add_error(
                    nom_valeur,
                    "Saisissez la valeur de remplacement.",
                )
                continue

            if est_type_numerique(information["type"]):
                try:
                    cleaned_data[nom_valeur] = float(
                        str(valeur)
                        .strip()
                        .replace(",", ".")
                    )
                except ValueError:
                    self.add_error(
                        nom_valeur,
                        (
                            "Cette colonne contient des nombres. "
                            "Saisissez une valeur numérique."
                        ),
                    )

        return cleaned_data

    def construire_plan(self):
        """Construit un plan JSON-compatible."""

        if not self.is_valid():
            raise ValueError(
                "Le formulaire doit être valide avant la construction du plan."
            )

        traitements_colonnes = {}

        for information in self.champs_structurels:
            traitements_colonnes[
                information["colonne"]
            ] = {
                "action": self.cleaned_data[
                    information["nom_action"]
                ],
                "cible": self.cleaned_data.get(
                    information["nom_cible"],
                    "",
                ),
            }

        traitements_manquants = {}

        for information in self.champs_manquants:
            traitements_manquants[
                information["colonne"]
            ] = {
                "strategie": self.cleaned_data[
                    information["nom_action"]
                ],
                "valeur": self.cleaned_data.get(
                    information["nom_valeur"]
                ),
            }

        traitements_aberrants = {}

        for information in self.champs_aberrants:
            traitements_aberrants[
                information["colonne"]
            ] = {
                "action": self.cleaned_data[
                    information["nom_action"]
                ],
            }

        mode_doublons = self.cleaned_data[
            "mode_doublons"
        ]

        return {
            "nom_version": self.cleaned_data[
                "nom_version"
            ],
            "nettoyer_textes": bool(
                self.cleaned_data.get("nettoyer_textes")
            ),
            "convertir_nombres": bool(
                self.cleaned_data.get("convertir_nombres")
            ),
            "convertir_dates": bool(
                self.cleaned_data.get("convertir_dates")
            ),
            "traitements_colonnes": traitements_colonnes,
            "supprimer_lignes_vides": (
                self.cleaned_data[
                    "supprimer_lignes_vides"
                ]
                == "OUI"
            ),
            "supprimer_doublons": (
                self.cleaned_data["action_doublons"]
                == "SUPPRIMER"
            ),
            "mode_doublons": mode_doublons,
            "colonnes_doublons": (
                self.cleaned_data.get(
                    "colonnes_doublons",
                    [],
                )
                if mode_doublons == "COLONNES"
                else []
            ),
            "traitements_manquants": traitements_manquants,
            "traitements_aberrants": traitements_aberrants,
        }
