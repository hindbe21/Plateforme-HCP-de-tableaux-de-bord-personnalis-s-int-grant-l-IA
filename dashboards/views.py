from __future__ import annotations
from datetime import timedelta

import json
from typing import Any

import numpy as np
import pandas as pd
from django.contrib import messages
from django.contrib.auth.decorators import (
    login_required,
)
from django.core.serializers.json import (
    DjangoJSONEncoder,
)
from django.core.paginator import Paginator
from django.db.models import Max, Q
from django.utils import timezone
from django.shortcuts import (
    get_object_or_404,
    redirect,
    render,
)

from datasets.models import JeuDonnees
from datasets.services import (
    charger_dataframe_postgresql,
)

from .forms import (
    FiltreForm,
    FiltreWidgetForm,
    TableauBordForm,
    WidgetForm,
)
from .models import (
    Filtre,
    FiltreWidget,
    TableauBord,
    Widget,
)


def est_administrateur(utilisateur):
    return bool(
        utilisateur.is_superuser
        or utilisateur.is_staff
        or getattr(
            utilisateur,
            "est_administrateur",
            False,
        )
        or getattr(
            utilisateur,
            "role",
            "",
        )
        == "ADMIN"
    )


def nom_champ_proprietaire(modele):
    champs = {
        champ.name
        for champ
        in modele._meta.get_fields()
    }

    for nom in (
        "proprietaire",
        "utilisateur_metier",
        "utilisateur",
        "createur",
    ):
        if nom in champs:
            return nom

    return None


def tableaux_autorises(utilisateur):
    queryset = (
        TableauBord.objects
        .select_related(
            "jeu_donnees"
        )
    )

    champ = nom_champ_proprietaire(
        TableauBord
    )

    if (
        champ
        and not est_administrateur(
            utilisateur
        )
    ):
        queryset = queryset.filter(
            **{
                champ:
                utilisateur
            }
        )

    return queryset


def recuperer_tableau_autorise(
    utilisateur,
    pk,
):
    return get_object_or_404(
        tableaux_autorises(
            utilisateur
        ),
        pk=pk,
    )


def recuperer_widget_autorise(
    utilisateur,
    pk,
):
    widget = get_object_or_404(
        Widget.objects
        .select_related(
            "tableau_bord",
            "tableau_bord__jeu_donnees",
        ),
        pk=pk,
    )

    tableau_bord = (
        recuperer_tableau_autorise(
            utilisateur,
            widget.tableau_bord_id,
        )
    )

    widget.tableau_bord = (
        tableau_bord
    )

    return widget


def recuperer_filtre_autorise(
    utilisateur,
    pk,
):
    filtre = get_object_or_404(
        Filtre.objects
        .select_related(
            "tableau_bord"
        ),
        pk=pk,
    )

    recuperer_tableau_autorise(
        utilisateur,
        filtre.tableau_bord_id,
    )

    return filtre


def recuperer_filtre_widget_autorise(
    utilisateur,
    pk,
):
    filtre = get_object_or_404(
        FiltreWidget.objects
        .select_related(
            "widget",
            "widget__tableau_bord",
            "widget__tableau_bord__jeu_donnees",
        ),
        pk=pk,
    )

    recuperer_widget_autorise(
        utilisateur,
        filtre.widget_id,
    )

    return filtre


def normaliser_vides(dataframe):
    resultat = dataframe.copy()

    for colonne in resultat.columns:
        resultat[colonne] = (
            resultat[colonne].apply(
                lambda valeur: (
                    pd.NA
                    if isinstance(
                        valeur,
                        str,
                    )
                    and not valeur.strip()
                    else valeur
                )
            )
        )

    return resultat


def convertir_serie_et_valeur(
    serie,
    valeur,
):
    serie_numerique = pd.to_numeric(
        serie,
        errors="coerce",
    )

    ratio_numerique = (
        float(
            serie_numerique
            .notna()
            .mean()
        )
        if len(serie)
        else 0
    )

    if ratio_numerique >= 0.80:
        try:
            valeur_numerique = float(
                str(valeur)
                .replace(
                    " ",
                    "",
                )
                .replace(
                    ",",
                    ".",
                )
            )

            return (
                serie_numerique,
                valeur_numerique,
            )

        except ValueError:
            pass

    serie_date = pd.to_datetime(
        serie,
        errors="coerce",
        dayfirst=True,
    )

    ratio_date = (
        float(
            serie_date
            .notna()
            .mean()
        )
        if len(serie)
        else 0
    )

    if ratio_date >= 0.80:
        valeur_date = pd.to_datetime(
            valeur,
            errors="coerce",
            dayfirst=True,
        )

        if pd.notna(
            valeur_date
        ):
            return (
                serie_date,
                valeur_date,
            )

    return (
        serie.astype("string"),
        str(valeur),
    )


def appliquer_filtres(
    dataframe,
    filtres,
):
    resultat = normaliser_vides(
        dataframe
    )

    for filtre in filtres:
        if (
            filtre.colonne
            not in resultat.columns
        ):
            continue

        serie = resultat[
            filtre.colonne
        ]

        operateur = (
            filtre.operateur
        )

        valeur = str(
            filtre.valeur
            or ""
        ).strip()

        if operateur == "VIDE":
            masque = serie.isna()

        elif operateur == "NON_VIDE":
            masque = serie.notna()

        elif operateur == "CONTIENT":
            masque = (
                serie
                .astype("string")
                .str.contains(
                    valeur,
                    case=False,
                    na=False,
                )
            )

        elif (
            operateur
            == "NE_CONTIENT_PAS"
        ):
            masque = ~(
                serie
                .astype("string")
                .str.contains(
                    valeur,
                    case=False,
                    na=False,
                )
            )

        elif operateur == "ENTRE":
            bornes = [
                element.strip()
                for element
                in valeur.split(";")
            ]

            if len(bornes) != 2:
                continue

            (
                serie_convertie,
                borne_min,
            ) = convertir_serie_et_valeur(
                serie,
                bornes[0],
            )

            (
                _,
                borne_max,
            ) = convertir_serie_et_valeur(
                serie,
                bornes[1],
            )

            masque = (
                (
                    serie_convertie
                    >= borne_min
                )
                &
                (
                    serie_convertie
                    <= borne_max
                )
            ).fillna(False)

        else:
            (
                serie_convertie,
                valeur_convertie,
            ) = convertir_serie_et_valeur(
                serie,
                valeur,
            )

            if operateur == "EGAL":
                masque = (
                    serie_convertie
                    == valeur_convertie
                )

            elif operateur == "DIFFERENT":
                masque = (
                    serie_convertie
                    != valeur_convertie
                )

            elif operateur == "SUPERIEUR":
                masque = (
                    serie_convertie
                    > valeur_convertie
                )

            elif (
                operateur
                == "SUPERIEUR_EGAL"
            ):
                masque = (
                    serie_convertie
                    >= valeur_convertie
                )

            elif operateur == "INFERIEUR":
                masque = (
                    serie_convertie
                    < valeur_convertie
                )

            elif (
                operateur
                == "INFERIEUR_EGAL"
            ):
                masque = (
                    serie_convertie
                    <= valeur_convertie
                )

            else:
                continue

            masque = masque.fillna(
                False
            )

        resultat = resultat.loc[
            masque
        ]

    return resultat.reset_index(
        drop=True
    )


def nom_agregation_pandas(
    agregation,
):
    return {
        "SOMME":
        "sum",

        "MOYENNE":
        "mean",

        "MEDIANE":
        "median",

        "MINIMUM":
        "min",

        "MAXIMUM":
        "max",
    }.get(
        agregation,
        "count",
    )


def trier_serie(
    serie,
    ordre_tri,
):
    if ordre_tri == "CROISSANT":
        return serie.sort_values(
            ascending=True
        )

    if ordre_tri == "DECROISSANT":
        return serie.sort_values(
            ascending=False
        )

    return serie


def valeur_json(valeur):
    if valeur is None:
        return None

    try:
        if pd.isna(valeur):
            return None

    except (
        TypeError,
        ValueError,
    ):
        pass

    if isinstance(
        valeur,
        pd.Timestamp,
    ):
        return valeur.isoformat()

    if hasattr(
        valeur,
        "item",
    ):
        return valeur.item()

    return valeur


def formater_valeur_indicateur(
    valeur,
):
    if valeur is None:
        return "—"

    try:
        if pd.isna(valeur):
            return "—"

    except (
        TypeError,
        ValueError,
    ):
        pass

    if isinstance(
        valeur,
        pd.Timestamp,
    ):
        return valeur.strftime(
            "%d/%m/%Y"
        )

    try:
        nombre = float(valeur)

    except (
        TypeError,
        ValueError,
    ):
        return str(valeur)

    if nombre.is_integer():
        return (
            f"{int(nombre):,}"
            .replace(
                ",",
                " ",
            )
        )

    return (
        f"{nombre:,.2f}"
        .replace(
            ",",
            " ",
        )
    )


def preparer_widget(widget, dataframe) -> dict[str, Any]:
    configuration = widget.configuration or {}
    dimension = widget.colonne_categorie
    mesure = configuration.get("colonne_mesure", "")
    serie = configuration.get("colonne_serie", "")
    agregation = configuration.get("agregation", "NOMBRE")
    ordre_tri = configuration.get("ordre_tri", "DECROISSANT")
    nombre_classes = int(configuration.get("nombre_classes", 10) or 10)
    inclure_manquantes = bool(configuration.get("inclure_manquantes", False))
    limite = max(1, int(widget.limite_resultats or 10))

    resultat = {
        "objet": widget, "type": widget.type_widget,
        "dimension": dimension, "mesure": mesure, "serie": serie,
        "agregation": agregation, "erreur": "", "chart_config_json": "",
        "valeur_indicateur": "", "colonnes_tableau": [], "lignes_tableau": [],
    }

    try:
        if widget.type_widget == "INDICATEUR":
            if agregation == "NOMBRE":
                valeur = len(dataframe)
            elif agregation == "NOMBRE_DISTINCT":
                valeur = dataframe[mesure].dropna().nunique()
            else:
                serie_numerique = pd.to_numeric(dataframe[mesure], errors="coerce")
                valeur = getattr(serie_numerique, nom_agregation_pandas(agregation))()
            resultat["valeur_indicateur"] = formater_valeur_indicateur(valeur)
            return resultat

        groupes_types = {
            "BARRES", "BARRES_HORIZONTALES", "CLASSEMENT", "CAMEMBERT",
            "ANNEAU", "COURBE", "AIRES",
        }
        series_types = {"BARRES", "BARRES_HORIZONTALES", "COURBE", "AIRES"}

        if widget.type_widget in groupes_types:
            if not dimension:
                raise ValueError("Une dimension est obligatoire.")
            colonnes=[]
            for col in (dimension, serie, mesure):
                if col and col not in colonnes: colonnes.append(col)
            travail=dataframe[colonnes].copy()
            if inclure_manquantes:
                travail[dimension]=travail[dimension].fillna("Valeur manquante")
                if serie: travail[serie]=travail[serie].fillna("Valeur manquante")
            else:
                subset=[dimension]+([serie] if serie else [])
                travail=travail.dropna(subset=subset)

            group_cols=[dimension]
            use_series=bool(serie and widget.type_widget in series_types)
            if use_series: group_cols.append(serie)

            if agregation == "NOMBRE":
                groupes=travail.groupby(group_cols,dropna=False).size()
            elif agregation == "NOMBRE_DISTINCT":
                if not mesure: raise ValueError("Le nombre distinct nécessite une mesure.")
                groupes=travail.groupby(group_cols,dropna=False)[mesure].nunique(dropna=True)
            else:
                if not mesure: raise ValueError("Cette agrégation nécessite une mesure numérique.")
                travail[mesure]=pd.to_numeric(travail[mesure],errors="coerce")
                travail=travail.dropna(subset=[mesure])
                groupes=travail.groupby(group_cols,dropna=False)[mesure].agg(nom_agregation_pandas(agregation))

            if use_series:
                table=groupes.unstack(fill_value=0)
                totals=table.sum(axis=1)
                if widget.type_widget in {"COURBE","AIRES"}:
                    parsed=pd.to_datetime(table.index,errors="coerce",dayfirst=True)
                    if len(parsed) and parsed.notna().mean() >= .8:
                        table.index=parsed; table=table.sort_index()
                    elif ordre_tri == "CROISSANT": table=table.loc[totals.sort_values().index]
                    else: table=table.loc[totals.sort_values(ascending=False).index]
                elif ordre_tri == "CROISSANT": table=table.loc[totals.sort_values().index]
                else: table=table.loc[totals.sort_values(ascending=False).index]
                table=table.head(limite)
                labels=[str(v) for v in table.index]
                datasets=[{"label":str(c),"data":[valeur_json(v) for v in table[c].tolist()]} for c in table.columns]
            else:
                if widget.type_widget in {"COURBE","AIRES"}:
                    parsed=pd.to_datetime(groupes.index,errors="coerce",dayfirst=True)
                    if len(parsed) and parsed.notna().mean() >= .8:
                        groupes.index=parsed; groupes=groupes.sort_index()
                    else: groupes=trier_serie(groupes,ordre_tri)
                elif widget.type_widget == "CLASSEMENT":
                    groupes=groupes.sort_values(ascending=False)
                else:
                    groupes=trier_serie(groupes,ordre_tri)
                groupes=groupes.head(limite)
                labels=[str(v) for v in groupes.index]
                datasets=[{"label":widget.titre,"data":[valeur_json(v) for v in groupes.values]}]

            type_chart={
                "BARRES":"bar", "BARRES_HORIZONTALES":"bar", "CLASSEMENT":"bar",
                "CAMEMBERT":"pie", "ANNEAU":"doughnut", "COURBE":"line", "AIRES":"line",
            }[widget.type_widget]
            options={"responsive":True,"maintainAspectRatio":False}
            if widget.type_widget in {"BARRES_HORIZONTALES","CLASSEMENT"}: options["indexAxis"]="y"
            if widget.type_widget == "AIRES":
                for dataset in datasets:
                    dataset["fill"]=True; dataset["tension"]=.25
            resultat["chart_config_json"] = json.dumps(
                {"type":type_chart,"data":{"labels":labels,"datasets":datasets},"options":options},
                cls=DjangoJSONEncoder, ensure_ascii=False,
            )
            return resultat

        if widget.type_widget == "HISTOGRAMME":
            numeric=pd.to_numeric(dataframe[dimension],errors="coerce").dropna()
            if numeric.empty: raise ValueError("Aucune valeur numérique exploitable.")
            counts,bins=np.histogram(numeric,bins=nombre_classes)
            labels=[f"{bins[i]:.2f} – {bins[i+1]:.2f}" for i in range(len(bins)-1)]
            resultat["chart_config_json"] = json.dumps({
                "type":"bar","data":{"labels":labels,"datasets":[{"label":"Effectif","data":counts.tolist()}]},
                "options":{"responsive":True,"maintainAspectRatio":False},
            },cls=DjangoJSONEncoder,ensure_ascii=False)
            return resultat

        if widget.type_widget == "NUAGE_POINTS":
            work=pd.DataFrame({"x":pd.to_numeric(dataframe[dimension],errors="coerce"),"y":pd.to_numeric(dataframe[mesure],errors="coerce")}).dropna().head(limite)
            points=[{"x":valeur_json(row.x),"y":valeur_json(row.y)} for row in work.itertuples()]
            resultat["chart_config_json"] = json.dumps({
                "type":"scatter","data":{"datasets":[{"label":widget.titre,"data":points}]},
                "options":{"responsive":True,"maintainAspectRatio":False},
            },cls=DjangoJSONEncoder,ensure_ascii=False)
            return resultat

        if widget.type_widget == "TABLEAU":
            cols=[]
            if dimension: cols.append(dimension)
            if mesure and mesure not in cols: cols.append(mesure)
            extrait=dataframe[cols].head(limite)
            resultat["colonnes_tableau"]=cols
            resultat["lignes_tableau"]=[[valeur_json(row[c]) for c in cols] for _,row in extrait.iterrows()]
            return resultat

        if widget.type_widget == "TABLEAU_CROISE":
            if not dimension or not serie: raise ValueError("Le tableau croisé nécessite deux dimensions.")
            cols=[dimension,serie]+([mesure] if mesure else [])
            work=dataframe[cols].copy().dropna(subset=[dimension,serie])
            if agregation == "NOMBRE":
                table=pd.crosstab(work[dimension],work[serie])
            elif agregation == "NOMBRE_DISTINCT":
                table=pd.pivot_table(work,index=dimension,columns=serie,values=mesure,aggfunc=pd.Series.nunique,fill_value=0)
            else:
                work[mesure]=pd.to_numeric(work[mesure],errors="coerce")
                table=pd.pivot_table(work,index=dimension,columns=serie,values=mesure,aggfunc=nom_agregation_pandas(agregation),fill_value=0)
            table=table.head(limite)
            resultat["colonnes_tableau"]=[dimension]+[str(c) for c in table.columns]
            resultat["lignes_tableau"]=[[valeur_json(idx)]+[valeur_json(row[c]) for c in table.columns] for idx,row in table.iterrows()]
            return resultat

        if widget.type_widget == "STATISTIQUES_DESCRIPTIVES":
            col=mesure or dimension
            numeric=pd.to_numeric(dataframe[col],errors="coerce").dropna()
            if numeric.empty: raise ValueError("Aucune valeur numérique exploitable.")
            stats=[
                ("Nombre de valeurs",int(numeric.count())), ("Valeurs distinctes",int(numeric.nunique())),
                ("Minimum",numeric.min()), ("Maximum",numeric.max()), ("Moyenne",numeric.mean()),
                ("Médiane",numeric.median()), ("Écart-type",numeric.std()),
                ("Premier quartile",numeric.quantile(.25)), ("Troisième quartile",numeric.quantile(.75)),
            ]
            resultat["colonnes_tableau"]=["Statistique",col]
            resultat["lignes_tableau"]=[[label,valeur_json(value)] for label,value in stats]
            return resultat

        raise ValueError("Ce type de widget n’est pas pris en charge.")
    except Exception as erreur:
        resultat["erreur"]=str(erreur)
        return resultat


@login_required
def liste_tableaux_bord(request):
    """
    Affiche les tableaux de bord accessibles avec
    recherche, filtres, indicateurs et pagination.
    """

    queryset_base = (
        tableaux_autorises(
            request.user
        )
        .select_related(
            "jeu_donnees",
            "proprietaire",
        )
    )

    stats = {
        "total":
        queryset_base.count(),

        "actifs":
        queryset_base.filter(
            actif=True
        ).count(),

        "recents":
        queryset_base.filter(
            date_modification__gte=(
                timezone.now()
                - timedelta(days=7)
            )
        ).count(),

        "widgets":
        Widget.objects.filter(
            tableau_bord__in=queryset_base
        ).count(),
    }

    q = request.GET.get("q", "").strip()
    jeu_selectionne = request.GET.get(
        "jeu_donnees",
        "",
    ).strip()
    date_selectionnee = request.GET.get(
        "date",
        "",
    ).strip()
    statut_selectionne = request.GET.get(
        "statut",
        "",
    ).strip()

    tableaux_bord = queryset_base

    if q:
        tableaux_bord = tableaux_bord.filter(
            Q(titre__icontains=q)
            | Q(description__icontains=q)
            | Q(jeu_donnees__nom__icontains=q)
        )

    if jeu_selectionne:
        tableaux_bord = tableaux_bord.filter(
            jeu_donnees_id=jeu_selectionne
        )

    if date_selectionnee:
        tableaux_bord = tableaux_bord.filter(
            date_modification__date=date_selectionnee
        )

    if statut_selectionne == "actif":
        tableaux_bord = tableaux_bord.filter(
            actif=True
        )
    elif statut_selectionne == "inactif":
        tableaux_bord = tableaux_bord.filter(
            actif=False
        )

    tableaux_bord = tableaux_bord.order_by(
        "-date_modification"
    )

    paginator = Paginator(
        tableaux_bord,
        12,
    )

    page_obj = paginator.get_page(
        request.GET.get("page")
    )

    jeux_filtres = (
        JeuDonnees.objects.filter(
            tableaux_bord__in=queryset_base
        )
        .distinct()
        .order_by("nom")
    )

    return render(
        request,
        "dashboards/liste.html",
        {
            "tableaux_bord":
            page_obj.object_list,

            "page_obj":
            page_obj,

            "stats":
            stats,

            "jeux_filtres":
            jeux_filtres,

            "filtres": {
                "q":
                q,

                "jeu_donnees":
                jeu_selectionne,

                "date":
                date_selectionnee,

                "statut":
                statut_selectionne,
            },
        },
    )


@login_required
def creer_tableau_bord(request):
    form = TableauBordForm(
        request.POST
        or None,
        utilisateur=request.user,
    )

    if (
        request.method
        == "POST"
        and form.is_valid()
    ):
        tableau_bord = form.save(
            commit=False
        )

        champ_proprietaire = (
            nom_champ_proprietaire(
                TableauBord
            )
        )

        if champ_proprietaire:
            setattr(
                tableau_bord,
                champ_proprietaire,
                request.user,
            )

        tableau_bord.save()

        messages.success(
            request,
            (
                "Le tableau de bord "
                "a été créé."
            ),
        )

        return redirect(
            "dashboards:detail",
            pk=tableau_bord.pk,
        )

    aucun_jeu_nettoye = not (
        form.fields[
            "jeu_donnees"
        ].queryset.exists()
    )

    return render(
        request,
        "dashboards/formulaire.html",
        {
            "form":
            form,

            "titre_page":
            "Créer un tableau de bord",

            "texte_bouton":
            "Créer le tableau de bord",

            "aucun_jeu_nettoye":
            aucun_jeu_nettoye,
        },
    )


@login_required
def modifier_tableau_bord(
    request,
    pk,
):
    tableau_bord = (
        recuperer_tableau_autorise(
            request.user,
            pk,
        )
    )

    form = TableauBordForm(
        request.POST
        or None,
        instance=tableau_bord,
        utilisateur=request.user,
    )

    if (
        request.method
        == "POST"
        and form.is_valid()
    ):
        form.save()

        messages.success(
            request,
            (
                "Le tableau de bord "
                "a été modifié."
            ),
        )

        return redirect(
            "dashboards:detail",
            pk=tableau_bord.pk,
        )

    return render(
        request,
        "dashboards/formulaire.html",
        {
            "form":
            form,

            "titre_page":
            "Modifier le tableau de bord",

            "texte_bouton":
            "Enregistrer les modifications",

            "aucun_jeu_nettoye":
            False,
        },
    )


@login_required
def supprimer_tableau_bord(
    request,
    pk,
):
    tableau_bord = (
        recuperer_tableau_autorise(
            request.user,
            pk,
        )
    )

    if request.method == "POST":
        tableau_bord.delete()

        messages.success(
            request,
            (
                "Le tableau de bord "
                "a été supprimé."
            ),
        )

        return redirect(
            "dashboards:liste"
        )

    return render(
        request,
        "dashboards/supprimer.html",
        {
            "tableau_bord":
            tableau_bord,
        },
    )


@login_required
def detail_tableau_bord(
    request,
    pk,
):
    tableau_bord = (
        recuperer_tableau_autorise(
            request.user,
            pk,
        )
    )

    dataframe = (
        charger_dataframe_postgresql(
            tableau_bord.jeu_donnees
        )
    )

    filtres = list(
        Filtre.objects.filter(
            tableau_bord=tableau_bord,
            actif=True,
        ).order_by(
            "ordre",
            "date_creation",
        )
    )

    dataframe_global = (
        appliquer_filtres(
            dataframe,
            filtres,
        )
    )

    widgets = list(
        Widget.objects.filter(
            tableau_bord=tableau_bord
        ).prefetch_related(
            "filtres_locaux"
        ).order_by(
            "ordre",
            "date_creation",
        )
    )

    widgets_prepares = []
    nombre_filtres_widgets = 0

    for widget in widgets:
        filtres_locaux = list(
            widget.filtres_locaux.filter(
                actif=True
            ).order_by(
                "ordre",
                "date_creation",
            )
        )

        nombre_filtres_widgets += (
            len(filtres_locaux)
        )

        dataframe_widget = (
            appliquer_filtres(
                dataframe_global,
                filtres_locaux,
            )
        )

        element = preparer_widget(
            widget,
            dataframe_widget,
        )

        element[
            "filtres_locaux"
        ] = filtres_locaux

        element[
            "nombre_lignes_widget"
        ] = int(
            len(
                dataframe_widget
            )
        )

        widgets_prepares.append(
            element
        )

    return render(
        request,
        "dashboards/detail.html",
        {
            "tableau_bord":
            tableau_bord,

            "widgets_prepares":
            widgets_prepares,

            "filtres":
            filtres,

            "nombre_lignes_total":
            int(
                len(dataframe)
            ),

            "nombre_lignes_affichees":
            int(
                len(
                    dataframe_global
                )
            ),

            "nombre_widgets":
            len(widgets),

            "nombre_filtres":
            len(filtres),

            "nombre_filtres_widgets":
            nombre_filtres_widgets,
        },
    )


@login_required
def ajouter_widget(request, pk):
    tableau_bord = recuperer_tableau_autorise(request.user, pk)
    form = WidgetForm(request.POST or None, tableau_bord=tableau_bord)

    if request.method == "POST" and form.is_valid():
        widget=form.save(commit=False)
        widget.tableau_bord=tableau_bord
        ordre_max=(Widget.objects.filter(tableau_bord=tableau_bord).aggregate(valeur=Max("ordre"))["valeur"] or 0)
        widget.ordre=ordre_max+1
        widget.save()
        messages.success(request,"Le widget a été ajouté.")
        return redirect("dashboards:detail",pk=tableau_bord.pk)

    contexte_ia={}
    try:
        from ai_assistant.services.workspace import construire_contexte_creation_widgets
        contexte_ia=construire_contexte_creation_widgets(request,tableau_bord)
    except Exception as erreur:
        contexte_ia={"erreur_assistant":str(erreur)}

    contexte={
        "form":form,"tableau_bord":tableau_bord,"titre_page":"Ajouter un widget",
        "texte_bouton":"Ajouter le widget","profils_colonnes":form.profils_colonnes,
        "mode_creation":request.GET.get("mode","manuel"),
    }
    contexte.update(contexte_ia)
    return render(request,"dashboards/widget_formulaire.html",contexte)


@login_required
def modifier_widget(
    request,
    pk,
):
    widget = (
        recuperer_widget_autorise(
            request.user,
            pk,
        )
    )

    tableau_bord = (
        widget.tableau_bord
    )

    form = WidgetForm(
        request.POST
        or None,
        instance=widget,
        tableau_bord=tableau_bord,
    )

    if (
        request.method
        == "POST"
        and form.is_valid()
    ):
        form.save()

        messages.success(
            request,
            (
                "Le widget a été "
                "modifié."
            ),
        )

        return redirect(
            "dashboards:detail",
            pk=tableau_bord.pk,
        )

    return render(
        request,
        (
            "dashboards/"
            "widget_formulaire.html"
        ),
        {
            "form":
            form,

            "tableau_bord":
            tableau_bord,

            "widget":
            widget,

            "titre_page":
            "Modifier le widget",

            "texte_bouton":
            "Enregistrer",

            "profils_colonnes":
            form.profils_colonnes,
        },
    )


@login_required
def supprimer_widget(
    request,
    pk,
):
    widget = (
        recuperer_widget_autorise(
            request.user,
            pk,
        )
    )

    tableau_bord = (
        widget.tableau_bord
    )

    if request.method == "POST":
        widget.delete()

        messages.success(
            request,
            (
                "Le widget a été "
                "supprimé."
            ),
        )

        return redirect(
            "dashboards:detail",
            pk=tableau_bord.pk,
        )

    return render(
        request,
        (
            "dashboards/"
            "widget_supprimer.html"
        ),
        {
            "widget":
            widget,

            "tableau_bord":
            tableau_bord,
        },
    )


@login_required
def ajouter_filtre(
    request,
    pk,
):
    tableau_bord = (
        recuperer_tableau_autorise(
            request.user,
            pk,
        )
    )

    form = FiltreForm(
        request.POST
        or None,
        tableau_bord=tableau_bord,
    )

    if (
        request.method
        == "POST"
        and form.is_valid()
    ):
        filtre = form.save(
            commit=False
        )

        filtre.tableau_bord = (
            tableau_bord
        )

        ordre_max = (
            Filtre.objects
            .filter(
                tableau_bord=
                tableau_bord
            )
            .aggregate(
                valeur=Max(
                    "ordre"
                )
            )[
                "valeur"
            ]
            or 0
        )

        filtre.ordre = (
            ordre_max
            + 1
        )

        filtre.actif = True
        filtre.save()

        messages.success(
            request,
            (
                "Le filtre global "
                "a été appliqué."
            ),
        )

        return redirect(
            "dashboards:detail",
            pk=tableau_bord.pk,
        )

    return render(
        request,
        (
            "dashboards/"
            "filtre_formulaire.html"
        ),
        {
            "form":
            form,

            "tableau_bord":
            tableau_bord,

            "widget":
            None,

            "titre_page":
            "Ajouter un filtre global",

            "texte_bouton":
            "Appliquer à tout le tableau de bord",

            "profils_colonnes":
            form.profils_colonnes,
        },
    )


@login_required
def supprimer_filtre(
    request,
    pk,
):
    filtre = (
        recuperer_filtre_autorise(
            request.user,
            pk,
        )
    )

    tableau_bord = (
        filtre.tableau_bord
    )

    if request.method == "POST":
        filtre.delete()

        messages.success(
            request,
            (
                "Le filtre global "
                "a été supprimé."
            ),
        )

    return redirect(
        "dashboards:detail",
        pk=tableau_bord.pk,
    )


@login_required
def ajouter_filtre_widget(
    request,
    pk,
):
    widget = (
        recuperer_widget_autorise(
            request.user,
            pk,
        )
    )

    tableau_bord = (
        widget.tableau_bord
    )

    form = FiltreWidgetForm(
        request.POST
        or None,
        widget=widget,
    )

    if (
        request.method
        == "POST"
        and form.is_valid()
    ):
        filtre = form.save(
            commit=False
        )

        filtre.widget = widget

        ordre_max = (
            FiltreWidget.objects
            .filter(
                widget=widget
            )
            .aggregate(
                valeur=Max(
                    "ordre"
                )
            )[
                "valeur"
            ]
            or 0
        )

        filtre.ordre = (
            ordre_max
            + 1
        )

        filtre.actif = True
        filtre.save()

        messages.success(
            request,
            (
                "Le filtre a été appliqué "
                "uniquement au widget."
            ),
        )

        return redirect(
            "dashboards:detail",
            pk=tableau_bord.pk,
        )

    return render(
        request,
        (
            "dashboards/"
            "filtre_formulaire.html"
        ),
        {
            "form":
            form,

            "tableau_bord":
            tableau_bord,

            "widget":
            widget,

            "titre_page":
            "Ajouter un filtre au widget",

            "texte_bouton":
            "Appliquer uniquement au widget",

            "profils_colonnes":
            form.profils_colonnes,
        },
    )


@login_required
def supprimer_filtre_widget(
    request,
    pk,
):
    filtre = (
        recuperer_filtre_widget_autorise(
            request.user,
            pk,
        )
    )

    tableau_bord = (
        filtre
        .widget
        .tableau_bord
    )

    if request.method == "POST":
        filtre.delete()

        messages.success(
            request,
            (
                "Le filtre du widget "
                "a été supprimé."
            ),
        )

    return redirect(
        "dashboards:detail",
        pk=tableau_bord.pk,
    )
