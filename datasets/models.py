from pathlib import Path
from uuid import uuid4

from django.conf import settings
from django.contrib.postgres.indexes import GinIndex
from django.db import models


def chemin_fichier_jeu_donnees(instance, filename):
    """
    Fonction conservée pour assurer la compatibilité
    avec l'ancienne migration 0001_initial.

    Le nouveau système n'enregistre plus les fichiers localement.
    """

    extension = Path(filename).suffix.lower()
    nom_unique = f"{uuid4().hex}{extension}"

    return (
        f"datasets/"
        f"utilisateur_{instance.proprietaire_id}/"
        f"{nom_unique}"
    )


class JeuDonnees(models.Model):
    """
    Jeu de données importé et stocké dans PostgreSQL.
    """

    class FormatFichier(models.TextChoices):
        CSV = "CSV", "CSV"
        EXCEL = "EXCEL", "Excel"

    class Statut(models.TextChoices):
        EN_ATTENTE = "EN_ATTENTE", "En attente"
        VALIDE = "VALIDE", "Valide"
        INVALIDE = "INVALIDE", "Invalide"

    class TypeVersion(models.TextChoices):
        ORIGINALE = "ORIGINALE", "Version originale"
        NETTOYEE = "NETTOYEE", "Version nettoyée"

    proprietaire = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="jeux_donnees",
        verbose_name="Propriétaire",
    )

    nom = models.CharField(
        max_length=200,
        verbose_name="Nom du jeu de données",
    )

    description = models.TextField(
        blank=True,
        verbose_name="Description",
    )

    nom_fichier_original = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name="Nom du fichier original",
    )

    format = models.CharField(
        max_length=10,
        choices=FormatFichier.choices,
        verbose_name="Format",
    )

    nombre_lignes = models.PositiveIntegerField(
        default=0,
        verbose_name="Nombre de lignes",
    )

    nombre_colonnes = models.PositiveIntegerField(
        default=0,
        verbose_name="Nombre de colonnes",
    )

    colonnes = models.JSONField(
        default=list,
        blank=True,
        verbose_name="Liste des colonnes",
    )

    types_colonnes = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Types des colonnes",
    )

    taille_fichier = models.PositiveBigIntegerField(
        default=0,
        verbose_name="Taille du fichier original en octets",
    )

    statut = models.CharField(
        max_length=20,
        choices=Statut.choices,
        default=Statut.EN_ATTENTE,
        verbose_name="Statut",
    )

    message_erreur = models.TextField(
        blank=True,
        verbose_name="Message d'erreur",
    )

    type_version = models.CharField(
        max_length=20,
        choices=TypeVersion.choices,
        default=TypeVersion.ORIGINALE,
        verbose_name="Type de version",
    )

    numero_version = models.PositiveIntegerField(
        default=1,
        verbose_name="Numéro de version",
    )

    source_jeu_donnees = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="versions_nettoyees",
        verbose_name="Jeu de données original",
    )

    date_importation = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Date d'importation",
    )

    date_modification = models.DateTimeField(
        auto_now=True,
        verbose_name="Dernière modification",
    )

    class Meta:
        verbose_name = "Jeu de données"
        verbose_name_plural = "Jeux de données"
        ordering = ["-date_importation"]

    def __str__(self):
        return self.nom

    @property
    def taille_fichier_formatee(self):
        """
        Retourne une taille lisible en octets, Ko ou Mo.
        """

        taille = self.taille_fichier

        if taille < 1024:
            return f"{taille} octets"

        if taille < 1024 * 1024:
            return f"{taille / 1024:.1f} Ko"

        return f"{taille / (1024 * 1024):.1f} Mo"

    def utilisateur_peut_modifier(self, utilisateur):
        """
        Vérifie si un utilisateur peut modifier le jeu de données.
        """

        return (
            utilisateur == self.proprietaire
            or utilisateur.is_superuser
            or utilisateur.est_administrateur
        )


class LigneDonnees(models.Model):
    """
    Une ligne d'un jeu de données stockée dans PostgreSQL.
    Les valeurs sont enregistrées dans une colonne JSONB.
    """

    jeu_donnees = models.ForeignKey(
        JeuDonnees,
        on_delete=models.CASCADE,
        related_name="lignes",
        verbose_name="Jeu de données",
    )

    numero_ligne = models.PositiveIntegerField(
        verbose_name="Numéro de ligne",
    )

    donnees = models.JSONField(
        default=dict,
        verbose_name="Valeurs de la ligne",
    )

    date_creation = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Date de création",
    )

    class Meta:
        verbose_name = "Ligne de données"
        verbose_name_plural = "Lignes de données"
        ordering = ["numero_ligne"]

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "jeu_donnees",
                    "numero_ligne",
                ],
                name="ligne_unique_par_jeu_donnees",
            ),
        ]

        indexes = [
            models.Index(
                fields=[
                    "jeu_donnees",
                    "numero_ligne",
                ],
                name="ligne_jeu_numero_idx",
            ),
            GinIndex(
                fields=["donnees"],
                name="ligne_donnees_gin_idx",
            ),
        ]

    def __str__(self):
        return (
            f"{self.jeu_donnees.nom} "
            f"— ligne {self.numero_ligne}"
        )


class OperationNettoyage(models.Model):
    """
    Historique d'une opération de nettoyage des données.
    """

    jeu_source = models.ForeignKey(
        JeuDonnees,
        on_delete=models.PROTECT,
        related_name="nettoyages_effectues",
        verbose_name="Version source",
    )

    jeu_resultat = models.OneToOneField(
        JeuDonnees,
        on_delete=models.CASCADE,
        related_name="operation_nettoyage",
        verbose_name="Version nettoyée",
    )

    utilisateur = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="operations_nettoyage",
        verbose_name="Utilisateur",
    )

    operations = models.JSONField(
        default=dict,
        verbose_name="Opérations appliquées",
    )

    diagnostic_avant = models.JSONField(
        default=dict,
        verbose_name="Diagnostic avant nettoyage",
    )

    diagnostic_apres = models.JSONField(
        default=dict,
        verbose_name="Diagnostic après nettoyage",
    )

    resume = models.JSONField(
        default=dict,
        verbose_name="Résumé du nettoyage",
    )

    date_creation = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Date du nettoyage",
    )

    class Meta:
        verbose_name = "Opération de nettoyage"
        verbose_name_plural = "Opérations de nettoyage"
        ordering = ["-date_creation"]

    def __str__(self):
        return (
            f"{self.jeu_source.nom} "
            f"→ {self.jeu_resultat.nom}"
        )