from django.urls import path

from . import views


urlpatterns = [
    path(
        "inscription/",
        views.inscription,
        name="inscription",
    ),
    path(
        "inscription/confirmee/",
        views.inscription_confirmee,
        name="inscription_confirmee",
    ),
    path(
        "profil/",
        views.profil,
        name="profil",
    ),
    path(
        "profil/modifier/",
        views.modifier_profil,
        name="modifier_profil",
    ),
    path(
        "profil/preferences/",
        views.preferences_compte,
        name="preferences_compte",
    ),
    path(
        "profil/mot-de-passe/",
        views.changer_mot_de_passe,
        name="changer_mot_de_passe",
    ),
]
