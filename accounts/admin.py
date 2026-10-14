from django.conf import settings
from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin
from django.core.mail import send_mail
from django.urls import reverse

from .forms import (
    CustomUserChangeForm,
    CustomUserCreationForm,
)
from .models import User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    model = User

    add_form = CustomUserCreationForm
    form = CustomUserChangeForm

    ordering = ("email",)

    list_display = (
        "email",
        "first_name",
        "last_name",
        "role",
        "statut",
        "is_active",
        "date_joined",
    )

    list_filter = (
        "statut",
        "role",
        "is_active",
        "is_staff",
        "date_joined",
    )

    search_fields = (
        "email",
        "first_name",
        "last_name",
    )

    readonly_fields = (
        "is_active",
        "last_login",
        "date_joined",
    )

    actions = (
        "accepter_demandes",
        "renvoyer_email_confirmation",
        "refuser_demandes",
        "suspendre_comptes",
        "reactiver_comptes",
    )

    fieldsets = (
        (
            "Authentification",
            {
                "fields": (
                    "email",
                    "password",
                )
            },
        ),
        (
            "Informations personnelles",
            {
                "fields": (
                    "first_name",
                    "last_name",
                )
            },
        ),
        (
            "Rôle et validation",
            {
                "fields": (
                    "role",
                    "statut",
                    "is_active",
                )
            },
        ),
        (
            "Permissions Django",
            {
                "fields": (
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        (
            "Dates importantes",
            {
                "fields": (
                    "last_login",
                    "date_joined",
                )
            },
        ),
    )

    add_fieldsets = (
        (
            "Créer un utilisateur",
            {
                "classes": ("wide",),
                "fields": (
                    "email",
                    "first_name",
                    "last_name",
                    "role",
                    "statut",
                    "password1",
                    "password2",
                    "is_staff",
                    "is_superuser",
                ),
            },
        ),
    )

    filter_horizontal = (
        "groups",
        "user_permissions",
    )

    def envoyer_email_activation(self, utilisateur):
        """
        Envoie à un utilisateur actif l'email
        de confirmation contenant le lien de connexion.
        """

        site_url = getattr(
            settings,
            "SITE_URL",
            "http://127.0.0.1:8000",
        ).rstrip("/")

        lien_connexion = (
            f"{site_url}"
            f"{reverse('login')}"
        )

        nom_utilisateur = (
            utilisateur.get_full_name().strip()
            or utilisateur.email
        )

        return send_mail(
            subject="Votre compte Plateforme HCP a été accepté",
            message=f"""Bonjour {nom_utilisateur},

Votre demande de création de compte sur la Plateforme HCP a été acceptée.

Votre compte est maintenant actif en tant qu'utilisateur métier.

Vous pouvez vous connecter avec l'adresse email et le mot de passe choisis lors de votre inscription :

{lien_connexion}

Adresse email : {utilisateur.email}

Cordialement,

L'administration de la Plateforme HCP
""",
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[utilisateur.email],
            fail_silently=False,
        )

    @admin.action(
        description="Accepter les demandes sélectionnées"
    )
    def accepter_demandes(self, request, queryset):
        """
        Active uniquement les comptes en attente
        et leur envoie un email de confirmation.
        """

        demandes = queryset.filter(
            is_superuser=False,
            statut=User.StatutCompte.EN_ATTENTE,
        )

        nombre_acceptes = 0
        nombre_emails = 0
        nombre_erreurs = 0

        for utilisateur in demandes:
            utilisateur.role = User.Role.METIER
            utilisateur.statut = User.StatutCompte.ACTIF
            utilisateur.is_active = True

            utilisateur.save(
                update_fields=[
                    "role",
                    "statut",
                    "is_active",
                ]
            )

            nombre_acceptes += 1

            try:
                nombre_emails += self.envoyer_email_activation(
                    utilisateur
                )

            except Exception as erreur:
                nombre_erreurs += 1

                print(
                    "Erreur d'envoi vers "
                    f"{utilisateur.email} : {erreur}"
                )

        if nombre_acceptes == 0:
            self.message_user(
                request,
                (
                    "Aucune demande en attente n'a été sélectionnée. "
                    "Les comptes déjà actifs ne sont pas modifiés."
                ),
                level=messages.WARNING,
            )
            return

        self.message_user(
            request,
            (
                f"{nombre_acceptes} demande(s) acceptée(s) et "
                f"{nombre_emails} email(s) envoyé(s)."
            ),
            level=messages.SUCCESS,
        )

        if nombre_erreurs:
            self.message_user(
                request,
                (
                    f"{nombre_erreurs} email(s) n'ont pas pu être "
                    "envoyés. Les comptes ont néanmoins été activés."
                ),
                level=messages.ERROR,
            )

    @admin.action(
        description="Renvoyer l'email de confirmation"
    )
    def renvoyer_email_confirmation(self, request, queryset):
        """
        Renvoie l'email aux comptes déjà actifs.
        """

        utilisateurs = queryset.filter(
            is_superuser=False,
            statut=User.StatutCompte.ACTIF,
            is_active=True,
        )

        nombre_emails = 0
        nombre_erreurs = 0

        for utilisateur in utilisateurs:
            try:
                nombre_emails += self.envoyer_email_activation(
                    utilisateur
                )

            except Exception as erreur:
                nombre_erreurs += 1

                print(
                    "Erreur d'envoi vers "
                    f"{utilisateur.email} : {erreur}"
                )

        if nombre_emails:
            self.message_user(
                request,
                (
                    f"{nombre_emails} email(s) de confirmation "
                    "envoyé(s)."
                ),
                level=messages.SUCCESS,
            )

        if nombre_erreurs:
            self.message_user(
                request,
                (
                    f"{nombre_erreurs} email(s) n'ont pas pu "
                    "être envoyés."
                ),
                level=messages.ERROR,
            )

        if nombre_emails == 0 and nombre_erreurs == 0:
            self.message_user(
                request,
                "Aucun compte actif éligible n'a été sélectionné.",
                level=messages.WARNING,
            )

    @admin.action(
        description="Refuser les demandes sélectionnées"
    )
    def refuser_demandes(self, request, queryset):
        nombre = queryset.filter(
            is_superuser=False,
            statut=User.StatutCompte.EN_ATTENTE,
        ).update(
            statut=User.StatutCompte.REFUSE,
            is_active=False,
        )

        self.message_user(
            request,
            f"{nombre} demande(s) refusée(s).",
            level=messages.WARNING,
        )

    @admin.action(
        description="Suspendre les comptes sélectionnés"
    )
    def suspendre_comptes(self, request, queryset):
        nombre = queryset.filter(
            is_superuser=False,
        ).update(
            statut=User.StatutCompte.SUSPENDU,
            is_active=False,
        )

        self.message_user(
            request,
            f"{nombre} compte(s) suspendu(s).",
            level=messages.WARNING,
        )

    @admin.action(
        description="Réactiver les comptes sélectionnés"
    )
    def reactiver_comptes(self, request, queryset):
        nombre = queryset.filter(
            is_superuser=False,
        ).update(
            role=User.Role.METIER,
            statut=User.StatutCompte.ACTIF,
            is_active=True,
        )

        self.message_user(
            request,
            f"{nombre} compte(s) réactivé(s).",
            level=messages.SUCCESS,
        )