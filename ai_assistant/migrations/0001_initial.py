from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("datasets", "0001_initial"),
        ("dashboards", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="AnalyseJeuDonnees",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "empreinte",
                    models.CharField(
                        db_index=True,
                        max_length=64,
                        verbose_name="Empreinte du jeu de données",
                    ),
                ),
                (
                    "schema",
                    models.JSONField(
                        blank=True,
                        default=dict,
                        verbose_name="Schéma analysé",
                    ),
                ),
                (
                    "statistiques",
                    models.JSONField(
                        blank=True,
                        default=dict,
                        verbose_name="Statistiques calculées",
                    ),
                ),
                (
                    "relations",
                    models.JSONField(
                        blank=True,
                        default=list,
                        verbose_name="Relations possibles",
                    ),
                ),
                (
                    "indicateurs",
                    models.JSONField(
                        blank=True,
                        default=list,
                        verbose_name="Indicateurs calculables",
                    ),
                ),
                (
                    "statut",
                    models.CharField(
                        choices=[
                            ("PRETE", "Prête"),
                            ("ERREUR", "Erreur"),
                        ],
                        default="PRETE",
                        max_length=20,
                        verbose_name="Statut",
                    ),
                ),
                (
                    "message_erreur",
                    models.TextField(
                        blank=True,
                        verbose_name="Message d’erreur",
                    ),
                ),
                (
                    "date_analyse",
                    models.DateTimeField(
                        auto_now=True,
                        verbose_name="Dernière analyse",
                    ),
                ),
                (
                    "jeu_donnees",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="analyse_intelligente",
                        to="datasets.jeudonnees",
                        verbose_name="Jeu de données",
                    ),
                ),
            ],
            options={
                "verbose_name": "Analyse intelligente",
                "verbose_name_plural": "Analyses intelligentes",
            },
        ),
        migrations.CreateModel(
            name="RapportStatistiqueIA",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "donnees_calculees",
                    models.JSONField(
                        blank=True,
                        default=dict,
                        verbose_name="Résultats calculés par Pandas",
                    ),
                ),
                (
                    "contenu",
                    models.JSONField(
                        blank=True,
                        default=dict,
                        verbose_name="Interprétation rédigée",
                    ),
                ),
                (
                    "modele_ollama",
                    models.CharField(
                        blank=True,
                        max_length=100,
                        verbose_name="Modèle Ollama",
                    ),
                ),
                (
                    "date_creation",
                    models.DateTimeField(
                        auto_now_add=True,
                        verbose_name="Date de création",
                    ),
                ),
                (
                    "auteur",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="rapports_statistiques_ia",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Auteur",
                    ),
                ),
                (
                    "tableau_bord",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="rapports_ia",
                        to="dashboards.tableaubord",
                        verbose_name="Tableau de bord",
                    ),
                ),
            ],
            options={
                "verbose_name": "Rapport statistique intelligent",
                "verbose_name_plural": "Rapports statistiques intelligents",
                "ordering": ["-date_creation"],
            },
        ),
        migrations.CreateModel(
            name="SuggestionWidget",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "source",
                    models.CharField(
                        choices=[
                            ("AUTOMATIQUE", "Analyse automatique"),
                            ("CONVERSATION", "Assistant conversationnel"),
                        ],
                        default="AUTOMATIQUE",
                        max_length=20,
                        verbose_name="Source",
                    ),
                ),
                (
                    "configuration",
                    models.JSONField(
                        default=dict,
                        verbose_name="Configuration proposée",
                    ),
                ),
                (
                    "justification",
                    models.TextField(
                        blank=True,
                        verbose_name="Justification",
                    ),
                ),
                (
                    "statut",
                    models.CharField(
                        choices=[
                            ("PROPOSEE", "Proposée"),
                            ("ACCEPTEE", "Acceptée"),
                            ("SUPPRIMEE", "Supprimée"),
                        ],
                        default="PROPOSEE",
                        max_length=20,
                        verbose_name="Statut",
                    ),
                ),
                (
                    "date_creation",
                    models.DateTimeField(
                        auto_now_add=True,
                        verbose_name="Date de création",
                    ),
                ),
                (
                    "date_modification",
                    models.DateTimeField(
                        auto_now=True,
                        verbose_name="Dernière modification",
                    ),
                ),
                (
                    "analyse",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="suggestions",
                        to="ai_assistant.analysejeudonnees",
                        verbose_name="Analyse utilisée",
                    ),
                ),
                (
                    "tableau_bord",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="suggestions_ia",
                        to="dashboards.tableaubord",
                        verbose_name="Tableau de bord",
                    ),
                ),
                (
                    "widget_cree",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="suggestion_source",
                        to="dashboards.widget",
                        verbose_name="Widget créé",
                    ),
                ),
            ],
            options={
                "verbose_name": "Suggestion de widget",
                "verbose_name_plural": "Suggestions de widgets",
                "ordering": ["-date_creation"],
            },
        ),
    ]
