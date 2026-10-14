from __future__ import annotations

import json
from datetime import timedelta

from django.apps import apps
from django.contrib.auth.decorators import (
    login_required,
)
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.utils.dateparse import (
    parse_date,
)
from django.views.decorators.http import (
    require_POST,
)
from django.core.exceptions import PermissionDenied

from .models import JournalActivite
from .services import journaliser_action


def est_administrateur(
    utilisateur,
):
    return bool(
        utilisateur.is_superuser
        or utilisateur.is_staff
        or getattr(
            utilisateur,
            "est_administrateur",
            False,
        )
        or getattr(
            utilisateur,
            "role",
            "",
        )
        == "ADMIN"
    )


def journal_autorise(
    utilisateur,
):
    queryset = (
        JournalActivite.objects
        .select_related(
            "utilisateur"
        )
        .all()
    )

    if not est_administrateur(
        utilisateur
    ):
        queryset = queryset.filter(
            utilisateur=utilisateur
        )

    return queryset


@login_required
@login_required
def liste_journal(
    request,
):
    """
    Affiche le journal complet uniquement
    aux administrateurs.

    Les utilisateurs métier ne peuvent pas
    accéder à cette page, même en saisissant
    directement son adresse.
    """

    if not est_administrateur(
        request.user
    ):
        raise PermissionDenied(
            (
                "Le journal d’activité est "
                "réservé aux administrateurs."
            )
        )

    administrateur = True

    # Base complète du journal.
    base_journal = (
        JournalActivite.objects
        .select_related(
            "utilisateur"
        )
        .all()
    )

    # Copie qui recevra les filtres.
    queryset = base_journal

    recherche = str(
        request.GET.get(
            "q",
            "",
        )
        or ""
    ).strip()

    action = str(
        request.GET.get(
            "action",
            "",
        )
        or ""
    ).strip()

    module = str(
        request.GET.get(
            "module",
            "",
        )
        or ""
    ).strip()

    date_debut_texte = str(
        request.GET.get(
            "date_debut",
            "",
        )
        or ""
    ).strip()

    date_fin_texte = str(
        request.GET.get(
            "date_fin",
            "",
        )
        or ""
    ).strip()

    # ==================================================
    # RECHERCHE
    # ==================================================

    if recherche:
        queryset = queryset.filter(
            Q(
                description__icontains=(
                    recherche
                )
            )
            |
            Q(
                objet_libelle__icontains=(
                    recherche
                )
            )
            |
            Q(
                objet_type__icontains=(
                    recherche
                )
            )
            |
            Q(
                module__icontains=(
                    recherche
                )
            )
            |
            Q(
                utilisateur__email__icontains=(
                    recherche
                )
            )
            |
            Q(
                utilisateur__first_name__icontains=(
                    recherche
                )
            )
            |
            Q(
                utilisateur__last_name__icontains=(
                    recherche
                )
            )
        )

    # ==================================================
    # FILTRE PAR ACTION
    # ==================================================

    actions_valides = {
        valeur
        for valeur, _
        in JournalActivite.Action.choices
    }

    if action in actions_valides:
        queryset = queryset.filter(
            action=action
        )

    # ==================================================
    # FILTRE PAR MODULE
    # ==================================================

    if module:
        queryset = queryset.filter(
            module=module
        )

    # ==================================================
    # FILTRE PAR DATE
    # ==================================================

    date_debut = parse_date(
        date_debut_texte
    )

    date_fin = parse_date(
        date_fin_texte
    )

    if date_debut:
        queryset = queryset.filter(
            date_action__date__gte=(
                date_debut
            )
        )

    if date_fin:
        queryset = queryset.filter(
            date_action__date__lte=(
                date_fin
            )
        )

    # ==================================================
    # LISTE DES MODULES
    # ==================================================

    modules = (
        base_journal
        .exclude(
            module=""
        )
        .values_list(
            "module",
            flat=True,
        )
        .distinct()
        .order_by(
            "module"
        )
    )

    # ==================================================
    # STATISTIQUES
    # ==================================================

    maintenant = timezone.now()

    debut_jour = maintenant.replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )

    statistiques = {
        "total":
        base_journal.count(),

        "aujourdhui":
        base_journal.filter(
            date_action__gte=debut_jour
        ).count(),

        "sept_jours":
        base_journal.filter(
            date_action__gte=(
                maintenant
                - timedelta(
                    days=7
                )
            )
        ).count(),

        "exports":
        base_journal.filter(
            action=(
                JournalActivite
                .Action
                .EXPORTATION
            )
        ).count(),
    }

    # ==================================================
    # PAGINATION
    # ==================================================

    pagination = Paginator(
        queryset,
        20,
    )

    page_obj = pagination.get_page(
        request.GET.get(
            "page"
        )
    )

    # Conserve les filtres lors du passage
    # à la page suivante.
    parametres = request.GET.copy()

    parametres.pop(
        "page",
        None,
    )

    return render(
        request,
        "audit/journal.html",
        {
            "page_obj":
            page_obj,

            "administrateur":
            administrateur,

            "actions":
            JournalActivite.Action.choices,

            "modules":
            modules,

            "recherche":
            recherche,

            "action_selectionnee":
            action,

            "module_selectionne":
            module,

            "date_debut":
            date_debut_texte,

            "date_fin":
            date_fin_texte,

            "statistiques":
            statistiques,

            "query_string":
            parametres.urlencode(),
        },
    )

def tableau_autorise(
    utilisateur,
    tableau_bord,
):
    methode = getattr(
        tableau_bord,
        "utilisateur_autorise",
        None,
    )

    if callable(
        methode
    ):
        return bool(
            methode(
                utilisateur
            )
        )

    proprietaire_id = getattr(
        tableau_bord,
        "proprietaire_id",
        None,
    )

    return bool(
        est_administrateur(
            utilisateur
        )
        or proprietaire_id
        == utilisateur.pk
    )


@login_required
@require_POST
def enregistrer_export(
    request,
):
    """
    Les exports PNG/PDF sont réalisés côté navigateur.
    Cette vue permet de journaliser le succès
    après la création du fichier.
    """

    try:
        donnees = json.loads(
            request.body.decode(
                "utf-8"
            )
        )

    except (
        json.JSONDecodeError,
        UnicodeDecodeError,
    ):
        return JsonResponse(
            {
                "ok":
                False,

                "erreur":
                "Requête JSON invalide.",
            },
            status=400,
        )

    objet_type = str(
        donnees.get(
            "objet_type",
            "",
        )
        or ""
    ).strip()

    objet_id = donnees.get(
        "objet_id"
    )

    format_export = str(
        donnees.get(
            "format",
            "",
        )
        or ""
    ).upper().strip()

    formats_autorises = {
        "PNG",
        "PDF",
        "CSV",
        "XLSX",
    }

    if (
        format_export
        not in formats_autorises
    ):
        return JsonResponse(
            {
                "ok":
                False,

                "erreur":
                "Format d’export non autorisé.",
            },
            status=400,
        )

    TableauBord = apps.get_model(
        "dashboards",
        "TableauBord",
    )

    Widget = apps.get_model(
        "dashboards",
        "Widget",
    )

    if objet_type == "tableau_bord":
        try:
            objet = (
                TableauBord.objects
                .select_related(
                    "proprietaire"
                )
                .get(
                    pk=objet_id
                )
            )

        except TableauBord.DoesNotExist:
            return JsonResponse(
                {
                    "ok":
                    False,

                    "erreur":
                    "Tableau de bord introuvable.",
                },
                status=404,
            )

        tableau_bord = objet

        libelle = objet.titre

        type_libelle = (
            "Tableau de bord"
        )

    elif objet_type == "widget":
        try:
            objet = (
                Widget.objects
                .select_related(
                    "tableau_bord",
                    "tableau_bord__proprietaire",
                )
                .get(
                    pk=objet_id
                )
            )

        except Widget.DoesNotExist:
            return JsonResponse(
                {
                    "ok":
                    False,

                    "erreur":
                    "Widget introuvable.",
                },
                status=404,
            )

        tableau_bord = (
            objet.tableau_bord
        )

        libelle = objet.titre

        type_libelle = "Widget"

    else:
        return JsonResponse(
            {
                "ok":
                False,

                "erreur":
                "Type d’objet non autorisé.",
            },
            status=400,
        )

    if not tableau_autorise(
        request.user,
        tableau_bord,
    ):
        return JsonResponse(
            {
                "ok":
                False,

                "erreur":
                "Accès refusé.",
            },
            status=403,
        )

    journaliser_action(
        utilisateur=request.user,

        action=(
            JournalActivite
            .Action
            .EXPORTATION
        ),

        niveau=(
            JournalActivite
            .Niveau
            .SUCCES
        ),

        module="Exports",

        objet_type=type_libelle,

        objet_id=getattr(
            objet,
            "pk",
            "",
        ),

        objet_libelle=libelle,

        description=(
            f"Export {format_export} de "
            f"« {libelle} »."
        ),

        metadata={
            "format":
            format_export,

            "type_export":
            objet_type,
        },

        request=request,
    )

    return JsonResponse(
        {
            "ok":
            True,
        }
    )
