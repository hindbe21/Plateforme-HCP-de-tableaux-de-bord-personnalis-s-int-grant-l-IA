from django.urls import path

from . import (
    ia_views,
    rapport_views,
    views,
)


app_name = "dashboards"


urlpatterns = [
    path(
        "",
        views.liste_tableaux_bord,
        name="liste",
    ),
    path(
        "creer/",
        views.creer_tableau_bord,
        name="creer",
    ),

    # Widgets
    path(
        "<int:pk>/widgets/ajouter/",
        views.ajouter_widget,
        name="ajouter_widget",
    ),
    path(
        "<int:pk>/widgets/assistant-ia/",
        ia_views.assistant_widget_ia,
        name="assistant_widget_ia",
    ),
    path(
        "widgets/<int:pk>/modifier/",
        views.modifier_widget,
        name="modifier_widget",
    ),
    path(
        "widgets/<int:pk>/supprimer/",
        views.supprimer_widget,
        name="supprimer_widget",
    ),

    # Filtres globaux
    path(
        "<int:pk>/filtres/ajouter/",
        views.ajouter_filtre,
        name="ajouter_filtre",
    ),
    path(
        "filtres/<int:pk>/supprimer/",
        views.supprimer_filtre,
        name="supprimer_filtre",
    ),

    # Filtres propres à un widget
    path(
        "widgets/<int:pk>/filtres/ajouter/",
        views.ajouter_filtre_widget,
        name="ajouter_filtre_widget",
    ),
    path(
        "filtres-widgets/<int:pk>/supprimer/",
        views.supprimer_filtre_widget,
        name="supprimer_filtre_widget",
    ),

    # Tableaux de bord
    path(
        "<int:pk>/modifier/",
        views.modifier_tableau_bord,
        name="modifier",
    ),
    path(
        "<int:pk>/supprimer/",
        views.supprimer_tableau_bord,
        name="supprimer",
    ),
    path(
    "<int:pk>/rapport-statistique/",
    rapport_views.rapport_statistique,
    name="rapport_statistique",
),
    path(
        "<int:pk>/",
        views.detail_tableau_bord,
        name="detail",
    ),
]
