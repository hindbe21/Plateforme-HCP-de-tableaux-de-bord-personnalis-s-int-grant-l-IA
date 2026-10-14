from __future__ import annotations
from ..forms import MessageAssistantForm
from ..models import SuggestionWidget
from .dataset_analyzer import analyser_et_enregistrer
from .widget_recommender import CATEGORIES_SUGGESTIONS, enregistrer_suggestions_automatiques

TAILLE_MAX_CONVERSATION=20

def cle_conversation(tableau_bord): return f"assistant_dashboard_{tableau_bord.pk}"
def lire_conversation(request,tableau_bord): return list(request.session.get(cle_conversation(tableau_bord),[]))[-TAILLE_MAX_CONVERSATION:]

def construire_contexte_creation_widgets(request,tableau_bord):
    analyse=analyser_et_enregistrer(tableau_bord.jeu_donnees)
    existe=SuggestionWidget.objects.filter(tableau_bord=tableau_bord,source=SuggestionWidget.Source.AUTOMATIQUE,statut=SuggestionWidget.Statut.PROPOSEE).exists()
    if not existe: enregistrer_suggestions_automatiques(tableau_bord,analyse)
    suggestions=list(SuggestionWidget.objects.filter(tableau_bord=tableau_bord,statut=SuggestionWidget.Statut.PROPOSEE).select_related("analyse"))
    suggestions.sort(key=lambda s:(0 if s.configuration.get("selection_equilibree") else 1,int(s.configuration.get("selection_rang",999) or 999),-float(s.configuration.get("score",0) or 0),s.pk))
    groups=[]; labels=dict(CATEGORIES_SUGGESTIONS)
    for code,label in CATEGORIES_SUGGESTIONS:
        items=[s for s in suggestions if s.configuration.get("categorie")==code]
        if items: groups.append({"code":code,"libelle":label,"suggestions":items,"nombre":len(items)})
    other=[s for s in suggestions if s.configuration.get("categorie") not in labels]
    if other: groups.append({"code":"AUTRES","libelle":"Autres suggestions","suggestions":other,"nombre":len(other)})
    schema=analyse.schema or {}
    return {"analyse":analyse,"suggestions":suggestions,"groupes_suggestions":groups,
            "selection_recommandee":[s for s in suggestions if s.configuration.get("selection_equilibree")],
            "filtres_recommandes":schema.get("filtres_recommandes",[]),
            "widgets_non_disponibles":schema.get("widgets_non_disponibles",[]),
            "form_chat":MessageAssistantForm(),"conversation":lire_conversation(request,tableau_bord)}
