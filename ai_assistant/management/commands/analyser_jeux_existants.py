from django.core.management.base import BaseCommand

from datasets.models import JeuDonnees

from ai_assistant.services.dataset_analyzer import analyser_et_enregistrer


class Command(BaseCommand):
    help = "Calcule l’analyse intelligente des jeux de données déjà importés."

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Recalculer même les analyses encore valides.",
        )

    def handle(self, *args, **options):
        force = bool(options["force"])
        succes = 0
        erreurs = 0

        for jeu_donnees in JeuDonnees.objects.all().order_by("pk"):
            try:
                analyser_et_enregistrer(jeu_donnees, force=force)
                succes += 1
                self.stdout.write(self.style.SUCCESS(
                    f"Analyse terminée : {jeu_donnees}"
                ))
            except Exception as erreur:
                erreurs += 1
                self.stderr.write(
                    f"Erreur pour {jeu_donnees} : {erreur}"
                )

        self.stdout.write(
            f"Terminé — {succes} analyse(s), {erreurs} erreur(s)."
        )
