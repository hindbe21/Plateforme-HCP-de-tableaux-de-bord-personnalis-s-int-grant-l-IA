from django import forms


class DemandeWidgetIAForm(forms.Form):
    """
    Demande formulée en langage naturel
    pour créer un widget.
    """

    demande = forms.CharField(
        label=(
            "Décrivez la visualisation "
            "que vous souhaitez créer"
        ),
        min_length=10,
        max_length=1000,
        widget=forms.Textarea(
            attrs={
                "class":
                "form-control",

                "rows":
                5,

                "placeholder": (
                    "Exemple : Affiche le nombre "
                    "d’événements par arrondissement "
                    "pour l’année 2009 sous forme "
                    "de graphique en barres."
                ),

                "autocomplete":
                "off",
            }
        ),
        help_text=(
            "Précisez, lorsque c’est utile, "
            "la dimension, la mesure, la période "
            "ou le type de graphique souhaité."
        ),
    )

    def clean_demande(self):
        demande = (
            self.cleaned_data[
                "demande"
            ]
            .strip()
        )

        if len(demande.split()) < 3:
            raise forms.ValidationError(
                (
                    "Décrivez votre besoin "
                    "avec un peu plus de précision."
                )
            )

        return demande
