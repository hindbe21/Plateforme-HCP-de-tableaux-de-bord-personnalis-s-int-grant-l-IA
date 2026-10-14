from __future__ import annotations
import json
from .ollama_client import ErreurOllama, appeler_ollama

BAD=("un paragraphe clair","chaînes uniquement","chaines uniquement","commentaire complémentaire")
def valid_text(value,minimum=35):
    if not isinstance(value,str): return ""
    text=value.strip(); low=text.lower()
    if len(text)<minimum or text.startswith(("{","[")) or any(x in low for x in BAD): return ""
    return text

def valid_list(value):
    if not isinstance(value,list): return []
    return [t for x in value if (t:=valid_text(x,20))]

def deterministic(calcs):
    g=calcs.get("general",{})
    summary=(f"Le jeu de données « {g.get('nom','')} » contient {g.get('nombre_lignes',0)} ligne(s) et {g.get('nombre_colonnes',0)} colonne(s). "
             f"{g.get('valeurs_manquantes',0)} valeur(s) sont manquantes ({g.get('taux_manquantes',0)} %) et {g.get('nombre_doublons',0)} ligne(s) dupliquée(s) ont été détectées.")
    return {"resume_executif":summary,"synthese_ia":"","constatations":list(calcs.get("constatations",[]) or []),"recommandations":list(calcs.get("recommandations",[]) or []),"limites":list(calcs.get("limites",[]) or []),"conclusion":"Le fichier peut être utilisé après validation des types et traitement des problèmes de qualité signalés. Les résultats décrivent les données sans établir de causalité."}

def rediger_rapport_jeu_donnees(calcs):
    content=deterministic(calcs)
    context={"general":calcs.get("general",{}),"repartition_types":calcs.get("repartition_types",{}),"constatations":calcs.get("constatations",[]),"recommandations":calcs.get("recommandations",[]),"correlations":calcs.get("correlations",[])[:5]}
    instructions="Tu rédiges une synthèse statistique à partir de résultats déjà calculés par Pandas. Tu ne calcules et n’inventes aucune valeur, colonne, catégorie ou causalité. Réponds par un JSON strict avec une synthèse, des constatations, des recommandations et des limites. Ne recopie jamais les consignes ou un exemple générique."
    try: result,model=appeler_ollama([{"role":"system","content":instructions},{"role":"user","content":json.dumps(context,ensure_ascii=False,default=str)}],temperature=.05)
    except ErreurOllama: return content,"Django/Pandas — mode sécurisé"
    if isinstance(result,dict):
        if (s:=valid_text(result.get("synthese"),80)): content["synthese_ia"]=s
        for key in ("constatations","recommandations","limites"):
            for t in valid_list(result.get(key,[])):
                if t not in content[key]: content[key].append(t)
    return content,model
