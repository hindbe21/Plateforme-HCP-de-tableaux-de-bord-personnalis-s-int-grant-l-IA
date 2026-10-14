# HCP Dashboard – Plateforme de tableaux de bord personnalisés

Ce projet a été réalisé dans le cadre de mon stage au sein de la Direction des Systèmes d'Informations Statistiques (DSIS) du Haut-Commissariat au Plan (HCP).

Il consiste à développer une application web permettant de gérer, nettoyer et analyser des jeux de données, puis de créer des tableaux de bord personnalisés.

## Fonctionnalités principales

- Importation de fichiers CSV et Excel
- Analyse de la qualité des données
- Nettoyage des données (doublons, valeurs manquantes, etc.)
- Création de tableaux de bord et de graphiques
- Gestion des utilisateurs et des permissions
- Exportation des résultats et des rapports
- Assistant IA pour l'analyse des données et les recommandations

## Technologies utilisées

- **Backend :** Python, Django
- **Base de données :** PostgreSQL
- **Frontend :** HTML, CSS, JavaScript
- **Traitement des données :** Pandas
- **Intelligence artificielle :** Ollama

## Structure du projet

- `accounts/` : gestion des utilisateurs
- `datasets/` : importation et nettoyage des données
- `dashboards/` : création des tableaux de bord
- `ai_assistant/` : assistant IA
- `audit/` : historique des activités
- `templates/` : pages HTML
- `static/` : fichiers CSS, JavaScript et images
- `config/` : configuration Django

## Exécution

Les dépendances nécessaires sont indiquées dans `requirements.txt`. L'application nécessite une configuration locale de PostgreSQL et des variables d'environnement.

Le dépôt contient le code source du projet. La démonstration de l'application est réalisée en local.

---

**Réalisé par :** Hind Berma  
**Établissement :** École des Sciences de l'Information (ESI) – Rabat  
**Année :** 2026
