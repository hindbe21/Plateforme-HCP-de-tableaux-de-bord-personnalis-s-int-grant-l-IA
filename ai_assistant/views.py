from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from dashboards.views import recuperer_tableau_autorise

from .forms import (
    MessageAssistantForm,
    RapportEditionForm,
    RapportJeuDonneesEditionForm,
    SuggestionWidgetForm,
)
from .models import RapportJeuDonneesIA, RapportStatistiqueIA, SuggestionWidget
from .services.dataset_analyzer import analyser_et_enregistrer
from .services.ollama_client import ErreurOllama, rediger_rapport, traiter_message
from .services.report_builder import calculer_resultats_tableau_bord
from .services.dataset_report_builder import calculer_rapport_jeu_donnees
from .services.dataset_report_writer import rediger_rapport_jeu_donnees
from .services.widget_factory import creer_widget_depuis_configuration
from .services.widget_recommender import (
    CATEGORIES_SUGGESTIONS,
    enregistrer_suggestions_automatiques,
)


TAILLE_MAX_CONVERSATION = 20


def cle_conversation(tableau_bord):
    return f"assistant_dashboard_{tableau_bord.pk}"


def lire_conversation(request, tableau_bord):
    conversation = request.session.get(cle_conversation(tableau_bord), [])
    return list(conversation)[-TAILLE_MAX_CONVERSATION:]


def enregistrer_conversation(request, tableau_bord, conversation):
    request.session[cle_conversation(tableau_bord)] = list(conversation)[-TAILLE_MAX_CONVERSATION:]
    request.session.modified = True


def obtenir_analyse_et_suggestions(tableau_bord):
    analyse = analyser_et_enregistrer(tableau_bord.jeu_donnees)
    existe = SuggestionWidget.objects.filter(
        tableau_bord=tableau_bord,
        source=SuggestionWidget.Source.AUTOMATIQUE,
        statut=SuggestionWidget.Statut.PROPOSEE,
    ).exists()
    if not existe:
        enregistrer_suggestions_automatiques(tableau_bord, analyse)
    return analyse


def url_creation_ia(tableau_bord):
    return reverse("dashboards:ajouter_widget", kwargs={"pk": tableau_bord.pk}) + "?mode=ia"


@login_required
def espace_assiste(request, pk):
    tableau_bord = recuperer_tableau_autorise(request.user, pk)
    return redirect(url_creation_ia(tableau_bord))


@login_required
def reanalyser(request, pk):
    tableau_bord = recuperer_tableau_autorise(request.user, pk)
    if request.method == "POST":
        try:
            analyse = analyser_et_enregistrer(tableau_bord.jeu_donnees, force=True)
            enregistrer_suggestions_automatiques(tableau_bord, analyse, remplacer=True)
            messages.success(request, "L’analyse et les suggestions ont été recalculées.")
        except Exception as erreur:
            messages.error(request, f"L’analyse a échoué : {erreur}")
    return redirect(url_creation_ia(tableau_bord))


@login_required
def regenerer_suggestions(request, pk):
    tableau_bord = recuperer_tableau_autorise(request.user, pk)
    if request.method == "POST":
        analyse = analyser_et_enregistrer(tableau_bord.jeu_donnees)
        objets = enregistrer_suggestions_automatiques(
            tableau_bord,
            analyse,
            remplacer=True,
        )
        messages.success(
            request,
            f"{len(objets)} suggestion(s) pertinente(s) ont été générées et organisées.",
        )
    return redirect(url_creation_ia(tableau_bord))

@login_required
def envoyer_message(request, pk):
    tableau_bord = recuperer_tableau_autorise(request.user, pk)
    if request.method != "POST":
        return redirect(url_creation_ia(tableau_bord))

    form = MessageAssistantForm(request.POST)
    conversation = lire_conversation(request, tableau_bord)
    if form.is_valid():
        demande = form.cleaned_data["message"]
        conversation.append({"role": "user", "content": demande})
        try:
            analyse = analyser_et_enregistrer(tableau_bord.jeu_donnees)
            resultat = traiter_message(demande, analyse, tableau_bord)
            configurations = list(resultat.get("suggestions", []) or [])[:6]
            objets = []

            for configuration in configurations:
                objets.append(
                    SuggestionWidget.objects.create(
                        tableau_bord=tableau_bord,
                        analyse=analyse,
                        source=SuggestionWidget.Source.CONVERSATION,
                        configuration=configuration,
                        justification=(
                            configuration.get("raison")
                            or resultat.get("message", "")
                        ),
                    )
                )

            conversation.append({
                "role": "assistant",
                "content": resultat["message"],
                "suggestion_ids": [objet.pk for objet in objets],
                "suggestion_count": len(objets),
            })
        except ErreurOllama as erreur:
            conversation.append({"role": "assistant", "content": str(erreur), "erreur": True})
            messages.error(request, str(erreur))
        except Exception as erreur:
            conversation.append({
                "role": "assistant",
                "content": "Une erreur contrôlée est survenue pendant l’analyse de la demande.",
                "erreur": True,
            })
            messages.error(request, f"Impossible de traiter la demande : {erreur}")
        enregistrer_conversation(request, tableau_bord, conversation)

    return redirect(url_creation_ia(tableau_bord))

@login_required
def effacer_conversation(request, pk):
    tableau_bord = recuperer_tableau_autorise(request.user, pk)
    if request.method == "POST":
        request.session.pop(cle_conversation(tableau_bord), None)
        request.session.modified = True
    return redirect(url_creation_ia(tableau_bord))


def suggestion_autorisee(utilisateur, pk):
    suggestion = get_object_or_404(
        SuggestionWidget.objects.select_related(
            "tableau_bord",
            "tableau_bord__jeu_donnees",
            "analyse",
        ),
        pk=pk,
    )
    recuperer_tableau_autorise(utilisateur, suggestion.tableau_bord_id)
    return suggestion


@login_required
def modifier_suggestion(request, pk):
    suggestion = suggestion_autorisee(request.user, pk)
    analyse = suggestion.analyse or analyser_et_enregistrer(suggestion.tableau_bord.jeu_donnees)
    initial = dict(suggestion.configuration or {})
    initial["justification"] = suggestion.justification
    form = SuggestionWidgetForm(
        request.POST or None,
        analyse=analyse,
        initial=initial,
    )
    if request.method == "POST" and form.is_valid():
        suggestion.configuration = form.configuration_validee
        suggestion.justification = form.cleaned_data.get("justification", "")
        suggestion.save(update_fields=["configuration", "justification", "date_modification"])
        messages.success(request, "La suggestion a été modifiée.")
        return redirect(url_creation_ia(suggestion.tableau_bord))

    return render(request, "ai_assistant/suggestion_form.html", {
        "suggestion": suggestion,
        "tableau_bord": suggestion.tableau_bord,
        "form": form,
    })


@login_required
def supprimer_suggestion(request, pk):
    suggestion = suggestion_autorisee(request.user, pk)
    if request.method == "POST":
        suggestion.statut = SuggestionWidget.Statut.SUPPRIMEE
        suggestion.save(update_fields=["statut", "date_modification"])
        messages.success(request, "La suggestion a été retirée.")
    return redirect(url_creation_ia(suggestion.tableau_bord))


@login_required
def creer_depuis_suggestion(request, pk):
    suggestion = suggestion_autorisee(request.user, pk)
    if request.method != "POST":
        return redirect(url_creation_ia(suggestion.tableau_bord))

    analyse = suggestion.analyse or analyser_et_enregistrer(suggestion.tableau_bord.jeu_donnees)
    creation_reussie = False
    try:
        widget = creer_widget_depuis_configuration(
            suggestion.tableau_bord,
            suggestion.configuration,
            analyse,
        )
    except ValidationError as erreur:
        messages.error(request, f"Le widget n’a pas été créé : {erreur}")
    else:
        suggestion.statut = SuggestionWidget.Statut.ACCEPTEE
        suggestion.widget_cree = widget
        suggestion.save(update_fields=["statut", "widget_cree", "date_modification"])
        messages.success(
            request,
            "Le widget a été créé après votre confirmation. Il reste modifiable manuellement.",
        )
        creation_reussie = True
    if creation_reussie:
        return redirect("dashboards:detail", pk=suggestion.tableau_bord_id)
    return redirect(url_creation_ia(suggestion.tableau_bord))


@login_required
def creer_selection_suggestions(request, pk):
    tableau_bord = recuperer_tableau_autorise(request.user, pk)
    if request.method != "POST":
        return redirect(url_creation_ia(tableau_bord))

    identifiants = request.POST.getlist("suggestion_ids")
    if not identifiants:
        messages.warning(request, "Sélectionnez au moins une suggestion.")
        return redirect(url_creation_ia(tableau_bord))

    suggestions = list(
        SuggestionWidget.objects.filter(
            pk__in=identifiants,
            tableau_bord=tableau_bord,
            statut=SuggestionWidget.Statut.PROPOSEE,
        ).select_related("analyse")
    )

    nombre_crees = 0
    erreurs = []

    for suggestion in suggestions:
        analyse = suggestion.analyse or analyser_et_enregistrer(
            tableau_bord.jeu_donnees
        )
        try:
            widget = creer_widget_depuis_configuration(
                tableau_bord,
                suggestion.configuration,
                analyse,
            )
        except ValidationError as erreur:
            erreurs.append(
                f"{suggestion.configuration.get('titre', 'Widget')} : {erreur}"
            )
            continue

        suggestion.statut = SuggestionWidget.Statut.ACCEPTEE
        suggestion.widget_cree = widget
        suggestion.save(update_fields=[
            "statut",
            "widget_cree",
            "date_modification",
        ])
        nombre_crees += 1

    if nombre_crees:
        messages.success(
            request,
            f"{nombre_crees} widget(s) ont été créés après votre validation.",
        )
    for erreur in erreurs[:5]:
        messages.error(request, erreur)

    if nombre_crees:
        return redirect("dashboards:detail", pk=tableau_bord.pk)
    return redirect(url_creation_ia(tableau_bord))


@login_required
def rapport_statistique(request, pk):
    tableau_bord = recuperer_tableau_autorise(request.user, pk)
    rapport = RapportStatistiqueIA.objects.filter(tableau_bord=tableau_bord).first()
    return render(request, "ai_assistant/rapport.html", {
        "tableau_bord": tableau_bord,
        "rapport": rapport,
    })


@login_required
def modifier_rapport(request, pk):
    tableau_bord = recuperer_tableau_autorise(request.user, pk)
    rapport = RapportStatistiqueIA.objects.filter(tableau_bord=tableau_bord).first()

    if rapport is None:
        messages.warning(request, "Générez d’abord un rapport avant de le modifier.")
        return redirect("ai_assistant:rapport", pk=tableau_bord.pk)

    form = RapportEditionForm(request.POST or None, contenu=rapport.contenu)
    if request.method == "POST" and form.is_valid():
        rapport.contenu = form.construire_contenu()
        rapport.save(update_fields=["contenu"])
        messages.success(request, "Les textes du rapport ont été enregistrés.")
        return redirect("ai_assistant:rapport", pk=tableau_bord.pk)

    return render(request, "ai_assistant/rapport_modifier.html", {
        "tableau_bord": tableau_bord,
        "rapport": rapport,
        "form": form,
        "groupes_widgets": form.groupes_widgets_lies(),
    })


@login_required
def generer_rapport(request, pk):
    tableau_bord = recuperer_tableau_autorise(request.user, pk)
    if request.method != "POST":
        return redirect("ai_assistant:rapport", pk=tableau_bord.pk)

    if not tableau_bord.widgets.exists():
        messages.warning(request, "Ajoutez au moins un widget avant de générer le rapport.")
        return redirect("ai_assistant:rapport", pk=tableau_bord.pk)

    try:
        donnees_calculees = calculer_resultats_tableau_bord(tableau_bord)
        contenu, modele = rediger_rapport(donnees_calculees)
        RapportStatistiqueIA.objects.create(
            tableau_bord=tableau_bord,
            auteur=request.user,
            donnees_calculees=donnees_calculees,
            contenu=contenu,
            modele_ollama=modele,
        )
        messages.success(request, "Le rapport statistique intelligent a été généré.")
    except ErreurOllama as erreur:
        messages.error(request, str(erreur))
    except Exception as erreur:
        messages.error(request, f"Impossible de générer le rapport : {erreur}")

    return redirect("ai_assistant:rapport", pk=tableau_bord.pk)


@login_required
def rapport_jeu_donnees(request, pk):
    from datasets.views import recuperer_jeu_donnees_autorise
    jeu=recuperer_jeu_donnees_autorise(request.user,pk)
    rapport=RapportJeuDonneesIA.objects.filter(jeu_donnees=jeu).first()
    return render(request,"ai_assistant/rapport_jeu_donnees.html",{"jeu_donnees":jeu,"rapport":rapport})

@login_required
def generer_rapport_jeu_donnees(request, pk):
    from datasets.views import recuperer_jeu_donnees_autorise
    jeu=recuperer_jeu_donnees_autorise(request.user,pk)
    if request.method=="POST":
        try:
            calculs=calculer_rapport_jeu_donnees(jeu); contenu,modele=rediger_rapport_jeu_donnees(calculs)
            RapportJeuDonneesIA.objects.create(jeu_donnees=jeu,auteur=request.user,donnees_calculees=calculs,contenu=contenu,modele_ollama=modele)
            messages.success(request,"Le rapport statistique du jeu de données a été généré.")
        except Exception as erreur:
            messages.error(request,f"Impossible de générer le rapport : {erreur}")
    return redirect("ai_assistant:rapport_jeu_donnees",pk=jeu.pk)

@login_required
def modifier_rapport_jeu_donnees(request, pk):
    from datasets.views import recuperer_jeu_donnees_autorise
    jeu=recuperer_jeu_donnees_autorise(request.user,pk)
    rapport=RapportJeuDonneesIA.objects.filter(jeu_donnees=jeu).first()
    if rapport is None:
        messages.warning(request,"Générez d’abord le rapport.")
        return redirect("ai_assistant:rapport_jeu_donnees",pk=jeu.pk)
    form=RapportJeuDonneesEditionForm(request.POST or None,contenu=rapport.contenu)
    if request.method=="POST" and form.is_valid():
        rapport.contenu=form.construire_contenu(); rapport.save(update_fields=["contenu"])
        messages.success(request,"Le rapport a été modifié.")
        return redirect("ai_assistant:rapport_jeu_donnees",pk=jeu.pk)
    return render(request,"ai_assistant/rapport_jeu_donnees_modifier.html",{"jeu_donnees":jeu,"rapport":rapport,"form":form})
