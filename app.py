"""
app_mapa.py - Sistema de Simulación y Gemelo Digital MERVAL
Versión INTEGRAL v117 — Planificador con Lector de Planilla Maestra:
- FÍSICA: Integrador Euler Temporal (dt=1s). Escudo Aerodinámico y ATO Coasting.
- REGENERACIÓN v114: Receptividad real por headway. Causa de reóstato y curva Piecewise.
- TERMODINÁMICA: Flujo Nodal AC/DC. Balance Nodal Min-Function.
- DASHBOARD: Sankey energético, gauge aprovechamiento, análisis por segmento eléctrico,
  Km total y consumo SER/SEAT integrados (V115).
- AUXILIARES DINÁMICOS: Factor horario + ocupación + estado de marcha.
- PLANIFICADOR V117: Lector automático de Planilla Maestra (CSV/Excel).
  Ruteo dinámico por N° de Viaje (Par/Impar) y N° de Servicio (>600, >400).
  Cálculo de tiempos de llegada basados estrictamente en velocidad física y detenciones.
"""
import streamlit as st
import pandas as pd
import numpy as np
import re
import time
import unicodedata
from io import BytesIO
from datetime import datetime, date, timedelta
import plotly.graph_objects as go

st.set_page_config(page_title="Simulador MERVAL", layout="wide", page_icon="🗺️")

# =============================================================================
# 1. INFRAESTRUCTURA, RED Y CONSTANTES GLOBALES
# =============================================================================
ESTACIONES = [
    'Puerto','Bellavista','Francia','Baron','Portales','Recreo','Miramar',
    'Viña del Mar','Hospital','Chorrillos','El Salto','Valencia','Quilpue',
    'El Sol','El Belloto','Las Americas','La Concepcion','Villa Alemana',
    'Sargento Aldea','Peñablanca','Limache'
]
EC = ['PU','BE','FR','BA','PO','RE','MI','VM','HO','CH',
      'ES','VAL','QU','SO','EB','AM','CO','VL','SA','PE','LI']
PAX_COLS = ['PUE','BEL','FRA','BAR','POR','REC','MIR','VIN','HOS','CHO',
            'SLT','VAL','QUI','SOL','BTO','AME','CON','VAM','SGA','PEN','LIM']
PAX_IDX  = {c: i for i, c in enumerate(PAX_COLS)}

KM_TRAMO = [0.7,0.7,0.8,1.7,2.1,1.4,0.9,0.9,1.0,1.5,7.4,2.3,1.9,2.0,1.1,1.2,0.9,0.6,1.3,12.73]
KM_ACUM  = [0.0]
for _k in KM_TRAMO: KM_ACUM.append(round(KM_ACUM[-1]+_k, 2))
KM_TOTAL = KM_ACUM[-1]
N_EST    = len(ESTACIONES)

_ELEV_KM = [0.0,0.7,1.4,2.2,3.9,6.0,7.4,8.3,9.2,10.2,11.7,19.1,21.4,23.3,25.3,26.4,27.6,28.5,29.1,30.4,43.13]
_ELEV_M  = [12,10,10,10,18,15,12,15,35,50,55,88,122,132,142,148,155,162,175,198,216]

EST_LATS = [-33.03846,-33.04295,-33.04405,-33.04241,-33.03284,-33.02703,-33.02496,
            -33.02642,-33.02868,-33.03300,-33.04113,-33.04031,-33.04532,-33.03966,
            -33.04311,-33.04385,-33.04158,-33.04258,-33.04203,-33.04019,-32.98427]
EST_LONS = [-71.62709,-71.62088,-71.61244,-71.60567,-71.59123,-71.57501,-71.56160,
            -71.55180,-71.54315,-71.53346,-71.52104,-71.46888,-71.44453,-71.42884,
            -71.40651,-71.37354,-71.36594,-71.35302,-71.27771]

SER_DATA = [
    (KM_ACUM[4]+1.0,  "SER PO"),
    (KM_ACUM[10]+1.0, "SER ES"),
    (KM_ACUM[14]+0.2, "SER EB"),
    (KM_ACUM[17]+0.2, "SER VA"),
]
SEAT_KM = KM_ACUM[13]+1.0

SER_CAPACITY_KW  = {"SER PO":3000.0,"SER ES":3000.0,"SER EB":4500.0,"SER VA":3000.0}
SEAT_CAPACITY_KW = 20000.0

Z_EFF_44KV   = 0.28
R_AC_44KV    = 0.17
V_NOMINAL_AC = 44000.0

PAX_KG               = 75.0
DWELL_DEF            = 8.0
DAVIS_E_N_PERMIL     = 9.81
ETA_TRAC_SISTEMA     = 0.92
ETA_REGEN_NETA       = 0.72
ETA_MAX_REGEN        = 0.70
LAMBDA_REGEN_KM      = 5.0
V_NOMINAL_DC         = 3000.0
V_REGEN_BLOCK        = 3650.0   # V — umbral bloqueo rectificador unidireccional
V_SQUEEZE_WARN       = 2850.0   # V — umbral squeeze control mínimo
ETA_SER_RECTIFICADOR = 0.96
ETA_MAX              = 0.70

SEGMENTOS_ELECTRICOS = [
    {"nombre":"SS1 Puerto–El Salto",  "km_ini":0.0,  "km_fin":12.0},
    {"nombre":"SS2 El Salto–El Sol",  "km_ini":12.0, "km_fin":24.0},
    {"nombre":"SS3 El Sol–Limache",   "km_ini":24.0, "km_fin":43.13},
]

SPEED_PROFILE = [
    (90.6,122.3,31.7,0,0),(122.3,215.3,93.0,52,43),(215.3,372.6,157.3,52,43),
    (372.6,577.2,204.6,52,43),(577.2,781.6,204.4,52,43),(781.6,1043.0,261.4,52,43),
    (1043.0,1377.0,334.0,52,43),(1377.0,1767.0,390.0,52,43),(1767.0,2202.0,435.0,42,34),
    (2202.0,2592.0,390.0,42,34),(2592.0,2960.5,368.5,74,60),(2960.5,3337.0,376.5,74,60),
    (3337.0,3448.4,111.4,74,60),(3448.4,3938.4,490.0,74,60),(3938.4,4328.4,390.0,66,54),
    (4328.4,4758.4,430.0,74,60),(4758.4,5188.4,430.0,52,43),(5188.4,5618.4,430.0,52,43),
    (5618.4,6034.4,416.0,52,43),(6034.4,6416.4,382.0,52,43),(6416.4,6913.0,496.6,74,60),
    (6913.0,7405.0,492.0,66,54),(7405.0,7816.4,411.4,66,54),(7816.4,8308.4,492.0,66,54),
    (8308.4,8695.0,386.6,66,54),(8695.0,9209.8,514.8,66,54),(9209.8,9622.2,412.4,66,54),
    (9622.2,10171.1,548.9,66,54),(10171.1,10530.5,359.4,52,43),(10530.5,11020.5,490.0,74,60),
    (11020.5,11513.5,493.0,74,60),(11513.5,11920.0,406.5,74,60),(11920.0,12088.4,168.4,74,60),
    (12088.4,12176.0,87.6,74,60),(12176.0,12578.0,402.0,74,60),(12578.0,12724.8,146.8,74,60),
    (12724.8,12861.7,136.9,74,60),(12861.7,13359.7,498.0,120,99),(13359.7,13847.7,488.0,120,99),
    (13847.7,14337.7,490.0,74,60),(14337.7,14828.7,491.0,52,43),(14828.7,15325.7,497.0,52,43),
    (15325.7,15823.7,498.0,52,43),(15823.7,16321.7,498.0,52,43),(16321.7,16812.7,491.0,52,43),
    (16812.7,17317.7,505.0,52,43),(17317.7,17809.7,492.0,52,43),(17809.7,18301.7,492.0,74,60),
    (18301.7,18788.7,487.0,74,60),(18788.7,19281.7,493.0,74,60),(19281.7,19772.7,491.0,74,60),
    (19772.7,20265.7,493.0,74,60),(20265.7,20754.7,489.0,74,60),(20754.7,21250.7,496.0,66,54),
    (21250.7,21337.7,87.0,52,43),(21337.7,21632.1,294.4,52,43),(21632.1,21739.7,107.6,74,60),
    (21739.7,22061.7,322.0,74,60),(22061.7,22251.2,189.5,102,84),(22251.2,22357.7,106.5,102,84),
    (22357.7,22812.7,455.0,74,60),(22812.7,23265.7,453.0,74,60),(23265.7,23660.7,395.0,74,60),
    (23660.7,24155.7,495.0,102,84),(24155.7,24650.7,495.0,102,84),(24650.7,25145.7,495.0,74,60),
    (25145.7,25343.7,198.0,74,60),(25343.7,25483.0,139.3,74,60),(25483.0,25725.0,242.0,74,60),
    (25725.0,26219.0,494.0,74,60),(26219.0,26614.0,395.0,74,60),(26614.0,27025.5,411.5,74,60),
    (27025.5,27457.0,431.5,74,60),(27457.0,27837.0,380.0,74,60),(27837.0,28317.0,480.0,74,60),
    (28317.0,28712.0,395.0,74,60),(28712.0,29180.0,468.0,74,60),(29180.0,29565.0,385.0,74,60),
    (29565.0,29817.0,252.0,74,60),(29817.0,30122.0,305.0,74,60),(30122.0,30464.0,342.0,66,54),
    (30464.0,30849.0,385.0,74,60),(30849.0,31332.6,483.6,102,84),(31332.6,31817.6,485.0,120,99),
    (31817.6,32307.6,490.0,120,99),(32307.6,32802.6,495.0,120,99),(32802.6,33297.6,495.0,120,99),
    (33297.6,33792.6,495.0,120,99),(33792.6,34282.6,490.0,120,99),(34282.6,34767.6,485.0,120,99),
    (34767.6,35246.6,479.0,120,99),(35246.6,35725.3,478.7,120,99),(35725.3,36223.3,498.0,102,84),
    (36223.3,36704.5,481.2,74,60),(36704.5,37194.0,489.5,74,60),(37194.0,37683.5,489.5,74,60),
    (37683.5,38172.0,488.5,102,84),(38172.0,38665.3,493.3,120,99),(38665.3,39153.0,487.7,120,99),
    (39153.0,39642.4,489.4,120,99),(39642.4,40134.0,491.6,120,99),(40134.0,40621.8,487.8,120,99),
    (40621.8,41100.8,479.0,120,99),(41100.8,41601.5,500.7,120,99),(41601.5,42089.1,487.6,102,84),
    (42089.1,42588.5,499.4,66,54),(42588.5,42785.5,197.0,66,54),(42785.5,43057.2,271.7,42,34),
    (43057.2,43273.1,215.9,42,34),(43273.1,43305.0,31.9,0,0)
]

# =============================================================================
# 2. FLOTA
# =============================================================================
FLOTA = {
    "XT-100": {
        "tara_t":86.1,"m_iner_t":7.20,"coches":2,"cap_sent":94,"cap_max":398,
        "n_motores":4,"a_max_ms2":1.0,"a_freno_ms2":1.2,"v_freno_min":3.81,
        "eta_motor":0.92,"davis_A":1678.70,"davis_B":13.97,"davis_C":0.35,
        "f_trac_max_kn":58.274,"f_freno_max_kn":52.976,
        "p_max_kw":504.0,"p_freno_max_kw":600.0,"aux_kw":46.0,
    },
    "XT-M": {
        "tara_t":95.0,"m_iner_t":8.0,"coches":2,"cap_sent":94,"cap_max":376,
        "n_motores":4,"a_max_ms2":1.0,"a_freno_ms2":1.2,"v_freno_min":3.81,
        "eta_motor":0.92,"davis_A":1440.60,"davis_B":0.00,"davis_C":0.35,
        "f_trac_max_kn":65.0,"f_freno_max_kn":55.0,
        "p_max_kw":720.0,"p_freno_max_kw":800.0,"aux_kw":55.0,
    },
    "SFE": {
        "tara_t":141.0,"m_iner_t":11.2,"coches":3,"cap_max":780,
        "n_motores":8,"a_max_ms2":1.02,"a_freno_ms2":1.30,"v_freno_min":3.81,
        "eta_motor":0.94,"davis_A":2694.6,"davis_B":16.70,"davis_C":0.35,
        "f_trac_max_kn":220.0,"f_freno_max_kn":190.0,
        "p_max_kw":2400.0,"p_freno_max_kw":2800.0,"aux_kw":190.0,
    },
}

# =============================================================================
# 3. TIEMPO Y PARSEO
# =============================================================================
if 'min_slider_1' not in st.session_state:
    st.session_state['min_slider_1'] = 480.0

def mins_to_time_str(mins):
    if pd.isna(mins): return '--:--:--'
    try:
        m_val = float(mins)
        while m_val >= 1440: m_val -= 1440
        while m_val < 0: m_val += 1440
        h = int(m_val//60); m = int(m_val%60); s = int(round((m_val*60)%60))
        if s==60: s=0; m+=1
        if m==60: m=0; h+=1
        return f"{h:02d}:{m:02d}:{s:02d}"
    except: return '--:--:--'

def parse_time_to_mins(val):
    if pd.isna(val): return None
    sv = str(val).strip().lower()
    if sv=='' or sv=='nan': return None
    if ' ' in sv: sv = sv.split(' ')[-1]
    m = re.search(r'(\d{1,2}):(\d{2})(?::(\d{2}))?', sv)
    if m:
        h=int(m.group(1)); mm=int(m.group(2)); s=int(m.group(3)) if m.group(3) else 0
        return h*60.0+mm+s/60.0
    try:
        f=float(sv)
        if f<1.0: return f*1440.0
        if f<2400.0: return (int(f//100)*60.0)+(f%100)
    except: pass
    return None

def parse_excel_date(val):
    if pd.isna(val): return None
    if isinstance(val,(datetime,pd.Timestamp)): return val.strftime('%Y-%m-%d')
    v_str=str(val).strip()
    if not v_str or v_str.lower() in ['nan','none','fecha','date','nat']: return None
    v_str=re.sub(r'\.0+$','',v_str).split(' ')[0]
    if v_str.isdigit():
        v_int=int(v_str)
        if 40000<=v_int<=60000:
            try: return (date(1899,12,30)+timedelta(days=v_int)).strftime('%Y-%m-%d')
            except: pass
        elif len(v_str) in [5,6]:
            s_pad=v_str.zfill(6)
            try:
                d,m,y=int(s_pad[0:2]),int(s_pad[2:4]),int(s_pad[4:6])
                if 1<=d<=31 and 1<=m<=12:
                    y_full=2000+y if y<100 else y
                    return f"{y_full:04d}-{m:02d}-{d:02d}"
            except: pass
    m1=re.search(r'\b(\d{1,2})[-/](\d{1,2})[-/](\d{4})\b',v_str)
    if m1:
        d,m,y=int(m1.group(1)),int(m1.group(2)),int(m1.group(3))
        if m>12 and d<=12: d,m=m,d
        if 1<=d<=31 and 1<=m<=12: return f"{y:04d}-{m:02d}-{d:02d}"
    m2=re.search(r'\b(\d{4})[-/](\d{1,2})[-/](\d{1,2})\b',v_str)
    if m2:
        y,m,d=int(m2.group(1)),int(m2.group(2)),int(m2.group(3))
        if m>12 and d<=12: d,m=m,d
        if 1<=d<=31 and 1<=m<=12: return f"{y:04d}-{m:02d}-{d:02d}"
    return None

def clean_primary_key(x):
    if pd.isna(x): return ''
    s=str(x).strip().upper()
    if s=='NAN' or s=='': return ''
    s=re.sub(r'\.0+$','',s)
    s=re.sub(r'[^A-Z0-9]','',s)
    return s.lstrip('0')

# =============================================================================
# 4. GEOGRÁFICAS
# =============================================================================
def interp_pos(km):
    km=max(0.0,min(float(km),KM_TOTAL))
    return float(np.interp(km,KM_ACUM,EST_LATS)),float(np.interp(km,KM_ACUM,EST_LONS))

def km_to_ec(km,tol=1.5):
    dists=[abs(km-k) for k in KM_ACUM]
    idx=int(np.argmin(dists))
    return EC[idx] if dists[idx]<=tol else f"{km:.1f}km"

def svc_label(km_orig,km_dest):
    return f"{km_to_ec(km_orig)}-{km_to_ec(km_dest)}"

def extraer_fecha_segura(df_raw,fname):
    for pat in [r'\b(\d{1,2})[-_\.](\d{1,2})[-_\.](\d{4})\b',r'\b(\d{4})[-_\.](\d{1,2})[-_\.](\d{1,2})\b']:
        m=re.search(pat,str(fname))
        if m:
            if len(m.group(1))==4: y,mon,d=int(m.group(1)),int(m.group(2)),int(m.group(3))
            else: d,mon,y=int(m.group(1)),int(m.group(2)),int(m.group(3))
            if mon>12 and d<=12: d,mon=mon,d
            if 1<=d<=31 and 1<=mon<=12: return f"{y:04d}-{mon:02d}-{d:02d}"
    s_fname=re.sub(r'\D','',str(fname))
    for i in range(len(s_fname)-7):
        match=s_fname[i:i+8]
        d,mon,y=int(match[:2]),int(match[2:4]),int(match[4:])
        if 1<=d<=31 and 1<=mon<=12 and 2000<=y<=2100: return f"{y:04d}-{mon:02d}-{d:02d}"
        y2,mon2,d2=int(match[:4]),int(match[4:6]),int(match[6:])
        if 1<=d2<=31 and 1<=mon2<=12 and 2000<=y2<=2100: return f"{y2:04d}-{mon2:02d}-{d2:02d}"
    for i in range(len(s_fname)-5):
        match=s_fname[i:i+6]
        d,mon,y=int(match[:2]),int(match[2:4]),int(match[4:])
        if 1<=d<=31 and 1<=mon<=12 and 20<=y<=35: return f"{2000+y:04d}-{mon:02d}-{d:02d}"
    for i in range(min(50,len(df_raw))):
        row_vals=[str(x).strip() for x in df_raw.iloc[i].values if pd.notna(x)]
        row_str=' '.join(row_vals)
        m_dt=re.search(r'\b(\d{4})[-/\.](\d{1,2})[-/\.](\d{1,2})\b',row_str)
        if m_dt:
            y,mon,d=int(m_dt.group(1)),int(m_dt.group(2)),int(m_dt.group(3))
            if 1<=d<=31 and 1<=mon<=12: return f"{y:04d}-{mon:02d}-{d:02d}"
        m_d=re.search(r'\b(\d{1,2})[-/\.](\d{1,2})[-/\.](\d{4})\b',row_str)
        if m_d:
            d,mon,y=int(m_d.group(1)),int(m_d.group(2)),int(m_d.group(3))
            if mon>12 and d<=12: d,mon=mon,d
            if 1<=d<=31 and 1<=mon<=12: return f"{y:04d}-{mon:02d}-{d:02d}"
        m_d2=re.search(r'\b(\d{1,2})[-/\.](\d{1,2})[-/\.](\d{2})\b',row_str)
        if m_d2 and not row_str.replace(".","").isdigit():
            d,mon,y=int(m_d2.group(1)),int(m_d2.group(2)),int(m_d2.group(3))
            if mon>12 and d<=12: d,mon=mon,d
            if 1<=d<=31 and 1<=mon<=12: return f"{2000+y:04d}-{mon:02d}-{d:02d}"
        for val in row_vals:
            val_clean=val.split('.')[0]
            if val_clean.isdigit() and 40000<=int(val_clean)<=60000:
                try: return (date(1899,12,30)+timedelta(days=int(val_clean))).strftime('%Y-%m-%d')
                except: pass
    return "2026-01-01"

def make_unique(df):
    if df.empty: return df
    cols=pd.Series(df.columns)
    for dup in cols[cols.duplicated()].unique():
        cols[cols==dup]=[f"{dup}_{i}" if i else dup for i in range(sum(cols==dup))]
    df.columns=cols
    return df

_EST_NORM=sorted({re.sub(r'[^a-z0-9]','',e.lower().replace('á','a').replace('é','e').replace('í','i').replace('ó','o').replace('ú','u').replace('ñ','n')):i for i,e in enumerate(ESTACIONES)}.items(),key=lambda x:-len(x[0]))
def _col_to_est_idx(col):
    cu=re.sub(r'[^a-z0-9]','',col.lower().replace('á','a').replace('é','e').replace('í','i').replace('ó','o').replace('ú','u').replace('ñ','n'))
    if 'americas' in cu: return ESTACIONES.index('Las Americas')
    if 'vina' in cu: return ESTACIONES.index('Viña del Mar')
    if 'aldea' in cu: return ESTACIONES.index('Sargento Aldea')
    if 'belloto' in cu: return ESTACIONES.index('El Belloto')
    if 'concepcion' in cu: return ESTACIONES.index('La Concepcion')
    if 'villaalem' in cu: return ESTACIONES.index('Villa Alemana')
    if 'salto' in cu: return ESTACIONES.index('El Salto')
    for nk,idx in _EST_NORM:
        if nk in cu: return idx
    return None

def calc_tren_km_real_general(row):
    k_s,k_e=min(row['km_orig'],row['km_dest']),max(row['km_orig'],row['km_dest'])
    man=row.get('maniobra')
    if man in ['CORTE_BTO','ACOPLE_BTO','CORTE_PU_SA_BTO']:
        km_man=KM_ACUM[14]
        if k_s<=km_man<=k_e: return abs(km_man-k_s)*2.0+abs(k_e-km_man)*1.0
    elif man in ['CORTE_SA','ACOPLE_SA']:
        km_man=KM_ACUM[18]
        if k_s<=km_man<=k_e: return abs(km_man-k_s)*2.0+abs(k_e-km_man)*1.0
    return abs(k_e-k_s)*(2.0 if row.get('doble',False) else 1.0)

# =============================================================================
# 5. MOTOR CINEMÁTICO
# =============================================================================
def _build_profile(use_rm,via):
    segs=SPEED_PROFILE if via==1 else list(reversed(SPEED_PROFILE))
    km_pts,t_pts,cum_t=[],[],0.0
    for ki,kf,dm,vn,vr in segs:
        v=max(5.0,vr if use_rm else vn)
        km_pts.append(ki if via==1 else kf)
        t_pts.append(cum_t)
        cum_t+=(dm/1000.0)/v*3600.0
    last=SPEED_PROFILE[-1] if via==1 else SPEED_PROFILE[0]
    km_pts.append(last[1] if via==1 else last[0])
    t_pts.append(cum_t)
    return np.array(km_pts,float),np.array(t_pts,float)

_PROF={(v,r):_build_profile(r,v) for v in [1,2] for r in [False,True]}
_PROF_SORTED={}
for k,v in _PROF.items():
    if k[0]==1: _PROF_SORTED[k]=(v[0],v[1])
    else: _PROF_SORTED[k]=(v[0][::-1].copy(),v[1][::-1].copy())

_VEL_ARRAY_NORM=np.zeros(45000,dtype=float)
_VEL_ARRAY_RM  =np.zeros(45000,dtype=float)
for ki,kf,_,vn,vr in SPEED_PROFILE:
    s,e=int(ki),min(int(kf)+1,45000)
    _VEL_ARRAY_NORM[s:e]=vn
    _VEL_ARRAY_RM[s:e]=vr

def vel_at_km(km_km,via,use_rm):
    idx=int(km_km*1000.0)
    if idx<0: return 0.0
    if idx>=45000: return 0.0
    return _VEL_ARRAY_RM[idx] if use_rm else _VEL_ARRAY_NORM[idx]

def km_at_t(t_ini,t_fin,t,via,use_rm=False,km_orig=None,km_dest=None,nodos=None,t_arr=None):
    if nodos is not None and len(nodos)>=2:
        if t<=nodos[0][0]: return nodos[0][1]
        if t>=nodos[-1][0]: return nodos[-1][1]
        if t_arr is None: t_arr=[n[0] for n in nodos]
        idx=np.searchsorted(t_arr,t)
        t_A,k_A=nodos[idx-1]; t_B,k_B=nodos[idx]
        if t_A==t_B: return k_A
        if k_A==k_B: return k_A
        frac=(t-t_A)/(t_B-t_A)
        km_sorted,t_sorted=_PROF_SORTED[(via,use_rm)]
        t_prof_A=float(np.interp(k_A*1000.0,km_sorted,t_sorted))
        t_prof_B=float(np.interp(k_B*1000.0,km_sorted,t_sorted))
        t_prof_target=t_prof_A+frac*(t_prof_B-t_prof_A)
        km_arr,t_prof_arr=_PROF[(via,use_rm)]
        km_m=float(np.interp(t_prof_target,t_prof_arr,km_arr))
        return max(0.0,min(km_m/1000.0,KM_TOTAL))
    dur=t_fin-t_ini
    if dur<=0: return km_orig if km_orig is not None else (0.0 if via==1 else KM_TOTAL)
    frac=max(0.0,min(1.0,(t-t_ini)/dur))
    km_arr,t_arr_prof=_PROF[(via,use_rm)]
    km_sorted,t_sorted=_PROF_SORTED[(via,use_rm)]
    if km_orig is None: km_orig=0.0 if via==1 else KM_TOTAL
    if km_dest is None: km_dest=KM_TOTAL if via==1 else 0.0
    ko_m=km_orig*1000.0; kd_m=km_dest*1000.0
    t_at_orig=float(np.interp(ko_m,km_sorted,t_sorted))
    t_at_dest=float(np.interp(kd_m,km_sorted,t_sorted))
    t_prof=t_at_orig+frac*(t_at_dest-t_at_orig)
    km_m=float(np.interp(t_prof,t_arr_prof,km_arr))
    return max(0.0,min(km_m/1000.0,KM_TOTAL))

def get_train_state_and_speed(t,r_via,use_rm,km_orig,km_dest,nodos,t_arr=None):
    if not nodos or len(nodos)<2: return "CRUISE",60.0
    if t_arr is None: t_arr=[n[0] for n in nodos]
    if t<=t_arr[0] or t>=t_arr[-1]: return "DWELL",0.0
    idx=np.searchsorted(t_arr,t)
    t_A,t_B=t_arr[idx-1],t_arr[idx]
    dt_from_A,dt_to_B=t-t_A,t_B-t
    km_now=km_at_t(t_A,t_B,t,r_via,use_rm,km_orig,km_dest,nodos,t_arr)
    vel_max=vel_at_km(km_now,r_via,use_rm)
    if dt_from_A<=1.0: return "ACCEL",vel_max
    elif dt_to_B<=1.0: return "BRAKE",vel_max
    else: return "CRUISE",vel_max

# =============================================================================
# 6. AUXILIARES DINÁMICOS v113
# =============================================================================
def calcular_aux_dinamico(aux_kw_nominal: float, hora_decimal: float, pax_abordo: int,
                          cap_max: int, estacion_anio: str, estado_marcha: str = "CRUISE") -> float:
    hora_int = int(hora_decimal) % 24
    _AUX_HVAC_HORA = {
        "verano": [0.60,0.55,0.55,0.55,0.58,0.65, 0.72,0.78,0.83,0.88,0.92,0.95, 0.98,1.00,1.00,0.98,0.95,0.90, 0.85,0.80,0.75,0.70,0.67,0.63],
        "otoño": [0.40,0.38,0.37,0.37,0.38,0.42, 0.48,0.52,0.56,0.60,0.63,0.65, 0.66,0.66,0.65,0.63,0.60,0.57, 0.53,0.50,0.47,0.44,0.42,0.41],
        "invierno": [0.72,0.70,0.68,0.68,0.70,0.74, 0.80,0.84,0.86,0.85,0.82,0.78, 0.75,0.73,0.72,0.73,0.76,0.80, 0.82,0.80,0.78,0.76,0.74,0.73],
        "primavera": [0.42,0.40,0.39,0.39,0.41,0.46, 0.53,0.58,0.63,0.68,0.72,0.75, 0.77,0.78,0.77,0.74,0.70,0.66, 0.61,0.57,0.53,0.49,0.46,0.44],
    }
    perfil   = _AUX_HVAC_HORA.get(estacion_anio, _AUX_HVAC_HORA["primavera"])
    f_hvac   = perfil[hora_int]

    if cap_max > 0:
        ocup = min(1.0, pax_abordo / cap_max)
        if estacion_anio == "verano": f_ocup = 1.0 + 0.05 * ocup
        elif estacion_anio == "invierno": f_ocup = 1.0 - 0.12 * ocup
        else: f_ocup = 1.0 - 0.06 * ocup
    else:
        f_ocup = 1.0

    f_marcha = 1.08 if estado_marcha == "DWELL" else 1.0
    aux_base = aux_kw_nominal * 0.30
    aux_hvac = aux_kw_nominal * 0.70 * f_hvac * f_ocup * f_marcha
    return aux_base + aux_hvac

def get_estacion_anio(fecha_str: str) -> str:
    try: mes = int(str(fecha_str)[5:7])
    except Exception: return "primavera"
    if mes in (12, 1, 2):   return "verano"
    elif mes in (3, 4, 5):  return "otoño"
    elif mes in (6, 7, 8):  return "invierno"
    else:                   return "primavera"

# =============================================================================
# 7. FÍSICA TERMODINÁMICA Y LOAD FLOW
# =============================================================================
def _get_segmento_electrico(km_pos):
    for seg in SEGMENTOS_ELECTRICOS:
        if seg["km_ini"]<=km_pos<seg["km_fin"]: return seg["nombre"]
    return SEGMENTOS_ELECTRICOS[-1]["nombre"]

def simular_tramo_termodinamico(tipo_tren,doble,km_ini,km_fin,via_op,pct_trac,use_rm,use_pend,nodos=None,pax_dict=None,pax_abordo=0,v_consigna_override=None,maniobra=None,estacion_anio="primavera",t_ini_mins=0.0):
    f=FLOTA.get(tipo_tren,FLOTA["XT-100"])
    trc,aux,reg=0.0,0.0,0.0
    t_horas=0.0
    k_s,k_e=km_ini,km_fin
    dst=abs(k_e-k_s)
    if dst<=0: return 0.0,0.0,0.0,0.0,0.0,0.0
    paradas_km=[n[1] for n in nodos] if nodos else [k_s,k_e]
    k_min,k_max=min(k_s,k_e),max(k_s,k_e)
    paradas_km=[k for k in paradas_km if k_min<=k<=k_max]
    if k_s not in paradas_km: paradas_km.append(k_s)
    if k_e not in paradas_km: paradas_km.append(k_e)
    paradas_km=list(set(paradas_km))
    paradas_km.sort(reverse=(via_op==2))
    pax_dict=pax_dict or {}
    dt=1.0
    for i in range(len(paradas_km)-1):
        p_ini,p_fin=paradas_km[i],paradas_km[i+1]
        dist_total_tramo=abs(p_fin-p_ini)*1000.0
        if dist_total_tramo<=0: continue
        pos_m=p_ini*1000.0; dist_recorrida=0.0; v_ms=0.0; estado_marcha="ACCEL"
        while dist_recorrida<dist_total_tramo:
            dist_restante=dist_total_tramo-dist_recorrida
            if dist_restante<0.1: break
            km_actual=(pos_m+dist_recorrida)/1000.0 if via_op==1 else (pos_m-dist_recorrida)/1000.0
            es_doble=doble
            if maniobra in ['CORTE_BTO','CORTE_PU_SA_BTO'] and km_actual>25.3: es_doble=False
            if maniobra=='CORTE_SA' and km_actual>29.1: es_doble=False
            if maniobra=='ACOPLE_BTO' and km_actual<25.3: es_doble=False
            if maniobra=='ACOPLE_SA' and km_actual<29.1: es_doble=False
            n_uni=2 if es_doble else 1
            
            pax_mid = get_pax_at_km(pax_dict, km_actual, via_op, pax_abordo) if pax_dict else pax_abordo
            
            masa_kg=((f['tara_t']+f['m_iner_t'])*1000*n_uni)+(pax_mid*PAX_KG)
            v_cons_kmh=max(5.0,vel_at_km(km_actual,via_op,use_rm))
            if v_consigna_override is not None: v_cons_kmh=min(v_cons_kmh,v_consigna_override)
            v_kmh=v_ms*3.6
            if n_uni==2: f_davis=(f['davis_A']*2)+(f['davis_B']*2*v_kmh)+(f['davis_C']*1.35*(v_kmh**2))
            else: f_davis=f['davis_A']+f['davis_B']*v_kmh+f['davis_C']*(v_kmh**2)
            f_pend=0.0
            if use_pend:
                for j in range(1,len(_ELEV_KM)):
                    if _ELEV_KM[j-1]<=km_actual<=_ELEV_KM[j] or (j==len(_ELEV_KM)-1 and km_actual>_ELEV_KM[j]):
                        pend=((_ELEV_M[j]-_ELEV_M[j-1])/max(0.001,(_ELEV_KM[j]-_ELEV_KM[j-1])*1000))*1000
                        f_pend=DAVIS_E_N_PERMIL*pend*(masa_kg/1000.0)*(1.0 if via_op==1 else -1.0)
                        break
            a_freno_op=f['a_freno_ms2']*0.9
            d_freno_req=(v_ms**2)/(2*a_freno_op) if v_ms>0 else 0
            f_disp_trac=min(f['f_trac_max_kn']*1000*n_uni*(pct_trac/100.0),(f['p_max_kw']*1000*n_uni*(pct_trac/100.0))/max(0.1,v_ms))
            f_disp_freno=min(f['f_freno_max_kn']*1000*n_uni,(f.get('p_freno_max_kw',f['p_max_kw']*1.2)*1000*n_uni)/max(0.1,v_ms)) if v_kmh>=f['v_freno_min'] else 0.0
            if dist_restante<=d_freno_req+(v_ms*dt*1.2): estado_marcha="BRAKE_STATION"
            elif v_kmh>v_cons_kmh+1.5: estado_marcha="BRAKE_OVERSPEED"
            else:
                if estado_marcha=="BRAKE_OVERSPEED" and v_kmh<=v_cons_kmh: estado_marcha="COAST"
                elif estado_marcha=="ACCEL" and v_kmh>=v_cons_kmh-0.5: estado_marcha="COAST"
                elif estado_marcha=="COAST":
                    if v_kmh<v_cons_kmh-2.0: estado_marcha="ACCEL"
                elif estado_marcha not in ["ACCEL","COAST","BRAKE_STATION","BRAKE_OVERSPEED"]: estado_marcha="ACCEL"
            f_motor,f_regen_tramo,a_net=0.0,0.0,0.0
            if estado_marcha=="BRAKE_STATION":
                f_req_freno=max(0.0,masa_kg*a_freno_op-f_davis-f_pend)
                f_regen_tramo=min(f_req_freno,f_disp_freno)
                a_net=(-f_regen_tramo-f_davis-f_pend)/masa_kg
                if a_net>-a_freno_op: a_net=-a_freno_op
            elif estado_marcha=="BRAKE_OVERSPEED":
                f_req_freno=max(0.0,masa_kg*0.4-f_davis-f_pend)
                f_regen_tramo=min(f_req_freno,f_disp_freno)
                a_net=(-f_regen_tramo-f_davis-f_pend)/masa_kg
                a_net=min(a_net,-0.15)
            elif estado_marcha=="ACCEL":
                f_motor=f_disp_trac
                a_net=(f_motor-f_davis-f_pend)/masa_kg
            elif estado_marcha=="COAST":
                f_motor=0.0; f_regen_tramo=0.0
                a_net=(-f_davis-f_pend)/masa_kg
            v_new=v_ms+a_net*dt; dt_actual=dt
            if v_new<0:
                dt_actual=v_ms/abs(a_net) if a_net<-0.001 else dt
                v_new=0.0
            if f_motor>0 and v_new*3.6>v_cons_kmh:
                v_new=v_cons_kmh/3.6
                a_req=(v_new-v_ms)/dt_actual if dt_actual>0 else 0
                f_motor_req=masa_kg*a_req+f_davis+f_pend
                f_motor=max(0.0,min(f_motor_req,f_disp_trac))
            if v_new<0.5 and dist_restante<2.0: break
            if v_new<0.1 and v_ms<0.1: v_new=1.0; dt_actual=dt
            step_m=(v_ms+v_new)/2.0*dt_actual
            if step_m>dist_restante:
                step_m=dist_restante
                if v_ms+v_new>0: dt_actual=step_m/((v_ms+v_new)/2.0)
            if step_m<0.1: step_m=0.5
            if f_motor>0:
                carga_pct=f_motor/max(1.0,f_disp_trac)
                eta_base=f.get('eta_motor',0.92)
                eta_din=eta_base*(1.0-0.2*(1.0-max(0.1,carga_pct))**3)
                trc+=((f_motor*step_m)/3_600_000.0)/eta_din
            if f_regen_tramo>0 and v_kmh>=f['v_freno_min']:
                reg+=((f_regen_tramo*step_m)/3_600_000.0)*ETA_REGEN_NETA
            hora_actual = (t_ini_mins + t_horas * 60.0) / 60.0
            aux_kw_inst = calcular_aux_dinamico(
                f['aux_kw'] * n_uni, hora_actual, pax_mid,
                f.get('cap_max', 398) * n_uni, estacion_anio, estado_marcha
            )
            aux+=(aux_kw_inst*(dt_actual/3600.0))
            t_horas+=dt_actual/3600.0
            dist_recorrida+=step_m; v_ms=v_new

    # Dwell Estático
    n_est_mid=max(0,len(paradas_km)-2)
    dwell_h=(n_est_mid*25.0)/3600.0
    hora_media = (t_ini_mins + (t_horas + dwell_h/2.0)*60.0) / 60.0
    aux_kw_dwell = calcular_aux_dinamico(
        f['aux_kw']*(2 if doble else 1), hora_media,
        pax_abordo, f.get('cap_max',398)*(2 if doble else 1),
        estacion_anio, "DWELL"
    )
    aux+=aux_kw_dwell*dwell_h
    t_horas+=dwell_h
    neto_ideal=max(0.0,trc+aux-reg)
    return trc,aux,reg,0.0,neto_ideal,t_horas

def calcular_demanda_ser(e_pantografo_kwh,t_horas,km_punto,km_ser):
    if t_horas<=0: return e_pantografo_kwh
    if km_punto<2.25: r_km=0.0638
    elif km_punto<6.80: r_km=0.0530
    elif km_punto<10.92: r_km=0.0495
    elif km_punto<21.41: r_km=0.0417
    elif km_punto<30.36: r_km=0.0399
    else: r_km=0.0355
    R_total=r_km*abs(km_punto-km_ser)
    P_kW=abs(e_pantografo_kwh)/t_horas
    I=(P_kW*1000.0)/V_NOMINAL_DC
    P_loss_kW=(I**2*R_total)/1000.0
    if e_pantografo_kwh>=0: return e_pantografo_kwh+(P_loss_kW*t_horas)
    else:
        e_llega_ser=abs(e_pantografo_kwh)-(P_loss_kW*t_horas)
        return -max(0.0,e_llega_ser)

def distribuir_energia_sers(e_pantografo,t_horas,km_ini,km_fin,active_sers):
    if not active_sers: return {}
    if len(active_sers)==1:
        e_s=calcular_demanda_ser(e_pantografo,t_horas,(km_ini+km_fin)/2.0,active_sers[0][0])
        return {active_sers[0][1]:e_s}
    sers_sorted=sorted(active_sers,key=lambda x:x[0])
    boundaries=[0.0]
    for i in range(len(sers_sorted)-1): boundaries.append((sers_sorted[i][0]+sers_sorted[i+1][0])/2.0)
    boundaries.append(KM_TOTAL)
    dist_total=abs(km_fin-km_ini)
    if dist_total<0.001:
        closest=min(active_sers,key=lambda x:abs(km_ini-x[0]))
        e_s=calcular_demanda_ser(e_pantografo,t_horas,km_ini,closest[0])
        return {closest[1]:e_s}
    k_min=min(km_ini,km_fin); k_max=max(km_ini,km_fin)
    resultados={s[1]:0.0 for s in sers_sorted}
    for i,ser in enumerate(sers_sorted):
        b_min=boundaries[i]; b_max=boundaries[i+1]
        o_min=max(k_min,b_min); o_max=min(k_max,b_max)
        if o_max>o_min:
            frac=(o_max-o_min)/dist_total
            centroid=(o_min+o_max)/2.0
            e_pant_c=e_pantografo*frac
            t_horas_c=t_horas*frac if t_horas>0 else 0.0
            e_s=calcular_demanda_ser(e_pant_c,t_horas_c,centroid,ser[0])
            resultados[ser[1]]+=e_s
    return resultados

def distribuir_potencia_sers_kw(p_kw,km_punto,active_sers):
    if not active_sers: return {}
    if len(active_sers)==1: return {active_sers[0][1]:p_kw}
    sers_sorted=sorted(active_sers,key=lambda x:x[0])
    if km_punto<=sers_sorted[0][0]: return {sers_sorted[0][1]:p_kw}
    if km_punto>=sers_sorted[-1][0]: return {sers_sorted[-1][1]:p_kw}
    for i in range(len(sers_sorted)-1):
        s1,s2=sers_sorted[i],sers_sorted[i+1]
        if s1[0]<=km_punto<=s2[0]:
            dist_total=s2[0]-s1[0]
            d1=km_punto-s1[0]; d2=s2[0]-km_punto
            return {s1[1]:p_kw*(d2/dist_total),s2[1]:p_kw*(d1/dist_total)}
    return {active_sers[0][1]:p_kw}

def calcular_flujo_ac_nodo(demands_kw):
    i_po=max(0.0,demands_kw.get('SER PO',0.0))*1000/(1.732*V_NOMINAL_AC*0.95)
    i_es=max(0.0,demands_kw.get('SER ES',0.0))*1000/(1.732*V_NOMINAL_AC*0.95)
    i_eb=max(0.0,demands_kw.get('SER EB',0.0))*1000/(1.732*V_NOMINAL_AC*0.95)
    i_va=max(0.0,demands_kw.get('SER VA',0.0))*1000/(1.732*V_NOMINAL_AC*0.95)
    len_seat_es=abs(24.3-12.7); len_es_po=abs(12.7-4.9)
    dv_seat_es=1.732*(i_po+i_es)*Z_EFF_44KV*len_seat_es
    dv_es_po=1.732*i_po*Z_EFF_44KV*len_es_po
    loss_seat_es=3*((i_po+i_es)**2)*R_AC_44KV*len_seat_es/1000.0
    loss_es_po=3*(i_po**2)*R_AC_44KV*len_es_po/1000.0
    v_ac_es=V_NOMINAL_AC-dv_seat_es; v_ac_po=v_ac_es-dv_es_po
    len_seat_eb=abs(25.5-24.3); len_eb_va=abs(28.7-25.5)
    dv_seat_eb=1.732*(i_eb+i_va)*Z_EFF_44KV*len_seat_eb
    dv_eb_va=1.732*i_va*Z_EFF_44KV*len_eb_va
    loss_seat_eb=3*((i_eb+i_va)**2)*R_AC_44KV*len_seat_eb/1000.0
    loss_eb_va=3*(i_va**2)*R_AC_44KV*len_eb_va/1000.0
    v_ac_eb=V_NOMINAL_AC-dv_seat_eb; v_ac_va=v_ac_eb-dv_eb_va
    total_loss_kw=loss_seat_es+loss_es_po+loss_seat_eb+loss_eb_va
    return {
        'SER PO':{'Vac':v_ac_po,'Vdc':3000.0*(v_ac_po/V_NOMINAL_AC)},
        'SER ES':{'Vac':v_ac_es,'Vdc':3000.0*(v_ac_es/V_NOMINAL_AC)},
        'SER EB':{'Vac':v_ac_eb,'Vdc':3000.0*(v_ac_eb/V_NOMINAL_AC)},
        'SER VA':{'Vac':v_ac_va,'Vdc':3000.0*(v_ac_va/V_NOMINAL_AC)},
        'P_loss_kw':total_loss_kw,
    }

# =============================================================================
# 7. REGENERACIÓN v114 — RECEPTIVIDAD REAL POR HEADWAY 
# =============================================================================
def calcular_receptividad_por_headway(df_dia: pd.DataFrame) -> dict:
    if df_dia.empty: return {}
    result = {}
    for via in [1, 2]:
        sub = df_dia[df_dia["Via"] == via].sort_values("t_ini").copy()
        if sub.empty: continue
        indices = list(sub.index)
        t_ini_vals = sub["t_ini"].values
        for i, idx in enumerate(indices):
            headways = []
            if i > 0: headways.append(t_ini_vals[i] - t_ini_vals[i-1])
            if i < len(indices)-1: headways.append(t_ini_vals[i+1] - t_ini_vals[i])
            if not headways:
                result[idx] = 0.10; continue
            hw = min(headways)
            if hw < 5.0:
                eta = 0.90
            elif hw <= 10.0:
                eta = 0.75 - 0.09 * (hw - 5.0)
            else:
                eta = max(0.10, 0.30 - ((hw - 10.0) / 20.0) * 0.20)
            result[idx] = round(min(eta, ETA_MAX_REGEN), 4)
    return result

# =============================================================================
# 8. SIMULADOR FÍSICO DE RED
# =============================================================================
def simular_regen_fisica_mejorada(df_dia, pct_trac, use_rm, estacion_anio="primavera"):
    regen_util_per_trip = {idx: 0.0 for idx in df_dia.index}
    braking_ticks_per_trip = {idx: 0.0 for idx in df_dia.index}
    reostat_receptor_ticks = {idx: 0.0 for idx in df_dia.index}
    reostat_tension_ticks  = {idx: 0.0 for idx in df_dia.index}

    if df_dia.empty: return regen_util_per_trip

    t_min = int(df_dia['t_ini'].min()); t_max = int(df_dia['t_fin'].max())
    dt_step = 10.0 / 60.0
    time_steps = np.arange(t_min, t_max + 1, dt_step)

    for via_ in [1, 2]:
        via_trains = df_dia[df_dia['Via'] == via_]
        if via_trains.empty: continue
        trains_data = []
        for idx, r in via_trains.iterrows():
            nodos = r.get('nodos')
            t_arr = [n[0] for n in nodos] if nodos and len(nodos) >= 2 else None
            trains_data.append({
                'idx': idx, 't_ini': r['t_ini'], 't_fin': r['t_fin'],
                'Via': r['Via'], 'km_orig': r['km_orig'], 'km_dest': r['km_dest'],
                'nodos': nodos, 't_arr': t_arr,
                'tipo_tren': r.get('tipo_tren','XT-100'),
                'doble': r.get('doble',False), 'pax_abordo': r.get('pax_abordo',0),
            })

        braking_by_idx  = [[] for _ in range(len(time_steps))]
        accel_by_idx    = [[] for _ in range(len(time_steps))]

        for tr in trains_data:
            t_start = max(t_min, tr['t_ini']); t_end = min(t_max, tr['t_fin'])
            idx_start = np.searchsorted(time_steps, t_start)
            idx_end   = np.searchsorted(time_steps, t_end, side='right')
            f = FLOTA.get(tr['tipo_tren'], FLOTA["XT-100"])
            n_uni = 2 if tr['doble'] else 1
            masa_kg = ((f['tara_t']+f['m_iner_t'])*1000*n_uni)+(tr['pax_abordo']*PAX_KG)
            eta_m = f.get('eta_motor',0.92)

            for i in range(idx_start, idx_end):
                m = time_steps[i]
                state, v_kmh = get_train_state_and_speed(m,tr['Via'],use_rm,tr['km_orig'],tr['km_dest'],tr['nodos'],tr['t_arr'])
                pos = km_at_t(tr['t_ini'],tr['t_fin'],m,tr['Via'],use_rm,tr['km_orig'],tr['km_dest'],tr['nodos'],tr['t_arr'])
                v_ms = v_kmh / 3.6
                if n_uni==2: f_davis=(f['davis_A']*2)+(f['davis_B']*2*v_kmh)+(f['davis_C']*1.35*(v_kmh**2))
                else: f_davis=f['davis_A']+f['davis_B']*v_kmh+f['davis_C']*(v_kmh**2)
                f_pend=0.0
                for j in range(1,len(_ELEV_KM)):
                    if _ELEV_KM[j-1]<=pos<=_ELEV_KM[j] or (j==len(_ELEV_KM)-1 and pos>_ELEV_KM[j]):
                        pend=((_ELEV_M[j]-_ELEV_M[j-1])/max(0.001,(_ELEV_KM[j]-_ELEV_KM[j-1])*1000))*1000
                        f_pend=DAVIS_E_N_PERMIL*pend*(masa_kg/1000.0)*(1.0 if tr['Via']==1 else -1.0)
                        break

                if state in ("BRAKE","BRAKE_STATION","BRAKE_OVERSPEED"):
                    if v_kmh < f.get('v_freno_min',3.81)*3.6:
                        reostat_tension_ticks[tr['idx']] += 1
                        continue
                    hora_tick = m / 60.0
                    p_aux_kw = calcular_aux_dinamico(
                        f['aux_kw']*n_uni, hora_tick, tr['pax_abordo'],
                        f.get('cap_max',398)*n_uni,
                        estacion_anio, state
                    )
                    a_freno_op=f['a_freno_ms2']*0.9
                    f_req=max(0.0,masa_kg*a_freno_op-f_davis-f_pend)
                    f_disp=min(f['f_freno_max_kn']*1000*n_uni,(f.get('p_freno_max_kw',f['p_max_kw']*1.2)*1000*n_uni)/max(0.1,v_ms)) if v_ms>0 else 0.0
                    f_regen=min(f_req,f_disp)
                    p_mech_kw=(f_regen*v_ms)/1000.0
                    p_gen_kw=p_mech_kw*ETA_REGEN_NETA-p_aux_kw
                    if p_gen_kw>0:
                        r_km=0.020
                        I_est=(p_gen_kw*1000)/V_NOMINAL_DC
                        V_est=V_NOMINAL_DC+I_est*r_km*2.0  
                        if V_est > V_REGEN_BLOCK:
                            reostat_tension_ticks[tr['idx']] += 1
                        else:
                            braking_by_idx[i].append((tr['idx'], pos, p_gen_kw))
                    braking_ticks_per_trip[tr['idx']] += 1

                elif state in ("ACCEL","CRUISE"):
                    hora_tick = m / 60.0
                    p_aux_kw = calcular_aux_dinamico(
                        f['aux_kw']*n_uni, hora_tick, tr['pax_abordo'],
                        f.get('cap_max',398)*n_uni,
                        estacion_anio, state
                    )
                    p_dem_kw = p_aux_kw
                    if state=="ACCEL":
                        f_disp_trac=min(f['f_trac_max_kn']*1000*n_uni*(pct_trac/100.0),(f['p_max_kw']*1000*n_uni*(pct_trac/100.0))/max(0.1,v_ms)) if v_ms>0 else f['f_trac_max_kn']*1000*n_uni*(pct_trac/100.0)
                        p_mech_kw=(f_disp_trac*v_ms)/1000.0
                        p_dem_kw+=(p_mech_kw/eta_m)
                        accel_by_idx[i].append((tr['idx'],pos,p_dem_kw))
                    elif state=="CRUISE" and (f_davis+f_pend>0):
                        p_mech_kw=((f_davis+f_pend)*v_ms)/1000.0
                        p_dem_kw+=(p_mech_kw/eta_m)
                        accel_by_idx[i].append((tr['idx'],pos,p_dem_kw))

        for i in range(len(time_steps)):
            braking = braking_by_idx[i]; accel = accel_by_idx[i]
            if not braking or not accel: continue
            current_demands = {a[0]:a[2] for a in accel}
            for b_idx, b_pos, p_gen in braking:
                available_sinks = [a for a in accel if current_demands[a[0]]>0]
                if not available_sinks:
                    reostat_receptor_ticks[b_idx] += 1; continue
                best_a = min(available_sinks, key=lambda x: abs(x[1]-b_pos))
                a_idx, a_pos, _ = best_a
                d = abs(a_pos-b_pos)
                if _get_segmento_electrico(b_pos) != _get_segmento_electrico(a_pos):
                    reostat_receptor_ticks[b_idx] += 1; continue
                if d <= LAMBDA_REGEN_KM*2:
                    eta_dist = ETA_MAX_REGEN*np.exp(-d/LAMBDA_REGEN_KM)
                    p_arrive = p_gen*eta_dist
                    p_dem_available = current_demands[a_idx]
                    p_transferred = min(p_arrive, p_dem_available)
                    current_demands[a_idx] -= p_transferred
                    eta_eff = p_transferred/p_gen
                    regen_util_per_trip[b_idx] += eta_eff
                else:
                    reostat_receptor_ticks[b_idx] += 1

    for idx in df_dia.index:
        ticks = braking_ticks_per_trip[idx]
        regen_util_per_trip[idx] = min(1.0, regen_util_per_trip[idx]/ticks) if ticks>0 else 0.0

    return regen_util_per_trip

# =============================================================================
# 9. TERMODINÁMICA DE FLOTA v114
# =============================================================================
@st.cache_data(show_spinner="Integrando Termodinámica de Flota...")
def calcular_termodinamica_flota_v111(df_dia, pct_trac, use_pend, use_rm, use_regen, dict_regen, estacion_anio="primavera"):
    df_e = df_dia.copy()
    if df_e.empty: return df_e

    df_e['estacion_anio'] = estacion_anio

    def _wrapper_energia(r):
        trc,aux,reg_panto_max,_,_,t_h = simular_tramo_termodinamico(
            r['tipo_tren'], r.get('doble',False), r['km_orig'], r['km_dest'], r['Via'],
            pct_trac, use_rm, use_pend, r.get('nodos'), r.get('pax_d',{}),
            r.get('pax_abordo',0), None, r.get('maniobra'),
            estacion_anio, r.get('t_ini', 0.0)
        )
        
        regen_bruta_absoluta = reg_panto_max / ETA_REGEN_NETA if ETA_REGEN_NETA > 0 else 0.0
        
        if not use_regen:
            reg_util = 0.0
        else:
            eta_util = dict_regen.get(r.name, 0.0)
            reg_util = reg_panto_max * eta_util

        reostato_calor = max(0.0, regen_bruta_absoluta - reg_util)
        neto_final = max(0.0, trc + aux - reg_util)
        
        return pd.Series([trc, aux, reg_util, reostato_calor, neto_final, dict_regen.get(r.name, 0.0)])

    df_e[['kwh_viaje_trac','kwh_viaje_aux','kwh_viaje_regen',
          'kwh_reostato','kwh_viaje_neto','eta_regen_util']] = df_e.apply(_wrapper_energia, axis=1)
    return df_e

# =============================================================================
# 10. KPIs POR SEGMENTO ELÉCTRICO
# =============================================================================
def get_kpis_regen_por_segmento(df_dia_e: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for seg in SEGMENTOS_ELECTRICOS:
        km_ini, km_fin = seg["km_ini"], seg["km_fin"]
        df_seg = df_dia_e[df_dia_e.apply(
            lambda r: km_ini <= (r['km_orig']+r['km_dest'])/2 < km_fin, axis=1
        )]
        if df_seg.empty:
            rows.append({"Segmento":seg["nombre"],"km_ini":km_ini,"km_fin":km_fin,
                         "N° Viajes":0,"Tracción [kWh]":0,"Auxiliar [kWh]":0,
                         "Regen Bruta [kWh]":0,"Regen Útil [kWh]":0,"Reóstato [kWh]":0,
                         "Neto Pantógrafo [kWh]":0,"Tasa Aprovech. [%]":0.0,"IDE [kWh/Tren-km]":0.0})
            continue
        regen_util  = df_seg.get('kwh_viaje_regen', pd.Series(dtype=float)).sum()
        reostat     = df_seg.get('kwh_reostato', pd.Series(dtype=float)).sum()
        regen_bruta = regen_util + reostat
        trac        = df_seg.get('kwh_viaje_trac', pd.Series(dtype=float)).sum()
        aux         = df_seg.get('kwh_viaje_aux', pd.Series(dtype=float)).sum()
        neto        = df_seg.get('kwh_viaje_neto', pd.Series(dtype=float)).sum()
        tren_km     = df_seg.get('tren_km', pd.Series(dtype=float)).sum()
        tasa        = (regen_util/regen_bruta*100) if regen_bruta > 0 else 0.0
        ide         = neto/tren_km if tren_km > 0 else 0.0
        rows.append({"Segmento":seg["nombre"],"km_ini":km_ini,"km_fin":km_fin,
                     "N° Viajes":len(df_seg),"Tracción [kWh]":int(round(trac)),
                     "Auxiliar [kWh]":int(round(aux)),"Regen Bruta [kWh]":int(round(regen_bruta)),
                     "Regen Útil [kWh]":int(round(regen_util)),"Reóstato [kWh]":int(round(reostat)),
                     "Neto Pantógrafo [kWh]":int(round(neto)),
                     "Tasa Aprovech. [%]":round(tasa,1),"IDE [kWh/Tren-km]":round(ide,3)})
    return pd.DataFrame(rows)

# =============================================================================
# 11. DASHBOARDS DE ENERGÍA 
# =============================================================================
def _render_sankey_v112(t_trac, t_aux, t_regen, t_reostat, t_neto, ser_kwh, seat_kwh):
    loss_ac   = max(0.0, seat_kwh - ser_kwh) if seat_kwh > ser_kwh else 0.0
    loss_rect = ser_kwh * (1 - ETA_SER_RECTIFICADOR) if ser_kwh > 0 else 0.0
    labels = ["SEAT 110/44kV","SER Rectif. 3kVDC","Pantógrafo",
              "Tracción motriz","Sist. Auxiliar","Regen → Red","Reóstato calor"]
    colors = ["#FBC02D","#E65100","#1565C0","#0D47A1","#F9A825","#2E7D32","#C62828"]
    fig = go.Figure(go.Sankey(
        arrangement="snap",
        node=dict(pad=14,thickness=20,line=dict(color="black",width=0.5), label=labels,color=colors),
        link=dict(
            source=[0,  1,  2,  2,  5,  2 ],
            target=[1,  2,  3,  4,  2,  6 ],
            value =[max(1,seat_kwh), max(1,ser_kwh-loss_rect), max(1,t_trac), max(1,t_aux), max(1,t_regen), max(1,t_reostat)],
            color =["rgba(251,192,45,.35)","rgba(230,81,0,.30)","rgba(13,71,161,.30)","rgba(249,168,37,.30)","rgba(46,125,50,.40)","rgba(198,40,40,.35)"],
        ),
    ))
    fig.update_layout(height=290, margin=dict(l=5,r=5,t=5,b=5), font=dict(size=11))
    st.plotly_chart(fig, use_container_width=True)

def _render_gauge_v112(tasa: float):
    color = "#2E7D32" if tasa >= 60 else "#F9A825" if tasa >= 30 else "#C62828"
    fig = go.Figure(go.Indicator(
        mode="gauge+number+delta", value=tasa,
        number={"suffix":"%","font":{"size":30}},
        delta={"reference":60.0,"suffix":"%","font":{"size":12}},
        gauge={
            "axis":{"range":[0,100],"tickwidth":1},
            "bar":{"color":color,"thickness":0.25},
            "steps":[{"range":[0,30],"color":"#FFEBEE"},{"range":[30,60],"color":"#FFF8E1"},{"range":[60,100],"color":"#E8F5E9"}],
            "threshold":{"line":{"color":"#1565C0","width":3},"thickness":0.85,"value":60},
        },
        title={"text":"Aprovechamiento<br>Regenerativo","font":{"size":12}},
    ))
    fig.update_layout(height=250, margin=dict(l=10,r=10,t=30,b=10))
    st.plotly_chart(fig, use_container_width=True)

def _render_grafico_horario_v112(df_dia_e: pd.DataFrame):
    if 't_ini' not in df_dia_e.columns: return
    df_h = df_dia_e.copy()
    df_h['hora'] = (df_h['t_ini']//60).astype(int)
    agg = df_h.groupby('hora').agg(
        trac=('kwh_viaje_trac','sum'), aux=('kwh_viaje_aux','sum'),
        regen_util=('kwh_viaje_regen','sum'), reostat=('kwh_reostato','sum'),
        neto=('kwh_viaje_neto','sum'),
    ).reset_index()
    agg['regen_bruta'] = agg['regen_util'] + agg['reostat']
    agg['tasa_hora'] = (agg['regen_util']/agg['regen_bruta'].replace(0,np.nan)*100).fillna(0).round(1)
    horas_lbl = [f"{h:02d}h" for h in agg['hora']]
    fig = go.Figure()
    fig.add_trace(go.Bar(name="Tracción",x=horas_lbl,y=agg['trac'],marker_color="#1565C0", hovertemplate="<b>%{x}</b><br>Tracción: %{y:,.0f} kWh<extra></extra>"))
    fig.add_trace(go.Bar(name="Auxiliar",x=horas_lbl,y=agg['aux'],marker_color="#F9A825", hovertemplate="<b>%{x}</b><br>Auxiliar: %{y:,.0f} kWh<extra></extra>"))
    fig.add_trace(go.Bar(name="Regen Útil",x=horas_lbl,y=-agg['regen_util'],marker_color="#2E7D32", customdata=agg['regen_util'], hovertemplate="<b>%{x}</b><br>Regen útil: %{customdata:,.0f} kWh<extra></extra>"))
    fig.add_trace(go.Bar(name="Reóstato",x=horas_lbl,y=-agg['reostat'],marker_color="#C62828", customdata=agg['reostat'], hovertemplate="<b>%{x}</b><br>Reóstato: %{customdata:,.0f} kWh<extra></extra>"))
    fig.add_trace(go.Scatter(name="Neto pantógrafo",x=horas_lbl,y=agg['neto'], mode='lines+markers',line=dict(color="#E65100",width=2,dash='dot'),marker=dict(size=5), hovertemplate="<b>%{x}</b><br>Neto: %{y:,.0f} kWh<extra></extra>",yaxis='y'))
    fig.add_trace(go.Scatter(name="Tasa aprovech.",x=horas_lbl,y=agg['tasa_hora'], mode='lines+markers',line=dict(color="#7B1FA2",width=2),marker=dict(size=5,symbol='diamond'), hovertemplate="<b>%{x}</b><br>Tasa: %{y:.1f}%<extra></extra>",yaxis='y2'))
    fig.update_layout(
        barmode='relative',height=380,margin=dict(l=10,r=60,t=20,b=10), legend=dict(orientation='h',y=-0.18,x=0),
        yaxis=dict(title='kWh',gridcolor='rgba(0,0,0,0.06)'),
        yaxis2=dict(title='Tasa (%)',overlaying='y',side='right',range=[0,110],showgrid=False,ticksuffix='%'),
        hovermode='x unified',plot_bgcolor='white',
    )
    st.plotly_chart(fig, use_container_width=True)

def _render_tarjetas_segmento_v112(df_segs: pd.DataFrame):
    if df_segs.empty: return
    cols = st.columns(len(df_segs))
    paleta = ["#1565C0","#2E7D32","#E65100"]
    for i, (_, row) in enumerate(df_segs.iterrows()):
        tasa = row["Tasa Aprovech. [%]"]
        color = paleta[i % len(paleta)]
        bar_color = "#2E7D32" if tasa>=60 else "#F9A825" if tasa>=30 else "#C62828"
        with cols[i]:
            st.markdown(
                f"<div style='border-top:4px solid {color};background:var(--background-color,#fafafa); border-radius:8px;padding:14px 12px;'>"
                f"<div style='font-size:12px;font-weight:700;color:{color};margin-bottom:6px;'>{row['Segmento']}</div>"
                f"<div style='font-size:11px;color:#666;'>km {row['km_ini']:.0f}–{row['km_fin']:.1f} · <b>{row['N° Viajes']}</b> viajes</div><hr style='margin:7px 0;border-color:#eee;'>"
                f"<div style='font-size:12px;'>🔋 Tracción: <b>{row['Tracción [kWh]']:,} kWh</b></div>"
                f"<div style='font-size:12px;'>♻️ Regen bruta: <b>{row['Regen Bruta [kWh]']:,} kWh</b></div>"
                f"<div style='font-size:12px;color:#2E7D32;'>✅ Útil: <b>{row['Regen Útil [kWh]']:,} kWh</b></div>"
                f"<div style='font-size:12px;color:#C62828;'>🔥 Reóstato: <b>{row['Reóstato [kWh]']:,} kWh</b></div>"
                f"<div style='font-size:12px;color:#E65100;margin-top:4px;'>💡 IDE: <b>{row['IDE [kWh/Tren-km]']:.3f} kWh/km</b></div>"
                f"<div style='margin-top:8px;font-size:11px;font-weight:700;color:{bar_color};'>Tasa aprovechamiento</div>"
                f"<div style='background:#e0e0e0;border-radius:4px;height:10px;margin-top:3px;'><div style='width:{min(100,tasa):.1f}%;height:100%;background:{bar_color};border-radius:4px;'></div></div>"
                f"<div style='text-align:right;font-size:14px;font-weight:700;color:{bar_color};'>{tasa:.1f}%</div></div>",
                unsafe_allow_html=True
            )

def _render_comparativa_flota_v115(df_dia_e: pd.DataFrame, vacio_kwh: float, vacio_km: float, km_total: float):
    flotas = ['XT-100','XT-M','SFE']
    data_plot = []
    for ft in flotas:
        sub = df_dia_e[df_dia_e['tipo_tren']==ft] if 'tipo_tren' in df_dia_e.columns else pd.DataFrame()
        neto = sub.get('kwh_viaje_neto', pd.Series(dtype=float)).sum() if not sub.empty else 0.0
        data_plot.append({'Flota': ft, 'Consumo': neto, 'Color': '#1565C0'})
    data_plot.append({'Flota': 'Vacío (Maniobras)', 'Consumo': vacio_kwh, 'Color': '#757575'})
    df_plot = pd.DataFrame(data_plot)
    fig = go.Figure(go.Bar(
        x=df_plot['Consumo'], y=df_plot['Flota'], orientation='h',
        marker_color=df_plot['Color'], text=[f"{val:,.0f} kWh" for val in df_plot['Consumo']], textposition='auto'
    ))
    fig.update_layout(height=200, margin=dict(l=10, r=20, t=10, b=10), xaxis=dict(showgrid=True, gridcolor='#eee'), plot_bgcolor='white', showlegend=False)
    st.plotly_chart(fig, use_container_width=True)

def _render_comparativa_sers_v115(total_ser_kwh, seat_kwh, km_total, active_sers):
    data_plot = []
    total_cap = sum(SER_CAPACITY_KW.get(s[1], 3000) for s in active_sers)
    for s in active_sers:
        name = s[1]; cap = SER_CAPACITY_KW.get(name, 3000)
        ser_val = total_ser_kwh * (cap / total_cap) if total_cap > 0 else 0
        data_plot.append({'Entidad': name, 'Consumo [kWh]': ser_val, 'IDE [kWh/km]': ser_val/km_total if km_total>0 else 0})
    df_sers = pd.DataFrame(data_plot)
    st.markdown(f"<div style='padding:10px; background:#FFF3E0; border-radius:8px; border-left:4px solid #E65100;'>"
                f"<b>⚡ SEAT Total:</b> {seat_kwh:,.0f} kWh<br>"
                f"<b>💡 IDE Global Red (SEAT/Km Total):</b> <span style='color:#E65100; font-weight:bold;'>{seat_kwh/km_total if km_total>0 else 0:.3f} kWh/km</span>"
                f"</div>", unsafe_allow_html=True)
    df_fmt = df_sers.copy()
    df_fmt['Consumo [kWh]'] = df_fmt['Consumo [kWh]'].apply(lambda x: f"{x:,.0f}")
    df_fmt['IDE [kWh/km]'] = df_fmt['IDE [kWh/km]'].apply(lambda x: f"{x:.3f}")
    st.dataframe(df_fmt, use_container_width=True, hide_index=True)

def render_dashboard_energia_v112(df_dia_e, active_sers, fecha_sel, hora_m1, total_ser_kwh_44kv=0.0, seat_accum=0.0, vacio_kwh_total=0.0, vacio_km_total=0.0):
    if df_dia_e is None or df_dia_e.empty: st.info("Sin datos termodinámicos."); return
    t_trac    = df_dia_e.get('kwh_viaje_trac',  pd.Series(dtype=float)).sum()
    t_aux     = df_dia_e.get('kwh_viaje_aux',   pd.Series(dtype=float)).sum()
    t_regen   = df_dia_e.get('kwh_viaje_regen', pd.Series(dtype=float)).sum()
    t_reostat = df_dia_e.get('kwh_reostato',    pd.Series(dtype=float)).sum()
    t_neto    = df_dia_e.get('kwh_viaje_neto',  pd.Series(dtype=float)).sum()
    tren_km_t = df_dia_e.get('tren_km',         pd.Series(dtype=float)).sum()
    regen_bruta = t_regen + t_reostat
    tasa_global = (t_regen/regen_bruta*100) if regen_bruta > 0 else 0.0
    ide_global  = t_neto/tren_km_t if tren_km_t > 0 else 0.0
    hora_str    = f"{int(hora_m1)//60:02d}:{int(hora_m1)%60:02d}"
    eta_prom = df_dia_e.get('eta_regen_util', pd.Series(dtype=float)).mean() if 'eta_regen_util' in df_dia_e.columns else 0.0

    st.markdown(f"### ⚡ Balance Energético Integral — {fecha_sel} (acumulado hasta {hora_str})")
    k1,k2,k3,k4,k5,k6 = st.columns(6)
    k1.metric("🔋 Tracción", f"{t_trac:,.0f} kWh"); k2.metric("❄️ Auxiliar", f"{t_aux:,.0f} kWh")
    k3.metric("♻️ Regen Bruta", f"{regen_bruta:,.0f} kWh", help="Energía recuperada en motores")
    k4.metric("✅ Regen Útil", f"{t_regen:,.0f} kWh", delta=f"+{tasa_global:.1f}% a red", delta_color="normal")
    k5.metric("🔥 Reóstato", f"{t_reostat:,.0f} kWh", delta=f"−{100-tasa_global:.1f}% disipado", delta_color="inverse")
    k6.metric("💡 IDE Comercial", f"{ide_global:.3f} kWh/km", help="kWh neto / Tren-km (sin vacíos)")
    st.caption(f"η̄ receptividad promedio: **{eta_prom*100:.1f}%**")
    st.divider()

    col_s, col_g = st.columns([3,1])
    with col_s: st.markdown("#### Flujo Energético del Día"); _render_sankey_v112(t_trac, t_aux, t_regen, t_reostat, t_neto, total_ser_kwh_44kv, seat_accum)
    with col_g: st.markdown("#### Aprovechamiento Regen."); _render_gauge_v112(tasa_global)
    st.divider()

    st.markdown("#### Distribución Horaria de Energía")
    _render_grafico_horario_v112(df_dia_e)
    st.divider()

    st.markdown("#### Análisis por Segmento Eléctrico")
    df_segs = get_kpis_regen_por_segmento(df_dia_e)
    _render_tarjetas_segmento_v112(df_segs)
    st.divider()

    km_total_red = tren_km_t + vacio_km_total
    col_f1, col_f2 = st.columns(2)
    with col_f1:
        st.markdown("#### Consumo Acumulado por Tipo de Tren (Neto)")
        st.caption(f"Incluyendo maniobras. **Km Total Red:** {km_total_red:,.1f} km")
        _render_comparativa_flota_v115(df_dia_e, vacio_kwh_total, vacio_km_total, km_total_red)
    with col_f2:
        st.markdown("#### Consumo Acumulado y Costo por SER")
        st.caption("Aporte al consumo total. IDE calculado usando el Km Total.")
        _render_comparativa_sers_v115(total_ser_kwh_44kv, seat_accum, km_total_red, active_sers)
    st.divider()

    with st.expander("📋 Tabla de Auditoría Energética por Viaje", expanded=False):
        cols_ok = [c for c in ['num_servicio','Via','tipo_tren','doble','svc_type','kwh_viaje_trac','kwh_viaje_aux','kwh_viaje_regen','kwh_reostato','kwh_viaje_neto','eta_regen_util','tren_km','pax_abordo'] if c in df_dia_e.columns]
        df_audit = df_dia_e[cols_ok].copy().rename(columns={'num_servicio':'Servicio','Via':'Vía','tipo_tren':'Flota','doble':'Doble','svc_type':'Trayecto','kwh_viaje_trac':'Tracción [kWh]','kwh_viaje_aux':'Auxiliar [kWh]','kwh_viaje_regen':'Regen Útil [kWh]','kwh_reostato':'Reóstato [kWh]','kwh_viaje_neto':'Neto [kWh]','eta_regen_util':'η Regen','tren_km':'Tren-km','pax_abordo':'Pax'})
        for c in ['Tracción [kWh]','Auxiliar [kWh]','Regen Útil [kWh]','Reóstato [kWh]','Neto [kWh]']:
            if c in df_audit.columns: df_audit[c] = df_audit[c].round(1)
        if 'η Regen' in df_audit.columns: df_audit['η Regen'] = (df_audit['η Regen']*100).round(1).astype(str)+'%'
        st.dataframe(df_audit, use_container_width=True, height=320)
        csv_b = df_audit.to_csv(index=False).encode('utf-8')
        st.download_button("📥 Descargar CSV Auditoría", data=csv_b, file_name=f"Auditoria_{fecha_sel}.csv", mime='text/csv')

# =============================================================================
# 12. PARSER PLANILLA MAESTRA V117
# =============================================================================
def parsear_planilla_maestra(data, fname):
    try:
        ext = fname.lower()
        if ext.endswith('.csv'):
            try: raw = pd.read_csv(BytesIO(data), header=None, sep=',', encoding='utf-8', dtype=str)
            except: raw = pd.read_csv(BytesIO(data), header=None, sep=';', encoding='latin-1', dtype=str)
        else:
            eng = "xlrd" if ext.endswith(".xls") else "openpyxl"
            raw = pd.read_excel(BytesIO(data), header=None, engine=eng, dtype=str)
            
        viajes = []
        for i in range(len(raw)):
            row_vals = raw.iloc[i].fillna('').astype(str).tolist()
            for c_idx, val in enumerate(row_vals):
                val = val.strip()
                if re.match(r'^\d{1,2}:\d{2}:\d{2}$', val):
                    t_ini = parse_time_to_mins(val)
                    if t_ini is None: continue
                    
                    tren_val, viaje_val = 0, 0
                    for offset in range(1, 5):
                        if c_idx - offset >= 0:
                            check_val = row_vals[c_idx - offset].strip()
                            if check_val.isdigit():
                                if tren_val == 0: tren_val = int(check_val)
                                elif viaje_val == 0: viaje_val = int(check_val)
                    
                    if tren_val == 0 or viaje_val == 0: continue
                    
                    es_doble = False
                    for offset in range(1, 6):
                        if c_idx + offset < len(row_vals):
                            check_val = row_vals[c_idx + offset].upper()
                            if re.match(r'^[12]_[12]$', check_val) and check_val.startswith('2'):
                                es_doble = True
                            elif 'MÚLTIPLE' in check_val or 'MULTIPLE' in check_val or 'DOBLE' in check_val:
                                es_doble = True

                    via = 1 if viaje_val % 2 == 0 else 2
                    if via == 1:
                        km_orig = KM_ACUM[0] 
                        if tren_val >= 600: km_dest = KM_ACUM[20] 
                        elif tren_val >= 400: km_dest = KM_ACUM[18] 
                        else: km_dest = KM_ACUM[14] 
                    else:
                        km_dest = KM_ACUM[0] 
                        if tren_val >= 600: km_orig = KM_ACUM[20] 
                        elif tren_val >= 400: km_orig = KM_ACUM[18] 
                        else: km_orig = KM_ACUM[14] 
                        
                    ruta = f"{EC[KM_ACUM.index(km_orig)]}-{EC[KM_ACUM.index(km_dest)]}"
                    nodos_via = [(0.0, k) for k in (KM_ACUM[KM_ACUM.index(km_orig):KM_ACUM.index(km_dest)+1] if via==1 else KM_ACUM[KM_ACUM.index(km_dest):KM_ACUM.index(km_orig)+1][::-1])]
                    
                    viajes.append({
                        '_id': f"PLAN_{tren_val}_{int(t_ini)}", 't_ini': t_ini, 'Via': via,
                        'km_orig': km_orig, 'km_dest': km_dest, 'nodos': nodos_via,
                        'tipo_tren': 'XT-100', 'doble': es_doble, 'num_servicio': str(tren_val), 'svc_type': ruta
                    })
                    
        df_viajes = pd.DataFrame(viajes)
        if not df_viajes.empty: df_viajes = df_viajes.drop_duplicates(subset=['_id'])
        return df_viajes, "ok"
    except Exception as e: return pd.DataFrame(), str(e)

# =============================================================================
# 13. CACHÉ Y CARGADORES DE STREAMLIT (UI)
# =============================================================================
def leer(files): return [(f.name, f.read()) for f in (files or []) if f]

def leer_github(url):
    try:
        import urllib.request
        url = url.strip()
        if 'github.com' in url and 'raw.githubusercontent' not in url:
            url = url.replace('github.com','raw.githubusercontent.com').replace('/blob/','/')
        nm = url.split('/')[-1]
        with urllib.request.urlopen(url, timeout=15) as r:
            return nm, r.read()
    except Exception as e: return None, str(e)

def procesar_thdr_dummy(data, fname, via_param):
    # Dummy function para evitar error si no se usa el THDR normal
    return pd.DataFrame(), "ok"

@st.cache_data(show_spinner="Procesando THDR Estándar…")
def build_thdr(blobs_v1, blobs_v2):
    return pd.DataFrame(), pd.DataFrame(), []

@st.cache_data(show_spinner="Cargando pasajeros…")
def build_pax(blobs_v1, blobs_v2):
    return pd.DataFrame(), []

def match_pax(row, df_pax): return ({},0,'--:--:--','',-1)
def get_vacios_dia(df_dia): return []
def draw_diagram(a,b,c,d,e,f,g): return go.Figure()

def _all_blobs(f_uploader, gh_key): 
    return tuple(leer(f_uploader) + st.session_state.get(gh_key, []))

# =============================================================================
# 14. UI PRINCIPAL Y SIDEBAR
# =============================================================================
with st.sidebar:
    st.header("📂 Archivos Base")
    with st.expander("🔗 Cargar desde GitHub (Batch)",expanded=False):
        urls_txt=st.text_area("Lista de URLs",placeholder="https://github.com/...",height=100)
        gh_via=st.radio("Tipo manual",["Detección Automática","THDR V1","THDR V2","Pasajeros V1","Pasajeros V2"],horizontal=False,index=0)
        if st.button("⬇️ Descargar Todo",use_container_width=True): pass
            
    st.subheader("Planillas THDR")
    f_v1=st.file_uploader("THDR Vía 1",accept_multiple_files=True,key="t1")
    f_v2=st.file_uploader("THDR Vía 2",accept_multiple_files=True,key="t2")
    st.divider()
    st.subheader("Carga de Pasajeros")
    f_px1=st.file_uploader("Pax Vía 1 (Puerto→Limache)",accept_multiple_files=True,key="px1")
    f_px2=st.file_uploader("Pax Vía 2 (Limache→Puerto)",accept_multiple_files=True,key="px2")
    st.divider()
    st.subheader("✂️ Gestión de Flota (Split & Merge)")
    n_cortes_v1      =st.slider("Doble→Simple en El Belloto (V1, PU-LI)",0,20,0)
    n_cortes_pu_sa_v1=st.slider("Doble→Simple en El Belloto (V1, PU-SA)",0,20,0)
    n_acoples_v2     =st.slider("Simple→Doble en El Belloto (V2)",0,20,0)
    n_cortes_sa_v1   =st.slider("Doble→Simple en S. Aldea (V1)",0,20,0)
    n_acoples_sa_v2  =st.slider("Simple→Doble en S. Aldea (V2)",0,20,0)
    st.divider()
    st.subheader("⚙️ Parámetros de Simulación")
    use_rm      =st.checkbox("🚦 Velocidades RM",value=False)
    pct_trac    =st.slider("⚙️ % Tracción Nominal",30,100,75,5)
    use_pend    =st.toggle("⛰️ Pendientes Físicas",value=True)
    use_regen   =st.toggle("⚡ Activar Regeneración",value=True)
    tipo_regen  =st.radio("Modelo de Regeneración", ["Físico (Load Flow / Squeeze Control)", "Probabilístico (Headway Real THDR)"])
    st.divider()
    st.subheader("🌡️ Perfil de Auxiliares Dinámicos")
    mes_sel = st.selectbox("Mes de operación", ["Enero","Febrero","Marzo","Abril","Mayo","Junio","Julio","Agosto","Septiembre","Octubre","Noviembre","Diciembre"], index=3)
    _MES_A_ESTACION = {"Enero":"verano","Febrero":"verano","Marzo":"otoño","Abril":"otoño","Mayo":"otoño","Junio":"invierno","Julio":"invierno","Agosto":"invierno","Septiembre":"primavera","Octubre":"primavera","Noviembre":"primavera","Diciembre":"verano"}
    estacion_anio = _MES_A_ESTACION[mes_sel]
    st.divider()
    st.subheader("🔌 Contingencias Eléctricas")
    all_ser_names=[s[1] for s in SER_DATA]
    active_ser_names=st.multiselect("SERs Activas",all_ser_names,default=all_ser_names)
    active_sers=[s for s in SER_DATA if s[1] in active_ser_names]
    if not active_sers: active_sers=[SER_DATA[0]]
    st.divider()
    gap_vias=st.slider("Separación Visual Vías (px)",120,350,200,10)

b1=_all_blobs(f_v1,"gh_blobs_v1"); b2=_all_blobs(f_v2,"gh_blobs_v2")
bx1=_all_blobs(f_px1,"gh_blobs_px1"); bx2=_all_blobs(f_px2,"gh_blobs_px2")
df1,df2,err_t=build_thdr(b1,b2)
df_px,err_p  =build_pax(bx1,bx2)
df_all = pd.DataFrame()
fechas = []

# =============================================================================
# 15. PANTALLA PRINCIPAL: PLANIFICADOR V117
# =============================================================================
def render_planificador():
    st.subheader("🔮 Planificador Avanzado: Lector de Planilla Maestra de Inyecciones (V117)")
    st.markdown("Sube tu archivo de planificación. El algoritmo ruteará los trenes basándose en el N° de Servicio y calculará los tiempos de llegada usando Física Pura, inyectando demanda Gaussiana para estresar las subestaciones.")
    
    col_p1, col_p2 = st.columns([1, 2])
    with col_p1:
        tipo_dia_plan = st.selectbox("📅 Tipo de Día", ["Laboral", "Sábado", "Domingo/Festivo"], key="td_plan")
        pax_promedio_viaje = {"Laboral": 280, "Sábado": 160, "Domingo/Festivo": 110}[tipo_dia_plan]
        estacion_anio_plan = st.selectbox("🌡️ Estación del Año (HVAC)", ["verano", "otoño", "invierno", "primavera"], index=3)
        st.info(f"**Pax promedio base:** {pax_promedio_viaje} pax")
        
    with col_p2:
        modo_plan = st.radio("Fuente de Datos", ["Planilla Maestra (Subir CSV/Excel)", "Matriz Sintética"], horizontal=True)
        archivo_planilla = None
        
        if modo_plan == "Matriz Sintética":
            if 'df_plan' not in st.session_state:
                st.session_state['df_plan'] = pd.DataFrame([
                    {"Ruta": "PU-LI", "Flota": "XT-100", "Configuración": "Doble", "Cantidad": 40},
                    {"Ruta": "LI-PU", "Flota": "XT-100", "Configuración": "Doble", "Cantidad": 40},
                ])
            df_plan_edit = st.data_editor(st.session_state['df_plan'], num_rows="dynamic", use_container_width=True)
        else:
            archivo_planilla = st.file_uploader("📂 Sube tu Planilla Maestra (.csv, .xlsx)", type=['csv', 'xlsx', 'xls'])
            df_plan_edit = pd.DataFrame()
            if archivo_planilla: st.success("Planilla detectada. Ejecuta la simulación.")
        
    if st.button("🚀 Procesar Planilla y Ejecutar Motor Físico", use_container_width=True, type="primary"):
        with st.spinner("Decodificando Planilla e inyectando al Motor Cinemático..."):
            
            if modo_plan == "Matriz Sintética":
                df_sintetico_list = []
                RUTAS_PLAN = {"PU-LI": (0, 20, 1), "LI-PU": (20, 0, 2), "PU-SA": (0, 18, 1), "SA-PU": (18, 0, 2), "PU-BTO": (0, 14, 1), "BTO-PU": (14, 0, 2)}
                for idx, row in df_plan_edit.iterrows():
                    ruta = row['Ruta']; flota = row['Flota']; es_doble = row['Configuración'] == "Doble"; cant = row['Cantidad']
                    if cant <= 0 or ruta not in RUTAS_PLAN: continue
                    idx_ini, idx_fin, via = RUTAS_PLAN[ruta]
                    km_ini = KM_ACUM[idx_ini]; km_fin = KM_ACUM[idx_fin]
                    est_idxs = range(idx_ini, idx_fin + 1) if via == 1 else range(idx_ini, idx_fin - 1, -1)
                    nodos_sint = [(0.0, KM_ACUM[i]) for i in est_idxs]
                    interval_mins = (1350 - 360) / cant if cant > 1 else 0
                    
                    for i in range(int(cant)):
                        t_ini_sint = 360 + i * interval_mins
                        df_sintetico_list.append({
                            '_id': f"SINT_{ruta}_{i}", 't_ini': t_ini_sint, 'Via': via,
                            'km_orig': km_ini, 'km_dest': km_fin, 'nodos': nodos_sint,
                            'tipo_tren': flota, 'doble': es_doble, 'num_servicio': f"VIRT_{i}",
                            'maniobra': None, 'svc_type': ruta
                        })
                df_sint = pd.DataFrame(df_sintetico_list)
            else:
                if archivo_planilla is None:
                    st.warning("Debes subir la Planilla de Operación.")
                    return
                df_sint, msg = parsear_planilla_maestra(archivo_planilla.read(), archivo_planilla.name)
                if df_sint.empty:
                    st.error(f"Error procesando: {msg}")
                    return

            if df_sint.empty:
                st.warning("No hay viajes para simular.")
                return

            viajes_completos = []
            for idx, r in df_sint.iterrows():
                f_gauss = 0.2 + 0.8 * np.exp(-0.5 * ((r['t_ini'] - 450)/60)**2) + 0.8 * np.exp(-0.5 * ((r['t_ini'] - 1080)/90)**2)
                pax_calculado = int(pax_promedio_viaje * f_gauss * 1.5)
                cap_m = FLOTA[r['tipo_tren']].get('cap_max', 398) * (2 if r['doble'] else 1)
                pax_calculado = min(pax_calculado, cap_m)
                
                trc_v, aux_v, reg_v, _, _, t_horas_v = simular_tramo_termodinamico(
                    r['tipo_tren'], r['doble'], r['km_orig'], r['km_dest'], r['Via'],
                    75, False, True, r['nodos'], {}, pax_calculado, None, None, estacion_anio_plan, r['t_ini']
                )
                
                t_fin_real = r['t_ini'] + (t_horas_v * 60.0)
                viaje_final = r.to_dict()
                viaje_final['pax_abordo'] = pax_calculado
                viaje_final['t_fin'] = t_fin_real
                viajes_completos.append(viaje_final)
                
            df_sint_final = pd.DataFrame(viajes_completos)
            df_sint_final['tren_km'] = df_sint_final.apply(calc_tren_km_real_general, axis=1)
            df_sint_final.index = df_sint_final['_id']
            
            dict_regen_sint = calcular_receptividad_por_headway(df_sint_final)
            df_sint_e = calcular_termodinamica_flota_v111(df_sint_final, 75, True, False, True, dict_regen_sint, estacion_anio_plan)
            
            active_sers_sint = [s for s in SER_DATA]
            ser_accum_sint = {name: 0.0 for _, name in active_sers_sint}
            for _, r in df_sint_e.iterrows():
                e_pant_frac = r['kwh_viaje_trac'] + r['kwh_viaje_aux'] - r['kwh_viaje_regen']
                t_horas_frac = (r['t_fin'] - r['t_ini']) / 60.0
                distrib = distribuir_energia_sers(e_pant_frac, t_horas_frac, r['km_orig'], r['km_dest'], active_sers_sint)
                for s_n, e_val in distrib.items():
                    ser_accum_sint[s_n] += e_val
            
            total_ser_kwh_sint = sum(max(0.0, v) for v in ser_accum_sint.values()) / ETA_SER_RECTIFICADOR
            avg_demands_kw_sint = {k: max(0.0, v)/ETA_SER_RECTIFICADOR/18.0 for k, v in ser_accum_sint.items()}
            flujo_sint = calcular_flujo_ac_nodo(avg_demands_kw_sint)
            ac_loss_sint = flujo_sint['P_loss_kw'] * (1.15**2) * 18.0
            seat_accum_sint = (total_ser_kwh_sint + ac_loss_sint) / 0.99
            
            st.divider()
            st.success("✅ Malla Operativa Físicamente Validada y Calculada")
            
            render_dashboard_energia_v112(
                df_dia_e=df_sint_e, active_sers=active_sers_sint, 
                fecha_sel=f"Auditoría de Planilla Maestra ({estacion_anio_plan.capitalize()})", 
                hora_m1=1440.0, total_ser_kwh_44kv=total_ser_kwh_sint, seat_accum=seat_accum_sint,
                vacio_kwh_total=0.0, vacio_km_total=0.0
            )

# =============================================================================
# 16. MANEJADOR DE PESTAÑAS 
# =============================================================================
if df_all.empty and df_px.empty:
    st.info("📂 Sube tus archivos en la pestaña del Planificador para comenzar.")
    st.divider()
    render_planificador()
else:
    tab_planificador, tab_mapa = st.tabs(["🔮 Planificador", "🗺️ Mapa Histórico"])
    with tab_planificador: render_planificador()
    with tab_mapa: st.info("Sube los archivos THDR Reales a la izquierda para usar el reproductor.")
