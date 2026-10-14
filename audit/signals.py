from __future__ import annotations

from django.contrib.auth.signals import (
    user_logged_in,
    user_logged_out,
)
from django.db import transaction
from django.db.models.signals import (
    post_delete,
    post_save,
)
from django.dispatch import receiver

from .models import JournalActivite
from .services import (
    acteur_requete,
    journaliser_action,
)


MODELES_SUIVIS = {
    "accounts.User": {
        "module":
        "Utilisateurs",

        "objet_type":
        "Utilisateur",
    },

    "datasets.JeuDonnees": {
        "module":
        "Jeux de données",

        "objet_type":
        "Jeu de données",
    },

    "datasets.OperationNettoyage": {
        "module":
        "Nettoyage",

        "objet_type":
        "Opération de nettoyage",
    },

    "dashboards.TableauBord": {
        "module":
        "Tableaux de bord",

        "objet_type":
        "Tableau de bord",
    },

    "dashboards.Widget": {
        "module":
        "Widgets",

        "objet_type":
        "Widget",
    },

    "dashboards.Filtre": {
        "module":
        "Filtres",

        "objet_type":
        "Filtre global",
    },

    "dashboards.FiltreWidget": {
        "module":
        "Filtres",

        "objet_type":
        "Filtre de widget",
    },
}


def libelle_instance(
    instance,
):
    try:
        valeur = str(
            instance
        ).strip()

    except Exception:
        valeur = ""

    if valeur:
        return valeur[:255]

    return (
        f"{instance._meta.verbose_name} "
        f"#{getattr(instance, 'pk', '')}"
    )[:255]


def utilisateur_instance(
    instance,
):
    for nom_champ in (
        "utilisateur",
        "proprietaire",
        "createur",
        "utilisateur_metier",
    ):
        utilisateur = getattr(
            instance,
            nom_champ,
            None,
        )

        if (
            utilisateur is not None
            and getattr(
                utilisateur,
                "is_authenticated",
                True,
            )
        ):
            return utilisateur

    tableau_bord = getattr(
        instance,
        "tableau_bord",
        None,
    )

    if tableau_bord is not None:
        return getattr(
            tableau_bord,
            "proprietaire",
            None,
        )

    widget = getattr(
        instance,
        "widget",
        None,
    )

    if widget is not None:
        tableau_bord = getattr(
            widget,
            "tableau_bord",
            None,
        )

        if tableau_bord is not None:
            return getattr(
                tableau_bord,
                "proprietaire",
                None,
            )

    return None


def determiner_creation(
    label_modele,
    instance,
):
    if label_modele == "accounts.User":
        return (
            JournalActivite.Action.INSCRIPTION,
            JournalActivite.Niveau.INFO,
            (
                "Création d’un nouveau compte "
                f"« {libelle_instance(instance)} »."
            ),
        )

    if label_modele == "datasets.JeuDonnees":
        type_version = str(
            getattr(
                instance,
                "type_version",
                "",
            )
            or ""
        ).upper()

        # La version nettoyée sera journalisée
        # par OperationNettoyage afin d’éviter
        # deux lignes pour la même opération.
        if type_version == "NETTOYEE":
            return None

        return (
            JournalActivite.Action.IMPORTATION,
            JournalActivite.Niveau.SUCCES,
            (
                "Importation du jeu de données "
                f"« {libelle_instance(instance)} »."
            ),
        )

    if (
        label_modele
        == "datasets.OperationNettoyage"
    ):
        return (
            JournalActivite.Action.NETTOYAGE,
            JournalActivite.Niveau.SUCCES,
            (
                "Création d’une nouvelle version "
                "après nettoyage des données."
            ),
        )

    if label_modele in {
        "dashboards.Filtre",
        "dashboards.FiltreWidget",
    }:
        return (
            JournalActivite.Action.FILTRAGE,
            JournalActivite.Niveau.SUCCES,
            (
                "Ajout du filtre "
                f"« {libelle_instance(instance)} »."
            ),
        )

    return (
        JournalActivite.Action.CREATION,
        JournalActivite.Niveau.SUCCES,
        (
            f"Création de "
            f"« {libelle_instance(instance)} »."
        ),
    )


def determiner_modification(
    label_modele,
    instance,
):
    if label_modele == "accounts.User":
        return (
            JournalActivite.Action.ADMINISTRATION,
            JournalActivite.Niveau.INFO,
            (
                "Mise à jour du compte "
                f"« {libelle_instance(instance)} »."
            ),
        )

    if label_modele in {
        "dashboards.Filtre",
        "dashboards.FiltreWidget",
    }:
        return (
            JournalActivite.Action.FILTRAGE,
            JournalActivite.Niveau.INFO,
            (
                "Modification du filtre "
                f"« {libelle_instance(instance)} »."
            ),
        )

    return (
        JournalActivite.Action.MODIFICATION,
        JournalActivite.Niveau.INFO,
        (
            f"Modification de "
            f"« {libelle_instance(instance)} »."
        ),
    )


@receiver(
    user_logged_in
)
def enregistrer_connexion(
    sender,
    request,
    user,
    **kwargs,
):
    journaliser_action(
        utilisateur=user,

        action=(
            JournalActivite
            .Action
            .CONNEXION
        ),

        niveau=(
            JournalActivite
            .Niveau
            .SUCCES
        ),

        module="Authentification",

        objet_type="Session",

        objet_id=getattr(
            user,
            "pk",
            "",
        ),

        objet_libelle=getattr(
            user,
            "email",
            "",
        ),

        description=(
            "Connexion réussie à la plateforme."
        ),

        request=request,
    )


@receiver(
    user_logged_out
)
def enregistrer_deconnexion(
    sender,
    request,
    user,
    **kwargs,
):
    if user is None:
        return

    journaliser_action(
        utilisateur=user,

        action=(
            JournalActivite
            .Action
            .DECONNEXION
        ),

        niveau=(
            JournalActivite
            .Niveau
            .INFO
        ),

        module="Authentification",

        objet_type="Session",

        objet_id=getattr(
            user,
            "pk",
            "",
        ),

        objet_libelle=getattr(
            user,
            "email",
            "",
        ),

        description=(
            "Déconnexion de la plateforme."
        ),

        request=request,
    )


@receiver(
    post_save
)
def enregistrer_sauvegarde(
    sender,
    instance,
    created,
    raw=False,
    update_fields=None,
    **kwargs,
):
    if raw:
        return

    label_modele = getattr(
        sender._meta,
        "label",
        "",
    )

    configuration = MODELES_SUIVIS.get(
        label_modele
    )

    if configuration is None:
        return

    # La connexion met automatiquement à jour
    # last_login. Cette modification ne doit pas
    # créer une seconde ligne dans le journal.
    if (
        label_modele == "accounts.User"
        and update_fields
        and set(update_fields)
        <= {"last_login"}
    ):
        return

    if created:
        resultat = determiner_creation(
            label_modele,
            instance,
        )

    else:
        resultat = determiner_modification(
            label_modele,
            instance,
        )

    if resultat is None:
        return

    (
        action,
        niveau,
        description,
    ) = resultat

    acteur = (
        acteur_requete()
        or utilisateur_instance(
            instance
        )
    )

    objet_id = getattr(
        instance,
        "pk",
        "",
    )

    objet_libelle = libelle_instance(
        instance
    )

    metadata = {
        "modele":
        label_modele,

        "creation":
        bool(created),
    }

    transaction.on_commit(
        lambda: journaliser_action(
            utilisateur=acteur,

            action=action,

            niveau=niveau,

            module=configuration[
                "module"
            ],

            objet_type=configuration[
                "objet_type"
            ],

            objet_id=objet_id,

            objet_libelle=objet_libelle,

            description=description,

            metadata=metadata,
        )
    )


@receiver(
    post_delete
)
def enregistrer_suppression(
    sender,
    instance,
    **kwargs,
):
    label_modele = getattr(
        sender._meta,
        "label",
        "",
    )

    configuration = MODELES_SUIVIS.get(
        label_modele
    )

    if configuration is None:
        return

    acteur = (
        acteur_requete()
        or utilisateur_instance(
            instance
        )
    )

    objet_id = getattr(
        instance,
        "pk",
        "",
    )

    objet_libelle = libelle_instance(
        instance
    )

    transaction.on_commit(
        lambda: journaliser_action(
            utilisateur=acteur,

            action=(
                JournalActivite
                .Action
                .SUPPRESSION
            ),

            niveau=(
                JournalActivite
                .Niveau
                .ATTENTION
            ),

            module=configuration[
                "module"
            ],

            objet_type=configuration[
                "objet_type"
            ],

            objet_id=objet_id,

            objet_libelle=objet_libelle,

            description=(
                f"Suppression de "
                f"« {objet_libelle} »."
            ),

            metadata={
                "modele":
                label_modele,
            },
        )
    )
