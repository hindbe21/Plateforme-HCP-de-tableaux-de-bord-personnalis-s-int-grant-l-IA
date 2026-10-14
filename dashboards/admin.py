from django.contrib import admin

from .models import (
    Filtre,
    TableauBord,
    Widget,
)

try:
    from .models import FiltreWidget
except ImportError:
    FiltreWidget = None


@admin.register(TableauBord)
class TableauBordAdmin(admin.ModelAdmin):
    list_display = (
        "titre",
        "proprietaire",
        "jeu_donnees",
        "actif",
        "nombre_widgets",
        "date_modification",
    )

    list_filter = (
        "actif",
        "date_creation",
        "date_modification",
    )

    search_fields = (
        "titre",
        "description",
        "proprietaire__email",
        "proprietaire__first_name",
        "proprietaire__last_name",
        "jeu_donnees__nom",
    )

    list_select_related = (
        "proprietaire",
        "jeu_donnees",
    )

    ordering = (
        "-date_modification",
    )

    readonly_fields = (
        "date_creation",
        "date_modification",
    )

    fieldsets = (
        (
            "Informations générales",
            {
                "fields": (
                    "titre",
                    "description",
                    "actif",
                )
            },
        ),
        (
            "Propriétaire et données",
            {
                "fields": (
                    "proprietaire",
                    "jeu_donnees",
                )
            },
        ),
        (
            "Dates",
            {
                "fields": (
                    "date_creation",
                    "date_modification",
                )
            },
        ),
    )

    @admin.display(
        description="Widgets"
    )
    def nombre_widgets(self, obj):
        return obj.widgets.count()


@admin.register(Widget)
class WidgetAdmin(admin.ModelAdmin):
    list_display = (
        "titre",
        "tableau_bord",
        "type_widget",
        "colonne_categorie",
        "limite_resultats",
        "ordre",
        "date_modification",
    )

    list_filter = (
        "type_widget",
        "date_creation",
        "date_modification",
    )

    search_fields = (
        "titre",
        "tableau_bord__titre",
        "tableau_bord__proprietaire__email",
        "colonne_categorie",
    )

    list_select_related = (
        "tableau_bord",
        "tableau_bord__proprietaire",
    )

    ordering = (
        "tableau_bord",
        "ordre",
        "date_creation",
    )

    readonly_fields = (
        "date_creation",
        "date_modification",
    )

    fieldsets = (
        (
            "Informations générales",
            {
                "fields": (
                    "tableau_bord",
                    "titre",
                    "type_widget",
                    "ordre",
                )
            },
        ),
        (
            "Configuration statistique",
            {
                "fields": (
                    "colonne_categorie",
                    "limite_resultats",
                    "configuration",
                )
            },
        ),
        (
            "Dates",
            {
                "fields": (
                    "date_creation",
                    "date_modification",
                )
            },
        ),
    )


@admin.register(Filtre)
class FiltreAdmin(admin.ModelAdmin):
    list_display = (
        "tableau_bord",
        "colonne",
        "operateur",
        "valeur",
        "actif",
        "ordre",
        "date_creation",
    )

    list_filter = (
        "operateur",
        "actif",
        "date_creation",
    )

    search_fields = (
        "tableau_bord__titre",
        "colonne",
        "valeur",
    )

    list_select_related = (
        "tableau_bord",
    )

    ordering = (
        "tableau_bord",
        "ordre",
        "date_creation",
    )


if FiltreWidget is not None:

    @admin.register(FiltreWidget)
    class FiltreWidgetAdmin(
        admin.ModelAdmin
    ):
        list_display = (
            "widget",
            "tableau_bord",
            "colonne",
            "operateur",
            "valeur",
            "actif",
            "ordre",
            "date_creation",
        )

        list_filter = (
            "operateur",
            "actif",
            "date_creation",
        )

        search_fields = (
            "widget__titre",
            "widget__tableau_bord__titre",
            "colonne",
            "valeur",
        )

        list_select_related = (
            "widget",
            "widget__tableau_bord",
        )

        ordering = (
            "widget",
            "ordre",
            "date_creation",
        )

        @admin.display(
            description="Tableau de bord"
        )
        def tableau_bord(self, obj):
            return (
                obj.widget.tableau_bord
            )
