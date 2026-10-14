from __future__ import annotations

from typing import Any

from .middleware import (
    get_current_request,
)
from .models import JournalActivite


def utilisateur_authentifie(
    utilisateur,
):
    return bool(
        utilisateur
        and getattr(
            utilisateur,
            "is_authenticated",
            False,
        )
    )


def recuperer_adresse_ip(
    request,
):
    if request is None:
        return None

    transferee = request.META.get(
        "HTTP_X_FORWARDED_FOR",
        "",
    )

    if transferee:
        return (
            transferee
            .split(",")[0]
            .strip()
            or None
        )

    return (
        request.META.get(
            "REMOTE_ADDR"
        )
        or None
    )


def contexte_requete(
    request=None,
) -> dict[str, Any]:
    request = (
        request
        or get_current_request()
    )

    if request is None:
        return {
            "methode_http":
            "",

            "chemin":
            "",

            "adresse_ip":
            None,

            "user_agent":
            "",
        }

    return {
        "methode_http":
        str(
            getattr(
                request,
                "method",
                "",
            )
            or ""
        )[:10],

        "chemin":
        str(
            getattr(
                request,
                "path",
                "",
            )
            or ""
        )[:500],

        "adresse_ip":
        recuperer_adresse_ip(
            request
        ),

        "user_agent":
        str(
            request.META.get(
                "HTTP_USER_AGENT",
                "",
            )
            or ""
        )[:500],
    }


def acteur_requete(
    request=None,
):
    request = (
        request
        or get_current_request()
    )

    if request is None:
        return None

    utilisateur = getattr(
        request,
        "user",
        None,
    )

    if utilisateur_authentifie(
        utilisateur
    ):
        return utilisateur

    return None


def journaliser_action(
    *,
    action,
    module,
    description,
    utilisateur=None,
    niveau=JournalActivite.Niveau.INFO,
    objet_type="",
    objet_id="",
    objet_libelle="",
    metadata=None,
    request=None,
):
    """
    Point unique utilisé par les signaux
    et par les vues explicites, comme les exports.
    """

    if utilisateur is None:
        utilisateur = acteur_requete(
            request
        )

    utilisateur_id = (
        getattr(
            utilisateur,
            "pk",
            None,
        )
        if utilisateur_authentifie(
            utilisateur
        )
        else None
    )

    contexte = contexte_requete(
        request
    )

    return JournalActivite.objects.create(
        utilisateur_id=utilisateur_id,

        action=action,

        niveau=niveau,

        module=str(
            module
            or "Plateforme"
        )[:100],

        objet_type=str(
            objet_type
            or ""
        )[:100],

        objet_id=str(
            objet_id
            or ""
        )[:100],

        objet_libelle=str(
            objet_libelle
            or ""
        )[:255],

        description=str(
            description
            or ""
        ),

        metadata=(
            metadata
            if isinstance(
                metadata,
                dict,
            )
            else {}
        ),

        **contexte,
    )
