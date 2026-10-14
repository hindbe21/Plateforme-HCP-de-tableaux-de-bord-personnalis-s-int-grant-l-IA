from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from datasets.models import JeuDonnees


class TableauBord(models.Model):
    proprietaire = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="tableaux_bord",
        verbose_name="Propriétaire",
    )

    jeu_donnees = models.ForeignKey(
        JeuDonnees,
        on_delete=models.CASCADE,
        related_name="tableaux_bord",
        verbose_name="Jeu de données",
    )

    titre = models.CharField(
        max_length=200,
        verbose_name="Titre",
    )

    description = models.TextField(
        blank=True,
        verbose_name="Description",
    )

    actif = models.BooleanField(
        default=True,
        verbose_name="Actif",
    )

    date_creation = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Date de création",
    )

    date_modification = models.DateTimeField(
        auto_now=True,
        verbose_name="Dernière modification",
    )

    class Meta:
        ordering = [
            "-date_modification",
        ]
        verbose_name = "Tableau de bord"
        verbose_name_plural = "Tableaux de bord"

    def __str__(self):
        return self.titre

    def utilisateur_autorise(self, utilisateur):
        return (
            utilisateur.is_superuser
            or getattr(
                utilisateur,
                "est_administrateur",
                False,
            )
            or self.proprietaire_id == utilisateur.id
        )


class Filtre(models.Model):
    class Operateur(models.TextChoices):
        EGAL = (
            "EGAL",
            "Est égal à",
        )
        DIFFERENT = (
            "DIFFERENT",
            "Est différent de",
        )
        CONTIENT = (
            "CONTIENT",
            "Contient",
        )
        NE_CONTIENT_PAS = (
            "NE_CONTIENT_PAS",
            "Ne contient pas",
        )
        SUPERIEUR = (
            "SUPERIEUR",
            "Supérieur à",
        )
        SUPERIEUR_EGAL = (
            "SUPERIEUR_EGAL",
            "Supérieur ou égal à",
        )
        INFERIEUR = (
            "INFERIEUR",
            "Inférieur à",
        )
        INFERIEUR_EGAL = (
            "INFERIEUR_EGAL",
            "Inférieur ou égal à",
        )
        ENTRE = (
            "ENTRE",
            "Entre deux valeurs",
        )
        VIDE = (
            "VIDE",
            "Est vide",
        )
        NON_VIDE = (
            "NON_VIDE",
            "N’est pas vide",
        )

    tableau_bord = models.ForeignKey(
        TableauBord,
        on_delete=models.CASCADE,
        related_name="filtres",
        verbose_name="Tableau de bord",
    )

    colonne = models.CharField(
        max_length=200,
        verbose_name="Colonne",
    )

    operateur = models.CharField(
        max_length=20,
        choices=Operateur.choices,
        default=Operateur.EGAL,
        verbose_name="Opérateur",
    )

    valeur = models.CharField(
        max_length=500,
        blank=True,
        verbose_name="Valeur",
    )

    actif = models.BooleanField(
        default=True,
        verbose_name="Actif",
    )

    ordre = models.PositiveIntegerField(
        default=0,
        verbose_name="Ordre",
    )

    date_creation = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Date de création",
    )

    date_modification = models.DateTimeField(
        auto_now=True,
        verbose_name="Dernière modification",
    )

    class Meta:
        ordering = [
            "ordre",
            "date_creation",
        ]
        verbose_name = "Filtre global"
        verbose_name_plural = "Filtres globaux"

    def __str__(self):
        if self.operateur in {
            self.Operateur.VIDE,
            self.Operateur.NON_VIDE,
        }:
            return (
                f"{self.colonne} "
                f"{self.get_operateur_display()}"
            )

        return (
            f"{self.colonne} "
            f"{self.get_operateur_display()} "
            f"{self.valeur}"
        )

    def clean(self):
        super().clean()

        if self.tableau_bord_id:
            colonnes = (
                self.tableau_bord
                .jeu_donnees
                .colonnes
                or []
            )

            if self.colonne not in colonnes:
                raise ValidationError(
                    {
                        "colonne": (
                            "Cette colonne n’existe pas "
                            "dans le jeu de données utilisé."
                        )
                    }
                )

        operateurs_sans_valeur = {
            self.Operateur.VIDE,
            self.Operateur.NON_VIDE,
        }

        if (
            self.operateur
            not in operateurs_sans_valeur
            and not str(self.valeur or "").strip()
        ):
            raise ValidationError(
                {
                    "valeur": (
                        "Saisissez une valeur pour "
                        "appliquer ce filtre."
                    )
                }
            )

        if self.operateur in operateurs_sans_valeur:
            self.valeur = ""


class Widget(models.Model):
    TYPE_WIDGET_CHOICES = (
        ("INDICATEUR", "Carte KPI"),
        ("BARRES", "Graphique en barres"),
        ("BARRES_HORIZONTALES", "Barres horizontales"),
        ("CLASSEMENT", "Classement"),
        ("CAMEMBERT", "Graphique circulaire"),
        ("ANNEAU", "Graphique en anneau"),
        ("COURBE", "Graphique en courbes"),
        ("AIRES", "Graphique en aires"),
        ("HISTOGRAMME", "Histogramme"),
        ("NUAGE_POINTS", "Nuage de points"),
        ("TABLEAU", "Tableau simple"),
        ("TABLEAU_CROISE", "Tableau croisé"),
        ("STATISTIQUES_DESCRIPTIVES", "Statistiques descriptives"),
    )

    tableau_bord = models.ForeignKey(
        TableauBord,
        on_delete=models.CASCADE,
        related_name="widgets",
        verbose_name="Tableau de bord",
    )

    titre = models.CharField(
        max_length=200,
        verbose_name="Titre",
    )

    type_widget = models.CharField(
        max_length=30,
        choices=TYPE_WIDGET_CHOICES,
        default="BARRES",
        verbose_name="Type de visualisation",
    )

    colonne_categorie = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Dimension / axe X",
    )

    limite_resultats = models.PositiveIntegerField(
        default=10,
        verbose_name="Nombre maximal de résultats",
    )

    configuration = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Configuration statistique",
    )

    ordre = models.PositiveIntegerField(
        default=0,
        verbose_name="Ordre",
    )

    date_creation = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Date de création",
    )

    date_modification = models.DateTimeField(
        auto_now=True,
        verbose_name="Dernière modification",
    )

    class Meta:
        ordering = [
            "ordre",
            "date_creation",
        ]
        verbose_name = "Widget"
        verbose_name_plural = "Widgets"

    def __str__(self):
        return self.titre


class FiltreWidget(models.Model):
    widget = models.ForeignKey(
        Widget,
        on_delete=models.CASCADE,
        related_name="filtres_locaux",
        verbose_name="Widget",
    )

    colonne = models.CharField(
        max_length=200,
        verbose_name="Colonne",
    )

    operateur = models.CharField(
        max_length=20,
        choices=Filtre.Operateur.choices,
        default=Filtre.Operateur.EGAL,
        verbose_name="Opérateur",
    )

    valeur = models.CharField(
        max_length=500,
        blank=True,
        verbose_name="Valeur",
    )

    actif = models.BooleanField(
        default=True,
        verbose_name="Actif",
    )

    ordre = models.PositiveIntegerField(
        default=0,
        verbose_name="Ordre",
    )

    date_creation = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Date de création",
    )

    date_modification = models.DateTimeField(
        auto_now=True,
        verbose_name="Dernière modification",
    )

    class Meta:
        ordering = [
            "ordre",
            "date_creation",
        ]
        verbose_name = "Filtre de widget"
        verbose_name_plural = "Filtres de widgets"

    def __str__(self):
        if self.operateur in {
            Filtre.Operateur.VIDE,
            Filtre.Operateur.NON_VIDE,
        }:
            return (
                f"{self.colonne} "
                f"{self.get_operateur_display()}"
            )

        return (
            f"{self.colonne} "
            f"{self.get_operateur_display()} "
            f"{self.valeur}"
        )

    def clean(self):
        super().clean()

        if self.widget_id:
            colonnes = (
                self.widget
                .tableau_bord
                .jeu_donnees
                .colonnes
                or []
            )

            if self.colonne not in colonnes:
                raise ValidationError(
                    {
                        "colonne": (
                            "Cette colonne n’existe pas "
                            "dans le jeu de données du widget."
                        )
                    }
                )

        operateurs_sans_valeur = {
            Filtre.Operateur.VIDE,
            Filtre.Operateur.NON_VIDE,
        }

        if (
            self.operateur
            not in operateurs_sans_valeur
            and not str(self.valeur or "").strip()
        ):
            raise ValidationError(
                {
                    "valeur": (
                        "Saisissez une valeur pour "
                        "appliquer ce filtre."
                    )
                }
            )

        if self.operateur in operateurs_sans_valeur:
            self.valeur = ""
