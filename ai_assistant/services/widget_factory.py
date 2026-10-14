from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Max

from dashboards.forms import WidgetForm
from dashboards.models import Filtre, FiltreWidget, Widget

from .widget_validation import valider_configuration


@transaction.atomic
def creer_widget_depuis_configuration(tableau_bord, configuration, analyse):
    configuration = valider_configuration(configuration, analyse)

    donnees_formulaire = {
        "titre": configuration["titre"],
        "type_widget": configuration["type_widget"],
        "colonne_categorie": configuration["colonne_categorie"],
        "colonne_mesure": configuration["colonne_mesure"],
        "colonne_serie": configuration["colonne_serie"],
        "agregation": configuration["agregation"],
        "ordre_tri": configuration["ordre_tri"],
        "limite_resultats": configuration["limite_resultats"],
        "nombre_classes": configuration["nombre_classes"],
    }
    if configuration.get("inclure_manquantes"):
        donnees_formulaire["inclure_manquantes"] = "on"

    formulaire = WidgetForm(
        donnees_formulaire,
        tableau_bord=tableau_bord,
    )

    if not formulaire.is_valid():
        messages = []
        for champ, erreurs in formulaire.errors.items():
            for erreur in erreurs:
                messages.append(f"{champ} : {erreur}")
        raise ValidationError(" ".join(messages))

    widget = formulaire.save(commit=False)
    widget.tableau_bord = tableau_bord
    widget.ordre = (
        Widget.objects.filter(tableau_bord=tableau_bord)
        .aggregate(valeur=Max("ordre"))
        .get("valeur")
        or 0
    ) + 1

    configuration_existante = dict(widget.configuration or {})
    configuration_existante.update({
        "colonne_mesure": configuration["colonne_mesure"],
        "colonne_serie": configuration["colonne_serie"],
        "agregation": configuration["agregation"],
        "ordre_tri": configuration["ordre_tri"],
        "nombre_classes": configuration["nombre_classes"],
        "inclure_manquantes": configuration["inclure_manquantes"],
    })
    widget.configuration = configuration_existante
    widget.save()

    for ordre, filtre in enumerate(
        configuration.get("filtres", []),
        start=1,
    ):
        objet_filtre = FiltreWidget(
            widget=widget,
            colonne=filtre["colonne"],
            operateur=filtre["operateur"],
            valeur=(
                ""
                if filtre["operateur"] in {
                    Filtre.Operateur.VIDE,
                    Filtre.Operateur.NON_VIDE,
                }
                else filtre.get("valeur", "")
            ),
            actif=True,
            ordre=ordre,
        )
        objet_filtre.full_clean()
        objet_filtre.save()

    return widget
