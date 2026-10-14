from django.urls import path

from . import views

app_name = "ai_assistant"

urlpatterns = [
    path("jeu-donnees/<int:pk>/rapport/", views.rapport_jeu_donnees, name="rapport_jeu_donnees"),
    path("jeu-donnees/<int:pk>/rapport/generer/", views.generer_rapport_jeu_donnees, name="generer_rapport_jeu_donnees"),
    path("jeu-donnees/<int:pk>/rapport/modifier/", views.modifier_rapport_jeu_donnees, name="modifier_rapport_jeu_donnees"),
    path(
        "tableau-bord/<int:pk>/",
        views.espace_assiste,
        name="espace_assiste",
    ),
    path(
        "tableau-bord/<int:pk>/reanalyser/",
        views.reanalyser,
        name="reanalyser",
    ),
    path(
        "tableau-bord/<int:pk>/suggestions/regenerer/",
        views.regenerer_suggestions,
        name="regenerer_suggestions",
    ),
    path(
        "tableau-bord/<int:pk>/chat/",
        views.envoyer_message,
        name="envoyer_message",
    ),
    path(
        "tableau-bord/<int:pk>/chat/effacer/",
        views.effacer_conversation,
        name="effacer_conversation",
    ),
    path(
        "tableau-bord/<int:pk>/suggestions/creer-selection/",
        views.creer_selection_suggestions,
        name="creer_selection_suggestions",
    ),
    path(
        "suggestion/<int:pk>/modifier/",
        views.modifier_suggestion,
        name="modifier_suggestion",
    ),
    path(
        "suggestion/<int:pk>/supprimer/",
        views.supprimer_suggestion,
        name="supprimer_suggestion",
    ),
    path(
        "suggestion/<int:pk>/creer/",
        views.creer_depuis_suggestion,
        name="creer_depuis_suggestion",
    ),
    path(
        "tableau-bord/<int:pk>/rapport/",
        views.rapport_statistique,
        name="rapport",
    ),
    path(
        "tableau-bord/<int:pk>/rapport/modifier/",
        views.modifier_rapport,
        name="modifier_rapport",
    ),
    path(
        "tableau-bord/<int:pk>/rapport/generer/",
        views.generer_rapport,
        name="generer_rapport",
    ),
]
