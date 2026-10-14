from django import forms
from django.contrib.auth.forms import (
    PasswordChangeForm,
    UserChangeForm,
    UserCreationForm,
)

from .models import User


class InscriptionForm(UserCreationForm):
    first_name = forms.CharField(
        label="Prénom",
        max_length=150,
        required=True,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Votre prénom",
                "autocomplete": "given-name",
            }
        ),
    )

    last_name = forms.CharField(
        label="Nom",
        max_length=150,
        required=True,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Votre nom",
                "autocomplete": "family-name",
            }
        ),
    )

    email = forms.EmailField(
        label="Adresse email professionnelle",
        required=True,
        widget=forms.EmailInput(
            attrs={
                "class": "form-control",
                "placeholder": "nom@exemple.ma",
                "autocomplete": "email",
            }
        ),
    )

    password1 = forms.CharField(
        label="Mot de passe",
        strip=False,
        widget=forms.PasswordInput(
            attrs={
                "class": "form-control",
                "placeholder": "Choisissez un mot de passe",
                "autocomplete": "new-password",
            }
        ),
    )

    password2 = forms.CharField(
        label="Confirmation du mot de passe",
        strip=False,
        widget=forms.PasswordInput(
            attrs={
                "class": "form-control",
                "placeholder": "Confirmez le mot de passe",
                "autocomplete": "new-password",
            }
        ),
    )

    class Meta:
        model = User
        fields = (
            "first_name",
            "last_name",
            "email",
            "password1",
            "password2",
        )

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()

        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError(
                "Un compte existe déjà avec cette adresse email."
            )

        return email

    def save(self, commit=True):
        utilisateur = super().save(commit=False)
        utilisateur.email = self.cleaned_data["email"]
        utilisateur.role = User.Role.METIER
        utilisateur.statut = User.StatutCompte.EN_ATTENTE
        utilisateur.is_active = False
        utilisateur.is_staff = False
        utilisateur.is_superuser = False

        if commit:
            utilisateur.save()

        return utilisateur


class ProfilModificationForm(forms.ModelForm):
    first_name = forms.CharField(
        label="Prénom",
        max_length=150,
        required=True,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Votre prénom",
                "autocomplete": "given-name",
            }
        ),
    )

    last_name = forms.CharField(
        label="Nom",
        max_length=150,
        required=True,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Votre nom",
                "autocomplete": "family-name",
            }
        ),
    )

    email = forms.EmailField(
        label="Adresse email",
        required=True,
        widget=forms.EmailInput(
            attrs={
                "class": "form-control",
                "placeholder": "nom@exemple.ma",
                "autocomplete": "email",
            }
        ),
    )

    class Meta:
        model = User
        fields = (
            "first_name",
            "last_name",
            "email",
        )

    def clean_first_name(self):
        valeur = self.cleaned_data["first_name"].strip()

        if not valeur:
            raise forms.ValidationError(
                "Le prénom est obligatoire."
            )

        return valeur

    def clean_last_name(self):
        valeur = self.cleaned_data["last_name"].strip()

        if not valeur:
            raise forms.ValidationError(
                "Le nom est obligatoire."
            )

        return valeur

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()

        existe = (
            User.objects
            .filter(email__iexact=email)
            .exclude(pk=self.instance.pk)
            .exists()
        )

        if existe:
            raise forms.ValidationError(
                "Cette adresse email est déjà utilisée par un autre compte."
            )

        return email


class ChangementMotDePasseForm(PasswordChangeForm):
    def __init__(self, user, *args, **kwargs):
        super().__init__(user, *args, **kwargs)

        configuration = {
            "old_password": {
                "label": "Mot de passe actuel",
                "placeholder": "Saisissez votre mot de passe actuel",
                "autocomplete": "current-password",
            },
            "new_password1": {
                "label": "Nouveau mot de passe",
                "placeholder": "Choisissez un nouveau mot de passe",
                "autocomplete": "new-password",
            },
            "new_password2": {
                "label": "Confirmation du nouveau mot de passe",
                "placeholder": "Confirmez le nouveau mot de passe",
                "autocomplete": "new-password",
            },
        }

        for nom_champ, parametres in configuration.items():
            champ = self.fields[nom_champ]
            champ.label = parametres["label"]
            champ.widget.attrs.update(
                {
                    "class": "form-control",
                    "placeholder": parametres["placeholder"],
                    "autocomplete": parametres["autocomplete"],
                }
            )


class CustomUserCreationForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = User
        fields = (
            "email",
            "first_name",
            "last_name",
            "role",
            "statut",
        )


class CustomUserChangeForm(UserChangeForm):
    class Meta:
        model = User
        fields = "__all__"


class PreferencesCompteForm(forms.Form):
    """Préférences d'interface distinctes des informations personnelles."""

    notifications = forms.ChoiceField(
        label="Notifications",
        choices=(
            ("STANDARD", "Notifications standard"),
            ("IMPORTANTES", "Uniquement les notifications importantes"),
            ("AUCUNE", "Aucune notification dans l’interface"),
        ),
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    theme = forms.ChoiceField(
        label="Thème de l’interface",
        choices=(
            ("CLAIR", "Clair"),
            ("SOMBRE", "Sombre"),
            ("SYSTEME", "Utiliser le thème du système"),
        ),
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    langue = forms.ChoiceField(
        label="Langue de l’interface",
        choices=(
            ("FR", "Français"),
        ),
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    fuseau_horaire = forms.ChoiceField(
        label="Fuseau horaire",
        choices=(
            ("Africa/Casablanca", "Casablanca — UTC+01:00"),
        ),
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    affichage_compact = forms.BooleanField(
        label="Utiliser un affichage plus compact pour les tableaux",
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )
