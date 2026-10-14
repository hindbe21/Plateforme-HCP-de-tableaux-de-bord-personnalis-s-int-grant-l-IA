from datetime import date, datetime
import hashlib
from decimal import Decimal
from io import BytesIO
from pathlib import Path

import pandas as pd
from django.core.exceptions import ValidationError
from django.db import transaction
from pandas.api.types import (
    is_bool_dtype,
    is_datetime64_any_dtype,
    is_float_dtype,
    is_integer_dtype,
)
from pandas.errors import EmptyDataError, ParserError

from django.db.models import Max

from .models import (
    JeuDonnees,
    LigneDonnees,
    OperationNettoyage,
)

NOMBRE_MAXIMAL_LIGNES = 100_000
TAILLE_LOT_INSERTION = 1000


def lire_csv(contenu):
    """Lit un CSV avec différents encodages."""

    encodages = [
        "utf-8-sig",
        "utf-8",
        "latin-1",
    ]

    derniere_erreur = None

    for encodage in encodages:
        try:
            return pd.read_csv(
                BytesIO(contenu),
                sep=None,
                engine="python",
                encoding=encodage,
            )

        except UnicodeDecodeError as erreur:
            derniere_erreur = erreur

        except EmptyDataError as erreur:
            raise ValidationError(
                "Le fichier CSV est vide."
            ) from erreur

        except ParserError as erreur:
            raise ValidationError(
                "Le fichier CSV est mal structuré."
            ) from erreur

    raise ValidationError(
        "Impossible de déterminer l'encodage du fichier CSV."
    ) from derniere_erreur


def normaliser_colonnes(dataframe):
    """Nettoie et rend uniques les noms des colonnes."""

    colonnes = []
    occurrences = {}

    for index, colonne in enumerate(dataframe.columns):
        nom = str(colonne).strip()

        if not nom or nom.lower().startswith("unnamed:"):
            nom = f"colonne_{index + 1}"

        nombre_occurrences = occurrences.get(nom, 0)

        if nombre_occurrences:
            nom_unique = f"{nom}_{nombre_occurrences + 1}"
        else:
            nom_unique = nom

        occurrences[nom] = nombre_occurrences + 1
        colonnes.append(nom_unique)

    dataframe.columns = colonnes

    return colonnes


def normaliser_valeur_numerique(valeur):
    """Prépare une valeur textuelle avant conversion numérique."""

    if valeur is None:
        return valeur

    if isinstance(valeur, str):
        texte = valeur.strip()

        if not texte:
            return pd.NA

        texte = (
            texte
            .replace("\u00a0", "")
            .replace(" ", "")
        )

        if "," in texte and "." not in texte:
            texte = texte.replace(",", ".")

        return texte

    return valeur


def analyser_conversion_numerique(serie):
    """Retourne la série convertie et le taux de conversion réussi."""

    preparee = serie.apply(
        normaliser_valeur_numerique
    )

    valeurs_non_vides = preparee.dropna()

    if valeurs_non_vides.empty:
        return None, 0.0

    conversion_non_vide = pd.to_numeric(
        valeurs_non_vides,
        errors="coerce",
    )

    ratio = float(
        conversion_non_vide.notna().mean()
    )

    conversion_complete = pd.to_numeric(
        preparee,
        errors="coerce",
    )

    return conversion_complete, ratio


def detecter_type_colonne(serie):
    """Détermine le type général d'une colonne."""

    valeurs = serie.dropna()

    if valeurs.empty:
        return "vide"

    if is_bool_dtype(valeurs):
        return "booleen"

    if is_integer_dtype(valeurs):
        return "entier"

    if is_float_dtype(valeurs):
        return "nombre"

    if is_datetime64_any_dtype(valeurs):
        return "date"

    _, ratio_numerique = analyser_conversion_numerique(
        serie
    )

    if ratio_numerique >= 0.90:
        return "nombre"

    return "texte"


def convertir_valeur_json(valeur):
    """Convertit une valeur pandas en valeur compatible JSON."""

    if valeur is None:
        return None

    try:
        if pd.isna(valeur):
            return None
    except (TypeError, ValueError):
        pass

    if isinstance(valeur, pd.Timestamp):
        return valeur.isoformat()

    if isinstance(valeur, (datetime, date)):
        return valeur.isoformat()

    if isinstance(valeur, Decimal):
        return float(valeur)

    if hasattr(valeur, "item"):
        valeur = valeur.item()

    if isinstance(
        valeur,
        (
            str,
            int,
            float,
            bool,
        ),
    ):
        return valeur

    return str(valeur)


def analyser_fichier(fichier):
    """
    Lit le fichier temporaire et retourne son DataFrame
    ainsi que ses métadonnées.
    """

    extension = Path(fichier.name).suffix.lower()
    contenu = fichier.read()

    fichier.seek(0)

    try:
        if extension == ".csv":
            dataframe = lire_csv(contenu)
            format_fichier = JeuDonnees.FormatFichier.CSV

        elif extension == ".xlsx":
            dataframe = pd.read_excel(
                BytesIO(contenu),
                engine="openpyxl",
            )

            format_fichier = JeuDonnees.FormatFichier.EXCEL

        else:
            raise ValidationError(
                "Le format du fichier n'est pas pris en charge."
            )

    except ValidationError:
        raise

    except EmptyDataError as erreur:
        raise ValidationError(
            "Le fichier ne contient aucune donnée."
        ) from erreur

    except Exception as erreur:
        raise ValidationError(
            "Impossible de lire le fichier. "
            "Vérifiez qu'il n'est pas endommagé."
        ) from erreur

    if dataframe.shape[1] == 0:
        raise ValidationError(
            "Le fichier ne contient aucune colonne."
        )

    if dataframe.empty:
        raise ValidationError(
            "Le fichier ne contient aucune ligne de données."
        )

    if len(dataframe) > NOMBRE_MAXIMAL_LIGNES:
        raise ValidationError(
            "Le fichier contient plus de 100 000 lignes. "
            "Veuillez importer un fichier plus petit."
        )

    dataframe = dataframe.reset_index(drop=True)

    colonnes = normaliser_colonnes(dataframe)

    types_colonnes = {
        colonne: detecter_type_colonne(dataframe[colonne])
        for colonne in colonnes
    }

    return {
        "dataframe": dataframe,
        "format": format_fichier,
        "nombre_lignes": int(dataframe.shape[0]),
        "nombre_colonnes": int(dataframe.shape[1]),
        "colonnes": colonnes,
        "types_colonnes": types_colonnes,
    }


@transaction.atomic
def enregistrer_dans_postgresql(
    *,
    proprietaire,
    nom,
    description,
    fichier,
    analyse,
):
    """
    Enregistre le jeu de données et toutes ses lignes
    dans une transaction PostgreSQL.
    """

    dataframe = analyse["dataframe"]
    colonnes = analyse["colonnes"]

    jeu_donnees = JeuDonnees.objects.create(
        proprietaire=proprietaire,
        nom=nom,
        description=description,
        nom_fichier_original=fichier.name,
        format=analyse["format"],
        nombre_lignes=analyse["nombre_lignes"],
        nombre_colonnes=analyse["nombre_colonnes"],
        colonnes=colonnes,
        types_colonnes=analyse["types_colonnes"],
        taille_fichier=fichier.size,
        statut=JeuDonnees.Statut.VALIDE,
        message_erreur="",
    )

    for debut in range(
        0,
        len(dataframe),
        TAILLE_LOT_INSERTION,
    ):
        fin = debut + TAILLE_LOT_INSERTION

        lot_dataframe = dataframe.iloc[
            debut:fin
        ]

        objets = []

        for numero, ligne in enumerate(
            lot_dataframe.to_dict(orient="records"),
            start=debut + 1,
        ):
            donnees = {
                colonne: convertir_valeur_json(
                    ligne.get(colonne)
                )
                for colonne in colonnes
            }

            objets.append(
                LigneDonnees(
                    jeu_donnees=jeu_donnees,
                    numero_ligne=numero,
                    donnees=donnees,
                )
            )

        LigneDonnees.objects.bulk_create(
            objets,
            batch_size=TAILLE_LOT_INSERTION,
        )

    return jeu_donnees
def charger_dataframe_postgresql(jeu_donnees):
    """Reconstruit un DataFrame depuis les lignes PostgreSQL."""

    lignes = list(
        jeu_donnees.lignes
        .order_by("numero_ligne")
        .values_list("donnees", flat=True)
    )

    return pd.DataFrame(
        lignes,
        columns=jeu_donnees.colonnes,
    )


MARQUEURS_VALEURS_MANQUANTES = {
    "",
    "na",
    "n/a",
    "n.a",
    "nan",
    "null",
    "none",
    "missing",
    "manquant",
    "manquante",
    "vide",
    "-",
    "--",
}


def valeur_est_marqueur_manquant(valeur):
    if valeur is None:
        return True

    try:
        if pd.isna(valeur):
            return True
    except (TypeError, ValueError):
        pass

    if not isinstance(valeur, str):
        return False

    texte = valeur.strip().casefold()

    return texte in MARQUEURS_VALEURS_MANQUANTES


def normaliser_valeurs_vides(dataframe):
    """
    Transforme les cellules vides et les marqueurs usuels
    (« Manquante », NA, null...) en véritables valeurs manquantes.
    """

    resultat = dataframe.copy()

    for colonne in resultat.columns:
        resultat[colonne] = resultat[colonne].apply(
            lambda valeur: (
                pd.NA
                if valeur_est_marqueur_manquant(valeur)
                else (
                    valeur.strip()
                    if isinstance(valeur, str)
                    else valeur
                )
            )
        )

    return resultat


def convertir_serie_numerique(
    serie,
    seuil=0.90,
):
    """
    Convertit une colonne lorsqu'au moins 90 % des valeurs
    non vides sont réellement numériques.
    """

    conversion, ratio = analyser_conversion_numerique(
        serie
    )

    if conversion is None or ratio < seuil:
        return None

    return conversion


def convertir_serie_date(
    serie,
    seuil=0.90,
):
    """
    Convertit prudemment une colonne textuelle en dates.

    Une colonne déjà numérique, par exemple une année 2011,
    reste numérique et n'est pas transformée en date complète.
    """

    serie = normaliser_valeurs_vides(
        pd.DataFrame({"valeur": serie})
    )["valeur"]

    valeurs = serie.dropna()

    if valeurs.empty:
        return None

    _, ratio_numerique = analyser_conversion_numerique(
        serie
    )

    if ratio_numerique >= 0.90:
        return None

    conversion_valide = pd.to_datetime(
        valeurs,
        errors="coerce",
        dayfirst=True,
        format="mixed",
    )

    ratio_date = float(
        conversion_valide.notna().mean()
    )

    if ratio_date < seuil:
        return None

    return pd.to_datetime(
        serie,
        errors="coerce",
        dayfirst=True,
        format="mixed",
    )


def normaliser_valeur_comparaison(valeur):
    """Produit une valeur stable pour comparer deux colonnes."""

    if valeur_est_marqueur_manquant(valeur):
        return "<VIDE>"

    if isinstance(valeur, (datetime, date, pd.Timestamp)):
        return pd.Timestamp(valeur).isoformat()

    if isinstance(valeur, Decimal):
        valeur = float(valeur)

    if isinstance(valeur, bool):
        return str(valeur).lower()

    if isinstance(valeur, (int, float)):
        nombre = float(valeur)

        if nombre.is_integer():
            return str(int(nombre))

        return format(nombre, ".12g")

    texte = str(valeur).strip().casefold()

    nombre = normaliser_valeur_numerique(texte)

    try:
        nombre_converti = float(nombre)

        if nombre_converti.is_integer():
            return str(int(nombre_converti))

        return format(nombre_converti, ".12g")
    except (TypeError, ValueError):
        return " ".join(texte.split())


def serie_normalisee_comparaison(serie):
    return serie.apply(
        normaliser_valeur_comparaison
    )


def analyser_colonnes_dupliquees(dataframe):
    """Retourne {colonne_dupliquée: colonne_originale}."""

    signatures = {}
    dupliquees = {}

    for colonne in dataframe.columns:
        normalisee = serie_normalisee_comparaison(
            dataframe[colonne]
        )

        empreinte = hashlib.sha256(
            pd.util.hash_pandas_object(
                normalisee,
                index=False,
            ).values.tobytes()
        ).hexdigest()

        candidates = signatures.setdefault(
            empreinte,
            [],
        )

        originale = None

        for candidate in candidates:
            if normalisee.equals(
                serie_normalisee_comparaison(
                    dataframe[candidate]
                )
            ):
                originale = candidate
                break

        if originale is None:
            candidates.append(colonne)
        else:
            dupliquees[colonne] = originale

    return dupliquees


def proposer_cible_fusion(
    dataframe,
    source,
    informations,
):
    """
    Cherche une colonne pouvant recevoir les rares valeurs
    d'une colonne presque vide.

    La recommandation repose sur les valeurs communes, le type
    et le fait que la destination soit vide sur les mêmes lignes.
    """

    serie_source = dataframe[source]
    masque_source = serie_source.notna()

    if not masque_source.any():
        return "", 0.0

    valeurs_source = {
        normaliser_valeur_comparaison(valeur)
        for valeur in serie_source.loc[
            masque_source
        ].tolist()
    }

    valeurs_source.discard("<VIDE>")

    if not valeurs_source:
        return "", 0.0

    type_source = informations[source]["type"]
    candidats = []

    for cible in dataframe.columns:
        if cible == source:
            continue

        information_cible = informations[cible]

        if information_cible["pourcentage"] >= 95:
            continue

        serie_cible = dataframe[cible]

        valeurs_cible = {
            normaliser_valeur_comparaison(valeur)
            for valeur in serie_cible.dropna().tolist()
        }

        valeurs_cible.discard("<VIDE>")

        if valeurs_cible:
            chevauchement = (
                len(
                    valeurs_source
                    & valeurs_cible
                )
                / len(valeurs_source)
            )
        else:
            chevauchement = 0.0

        complementarite = float(
            serie_cible.loc[
                masque_source
            ].isna().mean()
        )

        type_compatible = (
            1.0
            if type_source
            == information_cible["type"]
            else 0.0
        )

        score = (
            0.65 * chevauchement
            + 0.25 * complementarite
            + 0.10 * type_compatible
        )

        candidats.append(
            (
                score,
                cible,
            )
        )

    candidats.sort(
        key=lambda element: (
            -element[0],
            str(element[1]),
        )
    )

    if not candidats:
        return "", 0.0

    meilleur_score, meilleure_cible = candidats[0]
    deuxieme_score = (
        candidats[1][0]
        if len(candidats) > 1
        else 0.0
    )

    if (
        meilleur_score >= 0.78
        and (
            meilleur_score
            - deuxieme_score
            >= 0.10
            or meilleur_score >= 0.95
        )
    ):
        return meilleure_cible, round(
            meilleur_score,
            3,
        )

    return "", round(
        meilleur_score,
        3,
    )


def nom_ressemble_identifiant(colonne):
    nom = str(colonne).strip().lower()

    mots = {
        "id",
        "identifiant",
        "code",
        "numero",
        "numéro",
        "num",
        "cin",
        "cne",
        "matricule",
    }

    morceaux = (
        nom
        .replace("-", "_")
        .replace(" ", "_")
        .split("_")
    )

    return any(
        morceau in mots
        for morceau in morceaux
    )


def recommander_traitement_manquant(
    colonne,
    serie,
    type_colonne,
    pourcentage,
    contient_aberrantes,
):
    valeurs_valides = serie.dropna()
    nombre_valides = len(valeurs_valides)
    nombre_uniques = int(
        valeurs_valides.nunique()
    )
    ratio_uniques = (
        nombre_uniques / nombre_valides
        if nombre_valides
        else 0
    )

    if pourcentage >= 40:
        return {
            "recommandation_action": "AUCUNE",
            "recommandation_libelle": "Ne rien faire automatiquement",
            "recommandation": (
                "La proportion de valeurs manquantes est élevée. "
                "Une imputation automatique pourrait modifier fortement "
                "les résultats statistiques."
            ),
        }

    if (
        nom_ressemble_identifiant(colonne)
        and ratio_uniques >= 0.70
    ):
        return {
            "recommandation_action": "AUCUNE",
            "recommandation_libelle": "Ne rien faire automatiquement",
            "recommandation": (
                "Cette colonne ressemble à un identifiant ou à un code. "
                "Une moyenne, une médiane ou un mode n'aurait pas de sens."
            ),
        }

    if type_colonne == "nombre":
        serie_numerique = convertir_serie_numerique(
            serie
        )

        asymetrie = 0.0

        if serie_numerique is not None:
            valeurs_numeriques = (
                serie_numerique.dropna()
            )

            if len(valeurs_numeriques) >= 3:
                asymetrie = float(
                    valeurs_numeriques.skew()
                )

        if contient_aberrantes or abs(asymetrie) >= 1:
            return {
                "recommandation_action": "MEDIANE",
                "recommandation_libelle": "Remplacer par la médiane",
                "recommandation": (
                    "La médiane est recommandée, car la distribution "
                    "est asymétrique ou contient des valeurs inhabituelles. "
                    "Elle est moins sensible aux valeurs extrêmes."
                ),
            }

        return {
            "recommandation_action": "MOYENNE",
            "recommandation_libelle": "Remplacer par la moyenne",
            "recommandation": (
                "La moyenne est recommandée, car la colonne est numérique "
                "et aucune forte asymétrie n'a été détectée."
            ),
        }

    if (
        nombre_uniques <= 10
        and ratio_uniques <= 0.50
    ):
        return {
            "recommandation_action": "MODE",
            "recommandation_libelle": "Utiliser la valeur la plus fréquente",
            "recommandation": (
                "La colonne contient un nombre limité de catégories. "
                "La valeur la plus fréquente est le choix le plus cohérent."
            ),
        }

    return {
        "recommandation_action": "NON_RENSEIGNE",
        "recommandation_libelle": "Remplacer par « Non renseigné »",
        "recommandation": (
            "La colonne contient de nombreuses valeurs distinctes. "
            "« Non renseigné » permet de conserver explicitement "
            "l'absence d'information sans inventer une catégorie."
        ),
    }


def diagnostiquer_qualite(dataframe):
    """
    Produit un diagnostic complet mais prudent :
    doublons, lignes vides, valeurs manquantes,
    colonnes structurelles et valeurs inhabituelles.
    """

    dataframe = normaliser_valeurs_vides(
        dataframe
    ).reset_index(drop=True)

    nombre_lignes = len(dataframe)
    colonnes_dataframe = list(dataframe.columns)

    masque_doublons_complet = dataframe.duplicated(
        keep=False
    )

    nombre_doublons = int(
        dataframe.duplicated(
            keep="first"
        ).sum()
    )

    apercu_doublons = []

    for index in dataframe.index[
        masque_doublons_complet
    ].tolist()[:10]:
        ligne = dataframe.loc[index]

        apercu_doublons.append(
            {
                "numero": int(index) + 1,
                "valeurs": [
                    convertir_valeur_json(
                        ligne.get(colonne)
                    )
                    for colonne in colonnes_dataframe
                ],
            }
        )

    masque_lignes_vides = dataframe.isna().all(
        axis=1
    )

    lignes_vides = int(
        masque_lignes_vides.sum()
    )

    numeros_lignes_vides = [
        int(index) + 1
        for index in dataframe.index[
            masque_lignes_vides
        ].tolist()[:10]
    ]

    informations_colonnes = []
    informations_par_nom = {}
    valeurs_manquantes_total = 0
    colonnes_numeriques = []
    valeurs_aberrantes = []

    for colonne in dataframe.columns:
        serie = dataframe[colonne]
        serie_numerique = convertir_serie_numerique(
            serie
        )
        serie_date = None

        if serie_numerique is not None:
            type_colonne = "nombre"
            serie_analysee = serie_numerique
            colonnes_numeriques.append(colonne)
        else:
            serie_date = convertir_serie_date(
                serie
            )

            if serie_date is not None:
                type_colonne = "date"
                serie_analysee = serie_date
            else:
                type_colonne = "texte"
                serie_analysee = serie

        manquantes = int(
            serie_analysee.isna().sum()
        )

        valeurs_manquantes_total += manquantes

        pourcentage = (
            round(
                manquantes * 100 / nombre_lignes,
                2,
            )
            if nombre_lignes
            else 0.0
        )

        valeurs_valides = serie_analysee.dropna()
        nombre_uniques = int(
            valeurs_valides.nunique()
        )

        exemples_non_vides = []

        for valeur in (
            valeurs_valides
            .drop_duplicates()
            .head(5)
            .tolist()
        ):
            texte = str(
                convertir_valeur_json(valeur)
            )

            if len(texte) > 45:
                texte = texte[:42] + "..."

            exemples_non_vides.append(texte)

        lignes_non_vides = []

        for index in serie_analysee.index[
            serie_analysee.notna()
        ].tolist()[:8]:
            lignes_non_vides.append(
                {
                    "ligne": int(index) + 1,
                    "valeur": convertir_valeur_json(
                        serie_analysee.loc[index]
                    ),
                }
            )

        information = {
            "nom": colonne,
            "type": type_colonne,
            "manquantes": manquantes,
            "pourcentage": pourcentage,
            "remplissage": round(
                100 - pourcentage,
                2,
            ),
            "nombre_uniques": nombre_uniques,
            "exemples_non_vides": exemples_non_vides,
            "lignes_non_vides": lignes_non_vides,
            "lignes_exemples": [
                int(index) + 1
                for index in dataframe.index[
                    serie_analysee.isna()
                ].tolist()[:10]
            ],
        }

        informations_colonnes.append(
            information
        )
        informations_par_nom[colonne] = information

        if serie_numerique is None:
            continue

        if len(valeurs_valides) < 4:
            continue

        q1 = valeurs_valides.quantile(0.25)
        q3 = valeurs_valides.quantile(0.75)
        iqr = q3 - q1

        if pd.isna(iqr) or iqr == 0:
            continue

        borne_basse = q1 - 1.5 * iqr
        borne_haute = q3 + 1.5 * iqr

        masque_aberrantes = (
            (serie_numerique < borne_basse)
            | (serie_numerique > borne_haute)
        ).fillna(False)

        nombre_aberrantes = int(
            masque_aberrantes.sum()
        )

        if nombre_aberrantes == 0:
            continue

        exemples = [
            {
                "ligne": int(index) + 1,
                "valeur": convertir_valeur_json(
                    serie_numerique.loc[index]
                ),
            }
            for index in serie_numerique.index[
                masque_aberrantes
            ].tolist()[:10]
        ]

        valeurs_aberrantes.append(
            {
                "colonne": colonne,
                "nombre": nombre_aberrantes,
                "borne_basse": round(
                    float(borne_basse),
                    2,
                ),
                "borne_haute": round(
                    float(borne_haute),
                    2,
                ),
                "exemples": exemples,
            }
        )

    colonnes_dupliquees = analyser_colonnes_dupliquees(
        dataframe
    )

    colonnes_structurelles = []

    for information in informations_colonnes:
        colonne = information["nom"]
        pourcentage = information["pourcentage"]
        nombre_uniques = information["nombre_uniques"]
        nombre_valides = (
            nombre_lignes
            - information["manquantes"]
        )

        vide = bool(
            nombre_lignes == 0
            or information["manquantes"]
            == nombre_lignes
        )
        presque_vide = bool(
            not vide
            and pourcentage >= 95
        )
        constante = bool(
            nombre_valides > 0
            and nombre_uniques <= 1
        )
        dupliquee_de = colonnes_dupliquees.get(
            colonne,
            "",
        )

        if not (
            vide
            or presque_vide
            or constante
            or dupliquee_de
        ):
            continue

        raisons = []

        if vide:
            raisons.append("entièrement vide")
        elif presque_vide:
            raisons.append(
                f"vide à {pourcentage} %"
            )

        if constante:
            raisons.append("une seule valeur distincte")

        if dupliquee_de:
            raisons.append(
                f"identique à « {dupliquee_de} »"
            )

        cible_recommandee = ""
        score_cible = 0.0

        if presque_vide and not dupliquee_de:
            (
                cible_recommandee,
                score_cible,
            ) = proposer_cible_fusion(
                dataframe,
                colonne,
                informations_par_nom,
            )

        if dupliquee_de or vide:
            recommandation_action = "SUPPRIMER"
            recommandation = (
                "Cette colonne n'apporte aucune information "
                "supplémentaire. Sa suppression est recommandée."
            )
        elif cible_recommandee:
            recommandation_action = "FUSIONNER_SUPPRIMER"
            recommandation = (
                f"Les rares valeurs ressemblent à celles de "
                f"« {cible_recommandee} ». Vérifiez l'aperçu, "
                "puis déplacez-les sans écraser les données existantes."
            )
        elif presque_vide:
            recommandation_action = "CONSERVER"
            recommandation = (
                "La colonne est presque vide, mais aucune destination "
                "sûre n'a été trouvée. Vérifiez ses lignes non vides "
                "avant de décider de la supprimer."
            )
        else:
            recommandation_action = "CONSERVER"
            recommandation = (
                "Une colonne constante peut représenter une unité ou "
                "un contexte important. Conservez-la sauf si elle est inutile."
            )

        colonnes_structurelles.append(
            {
                **information,
                "vide": vide,
                "presque_vide": presque_vide,
                "constante": constante,
                "dupliquee_de": dupliquee_de,
                "raisons": raisons,
                "cible_recommandee": cible_recommandee,
                "score_cible": score_cible,
                "recommandation_action": recommandation_action,
                "recommandation": recommandation,
            }
        )

    colonnes_avec_aberrantes = {
        element["colonne"]
        for element in valeurs_aberrantes
    }

    for information in informations_colonnes:
        information.update(
            recommander_traitement_manquant(
                colonne=information["nom"],
                serie=dataframe[information["nom"]],
                type_colonne=information["type"],
                pourcentage=information["pourcentage"],
                contient_aberrantes=(
                    information["nom"]
                    in colonnes_avec_aberrantes
                ),
            )
        )

    for information in valeurs_aberrantes:
        information.update(
            {
                "recommandation_action": "AUCUNE",
                "recommandation_libelle": "Conserver et vérifier",
                "recommandation": (
                    "Une valeur inhabituelle n'est pas forcément erronée. "
                    "Le système recommande de la conserver jusqu'à "
                    "vérification de son sens métier."
                ),
            }
        )

    return {
        "nombre_lignes": nombre_lignes,
        "nombre_colonnes": len(dataframe.columns),
        "doublons": nombre_doublons,
        "apercu_doublons": apercu_doublons,
        "lignes_vides": lignes_vides,
        "numeros_lignes_vides": numeros_lignes_vides,
        "valeurs_manquantes": valeurs_manquantes_total,
        "colonnes": informations_colonnes,
        "colonnes_numeriques": colonnes_numeriques,
        "colonnes_structurelles": colonnes_structurelles,
        "nombre_colonnes_structurelles": len(
            colonnes_structurelles
        ),
        "nombre_colonnes_vides": sum(
            1
            for element in colonnes_structurelles
            if element["vide"]
        ),
        "nombre_colonnes_presque_vides": sum(
            1
            for element in colonnes_structurelles
            if element["presque_vide"]
        ),
        "nombre_colonnes_constantes": sum(
            1
            for element in colonnes_structurelles
            if element["constante"]
        ),
        "nombre_colonnes_dupliquees": len(
            colonnes_dupliquees
        ),
        "valeurs_aberrantes": valeurs_aberrantes,
        "nombre_valeurs_aberrantes": sum(
            element["nombre"]
            for element in valeurs_aberrantes
        ),
    }


def appliquer_plan_nettoyage(
    dataframe,
    plan,
):
    """Applique le plan sans modifier le jeu de données original."""

    nombre_manquantes_initial = int(
        dataframe.isna().sum().sum()
    )

    resultat = normaliser_valeurs_vides(
        dataframe
    )

    nombre_manquantes_normalise = int(
        resultat.isna().sum().sum()
    )

    resume = {
        "lignes_avant": int(len(resultat)),
        "lignes_apres": 0,
        "colonnes_avant": int(len(resultat.columns)),
        "colonnes_apres": 0,
        "marqueurs_manquants_normalises": max(
            0,
            nombre_manquantes_normalise
            - nombre_manquantes_initial,
        ),
        "colonnes_supprimees": [],
        "colonnes_fusionnees": [],
        "cellules_deplacees": 0,
        "lignes_vides_supprimees": 0,
        "doublons_supprimes": 0,
        "valeurs_manquantes_traitees": 0,
        "lignes_incompletes_supprimees": 0,
        "valeurs_aberrantes_detectees": 0,
        "valeurs_aberrantes_traitees": 0,
        "lignes_aberrantes_supprimees": 0,
        "textes_nettoyes": False,
        "nombres_convertis": [],
        "dates_converties": [],
        "details_valeurs_manquantes": [],
        "details_valeurs_aberrantes": [],
    }

    # 1. Nettoyage général
    if plan.get("nettoyer_textes"):
        for colonne in resultat.columns:
            resultat[colonne] = resultat[colonne].apply(
                lambda valeur: (
                    " ".join(valeur.split())
                    if isinstance(valeur, str)
                    else valeur
                )
            )

        resume["textes_nettoyes"] = True

    if plan.get("convertir_nombres"):
        for colonne in resultat.columns:
            serie_numerique = convertir_serie_numerique(
                resultat[colonne]
            )

            if serie_numerique is not None:
                resultat[colonne] = serie_numerique
                resume["nombres_convertis"].append(
                    str(colonne)
                )

    if plan.get("convertir_dates"):
        for colonne in resultat.columns:
            if colonne in resume["nombres_convertis"]:
                continue

            serie_date = convertir_serie_date(
                resultat[colonne]
            )

            if serie_date is not None:
                resultat[colonne] = serie_date
                resume["dates_converties"].append(
                    str(colonne)
                )

    # 2. Colonnes vides, presque vides, constantes ou dupliquées
    traitements_colonnes = plan.get(
        "traitements_colonnes",
        {},
    )

    for source, configuration in traitements_colonnes.items():
        action = configuration.get(
            "action",
            "CONSERVER",
        )

        if action != "FUSIONNER_SUPPRIMER":
            continue

        cible = configuration.get(
            "cible",
            "",
        )

        if source not in resultat.columns:
            continue

        if cible not in resultat.columns:
            raise ValidationError(
                f"La colonne de destination « {cible} » n'existe pas."
            )

        if source == cible:
            raise ValidationError(
                "Une colonne ne peut pas être fusionnée avec elle-même."
            )

        masque_source = resultat[source].notna()
        masque_cible_vide = resultat[cible].isna()
        masque_commun = masque_source & ~masque_cible_vide

        source_comparee = serie_normalisee_comparaison(
            resultat[source]
        )
        cible_comparee = serie_normalisee_comparaison(
            resultat[cible]
        )

        masque_conflit = (
            masque_commun
            & (
                source_comparee
                != cible_comparee
            )
        )

        nombre_conflits = int(
            masque_conflit.sum()
        )

        if nombre_conflits:
            lignes = [
                str(int(index) + 1)
                for index in resultat.index[
                    masque_conflit
                ].tolist()[:5]
            ]

            raise ValidationError(
                (
                    f"Impossible de fusionner « {source} » vers "
                    f"« {cible} » : {nombre_conflits} ligne(s) "
                    "contiennent deux valeurs différentes. "
                    f"Exemples de lignes : {', '.join(lignes)}."
                )
            )

        masque_deplacement = (
            masque_source
            & masque_cible_vide
        )

        nombre_deplace = int(
            masque_deplacement.sum()
        )

        if nombre_deplace:
            resultat.loc[
                masque_deplacement,
                cible,
            ] = resultat.loc[
                masque_deplacement,
                source,
            ]

        resultat = resultat.drop(
            columns=[source]
        )

        resume["cellules_deplacees"] += nombre_deplace
        resume["colonnes_fusionnees"].append(
            {
                "source": source,
                "cible": cible,
                "cellules": nombre_deplace,
            }
        )
        resume["colonnes_supprimees"].append(
            source
        )

    for colonne, configuration in traitements_colonnes.items():
        if configuration.get("action") != "SUPPRIMER":
            continue

        if colonne not in resultat.columns:
            continue

        resultat = resultat.drop(
            columns=[colonne]
        )
        resume["colonnes_supprimees"].append(
            colonne
        )

    if len(resultat.columns) == 0:
        raise ValidationError(
            "Le nettoyage supprimerait toutes les colonnes."
        )

    # 3. Lignes entièrement vides
    if plan.get("supprimer_lignes_vides"):
        avant = len(resultat)
        resultat = resultat.dropna(
            how="all"
        )
        resume["lignes_vides_supprimees"] = int(
            avant - len(resultat)
        )

    # 4. Doublons
    if plan.get("supprimer_doublons"):
        avant = len(resultat)
        colonnes = [
            colonne
            for colonne in plan.get(
                "colonnes_doublons",
                [],
            )
            if colonne in resultat.columns
        ]

        resultat = resultat.drop_duplicates(
            subset=colonnes or None,
            keep="first",
        )
        resume["doublons_supprimes"] = int(
            avant - len(resultat)
        )

    # 5. Valeurs manquantes
    for colonne, configuration in plan.get(
        "traitements_manquants",
        {},
    ).items():
        if colonne not in resultat.columns:
            continue

        strategie = configuration.get(
            "strategie",
            "AUCUNE",
        )
        nombre_avant = int(
            resultat[colonne].isna().sum()
        )

        if strategie == "AUCUNE" or nombre_avant == 0:
            resume["details_valeurs_manquantes"].append(
                {
                    "colonne": colonne,
                    "strategie": strategie,
                    "nombre": nombre_avant,
                    "valeur": None,
                }
            )
            continue

        valeur_utilisee = None

        if strategie == "SUPPRIMER":
            lignes_avant = len(resultat)
            resultat = resultat.dropna(
                subset=[colonne]
            )
            resume["lignes_incompletes_supprimees"] += int(
                lignes_avant - len(resultat)
            )

        elif strategie in {"MOYENNE", "MEDIANE"}:
            serie_numerique = convertir_serie_numerique(
                resultat[colonne]
            )

            if serie_numerique is None:
                raise ValidationError(
                    f"La colonne « {colonne} » n'est pas numérique."
                )

            valeur_utilisee = (
                serie_numerique.mean()
                if strategie == "MOYENNE"
                else serie_numerique.median()
            )

            if pd.isna(valeur_utilisee):
                raise ValidationError(
                    (
                        "Impossible de calculer une valeur de "
                        f"remplacement pour « {colonne} »."
                    )
                )

            resultat[colonne] = serie_numerique.fillna(
                valeur_utilisee
            )

        elif strategie == "MODE":
            mode = resultat[colonne].mode(
                dropna=True
            )

            if mode.empty:
                raise ValidationError(
                    (
                        "Impossible de calculer la valeur la plus "
                        f"fréquente de « {colonne} »."
                    )
                )

            valeur_utilisee = mode.iloc[0]
            resultat[colonne] = resultat[colonne].fillna(
                valeur_utilisee
            )

        elif strategie == "NON_RENSEIGNE":
            valeur_utilisee = "Non renseigné"
            resultat[colonne] = resultat[colonne].fillna(
                valeur_utilisee
            )

        elif strategie == "VALEUR":
            valeur_utilisee = configuration.get(
                "valeur"
            )
            serie_numerique = convertir_serie_numerique(
                resultat[colonne]
            )

            if serie_numerique is not None:
                resultat[colonne] = serie_numerique.fillna(
                    valeur_utilisee
                )
            else:
                resultat[colonne] = resultat[colonne].fillna(
                    valeur_utilisee
                )

        nombre_apres = int(
            resultat[colonne].isna().sum()
        )
        nombre_traite = max(
            0,
            nombre_avant - nombre_apres,
        )

        if strategie == "SUPPRIMER":
            nombre_traite = nombre_avant

        resume["valeurs_manquantes_traitees"] += int(
            nombre_traite
        )
        resume["details_valeurs_manquantes"].append(
            {
                "colonne": colonne,
                "strategie": strategie,
                "nombre": int(nombre_traite),
                "valeur": convertir_valeur_json(
                    valeur_utilisee
                ),
            }
        )

    # 6. Valeurs inhabituelles
    for colonne, configuration in plan.get(
        "traitements_aberrants",
        {},
    ).items():
        if colonne not in resultat.columns:
            continue

        action = configuration.get(
            "action",
            "AUCUNE",
        )
        serie_numerique = convertir_serie_numerique(
            resultat[colonne]
        )

        if serie_numerique is None:
            continue

        valeurs_valides = serie_numerique.dropna()

        if len(valeurs_valides) < 4:
            continue

        q1 = valeurs_valides.quantile(0.25)
        q3 = valeurs_valides.quantile(0.75)
        iqr = q3 - q1

        if pd.isna(iqr) or iqr == 0:
            continue

        borne_basse = q1 - 1.5 * iqr
        borne_haute = q3 + 1.5 * iqr
        masque = (
            (serie_numerique < borne_basse)
            | (serie_numerique > borne_haute)
        ).fillna(False)
        nombre_detecte = int(
            masque.sum()
        )

        resume["valeurs_aberrantes_detectees"] += nombre_detecte
        valeur_utilisee = None

        if nombre_detecte > 0 and action == "SUPPRIMER":
            resultat = resultat.loc[~masque]
            resume["valeurs_aberrantes_traitees"] += nombre_detecte
            resume["lignes_aberrantes_supprimees"] += nombre_detecte

        elif nombre_detecte > 0 and action == "BORNER":
            resultat[colonne] = serie_numerique.clip(
                lower=borne_basse,
                upper=borne_haute,
            )
            resume["valeurs_aberrantes_traitees"] += nombre_detecte

        elif nombre_detecte > 0 and action in {
            "MOYENNE",
            "MEDIANE",
        }:
            valeurs_habituelles = serie_numerique.loc[
                ~masque
            ].dropna()

            if valeurs_habituelles.empty:
                valeurs_habituelles = valeurs_valides

            valeur_utilisee = (
                valeurs_habituelles.mean()
                if action == "MOYENNE"
                else valeurs_habituelles.median()
            )
            resultat.loc[masque, colonne] = valeur_utilisee
            resume["valeurs_aberrantes_traitees"] += nombre_detecte

        resume["details_valeurs_aberrantes"].append(
            {
                "colonne": colonne,
                "action": action,
                "nombre": nombre_detecte,
                "borne_basse": round(float(borne_basse), 2),
                "borne_haute": round(float(borne_haute), 2),
                "valeur": convertir_valeur_json(
                    valeur_utilisee
                ),
            }
        )

    resultat = resultat.reset_index(drop=True)

    if resultat.empty:
        raise ValidationError(
            (
                "Les choix sélectionnés supprimeraient "
                "toutes les lignes du jeu de données."
            )
        )

    resume["lignes_apres"] = int(len(resultat))
    resume["colonnes_apres"] = int(len(resultat.columns))

    return resultat, resume


def creer_apercu_dataframe(
    dataframe,
    limite=10,
):
    """
    Retourne quelques lignes du DataFrame
    pour les afficher dans le template.
    """

    apercu = []

    dataframe_apercu = dataframe.head(
        limite
    )

    colonnes = list(
        dataframe.columns
    )

    for numero, ligne in enumerate(
        dataframe_apercu.to_dict(
            orient="records"
        ),
        start=1,
    ):
        apercu.append(
            {
                "numero": numero,
                "valeurs": [
                    convertir_valeur_json(
                        ligne.get(colonne)
                    )
                    for colonne in colonnes
                ],
            }
        )

    return apercu

def detecter_types_dataframe(dataframe):
    """Détermine le type de chaque colonne après nettoyage."""

    return {
        colonne: detecter_type_colonne(
            dataframe[colonne]
        )
        for colonne in dataframe.columns
    }


@transaction.atomic
def enregistrer_version_nettoyee(
    *,
    jeu_source,
    utilisateur,
    nom_version,
    dataframe,
    operations,
    diagnostic_avant,
    resume,
):
    """
    Crée une nouvelle version nettoyée dans PostgreSQL.

    La version source n'est jamais modifiée.
    Les lignes nettoyées sont enregistrées par lots.
    """

    # Retrouver la version originale du jeu de données.
    # Si jeu_source est déjà une version nettoyée,
    # on utilise son jeu original.
    jeu_original = (
        jeu_source.source_jeu_donnees
        or jeu_source
    )

    # Verrouiller le jeu original pendant la création
    # afin d'éviter deux numéros de version identiques.
    jeu_original = (
        JeuDonnees.objects
        .select_for_update()
        .get(pk=jeu_original.pk)
    )

    # Rechercher le dernier numéro de version existant.
    derniere_version = (
        jeu_original.versions_nettoyees
        .aggregate(
            maximum=Max("numero_version")
        )
        .get("maximum")
        or jeu_original.numero_version
    )

    numero_version = derniere_version + 1

    colonnes = list(dataframe.columns)

    # Créer les informations générales
    # de la nouvelle version nettoyée.
    jeu_resultat = JeuDonnees.objects.create(
        proprietaire=jeu_source.proprietaire,
        nom=nom_version,
        description=(
            f"Version nettoyée de "
            f"« {jeu_source.nom} »."
        ),
        nom_fichier_original=(
            jeu_source.nom_fichier_original
        ),
        format=jeu_source.format,
        nombre_lignes=int(
            dataframe.shape[0]
        ),
        nombre_colonnes=int(
            dataframe.shape[1]
        ),
        colonnes=colonnes,
        types_colonnes=(
            detecter_types_dataframe(
                dataframe
            )
        ),
        taille_fichier=(
            jeu_source.taille_fichier
        ),
        statut=JeuDonnees.Statut.VALIDE,
        message_erreur="",
        type_version=(
            JeuDonnees.TypeVersion.NETTOYEE
        ),
        numero_version=numero_version,
        source_jeu_donnees=jeu_original,
    )

    # Enregistrer les lignes nettoyées
    # par lots pour limiter l'utilisation de la mémoire.
    for debut in range(
        0,
        len(dataframe),
        TAILLE_LOT_INSERTION,
    ):
        fin = debut + TAILLE_LOT_INSERTION

        lot_dataframe = dataframe.iloc[
            debut:fin
        ]

        objets = []

        for numero, ligne in enumerate(
            lot_dataframe.to_dict(
                orient="records"
            ),
            start=debut + 1,
        ):
            donnees = {
                colonne: convertir_valeur_json(
                    ligne.get(colonne)
                )
                for colonne in colonnes
            }

            objets.append(
                LigneDonnees(
                    jeu_donnees=jeu_resultat,
                    numero_ligne=numero,
                    donnees=donnees,
                )
            )

        if objets:
            LigneDonnees.objects.bulk_create(
                objets,
                batch_size=TAILLE_LOT_INSERTION,
            )

    # Calculer la qualité de la nouvelle version
    # après application du nettoyage.
    diagnostic_apres = diagnostiquer_qualite(
        dataframe
    )

    # Enregistrer l'historique complet du nettoyage.
    OperationNettoyage.objects.create(
        jeu_source=jeu_source,
        jeu_resultat=jeu_resultat,
        utilisateur=utilisateur,
        operations=operations,
        diagnostic_avant=diagnostic_avant,
        diagnostic_apres=diagnostic_apres,
        resume=resume,
    )

    return jeu_resultat