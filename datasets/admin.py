from django.contrib import admin

from .models import (
    JeuDonnees,
    OperationNettoyage,
)
from django.utils.html import format_html, format_html_join

@admin.register(JeuDonnees)
class JeuDonneesAdmin(admin.ModelAdmin):
    list_display = (
        "nom",
        "proprietaire",
        "format",
        "type_version",
        "numero_version",
        "nombre_lignes",
        "nombre_colonnes",
        "statut",
        "date_importation",
    )

    list_filter = (
        "format",
        "statut",
        "type_version",
        "date_importation",
    )

    search_fields = (
        "nom",
        "description",
        "nom_fichier_original",
        "proprietaire__email",
        "proprietaire__first_name",
        "proprietaire__last_name",
    )

    readonly_fields = (
        "nombre_lignes",
        "nombre_colonnes",
        "colonnes",
        "types_colonnes",
        "taille_fichier",
        "date_importation",
        "date_modification",
    )

    ordering = (
        "-date_importation",
    )

    list_select_related = (
        "proprietaire",
        "source_jeu_donnees",
    )

    fieldsets = (
        (
            "Informations générales",
            {
                "fields": (
                    "proprietaire",
                    "nom",
                    "description",
                    "statut",
                )
            },
        ),
        (
            "Version du jeu de données",
            {
                "fields": (
                    "type_version",
                    "numero_version",
                    "source_jeu_donnees",
                )
            },
        ),
        (
            "Fichier d’origine",
            {
                "fields": (
                    "nom_fichier_original",
                    "format",
                    "taille_fichier",
                )
            },
        ),
        (
            "Structure des données",
            {
                "fields": (
                    "nombre_lignes",
                    "nombre_colonnes",
                    "colonnes",
                    "types_colonnes",
                )
            },
        ),
        (
            "Validation",
            {
                "fields": (
                    "message_erreur",
                )
            },
        ),
        (
            "Dates",
            {
                "fields": (
                    "date_importation",
                    "date_modification",
                )
            },
        ),
    )




@admin.register(OperationNettoyage)
class OperationNettoyageAdmin(admin.ModelAdmin):
    list_display = (
        "jeu_source",
        "jeu_resultat",
        "utilisateur",
        "resume_court",
        "date_creation",
    )

    list_filter = (
        "date_creation",
    )

    search_fields = (
        "jeu_source__nom",
        "jeu_resultat__nom",
        "utilisateur__email",
        "utilisateur__first_name",
        "utilisateur__last_name",
    )

    ordering = (
        "-date_creation",
    )

    list_select_related = (
        "jeu_source",
        "jeu_resultat",
        "utilisateur",
    )

    readonly_fields = (
        "jeu_source",
        "jeu_resultat",
        "utilisateur",
        "operations_lisibles",
        "resume_lisible",
        "diagnostic_avant_lisible",
        "diagnostic_apres_lisible",
        "date_creation",
    )

    fieldsets = (
        (
            "Informations générales",
            {
                "fields": (
                    "jeu_source",
                    "jeu_resultat",
                    "utilisateur",
                    "date_creation",
                )
            },
        ),
        (
            "Opérations appliquées",
            {
                "fields": (
                    "operations_lisibles",
                )
            },
        ),
        (
            "Résumé du nettoyage",
            {
                "fields": (
                    "resume_lisible",
                )
            },
        ),
        (
            "Diagnostic avant nettoyage",
            {
                "fields": (
                    "diagnostic_avant_lisible",
                ),
                "classes": (
                    "collapse",
                ),
            },
        ),
        (
            "Diagnostic après nettoyage",
            {
                "fields": (
                    "diagnostic_apres_lisible",
                ),
                "classes": (
                    "collapse",
                ),
            },
        ),
    )

    def has_add_permission(self, request):
        """
        Les opérations sont créées automatiquement
        par la plateforme.
        """
        return False

    def has_change_permission(
        self,
        request,
        obj=None,
    ):
        """
        L'historique ne doit pas être modifié
        manuellement depuis l'administration.
        """
        return False

    @admin.display(
        description="Résumé"
    )
    def resume_court(self, obj):
        resume = obj.resume or {}

        lignes_avant = resume.get(
            "lignes_avant",
            0,
        )

        lignes_apres = resume.get(
            "lignes_apres",
            0,
        )

        valeurs_traitees = resume.get(
            "valeurs_manquantes_traitees",
            0,
        )

        return (
            f"{lignes_avant} → {lignes_apres} lignes | "
            f"{valeurs_traitees} valeur(s) manquante(s) traitée(s)"
        )

    def formater_valeur(self, valeur):
        if isinstance(valeur, bool):
            return (
                "Oui"
                if valeur
                else "Non"
            )

        if isinstance(valeur, list):
            if not valeur:
                return "Aucune"

            return ", ".join(
                str(element)
                for element in valeur
            )

        if valeur in [
            None,
            "",
        ]:
            return "—"

        traductions = {
            "AUCUNE": "Aucune action",
            "MOYENNE": "Remplacement par la moyenne",
            "MEDIANE": "Remplacement par la médiane",
            "MODE": "Remplacement par la valeur la plus fréquente",
            "SUPPRIMER": "Suppression",
            "BORNER": "Limitation aux bornes",
        }

        return traductions.get(
            str(valeur),
            str(valeur),
        )

    def creer_liste_html(
        self,
        donnees,
        libelles,
    ):
        elements = []

        for cle, valeur in donnees.items():
            libelle = libelles.get(
                cle,
                cle.replace(
                    "_",
                    " ",
                ).capitalize(),
            )

            elements.append(
                (
                    libelle,
                    self.formater_valeur(
                        valeur
                    ),
                )
            )

        if not elements:
            return "Aucune information disponible."

        liste = format_html_join(
            "",
            (
                "<li style='margin-bottom:8px;'>"
                "<strong>{}</strong> : {}"
                "</li>"
            ),
            elements,
        )

        return format_html(
            (
                "<ul style='margin:0;"
                "padding-left:20px;"
                "line-height:1.5;'>"
                "{}"
                "</ul>"
            ),
            liste,
        )

    @admin.display(
        description="Opérations appliquées"
    )
    def operations_lisibles(self, obj):
        operations = obj.operations or {}

        libelles = {
            "nom_version": "Nom de la version créée",
            "nettoyer_textes": "Nettoyer les textes",
            "convertir_nombres": "Convertir les nombres",
            "supprimer_lignes_vides": (
                "Supprimer les lignes entièrement vides"
            ),
            "supprimer_doublons": "Supprimer les doublons",
            "colonnes_doublons": (
                "Colonnes utilisées pour les doublons"
            ),
            "colonne_manquante": (
                "Colonne contenant des valeurs manquantes"
            ),
            "strategie_manquante": (
                "Traitement des valeurs manquantes"
            ),
            "valeur_remplacement": (
                "Valeur de remplacement"
            ),
            "colonne_aberrante": (
                "Colonne des valeurs aberrantes"
            ),
            "action_aberrante": (
                "Traitement des valeurs aberrantes"
            ),
        }

        return self.creer_liste_html(
            operations,
            libelles,
        )

    @admin.display(
        description="Résumé du nettoyage"
    )
    def resume_lisible(self, obj):
        resume = obj.resume or {}

        libelles = {
            "lignes_avant": "Nombre de lignes avant",
            "lignes_apres": "Nombre de lignes après",
            "lignes_vides_supprimees": (
                "Lignes entièrement vides supprimées"
            ),
            "doublons_supprimes": "Doublons supprimés",
            "valeurs_manquantes_traitees": (
                "Valeurs manquantes traitées"
            ),
            "valeurs_aberrantes_detectees": (
                "Valeurs aberrantes détectées"
            ),
            "valeurs_aberrantes_traitees": (
                "Valeurs aberrantes traitées"
            ),
            "textes_nettoyes": "Textes nettoyés",
            "nombres_convertis": (
                "Colonnes numériques converties"
            ),
        }

        return self.creer_liste_html(
            resume,
            libelles,
        )

    def construire_diagnostic_html(
        self,
        diagnostic,
    ):
        if not diagnostic:
            return "Aucun diagnostic disponible."

        resume = format_html(
            """
            <div style="
                display:grid;
                grid-template-columns:repeat(3, minmax(160px, 1fr));
                gap:12px;
                margin-bottom:20px;
            ">
                <div style="
                    background:#f8f9fa;
                    border:1px solid #dee2e6;
                    border-radius:8px;
                    padding:12px;
                ">
                    <strong>{}</strong><br>
                    <span style="color:#6c757d;">Lignes</span>
                </div>

                <div style="
                    background:#f8f9fa;
                    border:1px solid #dee2e6;
                    border-radius:8px;
                    padding:12px;
                ">
                    <strong>{}</strong><br>
                    <span style="color:#6c757d;">Colonnes</span>
                </div>

                <div style="
                    background:#f8f9fa;
                    border:1px solid #dee2e6;
                    border-radius:8px;
                    padding:12px;
                ">
                    <strong>{}</strong><br>
                    <span style="color:#6c757d;">Valeurs manquantes</span>
                </div>

                <div style="
                    background:#f8f9fa;
                    border:1px solid #dee2e6;
                    border-radius:8px;
                    padding:12px;
                ">
                    <strong>{}</strong><br>
                    <span style="color:#6c757d;">Doublons</span>
                </div>

                <div style="
                    background:#f8f9fa;
                    border:1px solid #dee2e6;
                    border-radius:8px;
                    padding:12px;
                ">
                    <strong>{}</strong><br>
                    <span style="color:#6c757d;">Lignes vides</span>
                </div>

                <div style="
                    background:#f8f9fa;
                    border:1px solid #dee2e6;
                    border-radius:8px;
                    padding:12px;
                ">
                    <strong>{}</strong><br>
                    <span style="color:#6c757d;">Valeurs aberrantes</span>
                </div>
            </div>
            """,
            diagnostic.get(
                "nombre_lignes",
                0,
            ),
            diagnostic.get(
                "nombre_colonnes",
                0,
            ),
            diagnostic.get(
                "valeurs_manquantes",
                0,
            ),
            diagnostic.get(
                "doublons",
                0,
            ),
            diagnostic.get(
                "lignes_vides",
                0,
            ),
            diagnostic.get(
                "nombre_valeurs_aberrantes",
                0,
            ),
        )

        colonnes = diagnostic.get(
            "colonnes",
            [],
        )

        lignes_colonnes = format_html_join(
            "",
            """
            <tr>
                <td style="padding:8px;border-bottom:1px solid #ddd;">
                    {}
                </td>
                <td style="padding:8px;border-bottom:1px solid #ddd;">
                    {}
                </td>
                <td style="padding:8px;border-bottom:1px solid #ddd;">
                    {}
                </td>
                <td style="padding:8px;border-bottom:1px solid #ddd;">
                    {} %
                </td>
            </tr>
            """,
            (
                (
                    colonne.get(
                        "nom",
                        "—",
                    ),
                    colonne.get(
                        "type",
                        "—",
                    ),
                    colonne.get(
                        "manquantes",
                        0,
                    ),
                    colonne.get(
                        "pourcentage",
                        0,
                    ),
                )
                for colonne in colonnes
            ),
        )

        tableau_colonnes = format_html(
            """
            <h3 style="margin-top:15px;">
                Qualité par colonne
            </h3>

            <div style="overflow-x:auto;">
                <table style="
                    width:100%;
                    border-collapse:collapse;
                    background:white;
                ">
                    <thead>
                        <tr style="background:#f1f3f5;">
                            <th style="padding:8px;text-align:left;">
                                Colonne
                            </th>
                            <th style="padding:8px;text-align:left;">
                                Type
                            </th>
                            <th style="padding:8px;text-align:left;">
                                Valeurs manquantes
                            </th>
                            <th style="padding:8px;text-align:left;">
                                Pourcentage
                            </th>
                        </tr>
                    </thead>

                    <tbody>
                        {}
                    </tbody>
                </table>
            </div>
            """,
            lignes_colonnes,
        )

        valeurs_aberrantes = diagnostic.get(
            "valeurs_aberrantes",
            [],
        )

        if valeurs_aberrantes:
            lignes_aberrantes = format_html_join(
                "",
                """
                <tr>
                    <td style="padding:8px;border-bottom:1px solid #ddd;">
                        {}
                    </td>
                    <td style="padding:8px;border-bottom:1px solid #ddd;">
                        {}
                    </td>
                    <td style="padding:8px;border-bottom:1px solid #ddd;">
                        {}
                    </td>
                    <td style="padding:8px;border-bottom:1px solid #ddd;">
                        {}
                    </td>
                </tr>
                """,
                (
                    (
                        element.get(
                            "colonne",
                            "—",
                        ),
                        element.get(
                            "nombre",
                            0,
                        ),
                        element.get(
                            "borne_basse",
                            "—",
                        ),
                        element.get(
                            "borne_haute",
                            "—",
                        ),
                    )
                    for element in valeurs_aberrantes
                ),
            )

            tableau_aberrantes = format_html(
                """
                <h3 style="margin-top:25px;">
                    Valeurs potentiellement aberrantes
                </h3>

                <div style="overflow-x:auto;">
                    <table style="
                        width:100%;
                        border-collapse:collapse;
                        background:white;
                    ">
                        <thead>
                            <tr style="background:#f1f3f5;">
                                <th style="padding:8px;text-align:left;">
                                    Colonne
                                </th>
                                <th style="padding:8px;text-align:left;">
                                    Nombre
                                </th>
                                <th style="padding:8px;text-align:left;">
                                    Borne basse
                                </th>
                                <th style="padding:8px;text-align:left;">
                                    Borne haute
                                </th>
                            </tr>
                        </thead>

                        <tbody>
                            {}
                        </tbody>
                    </table>
                </div>
                """,
                lignes_aberrantes,
            )
        else:
            tableau_aberrantes = format_html(
                """
                <p style="margin-top:20px;color:#198754;">
                    Aucune valeur aberrante détectée.
                </p>
                """
            )

        return format_html(
            "{}{}{}",
            resume,
            tableau_colonnes,
            tableau_aberrantes,
        )

    @admin.display(
        description="Diagnostic avant nettoyage"
    )
    def diagnostic_avant_lisible(self, obj):
        return self.construire_diagnostic_html(
            obj.diagnostic_avant
        )

    @admin.display(
        description="Diagnostic après nettoyage"
    )
    def diagnostic_apres_lisible(self, obj):
        return self.construire_diagnostic_html(
            obj.diagnostic_apres
        )