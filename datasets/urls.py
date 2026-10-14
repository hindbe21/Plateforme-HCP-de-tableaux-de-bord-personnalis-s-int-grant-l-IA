from django.urls import path

from . import report_views
from . import views


app_name = "datasets"


urlpatterns = [
    path(
        "",
        views.liste_jeux_donnees,
        name="liste",
    ),
    path(
        "importer/",
        views.importer_jeu_donnees,
        name="importer",
    ),
    path(
        "<int:pk>/modifier/",
        views.modifier_jeu_donnees,
        name="modifier",
    ),
    path(
        "<int:pk>/apercu-complet/",
        views.apercu_complet_jeu_donnees,
        name="apercu_complet",
    ),
    path(
        "<int:pk>/nettoyer/",
        views.nettoyer_jeu_donnees,
        name="nettoyer",
    ),
    path(
        "<int:pk>/supprimer/",
        views.supprimer_jeu_donnees,
        name="supprimer",
    ),
    path(
        "<int:pk>/rapport-statistique/",
        report_views.rapport_statistique,
        name="rapport_statistique",
    ),
    path(
        "<int:pk>/",
        views.detail_jeu_donnees,
        name="detail",
    ),
]
