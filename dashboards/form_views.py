from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from .forms import TableauBordForm
from .models import TableauBord


def est_administrateur(utilisateur) -> bool:
    """Vérifie les différents indicateurs administrateur du projet."""
    return bool(
        utilisateur.is_superuser
        or utilisateur.is_staff
        or getattr(utilisateur, "est_administrateur", False)
        or getattr(utilisateur, "role", "") == "ADMIN"
    )


def nom_champ_proprietaire(modele) -> str | None:
    """Retourne le champ propriétaire disponible sur le modèle."""
    noms_champs = {
        champ.name
        for champ in modele._meta.get_fields()
    }

    for nom in (
        "proprietaire",
        "utilisateur_metier",
        "utilisateur",
        "createur",
    ):
        if nom in noms_champs:
            return nom

    return None


def recuperer_tableau_autorise(utilisateur, pk):
    """Retourne un tableau de bord accessible à l’utilisateur."""
    queryset = TableauBord.objects.select_related(
        "jeu_donnees"
    )

    champ_proprietaire = nom_champ_proprietaire(
        TableauBord
    )

    if (
        champ_proprietaire
        and not est_administrateur(utilisateur)
    ):
        queryset = queryset.filter(
            **{
                champ_proprietaire:
                utilisateur
            }
        )

    return get_object_or_404(
        queryset,
        pk=pk,
    )


@login_required
def creer_tableau_bord(request):
    """Affiche et traite le formulaire de création."""
    form = TableauBordForm(
        request.POST or None,
        utilisateur=request.user,
    )

    aucun_jeu_nettoye = not (
        form.fields["jeu_donnees"]
        .queryset
        .exists()
    )

    if (
        request.method == "POST"
        and form.is_valid()
        and not aucun_jeu_nettoye
    ):
        tableau_bord = form.save(
            commit=False
        )

        champ_proprietaire = (
            nom_champ_proprietaire(
                TableauBord
            )
        )

        if champ_proprietaire:
            setattr(
                tableau_bord,
                champ_proprietaire,
                request.user,
            )

        tableau_bord.save()

        messages.success(
            request,
            "Le tableau de bord a été créé avec succès.",
        )

        return redirect(
            "dashboards:detail",
            pk=tableau_bord.pk,
        )

    return render(
        request,
        "dashboards/formulaire.html",
        {
            "form": form,
            "mode_modification": False,
            "tableau_bord": None,
            "aucun_jeu_nettoye": aucun_jeu_nettoye,
        },
    )


@login_required
def modifier_tableau_bord(request, pk):
    """Affiche et traite le formulaire de modification."""
    tableau_bord = recuperer_tableau_autorise(
        request.user,
        pk,
    )

    form = TableauBordForm(
        request.POST or None,
        instance=tableau_bord,
        utilisateur=request.user,
    )

    if (
        request.method == "POST"
        and form.is_valid()
    ):
        form.save()

        messages.success(
            request,
            "Le tableau de bord a été modifié avec succès.",
        )

        return redirect(
            "dashboards:detail",
            pk=tableau_bord.pk,
        )

    return render(
        request,
        "dashboards/formulaire.html",
        {
            "form": form,
            "mode_modification": True,
            "tableau_bord": tableau_bord,
            "aucun_jeu_nettoye": False,
        },
    )
