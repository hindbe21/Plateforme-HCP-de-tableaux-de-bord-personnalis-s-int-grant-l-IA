from django.conf import settings
from django.db import models


class AnalyseJeuDonnees(models.Model):
    class Statut(models.TextChoices):
        PRETE = "PRETE", "Prête"
        ERREUR = "ERREUR", "Erreur"

    jeu_donnees = models.OneToOneField(
        "datasets.JeuDonnees",
        on_delete=models.CASCADE,
        related_name="analyse_intelligente",
        verbose_name="Jeu de données",
    )

    empreinte = models.CharField(
        max_length=64,
        db_index=True,
        verbose_name="Empreinte du jeu de données",
    )

    schema = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Schéma analysé",
    )

    statistiques = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Statistiques calculées",
    )

    relations = models.JSONField(
        default=list,
        blank=True,
        verbose_name="Relations possibles",
    )

    indicateurs = models.JSONField(
        default=list,
        blank=True,
        verbose_name="Indicateurs calculables",
    )

    statut = models.CharField(
        max_length=20,
        choices=Statut.choices,
        default=Statut.PRETE,
        verbose_name="Statut",
    )

    message_erreur = models.TextField(
        blank=True,
        verbose_name="Message d’erreur",
    )

    date_analyse = models.DateTimeField(
        auto_now=True,
        verbose_name="Dernière analyse",
    )

    class Meta:
        verbose_name = "Analyse intelligente"
        verbose_name_plural = "Analyses intelligentes"

    def __str__(self):
        return f"Analyse de {self.jeu_donnees}"


class SuggestionWidget(models.Model):
    class Source(models.TextChoices):
        AUTOMATIQUE = "AUTOMATIQUE", "Analyse automatique"
        CONVERSATION = "CONVERSATION", "Assistant conversationnel"

    class Statut(models.TextChoices):
        PROPOSEE = "PROPOSEE", "Proposée"
        ACCEPTEE = "ACCEPTEE", "Acceptée"
        SUPPRIMEE = "SUPPRIMEE", "Supprimée"

    tableau_bord = models.ForeignKey(
        "dashboards.TableauBord",
        on_delete=models.CASCADE,
        related_name="suggestions_ia",
        verbose_name="Tableau de bord",
    )

    analyse = models.ForeignKey(
        AnalyseJeuDonnees,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="suggestions",
        verbose_name="Analyse utilisée",
    )

    source = models.CharField(
        max_length=20,
        choices=Source.choices,
        default=Source.AUTOMATIQUE,
        verbose_name="Source",
    )

    configuration = models.JSONField(
        default=dict,
        verbose_name="Configuration proposée",
    )

    justification = models.TextField(
        blank=True,
        verbose_name="Justification",
    )

    statut = models.CharField(
        max_length=20,
        choices=Statut.choices,
        default=Statut.PROPOSEE,
        verbose_name="Statut",
    )

    widget_cree = models.ForeignKey(
        "dashboards.Widget",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="suggestion_source",
        verbose_name="Widget créé",
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
        ordering = ["-date_creation"]
        verbose_name = "Suggestion de widget"
        verbose_name_plural = "Suggestions de widgets"

    def __str__(self):
        titre = self.configuration.get("titre", "Widget proposé")
        return str(titre)


class RapportStatistiqueIA(models.Model):
    tableau_bord = models.ForeignKey(
        "dashboards.TableauBord",
        on_delete=models.CASCADE,
        related_name="rapports_ia",
        verbose_name="Tableau de bord",
    )

    auteur = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="rapports_statistiques_ia",
        verbose_name="Auteur",
    )

    donnees_calculees = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Résultats calculés par Pandas",
    )

    contenu = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Interprétation rédigée",
    )

    modele_ollama = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="Modèle Ollama",
    )

    date_creation = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Date de création",
    )

    class Meta:
        ordering = ["-date_creation"]
        verbose_name = "Rapport statistique intelligent"
        verbose_name_plural = "Rapports statistiques intelligents"

    def __str__(self):
        return f"Rapport — {self.tableau_bord}"


class RapportJeuDonneesIA(models.Model):
    jeu_donnees = models.ForeignKey(
        "datasets.JeuDonnees", on_delete=models.CASCADE,
        related_name="rapports_statistiques_ia", verbose_name="Jeu de données",
    )
    auteur = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="rapports_jeux_donnees_ia", verbose_name="Auteur",
    )
    donnees_calculees = models.JSONField(default=dict, blank=True, verbose_name="Résultats calculés par Pandas")
    contenu = models.JSONField(default=dict, blank=True, verbose_name="Contenu du rapport")
    modele_ollama = models.CharField(max_length=100, blank=True, verbose_name="Modèle Ollama")
    date_creation = models.DateTimeField(auto_now_add=True, verbose_name="Date de création")

    class Meta:
        ordering = ["-date_creation"]
        verbose_name = "Rapport de jeu de données"
        verbose_name_plural = "Rapports de jeux de données"

    def __str__(self):
        return f"Rapport — {self.jeu_donnees}"
