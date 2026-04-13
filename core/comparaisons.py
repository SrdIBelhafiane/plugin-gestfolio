import pandas as pd
import geopandas as gpd
from shapely import wkb
import numpy as np
import uuid
from shapely.geometry import LineString

from qgis.core import QgsMessageLog, Qgis
import os

def explode_lines(gdf):
    
    # Vérifier le type de géométrie global
    geom_types = gdf.geom_type.unique()

    # Si aucun LineString → on retourne direct
    if not any(gt in ["LineString", "MultiLineString"] for gt in geom_types):
        return gdf

    rows = []

    for _, row in gdf.iterrows():
        geom = row.geometry
        
        if geom is None:
            continue

        # ignorer points / polygones
        if geom.geom_type not in ["LineString", "MultiLineString"]:
            rows.append(row.to_dict())  # on garde tel quel
            continue

        lines = geom.geoms if geom.geom_type == "MultiLineString" else [geom]

        for line in lines:
            coords = list(line.coords)

            # ligne invalide
            if len(coords) < 2:
                continue

            for i in range(len(coords) - 1):
                seg = LineString([coords[i], coords[i+1]])

                new_row = row.to_dict()
                new_row["geometry"] = seg
                rows.append(new_row)

    # sécurité si jamais rien n'a été généré
    if not rows:
        return gdf

    df = gpd.GeoDataFrame(rows, geometry="geometry")

    return df.set_crs(gdf.crs)

def comparer(con, precision):

    sql="""
    SELECT table_name 
    FROM information_schema.tables 
    WHERE table_schema='recolement'
    AND table_name!='geo_z_9_0_6'; 
    """
    tables_en_cours_integration=df(sql,con)

    sql="""
    SELECT table_schema, table_name
    FROM information_schema.tables 
    WHERE table_schema IN ('sw_pr_res','sw_pr_topo')
    AND table_name IN ('"""+"','".join(list(tables_en_cours_integration['table_name']))+"""');
    """
    tables_res_topo_correspondantes=df(sql,con)
    #Vérification du bon nombre de correspondances
    if tables_res_topo_correspondantes.shape[0]!=tables_en_cours_integration.shape[0]:
        print("1/ Attention! Nombres de tables différents")
        tables_res_topo_correspondantes=pd.concat([tables_res_topo_correspondantes.loc[tables_res_topo_correspondantes['table_name'].duplicated(keep=False)==False,:],
                                                tables_res_topo_correspondantes.loc[(tables_res_topo_correspondantes['table_name'].duplicated(keep=False))&
                                                                                    (tables_res_topo_correspondantes['table_schema']=="sw_pr_res"),:]])
        if tables_res_topo_correspondantes.shape[0]!=tables_en_cours_integration.shape[0]:
            print("2/ Attention! Nombres de tables différents")


    #Données en cours d'intégration
    bd_integration={}
    for t in tables_en_cours_integration['table_name']:
        sql = f"""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'recolement'
                AND table_name = '{t}';
                """
        attributs=df(sql,con)
        attributs = attributs[~attributs['column_name'].isin(['geom', 'numfolio', 'natouv'])]
        if t=='geo_r_0_0_1':#points GPS
            sql = f"""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'recolement'
                AND table_name = '{t}';
                """
            sql=f"SELECT ST_Normalize(geom) AS geometry, numfolio AS numfolio_recol, natouv,{",".join(list(attributs['column_name']))} FROM recolement."+t+";"
        else:
            sql=f"SELECT ST_Normalize(geom) AS geometry, numfolio AS numfolio_recol,{",".join(list(attributs['column_name']))} FROM recolement."+t+";"
        bd_integration[t]=gdf(sql,con,geom_col='geometry')
        # explode est pour simplifier et reduire le stockage des géométries
        bd_integration[t]=bd_integration[t].explode(index_parts=True).reset_index(drop=True) 
        bd_integration[t]['source']='INTEGRATION'
        #bd_integration[t]['geom']= bd_integration[t]['geom'].buffer(precision) 
    #Liste des folios impliqués
    set_folios=set()
    for t in bd_integration:
        set_folios=set_folios.union(set(bd_integration[t]['numfolio_recol']))
    ls_folios=[f for f in set_folios if f!=None]
    sql="SELECT * FROM recolement.geo_z_9_0_6;"
    bd_folios=gdf(sql,con)
    bd_folios=bd_folios.set_crs('epsg:3947',allow_override=True)
    if bd_folios.shape[0]!=len(ls_folios):
        print("Attention! Nombres de folios différents")
        print("Folio(s) sans donnée:",[c for c in list(bd_folios['numfolio']) if c not in set_folios])
    #Données correspondantes présentes en base
    bd_existant={}
    for i,li in tables_res_topo_correspondantes.iterrows():
        t,s=li['table_name'],li['table_schema']
        sql = f"""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = '{s}'
                AND table_name = '{t}';
                """
        attributs=df(sql,con)
        attributs = attributs[~attributs['column_name'].isin(['geom', 'numfolio', 'natouv'])]
        if t=='geo_r_0_0_1':
            sql=f"SELECT ST_Normalize(the_geom) AS geometry, numfolio AS numfolio, natouv,{",".join(list(attributs['column_name']))} FROM "+s+"."+t+" WHERE numfolio IN ('"+"','".join(ls_folios)+"');"
        else:
            sql=f"SELECT ST_Normalize(the_geom) AS geometry, numfolio AS numfolio,{",".join(list(attributs['column_name']))} FROM "+s+"."+t+" WHERE numfolio IN ('"+"','".join(ls_folios)+"');"
        bd_existant[t]=gdf(sql,con,geom_col='geometry')
        bd_existant[t]['source']='EXISTANT'
        if bd_existant[t].shape[0]==0:
            continue
        bd_existant[t]=bd_existant[t].explode(index_parts=True).reset_index(drop=True)
        #bd_existant[t]['geom']=bd_existant[t]['geom'].buffer(precision) 
    
    bd_croisement={}
    for t in bd_integration:
        integration = explode_lines(bd_integration[t])
        existant = explode_lines(bd_existant[t])
        
        integration["i_uid"] = [str(uuid.uuid4()) for _ in range(len(integration))]
        existant["e_uid"] = [str(uuid.uuid4()) for _ in range(len(existant))]

        att=['geometry','source','moa','moeuvre','geotopo','daterel','geomori','dur','numvoie','i_uid','alti','hrms','vrms','oriobj']
        ancie_trace = gpd.sjoin(
                integration.rename(columns=lambda x: x + "_nouv" if x not in att else x),
                existant.rename(columns=lambda x: x + "_ancie" if x != 'geometry'  and x != 'source' and x != 'e_uid' else x).set_geometry(existant.buffer(precision)),
                predicate="within",
                how="inner"
            )
        

       
        # Faire une jointure dans l'autre sense et garder juste le commun entre les jountures
        nvelle_trace = integration[
            ~integration["i_uid"].isin(ancie_trace["i_uid"])
        ]
        nvelle_trace['croisement']='CREATION'
        nvelle_trace['attributs_modif'] = None
        nvelle_trace['gid_nouv'] = nvelle_trace['gid']
        ls_a_analyse_temp=[nvelle_trace]
        
        if existant.shape[0]>0:
            suppr_trace=existant[
                ~existant["e_uid"].isin(ancie_trace["e_uid"])
            ]
            suppr_trace['croisement']='SUPPRESSION'
            suppr_trace['attributs_modif'] = None
            suppr_trace['gid_ancie'] = suppr_trace['gid']
            ls_a_analyse_temp.append(suppr_trace)
        
        
        ### il faut verifier qu'on a gardé les memes attributs
        attributs_compare = [
            c.replace('_nouv', '')
            for c in ancie_trace.columns
            if c.endswith('_nouv') and c != 'gid_nouv'
        ]
        
        
        if not ancie_trace.empty :
            ancie_trace[['attributs_modif', 'modifications']] = ancie_trace.apply(
                lambda row: pd.Series(attributs_identiques(row, attributs_compare)),
                axis=1
            )
            
            conservation_identique = ancie_trace[ancie_trace['attributs_modif'].isna()]
            conservation_modifiee  = ancie_trace[ancie_trace['attributs_modif'].notna()]

            conservation_identique['croisement'] = 'CONSERVATION_IDENTIQUE'
            conservation_modifiee['croisement']  = 'CONSERVATION_MODIFIEE'
            ls_a_analyse_temp=ls_a_analyse_temp +[conservation_identique,conservation_modifiee]

            
        bd_croisement[t]=pd.concat(ls_a_analyse_temp)
        bd_croisement[t]['type_obj']=t
    
    bd_croisement_total=pd.concat([bd_croisement[t] for t in bd_croisement])
    
    bd_croisement_total=bd_croisement_total.set_geometry('geometry')
    bd_croisement_total=bd_croisement_total.merge(tables_res_topo_correspondantes,left_on='type_obj',right_on='table_name',how='left')

    bd_croisement_total['projet'] = np.where(
            (bd_croisement_total['croisement'] == 'CREATION') | (bd_croisement_total['croisement'] == 'SUPPRESSION'),
            bd_croisement_total['projet'],
            bd_croisement_total['projet_nouv']  
        )
    
    bd_croisement_total['daterel2'] = bd_croisement_total['daterel']
    bd_croisement_total['daterel'] = pd.to_datetime(bd_croisement_total['daterel'], errors='coerce')
    bd_croisement_total['annee'] = bd_croisement_total['daterel'].dt.strftime("%Y")
    bd_croisement_total['mois'] = bd_croisement_total['daterel'].dt.strftime("%Y/%m")
    bd_croisement_total=bd_croisement_total[['gid_ancie','gid_nouv','table_schema', 'table_name','projet', 'croisement','natouv', 'numfolio','geometry','attributs_modif', 'modifications','moeuvre','annee','mois','daterel2']]
    bd_croisement_total.plot(column='croisement')
    corres_natouv={'EP':'ep','EL':'elec','GZ':'GAZ'}

    bd_croisement_total.loc[bd_croisement_total['table_name']=='geo_r_0_0_1',
                            'grpe_objet']=bd_croisement_total.loc[bd_croisement_total['table_name']=='geo_r_0_0_1',
                                                                'natouv'].apply(lambda x: corres_natouv[x] if x in corres_natouv else 'NR')
    bd_croisement_total.loc[bd_croisement_total['table_name']=='geo_r_0_0_1','grpe_objet'].unique()
    bd_croisement_total['grpe_objet']=''
    bd_croisement_total.loc[bd_croisement_total['table_schema']=='sw_pr_topo','grpe_objet']='topo'
    bd_croisement_total.loc[(bd_croisement_total['table_schema']=='sw_pr_res')&
                            (bd_croisement_total['table_name'].str.match('geo_c_7')),'grpe_objet']='ep'
    bd_croisement_total.loc[(bd_croisement_total['table_schema']=='sw_pr_res')&
                            (bd_croisement_total['table_name'].str.match('geo_c_6')),'grpe_objet']='gaz'
    bd_croisement_total.loc[(bd_croisement_total['table_schema']=='sw_pr_res')&
                            (bd_croisement_total['table_name'].str.match('geo_c_[129]')),'grpe_objet']='elec'

    corres_natouv={'EP':'ep','EL':'elec','GZ':'GAZ'}

    bd_croisement_total.loc[bd_croisement_total['table_name']=='geo_r_0_0_1',
                            'grpe_objet']=bd_croisement_total.loc[bd_croisement_total['table_name']=='geo_r_0_0_1',
                                                                'natouv'].apply(lambda x: corres_natouv[x] if x in corres_natouv else 'NR')
    
    chemin_script = os.path.dirname(os.path.abspath(__file__))
    chemin_croisement = os.path.join(chemin_script, 'gestfolio_temp', 'bd_croisement_gestfolio.gpkg')
    chemin_folios = os.path.join(chemin_script, 'gestfolio_temp', 'bd_folios_gestfolio.gpkg')
    bd_croisement_total.to_file(chemin_croisement,driver='GPKG',index=False)
    bd_folios.to_file(chemin_folios,driver='GPKG',index=False)

def attributs_identiques(row, champs):
    """
    Retourne True si tous les attributs listés dans 'champs'
    sont identiques entre _nouv et _ancie
    """
    attributs_non_identiques = []
    modifications = []
    for c in champs:
        v_nouv = row[f"{c}_nouv"]
        v_ancie = row[f"{c.replace('numfolio_recol', 'numfolio')}_ancie"]

        
        if pd.isna(v_nouv) and pd.isna(v_ancie):
            continue
        if (v_nouv =='' and pd.isna(v_ancie)) or (pd.isna(v_nouv) and v_ancie ==''):
            continue
        if (v_nouv =='_' and pd.isna(v_ancie)) or (pd.isna(v_nouv) and v_ancie =='_'):
            continue
        v1 = to_float_if_possible(v_nouv)
        v2 = to_float_if_possible(v_ancie)
        if isinstance(v1, (int, float, np.floating)) and isinstance(v2, (int, float, np.floating)):
            if not np.isclose(v1, v2, atol=1e-6, equal_nan=True):
                attributs_non_identiques.append(c)
                modifications.append(f'{c}:{v_ancie}->{v_nouv}')
        else:
            # comparaison normale
            if v1 != v2:
                attributs_non_identiques.append(c)
                modifications.append(f'{c}:{v_ancie}->{v_nouv}')
    
    if attributs_non_identiques :
        return "|".join(attributs_non_identiques), "|".join(modifications)
    else :
        return None, None    
    
def to_float_if_possible(v):
    if isinstance(v, str):
        # remplace virgule par point (format français)
        v = v.replace(',', '.')
        try:
            return float(v)
        except ValueError:
            return v
    return v




def df(requette, con):
    cur = con.cursor()
    cur.execute(requette)
    rows = cur.fetchall()
    cols = [desc[0] for desc in cur.description]
    return pd.DataFrame(rows, columns=cols)

def gdf(requette, con, geom_col="geom", crs="EPSG:3947"):
    cur = con.cursor()
    cur.execute(requette)

    rows = cur.fetchall()
    cols = [desc[0] for desc in cur.description]

    df = pd.DataFrame(rows, columns=cols)

    # Conversion WKB → géométrie shapely
    df[geom_col] = df[geom_col].apply(
        lambda g: wkb.loads(g, hex=True) if g else None
    )

    return gpd.GeoDataFrame(df, geometry=geom_col, crs=crs)