from __future__ import annotations

from django.contrib.auth.decorators import (
    login_required,
)
from django.shortcuts import render

from .forms import construire_profils_colonnes
from .views import recuperer_tableau_autorise


def recommander_visualisation(
    profil,
) -> str:
    """
    Retourne une recommandation courte et simple
    pour aider l'utilisateur à choisir un widget.
    """

    type_colonne = str(
        profil.get(
            "type",
            "",
        )
        or ""
    )

    nombre_uniques = int(
        profil.get(
            "nombre_uniques",
            0,
        )
        or 0
    )

    semble_identifiant = bool(
        profil.get(
            "semble_identifiant",
            False,
        )
    )

    if semble_identifiant:
        return "Identifiant : éviter comme axe principal"

    if type_colonne == "DATE":
        return "Courbe pour suivre l’évolution"

    if type_colonne == "NUMÉRIQUE":
        return "Indicateur, histogramme ou mesure"

    if type_colonne == "TEXTE":
        if nombre_uniques <= 8:
            return "Barres ou camembert"

        return "Barres ou tableau"

    return "Tableau"


@login_required
def rapport_statistique(
    request,
    pk,
):
    """
    Affiche un rapport statistique compact du
    jeu de données utilisé par le tableau de bord.
    """

    tableau_bord = (
        recuperer_tableau_autorise(
            request.user,
            pk,
        )
    )

    profils = construire_profils_colonnes(
        tableau_bord.jeu_donnees
    )

    colonnes = []

    total_valeurs_manquantes = 0

    for nom, profil in profils.items():
        nombre_manquantes = int(
            profil.get(
                "nombre_manquantes",
                0,
            )
            or 0
        )

        total_valeurs_manquantes += (
            nombre_manquantes
        )

        colonnes.append(
            {
                "nom":
                nom,

                "type":
                profil.get(
                    "type",
                    "Inconnu",
                ),

                "nombre_uniques":
                int(
                    profil.get(
                        "nombre_uniques",
                        0,
                    )
                    or 0
                ),

                "nombre_manquantes":
                nombre_manquantes,

                "recommandation":
                recommander_visualisation(
                    profil
                ),
            }
        )

    nombre_lignes = int(
        getattr(
            tableau_bord.jeu_donnees,
            "nombre_lignes",
            0,
        )
        or 0
    )

    nombre_colonnes = len(
        colonnes
    )

    return render(
        request,
        (
            "dashboards/"
            "rapport_statistique.html"
        ),
        {
            "tableau_bord":
            tableau_bord,

            "jeu_donnees":
            tableau_bord.jeu_donnees,

            "nombre_lignes":
            nombre_lignes,

            "nombre_colonnes":
            nombre_colonnes,

            "total_valeurs_manquantes":
            total_valeurs_manquantes,

            "colonnes":
            colonnes,
        },
    )
