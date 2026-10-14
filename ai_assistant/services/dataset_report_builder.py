from __future__ import annotations
import math
import pandas as pd
from datasets.services import charger_dataframe_postgresql

TEMPORAL_WORDS={"date","annee","année","year","mois","month","trimestre","quarter","periode","période","time","temps"}

def serialiser(v):
    if v is None: return None
    try:
        if pd.isna(v): return None
    except (TypeError,ValueError): pass
    if isinstance(v,bool): return bool(v)
    if isinstance(v,int): return int(v)
    if isinstance(v,float):
        if not math.isfinite(v): return None
        return int(v) if v.is_integer() else round(v,4)
    return str(v)

def detecter_type(serie,nom):
    normalized=str(nom).lower().replace("_"," ")
    if any(word in normalized.split() for word in TEMPORAL_WORDS): return "TEMPORELLE"
    if pd.api.types.is_datetime64_any_dtype(serie): return "TEMPORELLE"
    numeric=pd.to_numeric(serie,errors="coerce")
    if float(numeric.notna().mean()) >= .85: return "NUMERIQUE"
    text=serie.dropna().astype(str).str.strip()
    if not text.empty:
        dates=pd.to_datetime(text,errors="coerce",dayfirst=True)
        if float(dates.notna().mean()) >= .85: return "TEMPORELLE"
    unique=int(serie.nunique(dropna=True)); total=max(1,len(serie))
    if unique >= 20 and unique/total >= .95: return "IDENTIFIANT"
    return "CATEGORIELLE"

def profil_colonne(dataframe,colonne):
    serie=dataframe[colonne]; typ=detecter_type(serie,colonne); total=len(serie)
    missing=int(serie.isna().sum()); unique=int(serie.nunique(dropna=True))
    profile={
        "nom":str(colonne),"type":typ,"nombre_uniques":unique,"nombre_manquantes":missing,
        "taux_manquantes":round(missing/total*100,2) if total else 0.0,
        "exemples":[serialiser(v) for v in serie.dropna().unique()[:3]],
        "minimum":None,"maximum":None,"moyenne":None,"mediane":None,"ecart_type":None,
        "quartile_1":None,"quartile_3":None,"date_minimum":None,"date_maximum":None,
        "modalites_principales":[],"alertes":[],
    }
    if total and missing==total: profile["alertes"].append("Colonne entièrement vide.")
    elif total and missing/total>=.95: profile["alertes"].append("Colonne presque entièrement vide.")
    if unique==1 and total-missing>0: profile["alertes"].append("Colonne constante.")
    if typ=="NUMERIQUE":
        vals=pd.to_numeric(serie,errors="coerce").dropna()
        if not vals.empty:
            profile.update({
                "minimum":serialiser(float(vals.min())),"maximum":serialiser(float(vals.max())),
                "moyenne":serialiser(float(vals.mean())),"mediane":serialiser(float(vals.median())),
                "ecart_type":serialiser(float(vals.std())),"quartile_1":serialiser(float(vals.quantile(.25))),
                "quartile_3":serialiser(float(vals.quantile(.75))),
            })
    elif typ=="TEMPORELLE":
        dates=pd.to_datetime(serie,errors="coerce",dayfirst=True).dropna()
        if not dates.empty:
            profile["date_minimum"]=dates.min().date().isoformat(); profile["date_maximum"]=dates.max().date().isoformat()
    else:
        counts=serie.dropna().astype(str).value_counts().head(5)
        denominator=max(1,total-missing)
        profile["modalites_principales"]=[{"valeur":str(k),"effectif":int(v),"pourcentage":round(int(v)/denominator*100,2)} for k,v in counts.items()]
    return profile

def correlations(dataframe,profils):
    cols=[p["nom"] for p in profils if p["type"]=="NUMERIQUE"][:30]
    if len(cols)<2:return []
    matrix=dataframe[cols].apply(pd.to_numeric,errors="coerce").corr(); out=[]
    for i,x in enumerate(cols):
        for y in cols[i+1:]:
            val=matrix.loc[x,y]
            if pd.isna(val): continue
            out.append({"colonne_x":x,"colonne_y":y,"coefficient":round(float(val),4),"force":"Forte" if abs(val)>=.7 else ("Modérée" if abs(val)>=.4 else "Faible")})
    return sorted(out,key=lambda x:abs(x["coefficient"]),reverse=True)[:15]

def calculer_rapport_jeu_donnees(jeu_donnees):
    df=charger_dataframe_postgresql(jeu_donnees)
    rows=len(df); cols=len(df.columns); cells=rows*cols
    missing=int(df.isna().sum().sum()); duplicates=int(df.duplicated().sum())
    profiles=[profil_colonne(df,c) for c in df.columns]
    type_counts={}
    for p in profiles:type_counts[p["type"]]=type_counts.get(p["type"],0)+1
    empty=[p["nom"] for p in profiles if rows and p["nombre_manquantes"]==rows]
    near=[p["nom"] for p in profiles if p["taux_manquantes"]>=95 and p["nom"] not in empty]
    constant=[p["nom"] for p in profiles if "Colonne constante." in p["alertes"]]
    corr=correlations(df,profiles)
    findings=[f"Le jeu contient {rows} ligne(s) et {cols} colonne(s).",f"{missing} valeur(s) sont manquantes, soit {round(missing/cells*100,2) if cells else 0} % des cellules.",f"{duplicates} ligne(s) dupliquée(s) ont été détectées."]
    if corr: findings.append(f"La corrélation linéaire la plus marquée concerne « {corr[0]['colonne_x']} » et « {corr[0]['colonne_y']} » ({corr[0]['coefficient']}).")
    rec=[]
    if duplicates: rec.append("Vérifier et, si nécessaire, supprimer les lignes dupliquées.")
    if empty: rec.append("Supprimer ou documenter les colonnes entièrement vides : "+", ".join(empty[:10])+".")
    if near: rec.append("Examiner les colonnes remplies à moins de 5 % : "+", ".join(near[:10])+".")
    if constant: rec.append("Vérifier l’utilité des colonnes constantes : "+", ".join(constant[:10])+".")
    if not rec: rec.append("Aucune correction prioritaire n’a été détectée par les règles automatiques.")
    limits=["Le rapport décrit la structure et les statistiques du fichier ; il ne prouve aucune relation causale.","Les valeurs atypiques peuvent être correctes selon le contexte métier.","Les types détectés automatiquement doivent être validés lorsque les formats sont ambigus."]
    return {
        "general":{"nom":jeu_donnees.nom,"nombre_lignes":rows,"nombre_colonnes":cols,"nombre_cellules":cells,"lignes_completes":int(df.notna().all(axis=1).sum()),"lignes_vides":int(df.isna().all(axis=1).sum()),"nombre_doublons":duplicates,"valeurs_manquantes":missing,"taux_manquantes":round(missing/cells*100,2) if cells else 0.0},
        "repartition_types":type_counts,"profils":profiles,"correlations":corr,
        "colonnes_vides":empty,"colonnes_presque_vides":near,"colonnes_constantes":constant,
        "constatations":findings,"recommandations":rec,"limites":limits,
    }
