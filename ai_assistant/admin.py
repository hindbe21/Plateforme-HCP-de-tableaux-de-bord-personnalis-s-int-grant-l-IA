from django.contrib import admin

from .models import (
    AnalyseJeuDonnees,
    RapportStatistiqueIA,
    SuggestionWidget,
)


@admin.register(AnalyseJeuDonnees)
class AnalyseJeuDonneesAdmin(admin.ModelAdmin):
    list_display = (
        "jeu_donnees",
        "statut",
        "date_analyse",
    )
    list_filter = ("statut", "date_analyse")
    search_fields = ("jeu_donnees__nom",)
    readonly_fields = ("date_analyse",)


@admin.register(SuggestionWidget)
class SuggestionWidgetAdmin(admin.ModelAdmin):
    list_display = (
        "__str__",
        "tableau_bord",
        "source",
        "statut",
        "date_creation",
    )
    list_filter = ("source", "statut", "date_creation")
    search_fields = (
        "tableau_bord__titre",
        "justification",
    )


@admin.register(RapportStatistiqueIA)
class RapportStatistiqueIAAdmin(admin.ModelAdmin):
    list_display = (
        "tableau_bord",
        "auteur",
        "modele_ollama",
        "date_creation",
    )
    list_filter = ("date_creation", "modele_ollama")
    search_fields = ("tableau_bord__titre",)
