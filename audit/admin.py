from django.contrib import admin

from .models import JournalActivite


@admin.register(JournalActivite)
class JournalActiviteAdmin(
    admin.ModelAdmin
):
    list_display = (
        "date_action",
        "utilisateur",
        "action",
        "niveau",
        "module",
        "objet_type",
        "objet_libelle",
        "adresse_ip",
    )

    list_filter = (
        "action",
        "niveau",
        "module",
        "date_action",
    )

    search_fields = (
        "utilisateur__email",
        "utilisateur__first_name",
        "utilisateur__last_name",
        "description",
        "objet_libelle",
        "objet_type",
        "adresse_ip",
    )

    date_hierarchy = (
        "date_action"
    )

    ordering = (
        "-date_action",
    )

    list_select_related = (
        "utilisateur",
    )

    readonly_fields = (
        "utilisateur",
        "action",
        "niveau",
        "module",
        "objet_type",
        "objet_id",
        "objet_libelle",
        "description",
        "methode_http",
        "chemin",
        "adresse_ip",
        "user_agent",
        "metadata",
        "date_action",
    )

    fieldsets = (
        (
            "Action",
            {
                "fields": (
                    "date_action",
                    "utilisateur",
                    "action",
                    "niveau",
                    "module",
                    "description",
                )
            },
        ),

        (
            "Objet concerné",
            {
                "fields": (
                    "objet_type",
                    "objet_id",
                    "objet_libelle",
                    "metadata",
                )
            },
        ),

        (
            "Contexte technique",
            {
                "classes": (
                    "collapse",
                ),

                "fields": (
                    "methode_http",
                    "chemin",
                    "adresse_ip",
                    "user_agent",
                ),
            },
        ),
    )

    def has_add_permission(
        self,
        request,
    ):
        return False

    def has_change_permission(
        self,
        request,
        obj=None,
    ):
        return False

    def has_delete_permission(
        self,
        request,
        obj=None,
    ):
        return False
