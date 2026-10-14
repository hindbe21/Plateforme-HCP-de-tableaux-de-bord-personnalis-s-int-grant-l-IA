from django.conf import settings
from django.db import models


class JournalActivite(models.Model):
    """
    Trace une action importante réalisée
    dans la plateforme.

    Les détails techniques du nettoyage restent
    stockés dans OperationNettoyage.
    """

    class Action(models.TextChoices):
        CONNEXION = (
            "CONNEXION",
            "Connexion",
        )

        DECONNEXION = (
            "DECONNEXION",
            "Déconnexion",
        )

        INSCRIPTION = (
            "INSCRIPTION",
            "Inscription",
        )

        IMPORTATION = (
            "IMPORTATION",
            "Importation",
        )

        NETTOYAGE = (
            "NETTOYAGE",
            "Nettoyage",
        )

        CREATION = (
            "CREATION",
            "Création",
        )

        MODIFICATION = (
            "MODIFICATION",
            "Modification",
        )

        SUPPRESSION = (
            "SUPPRESSION",
            "Suppression",
        )

        FILTRAGE = (
            "FILTRAGE",
            "Filtrage",
        )

        EXPORTATION = (
            "EXPORTATION",
            "Exportation",
        )

        IA = (
            "IA",
            "Assistant IA",
        )

        ADMINISTRATION = (
            "ADMINISTRATION",
            "Administration",
        )

    class Niveau(models.TextChoices):
        INFO = (
            "INFO",
            "Information",
        )

        SUCCES = (
            "SUCCES",
            "Succès",
        )

        ATTENTION = (
            "ATTENTION",
            "Attention",
        )

        ERREUR = (
            "ERREUR",
            "Erreur",
        )

    utilisateur = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="journal_activites",
        null=True,
        blank=True,
        verbose_name="Utilisateur",
    )

    action = models.CharField(
        max_length=30,
        choices=Action.choices,
        db_index=True,
        verbose_name="Action",
    )

    niveau = models.CharField(
        max_length=15,
        choices=Niveau.choices,
        default=Niveau.INFO,
        db_index=True,
        verbose_name="Niveau",
    )

    module = models.CharField(
        max_length=100,
        db_index=True,
        verbose_name="Module",
    )

    objet_type = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="Type d’objet",
    )

    objet_id = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="Identifiant de l’objet",
    )

    objet_libelle = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Objet concerné",
    )

    description = models.TextField(
        verbose_name="Description",
    )

    methode_http = models.CharField(
        max_length=10,
        blank=True,
        verbose_name="Méthode HTTP",
    )

    chemin = models.CharField(
        max_length=500,
        blank=True,
        verbose_name="Chemin",
    )

    adresse_ip = models.GenericIPAddressField(
        null=True,
        blank=True,
        verbose_name="Adresse IP",
    )

    user_agent = models.CharField(
        max_length=500,
        blank=True,
        verbose_name="Navigateur",
    )

    metadata = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Métadonnées",
    )

    date_action = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        verbose_name="Date de l’action",
    )

    class Meta:
        ordering = [
            "-date_action",
            "-pk",
        ]

        verbose_name = (
            "Entrée du journal"
        )

        verbose_name_plural = (
            "Journal d’activité"
        )

        indexes = [
            models.Index(
                fields=[
                    "utilisateur",
                    "-date_action",
                ],
                name="audit_user_date_idx",
            ),

            models.Index(
                fields=[
                    "action",
                    "-date_action",
                ],
                name="audit_action_date_idx",
            ),

            models.Index(
                fields=[
                    "module",
                    "-date_action",
                ],
                name="audit_module_date_idx",
            ),
        ]

    def __str__(self):
        return (
            f"{self.get_action_display()} — "
            f"{self.objet_libelle or self.module}"
        )

    @property
    def classe_badge(self):
        return {
            self.Action.CONNEXION:
            "text-bg-success",

            self.Action.DECONNEXION:
            "text-bg-secondary",

            self.Action.INSCRIPTION:
            "text-bg-info",

            self.Action.IMPORTATION:
            "text-bg-primary",

            self.Action.NETTOYAGE:
            "text-bg-warning",

            self.Action.CREATION:
            "text-bg-success",

            self.Action.MODIFICATION:
            "text-bg-primary",

            self.Action.SUPPRESSION:
            "text-bg-danger",

            self.Action.FILTRAGE:
            "text-bg-info",

            self.Action.EXPORTATION:
            "text-bg-dark",

            self.Action.IA:
            "text-bg-primary",

            self.Action.ADMINISTRATION:
            "text-bg-warning",
        }.get(
            self.action,
            "text-bg-secondary",
        )

    @property
    def classe_niveau(self):
        return {
            self.Niveau.INFO:
            "text-bg-light",

            self.Niveau.SUCCES:
            "text-bg-success",

            self.Niveau.ATTENTION:
            "text-bg-warning",

            self.Niveau.ERREUR:
            "text-bg-danger",
        }.get(
            self.niveau,
            "text-bg-light",
        )
