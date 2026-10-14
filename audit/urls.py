from django.urls import path

from . import views


app_name = "audit"


urlpatterns = [
    path(
        "",
        views.liste_journal,
        name="liste",
    ),

    path(
        "exports/enregistrer/",
        views.enregistrer_export,
        name="enregistrer_export",
    ),
]
