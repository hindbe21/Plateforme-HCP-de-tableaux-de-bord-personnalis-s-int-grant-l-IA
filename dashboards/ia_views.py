from django.contrib import messages
from django.contrib.auth.decorators import (
    login_required,
)
from django.shortcuts import (
    redirect,
    render,
)

from .forms import (
    construire_profils_colonnes,
)
from .forms_ia import (
    DemandeWidgetIAForm,
)
from .services_ia import (
    ErreurAssistantIA,
    creer_widget_depuis_proposition,
    generer_proposition_widget_ia,
    valider_proposition_widget_ia,
)
from .views import (
    recuperer_tableau_autorise,
)


SESSION_PREFIX = (
    "proposition_widget_ia"
)


def cle_session_proposition(
    tableau_bord,
):
    return (
        f"{SESSION_PREFIX}_"
        f"{tableau_bord.pk}"
    )


@login_required
def assistant_widget_ia(
    request,
    pk,
):
    """
    Génère une proposition de widget,
    l’affiche, puis attend la confirmation.
    """

    tableau_bord = (
        recuperer_tableau_autorise(
            request.user,
            pk,
        )
    )

    # Profil affiché dans la page IA et réutilisé
    # pour construire le contexte de l’assistant.
    profils_colonnes = (
        construire_profils_colonnes(
            tableau_bord.jeu_donnees
        )
    )

    cle_session = (
        cle_session_proposition(
            tableau_bord
        )
    )

    proposition = (
        request.session.get(
            cle_session
        )
    )

    demande_initiale = ""

    if proposition:
        demande_initiale = str(
            proposition.get(
                "demande_utilisateur",
                "",
            )
            or ""
        )

    form = DemandeWidgetIAForm(
        initial={
            "demande":
            demande_initiale,
        }
    )

    if request.method == "POST":
        action = request.POST.get(
            "action",
            "generer",
        )

        if action == "generer":
            form = DemandeWidgetIAForm(
                request.POST
            )

            if form.is_valid():
                try:
                    demande = (
                        form.cleaned_data[
                            "demande"
                        ]
                    )

                    proposition = (
                        generer_proposition_widget_ia(
                            tableau_bord,
                            demande,
                            profils_colonnes=(
                                profils_colonnes
                            ),
                        )
                    )

                    proposition[
                        "demande_utilisateur"
                    ] = demande

                    request.session[
                        cle_session
                    ] = proposition

                    request.session.modified = (
                        True
                    )

                    messages.success(
                        request,
                        (
                            "La proposition a été générée. "
                            "Vérifiez-la avant de confirmer."
                        ),
                    )

                except ErreurAssistantIA as erreur:
                    proposition = None

                    messages.error(
                        request,
                        str(erreur),
                    )

        elif action == "creer":
            if not proposition:
                messages.warning(
                    request,
                    (
                        "Aucune proposition "
                        "n’est disponible."
                    ),
                )

                return redirect(
                    "dashboards:"
                    "assistant_widget_ia",
                    pk=tableau_bord.pk,
                )

            try:
                proposition_validee = (
                    valider_proposition_widget_ia(
                        tableau_bord,
                        proposition,
                    )
                )

                widget = (
                    creer_widget_depuis_proposition(
                        tableau_bord,
                        proposition_validee,
                    )
                )

                request.session.pop(
                    cle_session,
                    None,
                )

                messages.success(
                    request,
                    (
                        f"Le widget « {widget.titre} » "
                        "a été créé avec succès."
                    ),
                )

                return redirect(
                    "dashboards:detail",
                    pk=tableau_bord.pk,
                )

            except ErreurAssistantIA as erreur:
                messages.error(
                    request,
                    str(erreur),
                )

        elif action == "effacer":
            request.session.pop(
                cle_session,
                None,
            )

            messages.info(
                request,
                (
                    "La proposition a été "
                    "supprimée."
                ),
            )

            return redirect(
                "dashboards:"
                "assistant_widget_ia",
                pk=tableau_bord.pk,
            )

    return render(
        request,
        (
            "dashboards/"
            "widget_assistant_ia.html"
        ),
        {
            "tableau_bord":
            tableau_bord,

            "form":
            form,

            "proposition":
            proposition,

            "profils_colonnes":
            profils_colonnes,
        },
    )
