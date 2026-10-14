from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models


class UserManager(BaseUserManager):
    """Gestionnaire utilisant l'adresse email pour l'authentification."""

    use_in_migrations = True

    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("L'adresse email est obligatoire.")

        email = self.normalize_email(email)

        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        extra_fields.setdefault("role", "METIER")
        extra_fields.setdefault("statut", "EN_ATTENTE")

        user = self.model(
            email=email,
            **extra_fields,
        )

        user.set_password(password)
        user.save(using=self._db)

        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("role", "ADMIN")
        extra_fields.setdefault("statut", "ACTIF")

        if extra_fields.get("is_staff") is not True:
            raise ValueError(
                "Un superutilisateur doit avoir is_staff=True."
            )

        if extra_fields.get("is_superuser") is not True:
            raise ValueError(
                "Un superutilisateur doit avoir is_superuser=True."
            )

        return self.create_user(
            email,
            password,
            **extra_fields,
        )


class User(AbstractUser):
    """Utilisateur de la plateforme HCP."""

    class Role(models.TextChoices):
        ADMIN = "ADMIN", "Administrateur"
        METIER = "METIER", "Utilisateur métier"

    class StatutCompte(models.TextChoices):
        EN_ATTENTE = "EN_ATTENTE", "En attente de validation"
        ACTIF = "ACTIF", "Actif"
        REFUSE = "REFUSE", "Refusé"
        SUSPENDU = "SUSPENDU", "Suspendu"
        DESACTIVE = "DESACTIVE", "Désactivé"

    username = None

    email = models.EmailField(
        verbose_name="Adresse email",
        unique=True,
    )

    role = models.CharField(
        verbose_name="Rôle",
        max_length=20,
        choices=Role.choices,
        default=Role.METIER,
    )

    statut = models.CharField(
        verbose_name="Statut du compte",
        max_length=20,
        choices=StatutCompte.choices,
        default=StatutCompte.EN_ATTENTE,
    )

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = UserManager()

    class Meta:
        verbose_name = "Utilisateur"
        verbose_name_plural = "Utilisateurs"
        ordering = [
            "last_name",
            "first_name",
            "email",
        ]

    def save(self, *args, **kwargs):
        """
        Synchronise automatiquement le statut métier
        avec le champ is_active de Django.
        """

        if self.is_superuser:
            self.role = self.Role.ADMIN
            self.statut = self.StatutCompte.ACTIF
            self.is_staff = True
            self.is_active = True
        else:
            self.is_active = (
                self.statut == self.StatutCompte.ACTIF
            )

        super().save(*args, **kwargs)

    def __str__(self):
        nom_complet = self.get_full_name().strip()

        return nom_complet if nom_complet else self.email

    @property
    def est_administrateur(self):
        return self.role == self.Role.ADMIN

    @property
    def est_utilisateur_metier(self):
        return self.role == self.Role.METIER

    @property
    def est_en_attente(self):
        return self.statut == self.StatutCompte.EN_ATTENTE