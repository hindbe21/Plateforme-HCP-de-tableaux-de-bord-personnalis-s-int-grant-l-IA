# Plateforme HCP — Code source

Projet pédagogique Django de gestion et d'analyse de jeux de données, nettoyage, tableaux de bord, administration et assistant IA.

## Organisation

- `accounts/` : utilisateurs et authentification
- `datasets/` : importation CSV/XLSX, qualité, nettoyage et stockage
- `dashboards/` : tableaux de bord, widgets et filtres
- `ai_assistant/` : fonctionnalités d'assistance IA et rapports
- `audit/` : suivi et journal d'activité
- `templates/` et `static/` : interface utilisateur
- `config/` : configuration Django
- `requirements.txt` : dépendances Python

## Mise en route locale (Windows / PowerShell)

Prérequis : Python compatible avec les versions de `requirements.txt`, PostgreSQL configuré, accès aux dépendances pip. Ollama est nécessaire pour certaines fonctions IA et doit disposer du modèle configuré.

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Modifier le nouveau fichier `.env` : choisir une véritable clé secrète Django, renseigner les identifiants PostgreSQL et, si nécessaire, les paramètres SMTP et Ollama. Pour générer une clé :

```powershell
python -c "import secrets; print(secrets.token_urlsafe(50))"
```

Préparer une **base PostgreSQL vide** destinée à l'installation, puis :

```powershell
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Adresse locale : `http://127.0.0.1:8000/`.

## Remarques de remise

- Le vrai `.env`, les mots de passe et les données des utilisateurs ne sont **pas** inclus. Les valeurs de `.env.example` sont fictives.
- L'environnement virtuel `venv` n'est pas inclus : chaque machine doit installer ses propres dépendances.
- Les migrations historiques sont conservées, car elles définissent le schéma Django.
- Ce ZIP est une **livraison de code source**, pas une base de données préremplie ni une installation vérifiée de bout en bout.
- La base PostgreSQL locale de développement a présenté un décalage entre des colonnes et les modèles, ainsi qu'un conflit d'historique de migrations. Tester `migrate` sur une base vide avant toute démonstration sur une autre machine. Ne pas appliquer une correction arbitraire à une base contenant des données.
- Les images de l'interface sont conservées ; vérifier les droits d'utilisation et la source du logo pour toute diffusion publique.
