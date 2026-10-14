from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher


ALIASES = {
    "annee": "year",
    "annees": "year",
    "an": "year",
    "ans": "year",
    "years": "year",
    "mois": "month",
    "trimestre": "quarter",
    "date": "date",
    "dates": "date",
    "nom": "name",
    "noms": "name",
    "libelle": "name",
    "industrie": "industry",
    "industries": "industry",
    "secteur": "industry",
    "secteurs": "industry",
    "region": "region",
    "regions": "region",
    "valeur": "value",
    "valeurs": "value",
    "montant": "amount",
    "montants": "amount",
    "nombre": "count",
    "nombres": "count",
    "categorie": "category",
    "categories": "category",
    "groupe": "group",
    "groupes": "group",
    "taille": "size",
    "unite": "unit",
    "unites": "unit",
    "code": "code",
    "codes": "code",
}

MOTS_IGNORES = {
    "la", "le", "les", "de", "du", "des", "d", "l",
    "une", "un", "colonne", "colonnes", "champ", "champs",
    "variable", "variables", "the", "of", "column", "columns",
}


def normaliser_texte(valeur) -> str:
    texte = str(valeur or "").lower()
    texte = unicodedata.normalize("NFKD", texte)
    texte = "".join(
        caractere
        for caractere in texte
        if not unicodedata.combining(caractere)
    )
    texte = re.sub(r"[^a-z0-9]+", " ", texte)
    return " ".join(texte.split())


def tokens(valeur) -> list[str]:
    resultat = []
    for token in normaliser_texte(valeur).split():
        token = ALIASES.get(token, token)
        if token and token not in MOTS_IGNORES:
            resultat.append(token)
    return resultat


def score_colonne(expression, colonne) -> float:
    gauche = tokens(expression)
    droite = tokens(colonne)
    if not gauche or not droite:
        return 0.0

    set_gauche = set(gauche)
    set_droite = set(droite)
    if set_gauche == set_droite:
        return 1.0

    intersection = set_gauche & set_droite
    precision = len(intersection) / len(set_gauche)
    rappel = len(intersection) / len(set_droite)
    f1 = (
        2 * precision * rappel / (precision + rappel)
        if precision + rappel
        else 0.0
    )

    ratio_ordre = SequenceMatcher(
        None,
        " ".join(gauche),
        " ".join(droite),
    ).ratio()
    ratio_trie = SequenceMatcher(
        None,
        " ".join(sorted(set_gauche)),
        " ".join(sorted(set_droite)),
    ).ratio()
    return max(f1, ratio_ordre, ratio_trie)


def resoudre_colonne(nom, colonnes, seuil=None) -> str:
    nom = str(nom or "").strip()
    if not nom:
        return ""
    if nom in colonnes:
        return nom

    normalise = normaliser_texte(nom)
    for colonne in colonnes:
        if normaliser_texte(colonne) == normalise:
            return colonne

    candidats = sorted(
        (
            (score_colonne(nom, colonne), colonne)
            for colonne in colonnes
        ),
        key=lambda item: (-item[0], str(item[1])),
    )
    if not candidats:
        return nom

    meilleur_score, meilleure = candidats[0]
    deuxieme = candidats[1][0] if len(candidats) > 1 else 0.0
    if seuil is None:
        seuil = 0.88 if len(tokens(nom)) <= 1 else 0.74

    if meilleur_score >= seuil and (
        meilleur_score - deuxieme >= 0.05
        or meilleur_score >= 0.95
    ):
        return meilleure
    return nom


def colonnes_mentionnees(demande, colonnes) -> list[str]:
    texte = normaliser_texte(demande)
    trouves = []

    for colonne in colonnes:
        nom = normaliser_texte(colonne)
        if nom and re.search(rf"\b{re.escape(nom)}\b", texte):
            trouves.append(colonne)

    mots = tokens(demande)
    for colonne in colonnes:
        if colonne in trouves:
            continue
        longueur = max(1, len(tokens(colonne)))
        meilleur = 0.0
        for taille in {max(1, longueur - 1), longueur, longueur + 1}:
            if taille > len(mots):
                continue
            for index in range(len(mots) - taille + 1):
                morceau = " ".join(mots[index:index + taille])
                meilleur = max(meilleur, score_colonne(morceau, colonne))
        seuil = 0.90 if longueur == 1 else 0.78
        if meilleur >= seuil:
            trouves.append(colonne)

    return trouves
