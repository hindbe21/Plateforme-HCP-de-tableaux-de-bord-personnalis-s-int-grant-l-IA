from django.apps import AppConfig


class AuditConfig(AppConfig):
    default_auto_field = (
        "django.db.models.BigAutoField"
    )

    name = "audit"

    verbose_name = (
        "Journal d’activité"
    )

    def ready(self):
        # Enregistre les signaux automatiques.
        from . import signals  # noqa: F401
