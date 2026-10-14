from copy import deepcopy
from datetime import timedelta
import traceback

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Q
from django.db.models.deletion import ProtectedError
from django.utils import timezone
from django.shortcuts import (
    get_object_or_404,
    redirect,
    render,
)

from .forms import (
    JeuDonneesImportForm,
    JeuDonneesModificationForm,
    NettoyageDonneesForm,
)
from .models import JeuDonnees
from .services import (
    analyser_fichier,
    appliquer_plan_nettoyage,
    charger_dataframe_postgresql,
    creer_apercu_dataframe,
    diagnostiquer_qualite,
    enregistrer_dans_postgresql,
    enregistrer_version_nettoyee,
)


def recuperer_jeu_donnees_autorise(
    utilisateur,
    pk,
):
    """
    Retourne le jeu de données demandé lorsque
    l'utilisateur a le droit de le consulter.

    Un administrateur peut consulter tous les jeux.
    Un utilisateur métier ne consulte que ses jeux.
    """

    queryset = JeuDonnees.objects.select_related(
        "proprietaire",
        "source_jeu_donnees",
    )

    if not (
        utilisateur.is_superuser
        or utilisateur.est_administrateur
    ):
        queryset = queryset.filter(
            proprietaire=utilisateur
        )

    return get_object_or_404(
        queryset,
        pk=pk,
    )


@login_required
def apercu_complet_jeu_donnees(
    request,
    pk,
):
    """
    Affiche toutes les lignes du jeu de données
    avec une pagination de 50 lignes.
    """

    jeu_donnees = recuperer_jeu_donnees_autorise(
        request.user,
        pk,
    )

    lignes_queryset = (
        jeu_donnees.lignes
        .order_by("numero_ligne")
    )

    paginator = Paginator(
        lignes_queryset,
        50,
    )

    page_obj = paginator.get_page(
        request.GET.get("page")
    )

    lignes_tableau = []

    for ligne in page_obj:
        lignes_tableau.append(
            {
                "numero": ligne.numero_ligne,
                "valeurs": [
                    ligne.donnees.get(colonne)
                    for colonne
                    in jeu_donnees.colonnes
                ],
            }
        )

    return render(
        request,
        "datasets/apercu_complet.html",
        {
            "jeu_donnees": jeu_donnees,
            "lignes_tableau": lignes_tableau,
            "page_obj": page_obj,
        },
    )


@login_required
def liste_jeux_donnees(request):
    """
    Affiche les jeux accessibles avec recherche,
    filtres, statistiques et pagination.
    """

    queryset_base = JeuDonnees.objects.select_related(
        "proprietaire",
        "source_jeu_donnees",
    )

    if not (
        request.user.is_superuser
        or request.user.is_staff
        or getattr(
            request.user,
            "est_administrateur",
            False,
        )
    ):
        queryset_base = queryset_base.filter(
            proprietaire=request.user
        )

    noms_champs = {
        champ.name
        for champ
        in JeuDonnees._meta.get_fields()
    }

    stats = {
        "total":
        queryset_base.count(),

        "nettoyes":
        (
            queryset_base.filter(
                type_version="NETTOYEE"
            ).count()
            if "type_version" in noms_champs
            else 0
        ),

        "csv":
        queryset_base.filter(
            format="CSV"
        ).count(),

        "excel":
        queryset_base.filter(
            format="EXCEL"
        ).count(),

        "recents":
        queryset_base.filter(
            date_importation__gte=(
                timezone.now()
                - timedelta(days=7)
            )
        ).count(),
    }

    stats["fichiers"] = stats["csv"] + stats["excel"]

    q = request.GET.get("q", "").strip()
    format_selectionne = request.GET.get("format", "").strip()
    statut_selectionne = request.GET.get("statut", "").strip()
    date_selectionnee = request.GET.get("date", "").strip()

    jeux_donnees = queryset_base

    if q:
        jeux_donnees = jeux_donnees.filter(
            Q(nom__icontains=q)
            | Q(description__icontains=q)
            | Q(nom_fichier_original__icontains=q)
        )

    if format_selectionne:
        jeux_donnees = jeux_donnees.filter(
            format=format_selectionne
        )

    if statut_selectionne:
        jeux_donnees = jeux_donnees.filter(
            statut=statut_selectionne
        )

    if date_selectionnee:
        jeux_donnees = jeux_donnees.filter(
            date_importation__date=date_selectionnee
        )

    jeux_donnees = jeux_donnees.order_by(
        "-date_importation"
    )

    try:
        page_size = int(
            request.GET.get(
                "page_size",
                10,
            )
        )
    except (TypeError, ValueError):
        page_size = 10

    page_size = min(max(page_size, 5), 100)

    paginator = Paginator(
        jeux_donnees,
        page_size,
    )

    page_obj = paginator.get_page(
        request.GET.get("page")
    )

    format_choices = (
        JeuDonnees._meta
        .get_field("format")
        .choices
    )

    statut_choices = (
        JeuDonnees._meta
        .get_field("statut")
        .choices
    )

    return render(
        request,
        "datasets/liste.html",
        {
            "jeux_donnees":
            page_obj.object_list,

            "page_obj":
            page_obj,

            "stats":
            stats,

            "format_choices":
            format_choices,

            "statut_choices":
            statut_choices,

            "filtres": {
                "q":
                q,

                "format":
                format_selectionne,

                "statut":
                statut_selectionne,

                "date":
                date_selectionnee,

                "page_size":
                page_size,
            },
        },
    )


@login_required
def importer_jeu_donnees(request):
    """
    Analyse un fichier CSV ou Excel et enregistre
    toutes ses lignes dans PostgreSQL.
    """

    if request.method == "POST":
        form = JeuDonneesImportForm(
            request.POST,
            request.FILES,
        )

        if form.is_valid():
            fichier = form.cleaned_data["fichier"]

            try:
                analyse = analyser_fichier(
                    fichier
                )

                jeu_donnees = enregistrer_dans_postgresql(
                    proprietaire=request.user,
                    nom=form.cleaned_data["nom"],
                    description=form.cleaned_data.get(
                        "description",
                        "",
                    ),
                    fichier=fichier,
                    analyse=analyse,
                )

            except ValidationError as erreur:
                message = (
                    erreur.messages[0]
                    if erreur.messages
                    else "Le fichier est invalide."
                )

                form.add_error(
                    "fichier",
                    message,
                )

            except Exception:
                traceback.print_exc()

                form.add_error(
                    None,
                    (
                        "Une erreur est survenue pendant "
                        "l'enregistrement dans PostgreSQL."
                    ),
                )

            else:
                messages.success(
                    request,
                    (
                        "Le jeu de données et toutes ses "
                        "lignes ont été enregistrés "
                        "dans PostgreSQL."
                    ),
                )

                return redirect(
                    "datasets:detail",
                    pk=jeu_donnees.pk,
                )

    else:
        form = JeuDonneesImportForm()

    return render(
        request,
        "datasets/importer.html",
        {
            "form": form,
        },
    )


@login_required
def detail_jeu_donnees(request, pk):
    """
    Affiche les informations du jeu et les dix
    premières lignes stockées dans PostgreSQL.
    """

    jeu_donnees = recuperer_jeu_donnees_autorise(
        request.user,
        pk,
    )

    lignes = (
        jeu_donnees.lignes
        .order_by("numero_ligne")[:10]
    )

    apercu = []

    for ligne in lignes:
        apercu.append(
            {
                "numero": ligne.numero_ligne,
                "valeurs": [
                    ligne.donnees.get(colonne)
                    for colonne
                    in jeu_donnees.colonnes
                ],
            }
        )

    return render(
        request,
        "datasets/detail.html",
        {
            "jeu_donnees": jeu_donnees,
            "apercu": apercu,
        },
    )


@login_required
def modifier_jeu_donnees(request, pk):
    """
    Modifie uniquement le nom et la description
    du jeu de données.
    """

    jeu_donnees = recuperer_jeu_donnees_autorise(
        request.user,
        pk,
    )

    if request.method == "POST":
        form = JeuDonneesModificationForm(
            request.POST,
            instance=jeu_donnees,
        )

        if form.is_valid():
            form.save()

            messages.success(
                request,
                (
                    "Le jeu de données a été "
                    "modifié avec succès."
                ),
            )

            return redirect(
                "datasets:detail",
                pk=jeu_donnees.pk,
            )

    else:
        form = JeuDonneesModificationForm(
            instance=jeu_donnees,
        )

    return render(
        request,
        "datasets/modifier.html",
        {
            "form": form,
            "jeu_donnees": jeu_donnees,
        },
    )


def creer_apercu_nettoyage(
    dataframe,
    limite=15,
):
    """
    Prépare les premières lignes pour
    l'affichage avant et après nettoyage.
    """

    return creer_apercu_dataframe(
        dataframe,
        limite=limite,
    )


def preparer_diagnostic_interface(
    dataframe,
    diagnostic,
):
    """
    Ajoute les niveaux et recommandations utiles
    à l'interface de nettoyage.

    Le paramètre dataframe est conservé pour rendre
    la fonction explicite et permettre son évolution.
    """

    del dataframe

    resultat = deepcopy(diagnostic)

    colonnes_aberrantes = {
        element["colonne"]
        for element in resultat.get(
            "valeurs_aberrantes",
            [],
        )
    }

    for information in resultat.get(
        "colonnes",
        [],
    ):
        colonne = information["nom"]

        type_colonne = str(
            information.get(
                "type",
                "texte",
            )
        ).strip().lower()

        information["type"] = type_colonne

        pourcentage = float(
            information.get(
                "pourcentage",
                0,
            )
            or 0
        )

        if pourcentage < 10:
            information["niveau"] = "Faible"
        elif pourcentage <= 30:
            information["niveau"] = "Moyen"
        else:
            information["niveau"] = "Élevé"

        if type_colonne == "nombre":
            if colonne in colonnes_aberrantes:
                information["recommandation"] = (
                    "La médiane est recommandée, "
                    "car cette colonne contient "
                    "des valeurs inhabituelles."
                )
            else:
                information["recommandation"] = (
                    "La moyenne ou la médiane peuvent "
                    "être utilisées après vérification."
                )
        else:
            information["recommandation"] = (
                "Utilisez « Non renseigné » pour "
                "rendre l'absence d'information visible."
            )

        information.setdefault(
            "lignes_exemples",
            [],
        )

    resultat.setdefault(
        "apercu_doublons",
        [],
    )

    for information in resultat.get(
        "valeurs_aberrantes",
        [],
    ):
        information.setdefault(
            "exemples",
            [],
        )

    return resultat


def construire_sections_nettoyage(
    form,
    diagnostic,
):
    """
    Associe les champs dynamiques du formulaire
    aux informations affichées dans le template.
    """

    informations_colonnes = {
        element["nom"]: element
        for element in diagnostic.get(
            "colonnes",
            [],
        )
    }

    informations_aberrantes = {
        element["colonne"]: element
        for element in diagnostic.get(
            "valeurs_aberrantes",
            [],
        )
    }

    sections_manquantes = []

    for configuration in getattr(
        form,
        "champs_manquants",
        [],
    ):
        colonne = configuration["colonne"]

        information = informations_colonnes.get(
            colonne,
            {
                "nom": colonne,
                "type": configuration.get(
                    "type",
                    "texte",
                ),
                "manquantes": 0,
                "pourcentage": 0,
                "niveau": "Faible",
                "lignes_exemples": [],
                "recommandation": "",
            },
        )

        sections_manquantes.append(
            {
                **information,
                "colonne": colonne,
                "champ_action": form[
                    configuration["nom_action"]
                ],
                "champ_valeur": form[
                    configuration["nom_valeur"]
                ],
            }
        )

    sections_aberrantes = []

    for configuration in getattr(
        form,
        "champs_aberrants",
        [],
    ):
        colonne = configuration["colonne"]

        information = informations_aberrantes.get(
            colonne,
            {
                "colonne": colonne,
                "nombre": 0,
                "borne_basse": 0,
                "borne_haute": 0,
                "exemples": [],
            },
        )

        sections_aberrantes.append(
            {
                **information,
                "champ_action": form[
                    configuration["nom_action"]
                ],
            }
        )

    return (
        sections_manquantes,
        sections_aberrantes,
    )


@login_required
def nettoyer_jeu_donnees(request, pk):
    """
    Parcours guidé :
    analyser, corriger, prévisualiser,
    puis créer une nouvelle version.
    """

    jeu_donnees = recuperer_jeu_donnees_autorise(
        request.user,
        pk,
    )

    dataframe = charger_dataframe_postgresql(
        jeu_donnees
    )

    diagnostic_brut = diagnostiquer_qualite(
        dataframe
    )

    diagnostic = preparer_diagnostic_interface(
        dataframe,
        diagnostic_brut,
    )

    form = NettoyageDonneesForm(
        request.POST or None,
        jeu_donnees=jeu_donnees,
        diagnostic=diagnostic,
    )

    apercu_disponible = False
    resume_apercu = None
    diagnostic_apres = None
    apercu_avant = creer_apercu_nettoyage(
        dataframe
    )
    apercu_apres = None

    if (
        request.method == "POST"
        and form.is_valid()
    ):
        try:
            plan = form.construire_plan()

            resultat, resume_apercu = (
                appliquer_plan_nettoyage(
                    dataframe,
                    plan,
                )
            )

            diagnostic_apres_brut = (
                diagnostiquer_qualite(
                    resultat
                )
            )

            diagnostic_apres = (
                preparer_diagnostic_interface(
                    resultat,
                    diagnostic_apres_brut,
                )
            )

            apercu_apres = (
                creer_apercu_nettoyage(
                    resultat
                )
            )

            apercu_disponible = True

            action = request.POST.get(
                "action",
                "apercu",
            )

            if action == "creer":
                nouvelle_version = (
                    enregistrer_version_nettoyee(
                        jeu_source=jeu_donnees,
                        utilisateur=request.user,
                        nom_version=(
                            form.cleaned_data[
                                "nom_version"
                            ]
                        ),
                        dataframe=resultat,
                        operations=plan,
                        diagnostic_avant=(
                            diagnostic_brut
                        ),
                        resume=resume_apercu,
                    )
                )

                messages.success(
                    request,
                    (
                        "La nouvelle version nettoyée "
                        "a été créée avec succès."
                    ),
                )

                return redirect(
                    "datasets:detail",
                    pk=nouvelle_version.pk,
                )

        except ValidationError as erreur:
            message = (
                erreur.messages[0]
                if erreur.messages
                else str(erreur)
            )

            form.add_error(
                None,
                message,
            )

        except Exception as erreur:
            traceback.print_exc()

            form.add_error(
                None,
                (
                    "Une erreur technique est survenue "
                    "pendant la prévisualisation. "
                    f"Détail : "
                    f"{type(erreur).__name__} — {erreur}"
                ),
            )

    (
        sections_manquantes,
        sections_aberrantes,
    ) = construire_sections_nettoyage(
        form,
        diagnostic,
    )

    return render(
        request,
        "datasets/nettoyer.html",
        {
            "jeu_donnees": jeu_donnees,
            "diagnostic": diagnostic,
            "form": form,
            "sections_manquantes": (
                sections_manquantes
            ),
            "sections_aberrantes": (
                sections_aberrantes
            ),
            "apercu_disponible": (
                apercu_disponible
            ),
            "resume_apercu": resume_apercu,
            "diagnostic_apres": diagnostic_apres,
            "apercu_avant": apercu_avant,
            "apercu_apres": apercu_apres,
        },
    )


@login_required
def supprimer_jeu_donnees(request, pk):
    """
    Supprime un jeu de données et ses lignes.

    Une version originale possédant encore des versions
    nettoyées ne peut pas être supprimée immédiatement.
    """

    jeu_donnees = recuperer_jeu_donnees_autorise(
        request.user,
        pk,
    )

    if request.method == "POST":
        nom_jeu_donnees = jeu_donnees.nom

        try:
            jeu_donnees.delete()

        except ProtectedError:
            messages.error(
                request,
                (
                    "Ce jeu de données ne peut pas "
                    "être supprimé car des versions "
                    "nettoyées dépendent encore de lui. "
                    "Supprimez d'abord ses versions "
                    "nettoyées."
                ),
            )

            return redirect(
                "datasets:detail",
                pk=jeu_donnees.pk,
            )

        messages.success(
            request,
            (
                f'Le jeu de données « {nom_jeu_donnees} » '
                "et ses lignes ont été supprimés."
            ),
        )

        return redirect(
            "datasets:liste"
        )

    return render(
        request,
        "datasets/supprimer.html",
        {
            "jeu_donnees": jeu_donnees,
        },
    )
