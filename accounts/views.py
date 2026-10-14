from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from .forms import (
    ChangementMotDePasseForm,
    InscriptionForm,
    PreferencesCompteForm,
    ProfilModificationForm,
)


PREFERENCES_PAR_DEFAUT = {
    "notifications": "STANDARD",
    "theme": "CLAIR",
    "langue": "FR",
    "fuseau_horaire": "Africa/Casablanca",
    "affichage_compact": False,
}

LIBELLES_PREFERENCES = {
    "notifications": {
        "STANDARD": "Standard",
        "IMPORTANTES": "Importantes uniquement",
        "AUCUNE": "Désactivées",
    },
    "theme": {
        "CLAIR": "Clair",
        "SOMBRE": "Sombre",
        "SYSTEME": "Selon le système",
    },
    "langue": {
        "FR": "Français",
    },
    "fuseau_horaire": {
        "Africa/Casablanca": "Casablanca",
    },
}


def _est_administrateur(utilisateur):
    return bool(
        utilisateur.is_superuser
        or utilisateur.is_staff
        or getattr(utilisateur, "est_administrateur", False)
        or getattr(utilisateur, "role", "") == "ADMIN"
    )


def _champ_proprietaire(modele):
    champs = {
        champ.name
        for champ in modele._meta.get_fields()
    }

    for nom in (
        "proprietaire",
        "utilisateur_metier",
        "utilisateur",
        "createur",
    ):
        if nom in champs:
            return nom

    return None


def _preferences(request):
    valeurs = PREFERENCES_PAR_DEFAUT.copy()
    valeurs.update(
        request.session.get("preferences_compte", {})
    )
    return valeurs


def _preferences_affichees(request):
    valeurs = _preferences(request)

    return {
        "notifications": LIBELLES_PREFERENCES["notifications"].get(
            valeurs["notifications"],
            "Standard",
        ),
        "theme": LIBELLES_PREFERENCES["theme"].get(
            valeurs["theme"],
            "Clair",
        ),
        "langue": LIBELLES_PREFERENCES["langue"].get(
            valeurs["langue"],
            "Français",
        ),
        "fuseau_horaire": LIBELLES_PREFERENCES["fuseau_horaire"].get(
            valeurs["fuseau_horaire"],
            "Casablanca",
        ),
        "affichage_compact": valeurs["affichage_compact"],
    }


@login_required
def home(request):
    """Page d'accueil toujours visible, même si un compteur échoue."""

    contexte = {
        "nombre_jeux_donnees": 0,
        "nombre_tableaux_bord": 0,
        "nombre_widgets": 0,
        "securite_conformite": 100,
        "jeux_recents": [],
        "tableaux_recents": [],
    }

    try:
        from datasets.models import JeuDonnees
        from dashboards.models import TableauBord, Widget

        jeux_donnees = JeuDonnees.objects.all()
        tableaux_bord = TableauBord.objects.all()

        if not _est_administrateur(request.user):
            champ_jeu = _champ_proprietaire(JeuDonnees)
            champ_tableau = _champ_proprietaire(TableauBord)

            if champ_jeu:
                jeux_donnees = jeux_donnees.filter(
                    **{champ_jeu: request.user}
                )

            if champ_tableau:
                tableaux_bord = tableaux_bord.filter(
                    **{champ_tableau: request.user}
                )

        widgets = Widget.objects.filter(
            tableau_bord__in=tableaux_bord
        )

        contexte.update(
            {
                "nombre_jeux_donnees": jeux_donnees.count(),
                "nombre_tableaux_bord": tableaux_bord.count(),
                "nombre_widgets": widgets.count(),
                "jeux_recents": list(
                    jeux_donnees.order_by("-date_importation")[:4]
                ),
                "tableaux_recents": list(
                    tableaux_bord.order_by("-date_modification")[:4]
                ),
            }
        )
    except Exception:
        # Les accès rapides restent disponibles même si une statistique
        # secondaire ne peut momentanément pas être calculée.
        pass

    return render(
        request,
        "accounts/home.html",
        contexte,
    )


def inscription(request):
    if request.user.is_authenticated:
        return redirect("home")

    form = InscriptionForm(
        request.POST or None
    )

    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("inscription_confirmee")

    return render(
        request,
        "accounts/inscription.html",
        {"form": form},
    )


def inscription_confirmee(request):
    return render(
        request,
        "accounts/inscription_confirmee.html",
    )


@login_required
def profil(request):
    return render(
        request,
        "accounts/profil.html",
        {
            "utilisateur": request.user,
            "preferences": _preferences_affichees(request),
        },
    )


@login_required
def modifier_profil(request):
    form = ProfilModificationForm(
        request.POST or None,
        instance=request.user,
    )

    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(
            request,
            "Vos informations personnelles ont été mises à jour.",
        )
        return redirect("profil")

    return render(
        request,
        "accounts/modifier_profil.html",
        {"form": form},
    )


@login_required
def preferences_compte(request):
    """Gère les préférences sans modifier le nom, l'email ou le rôle."""

    form = PreferencesCompteForm(
        request.POST or None,
        initial=_preferences(request),
    )

    if request.method == "POST" and form.is_valid():
        request.session["preferences_compte"] = {
            "notifications": form.cleaned_data["notifications"],
            "theme": form.cleaned_data["theme"],
            "langue": form.cleaned_data["langue"],
            "fuseau_horaire": form.cleaned_data["fuseau_horaire"],
            "affichage_compact": form.cleaned_data["affichage_compact"],
        }
        request.session.modified = True

        messages.success(
            request,
            "Les paramètres du compte ont été enregistrés.",
        )
        return redirect("profil")

    return render(
        request,
        "accounts/preferences.html",
        {"form": form},
    )


@login_required
def changer_mot_de_passe(request):
    form = ChangementMotDePasseForm(
        request.user,
        request.POST or None,
    )

    if request.method == "POST" and form.is_valid():
        utilisateur = form.save()
        update_session_auth_hash(request, utilisateur)

        messages.success(
            request,
            "Votre mot de passe a été modifié avec succès.",
        )
        return redirect("profil")

    return render(
        request,
        "accounts/changer_mot_de_passe.html",
        {"form": form},
    )
