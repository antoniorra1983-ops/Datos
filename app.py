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

_ELEV_KM = [0.0, 0.7, 1.4, 2.2, 3.9, 6.0, 7.4, 8.3, 9.2, 10.2, 11.7, 19.1, 21.4, 23.3, 25.3, 26.4, 27.6, 28.5, 29.1, 30.4, 43.13]
_ELEV_M  = [12, 10, 10, 10, 18, 15, 12, 15, 35, 50, 55, 88, 122, 132, 142, 148, 155, 162, 175, 198, 216]

EST_LATS = [-33.03846,-33.04295,-33.04405,-33.04241,-33.03284,-33.02703,-33.02496,
            -33.02642,-33.02868,-33.03300,-33.04113,-33.04031,-33.04532,-33.03966,
            -33.04311,-33.04385,-33.04158,-33.04258,-33.04203,-33.04019,-32.98427]
EST_LONS = [-71.62709,-71.62088,-71.61244,-71.60567,-71.59123,-71.57501,-71.56160,
            -71.55180,-71.54315,-71.53346,-71.52104,-71.46888,-71.44453,-71.42884,
            -71.40651,-71.37354,-71.36594,-71.35302,-71.27771]

SER_DATA = [
    (KM_ACUM[4] + 1.0, "SER PO"),
    (KM_ACUM[10] + 1.0, "SER ES"),
    (KM_ACUM[14] + 0.2, "SER EB"),
    (KM_ACUM[17] + 0.2, "SER VA")
]
SEAT_KM = KM_ACUM[13] + 1.0

SER_CAPACITY_KW = {"SER PO": 3000.0, "SER ES": 3000.0, "SER EB": 4500.0, "SER VA": 3000.0}
SEAT_CAPACITY_KW = 20000.0 

Z_EFF_44KV = 0.28  
R_AC_44KV = 0.17   
V_NOMINAL_AC = 44000.0

PAX_KG    = 75.0
DWELL_DEF = 8.0  
DAVIS_E_N_PERMIL = 9.81
ETA_TRAC_SISTEMA = 0.92  
ETA_REGEN_NETA   = 0.72   
LAMBDA_REGEN_KM  = 5.0     
ETA_SER_RECTIFICADOR = 0.96 
ETA_MAX   = 0.70
V_NOMINAL_DC = 3000.0
V_SQUEEZE_WARN = 2850.0

# --- PERFILES DE AUXILIARES DINÁMICOS ---
_AUX_HVAC_HORA = {
    "verano": [0.60,0.55,0.55,0.55,0.58,0.65, 0.72,0.78,0.83,0.88,0.92,0.95, 0.98,1.00,1.00,0.98,0.95,0.90, 0.85,0.80,0.75,0.70,0.67,0.63],
    "otoño": [0.40,0.38,0.37,0.37,0.38,0.42, 0.48,0.52,0.56,0.60,0.63,0.65, 0.66,0.66,0.65,0.63,0.60,0.57, 0.53,0.50,0.47,0.44,0.42,0.41],
    "invierno": [0.72,0.70,0.68,0.68,0.70,0.74, 0.80,0.84,0.86,0.85,0.82,0.78, 0.75,0.73,0.72,0.73,0.76,0.80, 0.82,0.80,0.78,0.76,0.74,0.73],
    "primavera": [0.42,0.40,0.39,0.39,0.41,0.46, 0.53,0.58,0.63,0.68,0.72,0.75, 0.77,0.78,0.77,0.74,0.70,0.66, 0.61,0.57,0.53,0.49,0.46,0.44],
}
_FRAC_HVAC = 0.70
_FRAC_BASE = 0.30
_FACTOR_DWELL_COMPRESOR = 1.08

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
# 2. DICCIONARIO DE FLOTA CERTIFICADA 
# =============================================================================
FLOTA = {
    "XT-100": {
        "tara_t"       : 86.1,  
        "m_iner_t"     : 7.20,  
        "coches"       : 2,  
        "cap_sent"     : 94,  
        "cap_max"      : 398,
        "n_motores"    : 4,  
        "a_max_ms2"    : 1.0,  
        "a_freno_ms2"  : 1.2,
        "v_freno_min"  : 3.81,  
        "eta_motor"    : 0.92,  
        "davis_A"      : 1615.00,  
        "davis_B"      : 0.00,
        "davis_C"      : 0.5458,     
        "f_trac_max_kn": 110.0,   
        "f_freno_max_kn": 105.0,  
        "p_max_kw"     : 720.0,
        "p_freno_max_kw": 600.0,
        "aux_kw"       : 46.0      
    },
    "XT-M": {
        "tara_t"       : 95.0,  
        "m_iner_t"     : 8.0,  
        "coches"       : 2,  
        "cap_sent"     : 94,  
        "cap_max"      : 376,
        "n_motores"    : 4,  
        "a_max_ms2"    : 1.0,  
        "a_freno_ms2"  : 1.2,
        "v_freno_min"  : 3.81,  
        "eta_motor"    : 0.92,  
        "davis_A"      : 1440.60,  
        "davis_B"      : 0.00,
        "davis_C"      : 0.35,      
        "f_trac_max_kn": 115.0,   
        "f_freno_max_kn": 110.0,  
        "p_max_kw"     : 1040.0,
        "p_freno_max_kw": 800.0,
        "aux_kw"       : 55.0      
    },
    "SFE": {
        "tara_t"       : 141.0,  
        "m_iner_t"     : 11.2,  
        "coches"       : 3,  
        "cap_max"      : 780,
        "n_motores"    : 8,       
        "a_max_ms2"    : 1.02,
        "a_freno_ms2"  : 1.30,  
        "v_freno_min"  : 3.81,
        "eta_motor"    : 0.94,      
        "davis_A"      : 2480.00,  
        "davis_B"      : 0.00,
        "davis_C"      : 0.4714,     
        "f_trac_max_kn": 220.0,   
        "f_freno_max_kn": 190.0,  
        "p_max_kw"     : 2400.0,
        "p_freno_max_kw": 2800.0,
        "aux_kw"       : 190.0     
    },
}

feriados_2026 = [
    '2026-01-01', '2026-04-03', '2026-04-04', '2026-05-01', '2026-05-21', 
    '2026-06-21', '2026-07-16', '2026-08-15', '2026-09-18', '2026-09-19', 
    '2026-10-12', '2026-10-31', '2026-12-08', '2026-12-25'
]

# =============================================================================
# 2. FUNCIONES DE TIEMPO Y PARSEO
# =============================================================================
if 'min_slider_1' not in st.session_state:
    st.session_state['min_slider_1'] = 480.0

def clasificar_dia(d_str):
    try:
        d = datetime.strptime(d_str, '%Y-%m-%d')
        if d_str in feriados_2026 or d.weekday() == 6: return 'Domingo/Festivo'
        if d.weekday() == 5: return 'Sábado'
        return 'Laboral'
    except:
        return 'Laboral'

@st.cache_data(show_spinner="Calculando perfiles promedio de pasajeros por tipo de día...")
def get_perfiles_pax(df_px):
    if df_px.empty: return {}
    df_p = df_px.copy()
    
    df_p['Fecha_dt'] = pd.to_datetime(df_p['Fecha_s'], errors='coerce')
    df_p = df_p.dropna(subset=['Fecha_dt'])
    
    if df_p.empty: return {}
    
    df_p['Tipo_Dia'] = df_p['Fecha_s'].apply(clasificar_dia)
    
    for c in PAX_COLS + ['CargaMax']:
        if c in df_p.columns:
            df_p[c] = pd.to_numeric(df_p[c], errors='coerce').fillna(0)
            
    perfiles = {}
    for t_dia in ['Laboral', 'Sábado', 'Domingo/Festivo']:
        for via in [1, 2]:
            sub = df_p[(df_p['Tipo_Dia'] == t_dia) & (df_p['Via'] == via)]
            if not sub.empty:
                promedios = sub[PAX_COLS].mean().round().astype(int).to_dict()
                promedios['CargaMax_Promedio'] = int(sub['CargaMax'].mean().round())
            else:
                promedios = {c: 0 for c in PAX_COLS}
                promedios['CargaMax_Promedio'] = 0
            perfiles[(t_dia, via)] = promedios
            
    return perfiles

def mins_to_time_str(mins):
    if pd.isna(mins): return '--:--:--'
    try:
        m_val = float(mins)
        while m_val >= 1440: m_val -= 1440
        while m_val < 0: m_val += 1440
        h = int(m_val // 60)
        m = int(m_val % 60)
        s = int(round((m_val * 60) % 60))
        if s == 60: 
            s = 0; m += 1
        if m == 60: 
            m = 0; h += 1
        return f"{h:02d}:{m:02d}:{s:02d}"
    except: return '--:--:--'

def parse_time_to_mins(val):
    if pd.isna(val): return None
    sv = str(val).strip().lower()
    if sv == '' or sv == 'nan': return None
    if ' ' in sv: sv = sv.split(' ')[-1]
    m = re.search(r'(\d{1,2}):(\d{2})(?::(\d{2}))?', sv)
    if m:
        h = int(m.group(1)); m_min = int(m.group(2))
        s_sec = int(m.group(3)) / 60.0 if m.group(3) else 0.0
        return h * 60.0 + m_min + s_sec
    try:
        f = float(sv)
        if f < 1.0: return f * 1440.0
        if f < 2400.0: return (int(f // 100) * 60.0) + (f % 100)
    except: pass
    return None

def parse_excel_date(val):
    if pd.isna(val): return None
    if isinstance(val, (datetime, pd.Timestamp)): return val.strftime('%Y-%m-%d')
    v_str = re.sub(r'\.0+$', '', str(val).strip()).split(' ')[0]
    if not v_str or v_str.lower() in ['nan', 'none', 'fecha', 'date', 'nat']: return None
    
    if v_str.isdigit():
        v_int = int(v_str)
        if 40000 <= v_int <= 60000:
            try: return (date(1899, 12, 30) + timedelta(days=v_int)).strftime('%Y-%m-%d')
            except: pass
        elif len(v_str) in [5, 6]:
            s_pad = v_str.zfill(6)
            try:
                d, m_val, y = int(s_pad[0:2]), int(s_pad[2:4]), int(s_pad[4:6])
                if 1 <= d <= 31 and 1 <= m_val <= 12: return f"{2000+y if y<100 else y:04d}-{m_val:02d}-{d:02d}"
            except: pass
            
    for pat in [r'\b(\d{1,2})[-/](\d{1,2})[-/](\d{4})\b', r'\b(\d{4})[-/](\d{1,2})[-/](\d{1,2})\b']:
        m_dt = re.search(pat, v_str)
        if m_dt:
            if len(m_dt.group(1)) == 4: 
                y, m_val, d = int(m_dt.group(1)), int(m_dt.group(2)), int(m_dt.group(3))
            else: 
                d, m_val, y = int(m_dt.group(1)), int(m_dt.group(2)), int(m_dt.group(3))
            if m_val > 12 and d <= 12: d, m_val = m_val, d
            if 1 <= d <= 31 and 1 <= m_val <= 12: return f"{y:04d}-{m_val:02d}-{d:02d}"
    return None

def clean_primary_key(x):
    if pd.isna(x): return ''
    s = re.sub(r'[^A-Z0-9]', '', re.sub(r'\.0+$', '', str(x).strip().upper()))
    return s.lstrip('0') if s not in ['NAN', ''] else ''

def clean_id(x):
    try:
        nums = re.findall(r'\d+', str(x).strip().lower().replace(".0", ""))
        return str(int(nums[0])) if nums else str(x).strip().upper()
    except: return str(x).strip().upper()

def clean_pax_number(x):
    if pd.isna(x): return 0
    s = re.sub(r'[^\d]', '', re.sub(r'\.0+$', '', str(x).strip().lower()).replace('.', '').replace(',', ''))
    try: return int(s) if s and s != 'nan' else 0
    except: return 0

# =============================================================================
# 4. GEOGRÁFICAS Y UTILIDADES
# =============================================================================
def interp_pos(km):
    km = max(0.0, min(float(km), KM_TOTAL))
    return float(np.interp(km, KM_ACUM, EST_LATS)), float(np.interp(km, KM_ACUM, EST_LONS))

def km_to_ec(km, tol=1.5):
    dists = [abs(km - k) for k in KM_ACUM]
    idx = int(np.argmin(dists))
    return EC[idx] if dists[idx] <= tol else f"{km:.1f}km"

def svc_label(km_orig, km_dest): 
    return f"{km_to_ec(km_orig)}-{km_to_ec(km_dest)}"

def extraer_fecha_segura(df_raw, fname):
    for pat in [r'\b(\d{1,2})[-_\.](\d{1,2})[-_\.](\d{4})\b', r'\b(\d{4})[-_\.](\d{1,2})[-_\.](\d{1,2})\b']:
        m = re.search(pat, str(fname))
        if m:
            if len(m.group(1)) == 4:
                y, m_val, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
            else:
                d, m_val, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
            if m_val > 12 and d <= 12: d, m_val = m_val, d
            if 1 <= d <= 31 and 1 <= m_val <= 12: return f"{y:04d}-{m_val:02d}-{d:02d}"

    for i in range(min(50, len(df_raw))):
        row_str = ' '.join([str(x).strip() for x in df_raw.iloc[i].values if pd.notna(x)])
        for pat in [r'\b(\d{4})[-/\.](\d{1,2})[-/\.](\d{1,2})\b', r'\b(\d{1,2})[-/\.](\d{1,2})[-/\.](\d{4})\b']:
            m_dt = re.search(pat, row_str)
            if m_dt:
                if len(m_dt.group(1)) == 4:
                    y, m_val, d = int(m_dt.group(1)), int(m_dt.group(2)), int(m_dt.group(3))
                else:
                    d, m_val, y = int(m_dt.group(1)), int(m_dt.group(2)), int(m_dt.group(3))
                if m_val > 12 and d <= 12: d, m_val = m_val, d
                if 1 <= d <= 31 and 1 <= m_val <= 12: return f"{y:04d}-{m_val:02d}-{d:02d}"
    return "2026-01-01"

def make_unique(df):
    if df.empty: return df
    cols = pd.Series(df.columns)
    for dup in cols[cols.duplicated()].unique(): 
        cols[cols==dup] = [f"{dup}_{i}" if i else dup for i in range(sum(cols==dup))]
    df.columns = cols
    return df

_EST_NORM = sorted({re.sub(r'[^a-z0-9]','', e.lower().replace('á','a').replace('é','e').replace('í','i').replace('ó','o').replace('ú','u').replace('ñ','n')): i for i, e in enumerate(ESTACIONES)}.items(), key=lambda x: -len(x[0]))
def _col_to_est_idx(col):
    cu = re.sub(r'[^a-z0-9]','', col.lower().replace('á','a').replace('é','e').replace('í','i').replace('ó','o').replace('ú','u').replace('ñ','n'))
    if 'americas' in cu: return ESTACIONES.index('Las Americas')
    if 'vina' in cu: return ESTACIONES.index('Viña del Mar')
    if 'aldea' in cu: return ESTACIONES.index('Sargento Aldea')
    if 'belloto' in cu: return ESTACIONES.index('El Belloto')
    if 'concepcion' in cu: return ESTACIONES.index('La Concepcion')
    if 'villaalem' in cu: return ESTACIONES.index('Villa Alemana')
    if 'salto' in cu: return ESTACIONES.index('El Salto')
    for nk, idx in _EST_NORM:
        if nk in cu: return idx
    return None

def calc_tren_km_real_general(row):
    k_s,k_e = min(row['km_orig'],row['km_dest']), max(row['km_orig'],row['km_dest'])
    man = row.get('maniobra')
    if man in ['CORTE_BTO','ACOPLE_BTO','CORTE_PU_SA_BTO']:
        km_man = KM_ACUM[14]
        if k_s <= km_man <= k_e: return abs(km_man-k_s)*2.0 + abs(k_e-km_man)*1.0
    elif man in ['CORTE_SA','ACOPLE_SA']:
        km_man = KM_ACUM[18]
        if k_s <= km_man <= k_e: return abs(km_man-k_s)*2.0 + abs(k_e-km_man)*1.0
    return abs(k_e-k_s) * (2.0 if row.get('doble',False) else 1.0)

# =============================================================================
# 5. MOTOR CINEMÁTICO TRAMO A TRAMO
# =============================================================================
def _build_profile(use_rm, via):
    segs = SPEED_PROFILE if via == 1 else list(reversed(SPEED_PROFILE))
    km_pts, t_pts, cum_t = [], [], 0.0
    for ki, kf, dm, vn, vr in segs:
        v = max(5.0, vr if use_rm else vn)
        km_pts.append(ki if via == 1 else kf)
        t_pts.append(cum_t)
        cum_t += (dm / 1000.0) / v * 3600.0
    last = SPEED_PROFILE[-1] if via == 1 else SPEED_PROFILE[0]
    km_pts.append(last[1] if via == 1 else last[0])
    t_pts.append(cum_t)
    return np.array(km_pts, float), np.array(t_pts, float)

_PROF = {(v, r): _build_profile(r, v) for v in [1, 2] for r in [False, True]}
_PROF_SORTED = {}
for k, v in _PROF.items(): 
    if k[0] == 1: _PROF_SORTED[k] = (v[0], v[1])
    else: _PROF_SORTED[k] = (v[0][::-1].copy(), v[1][::-1].copy())

_VEL_ARRAY_NORM = np.zeros(45000, dtype=float)
_VEL_ARRAY_RM = np.zeros(45000, dtype=float)
for ki, kf, _, vn, vr in SPEED_PROFILE:
    start_idx = int(ki)
    end_idx = min(int(kf) + 1, 45000)
    _VEL_ARRAY_NORM[start_idx:end_idx] = vn
    _VEL_ARRAY_RM[start_idx:end_idx] = vr

def vel_at_km(km_km, via, use_rm):
    idx = int(km_km * 1000.0)
    if 0 <= idx < 45000: return _VEL_ARRAY_RM[idx] if use_rm else _VEL_ARRAY_NORM[idx]
    return 0.0

def km_at_t(t_ini, t_fin, t, via, use_rm=False, km_orig=None, km_dest=None, nodos=None, t_arr=None):
    if nodos is not None and len(nodos) >= 2:
        if t <= nodos[0][0]: return nodos[0][1]
        if t >= nodos[-1][0]: return nodos[-1][1]
        if t_arr is None: t_arr = [n[0] for n in nodos]
        idx = np.searchsorted(t_arr, t)
        t_A, k_A = nodos[idx-1]
        t_B, k_B = nodos[idx]
        if t_A == t_B or k_A == k_B: return k_A 
        frac = (t - t_A) / (t_B - t_A)
        km_sorted, t_sorted = _PROF_SORTED[(via, use_rm)]
        t_prof_A = float(np.interp(k_A * 1000.0, km_sorted, t_sorted))
        t_prof_B = float(np.interp(k_B * 1000.0, km_sorted, t_sorted))
        t_prof_target = t_prof_A + frac * (t_prof_B - t_prof_A)
        km_arr, t_prof_arr = _PROF[(via, use_rm)]
        km_m = float(np.interp(t_prof_target, t_prof_arr, km_arr))
        return max(0.0, min(km_m / 1000.0, KM_TOTAL))
        
    dur = t_fin - t_ini
    if dur <= 0: return km_orig if km_orig is not None else (0.0 if via==1 else KM_TOTAL)
    frac = max(0.0, min(1.0, (t - t_ini) / dur))
    
    if km_orig is None: km_orig = 0.0 if via == 1 else KM_TOTAL
    if km_dest is None: km_dest = KM_TOTAL if via == 1 else 0.0
    
    km_sorted, t_sorted = _PROF_SORTED[(via, use_rm)]
    t_at_orig = float(np.interp(km_orig * 1000.0, km_sorted, t_sorted))
    t_at_dest = float(np.interp(km_dest * 1000.0, km_sorted, t_sorted))
    t_prof = t_at_orig + frac * (t_at_dest - t_at_orig)
    
    km_arr, t_arr_prof = _PROF[(via, use_rm)]
    km_m = float(np.interp(t_prof, t_arr_prof, km_arr))
    return max(0.0, min(km_m / 1000.0, KM_TOTAL))

def get_train_state_and_speed(t, r_via, use_rm, km_orig, km_dest, nodos, t_arr=None):
    if not nodos or len(nodos) < 2: return "CRUISE", 60.0
    if t_arr is None: t_arr = [n[0] for n in nodos]
    if t <= t_arr[0] or t >= t_arr[-1]: return "DWELL", 0.0
    idx = np.searchsorted(t_arr, t)
    t_A, t_B = t_arr[idx-1], t_arr[idx]
    dt_from_A, dt_to_B = t - t_A, t_B - t
    km_now = km_at_t(t_A, t_B, t, r_via, use_rm, km_orig, km_dest, nodos, t_arr)
    vel_max = vel_at_km(km_now, r_via, use_rm)
    if dt_from_A <= 1.0: return "ACCEL", vel_max
    elif dt_to_B <= 1.0: return "BRAKE", vel_max
    else: return "CRUISE", vel_max

def calcular_aux_dinamico(aux_kw_nominal, hora_decimal, pax_abordo, cap_max, estacion_anio, estado_marcha="CRUISE"):
    hora_int = int(hora_decimal) % 24
    perfil = _AUX_HVAC_HORA.get(estacion_anio, _AUX_HVAC_HORA["primavera"])
    f_hvac = perfil[hora_int]
    if cap_max > 0:
        ocup = min(1.0, pax_abordo / cap_max)
        if estacion_anio == "verano": f_ocup = 1.0 + 0.05 * ocup
        elif estacion_anio == "invierno": f_ocup = 1.0 - 0.12 * ocup
        else: f_ocup = 1.0 - 0.06 * ocup
    else:
        f_ocup = 1.0
    f_marcha = _FACTOR_DWELL_COMPRESOR if estado_marcha == "DWELL" else 1.0
    aux_base = aux_kw_nominal * _FRAC_BASE
    aux_hvac = aux_kw_nominal * _FRAC_HVAC * f_hvac * f_ocup * f_marcha
    return aux_base + aux_hvac

def simular_tramo_termodinamico(tipo_tren, doble, km_ini, km_fin, via_op, pct_trac, use_rm, use_pend, nodos=None, pax_dict=None, pax_abordo=0, v_consigna_override=None, maniobra=None, estacion_anio="primavera", t_ini_mins=0.0, es_vacio=False):
    f = FLOTA.get(tipo_tren, FLOTA["XT-100"])
    trc, aux, reg, t_horas = 0.0, 0.0, 0.0, 0.0
    
    k_s, k_e = km_ini, km_fin
    dst = abs(k_e - k_s)
    if dst <= 0: return 0.0, 0.0, 0.0, 0.0, 0.0, 0.0
    
    paradas_km = [n[1] for n in nodos] if nodos else [k_s, k_e]
    k_min, k_max = min(k_s, k_e), max(k_s, k_e)
    paradas_km = [k for k in paradas_km if k_min <= k <= k_max]
    if k_s not in paradas_km: paradas_km.append(k_s)
    if k_e not in paradas_km: paradas_km.append(k_e)
    paradas_km = list(set(paradas_km))
    paradas_km.sort(reverse=(via_op == 2))
    
    pax_dict = pax_dict or {}
    dt = 1.0  
    
    for i in range(len(paradas_km)-1):
        p_ini, p_fin = paradas_km[i], paradas_km[i+1]
        dist_total_tramo = abs(p_fin - p_ini) * 1000.0
        if dist_total_tramo <= 0: continue
        
        pos_m = p_ini * 1000.0
        dist_recorrida = 0.0
        v_ms = 0.0
        a_prev = 0.0 
        estado_marcha = "ACCEL"
        
        while dist_recorrida < dist_total_tramo:
            dist_restante = dist_total_tramo - dist_recorrida
            if dist_restante < 0.1: break
            
            km_actual = (pos_m + dist_recorrida) / 1000.0 if via_op == 1 else (pos_m - dist_recorrida) / 1000.0
            
            es_doble = doble
            if maniobra in ['CORTE_BTO', 'CORTE_PU_SA_BTO'] and km_actual > 25.3: es_doble = False
            elif maniobra == 'CORTE_SA' and km_actual > 29.1: es_doble = False
            elif maniobra == 'ACOPLE_BTO' and km_actual < 25.3: es_doble = False
            elif maniobra == 'ACOPLE_SA' and km_actual < 29.1: es_doble = False
            
            n_uni = 2 if es_doble else 1
            pax_mid = get_pax_at_km(pax_dict, km_actual, via_op, pax_abordo) if pax_dict else pax_abordo
            masa_kg = ((f['tara_t'] + f['m_iner_t']) * 1000 * n_uni) + (pax_mid * PAX_KG)
            
            v_cons_kmh = max(5.0, vel_at_km(km_actual, via_op, use_rm))
            if v_consigna_override is not None: v_cons_kmh = min(v_cons_kmh, v_consigna_override)
            
            if es_vacio:
                min_dist_est_m = min([abs(km_actual - k) for k in KM_ACUM]) * 1000.0
                v_30_ms = 30.0 / 3.6
                d_brake_to_30 = ((v_ms**2 - v_30_ms**2) / (2 * (f['a_freno_ms2'] * 0.85))) if v_ms > v_30_ms else 0.0
                dist_to_next_station_m = 9999000.0
                for est_k in KM_ACUM:
                    if via_op == 1 and est_k > km_actual + 0.01:
                        dist_to_next_station_m = min(dist_to_next_station_m, (est_k - km_actual)*1000.0)
                    elif via_op == 2 and est_k < km_actual - 0.01:
                        dist_to_next_station_m = min(dist_to_next_station_m, (km_actual - est_k)*1000.0)
                if dist_to_next_station_m <= d_brake_to_30 + 50.0 or min_dist_est_m <= 120.0:
                    v_cons_kmh = min(v_cons_kmh, 30.0)
                
            v_kmh = v_ms * 3.6
            if n_uni == 2: f_davis = (f['davis_A'] * 2) + (f['davis_B'] * 2 * v_kmh) + (f['davis_C'] * 1.35 * (v_kmh**2))
            else: f_davis = f['davis_A'] + f['davis_B']*v_kmh + f['davis_C']*(v_kmh**2)
                
            f_pend = 0.0
            if use_pend:
                for j in range(1, len(_ELEV_KM)):
                    if _ELEV_KM[j-1] <= km_actual <= _ELEV_KM[j] or (j == len(_ELEV_KM)-1 and km_actual > _ELEV_KM[j]):
                        pend = ((_ELEV_M[j] - _ELEV_M[j-1]) / max(0.001, (_ELEV_KM[j] - _ELEV_KM[j-1])*1000)) * 1000
                        f_pend = DAVIS_E_N_PERMIL * pend * (masa_kg / 1000.0) * (1.0 if via_op==1 else -1.0)
                        break
                        
            a_freno_op = f['a_freno_ms2'] * 0.9 
            d_freno_req = (v_ms**2) / (2 * a_freno_op) if v_ms > 0 else 0
            
            f_disp_trac = min(f['f_trac_max_kn']*1000*n_uni*(pct_trac/100.0), (f['p_max_kw']*1000*n_uni*(pct_trac/100.0))/max(0.1, v_ms))
            f_disp_freno = min(f['f_freno_max_kn']*1000*n_uni, (f.get('p_freno_max_kw', f['p_max_kw']*1.2)*1000*n_uni)/max(0.1, v_ms)) if v_kmh >= f['v_freno_min'] else 0.0
            
            if dist_restante <= d_freno_req + (v_ms * dt * 1.2): estado_marcha = "BRAKE_STATION"
            elif v_kmh > v_cons_kmh + 1.5: estado_marcha = "BRAKE_OVERSPEED"
            elif estado_marcha == "BRAKE_OVERSPEED" and v_kmh <= v_cons_kmh: estado_marcha = "COAST"
            elif estado_marcha == "ACCEL" and v_kmh >= v_cons_kmh - 0.5: estado_marcha = "COAST"
            elif estado_marcha == "COAST" and v_kmh < v_cons_kmh - 2.0: estado_marcha = "ACCEL"
            elif estado_marcha not in ["ACCEL", "COAST", "BRAKE_STATION", "BRAKE_OVERSPEED"]: estado_marcha = "ACCEL"

            f_motor, f_regen_tramo, a_net_target = 0.0, 0.0, 0.0
            if estado_marcha == "BRAKE_STATION":
                f_req_freno = max(0.0, masa_kg * a_freno_op - f_davis - f_pend)
                f_regen_tramo = min(f_req_freno, f_disp_freno)
                a_net_target = max(-a_freno_op, (-f_regen_tramo - f_davis - f_pend) / masa_kg)
            elif estado_marcha == "BRAKE_OVERSPEED":
                f_req_freno = max(0.0, masa_kg * 0.4 - f_davis - f_pend)
                f_regen_tramo = min(f_req_freno, f_disp_freno)
                a_net_target = min((-f_regen_tramo - f_davis - f_pend) / masa_kg, -0.15)
            elif estado_marcha == "ACCEL":
                f_motor = f_disp_trac
                a_net_target = (f_motor - f_davis - f_pend) / masa_kg
            elif estado_marcha == "COAST":
                a_net_target = (-f_davis - f_pend) / masa_kg
                
            jerk_limit = 0.8 * dt
            if a_net_target > a_prev + jerk_limit: a_net = a_prev + jerk_limit
            elif a_net_target < a_prev - jerk_limit: a_net = a_prev - jerk_limit
            else: a_net = a_net_target
            a_prev = a_net
            
            v_new, dt_actual = v_ms + a_net * dt, dt
            if v_new < 0:
                dt_actual = v_ms / abs(a_net) if a_net < -0.001 else dt
                v_new = 0.0
                
            if f_motor > 0 and v_new * 3.6 > v_cons_kmh:
                v_new = v_cons_kmh / 3.6
                a_req = (v_new - v_ms) / dt_actual if dt_actual > 0 else 0
                f_motor = max(0.0, min(masa_kg * a_req + f_davis + f_pend, f_disp_trac))
                
            if v_new < 0.5 and dist_restante < 2.0: break
            if v_new < 0.1 and v_ms < 0.1: v_new, dt_actual = 1.0, dt

            step_m = (v_ms + v_new) / 2.0 * dt_actual
            if step_m > dist_restante:
                step_m = dist_restante
                if v_ms + v_new > 0: dt_actual = step_m / ((v_ms + v_new) / 2.0)
            if step_m < 0.1: step_m = 0.5 
                
            if f_motor > 0: 
                eta_din = f.get('eta_motor', 0.92) * (1.0 - 0.2 * (1.0 - max(0.1, f_motor / max(1.0, f_disp_trac)))**3)
                trc += ((f_motor * step_m) / 3_600_000.0) / eta_din
            if f_regen_tramo > 0 and v_kmh >= f['v_freno_min']: 
                reg += ((f_regen_tramo * step_m) / 3_600_000.0) * ETA_REGEN_NETA
                
            aux += (calcular_aux_dinamico(f['aux_kw'] * n_uni, (t_ini_mins + t_horas * 60.0) / 60.0, pax_mid, f.get('cap_max', 398) * n_uni, estacion_anio, estado_marcha) * (dt_actual / 3600.0))
            t_horas += dt_actual / 3600.0
            dist_recorrida += step_m
            v_ms = v_new

    dwell_h = (max(0, len(paradas_km) - 2) * 25.0) / 3600.0
    aux += calcular_aux_dinamico(f['aux_kw'] * (2 if doble else 1), (t_ini_mins + (t_horas + dwell_h / 2.0) * 60.0) / 60.0, pax_abordo, f.get('cap_max', 398) * (2 if doble else 1), estacion_anio, "DWELL") * dwell_h
    t_horas += dwell_h
    return trc, aux, reg, 0.0, max(0.0, trc + aux - reg), t_horas

def calcular_demanda_ser(e_pantografo_kwh, t_horas, km_punto, km_ser):
    if t_horas <= 0: return e_pantografo_kwh
    r_km = 0.0638 if km_punto < 2.25 else (0.0530 if km_punto < 6.80 else (0.0495 if km_punto < 10.92 else (0.0417 if km_punto < 21.41 else (0.0399 if km_punto < 30.36 else 0.0355))))
    P_loss_kW = (((abs(e_pantografo_kwh) / t_horas * 1000.0) / 3000.0)**2 * (r_km * abs(km_punto - km_ser))) / 1000.0
    return e_pantografo_kwh + (P_loss_kW * t_horas) if e_pantografo_kwh >= 0 else -max(0.0, abs(e_pantografo_kwh) - (P_loss_kW * t_horas))

def distribuir_energia_sers(e_pantografo, t_horas, km_ini, km_fin, active_sers):
    if not active_sers: return {}
    if len(active_sers) == 1: return {active_sers[0][1]: calcular_demanda_ser(e_pantografo, t_horas, (km_ini+km_fin)/2.0, active_sers[0][0])}
    sers_sorted = sorted(active_sers, key=lambda x: x[0])
    boundaries = [0.0] + [(sers_sorted[i][0] + sers_sorted[i+1][0]) / 2.0 for i in range(len(sers_sorted)-1)] + [KM_TOTAL]
    if abs(km_fin - km_ini) < 0.001:
        closest = min(active_sers, key=lambda x: abs(km_ini - x[0]))
        return {closest[1]: calcular_demanda_ser(e_pantografo, t_horas, km_ini, closest[0])}
    k_min, k_max = min(km_ini, km_fin), max(km_ini, km_fin)
    resultados = {s[1]: 0.0 for s in sers_sorted}
    for i, ser in enumerate(sers_sorted):
        o_min, o_max = max(k_min, boundaries[i]), min(k_max, boundaries[i+1])
        if o_max > o_min: resultados[ser[1]] += calcular_demanda_ser(e_pantografo * ((o_max - o_min) / abs(km_fin - km_ini)), t_horas * ((o_max - o_min) / abs(km_fin - km_ini)) if t_horas > 0 else 0.0, (o_min + o_max) / 2.0, ser[0])
    return resultados

def distribuir_potencia_sers_kw(p_kw, km_punto, active_sers):
    if not active_sers: return {}
    if len(active_sers) == 1: return {active_sers[0][1]: p_kw}
    sers_sorted = sorted(active_sers, key=lambda x: x[0])
    if km_punto <= sers_sorted[0][0]: return {sers_sorted[0][1]: p_kw}
    if km_punto >= sers_sorted[-1][0]: return {sers_sorted[-1][1]: p_kw}
    for i in range(len(sers_sorted)-1):
        if sers_sorted[i][0] <= km_punto <= sers_sorted[i+1][0]:
            return {sers_sorted[i][1]: p_kw * ((sers_sorted[i+1][0] - km_punto) / (sers_sorted[i+1][0] - sers_sorted[i][0])), sers_sorted[i+1][1]: p_kw * ((km_punto - sers_sorted[i][0]) / (sers_sorted[i+1][0] - sers_sorted[i][0]))}
    return {active_sers[0][1]: p_kw}

def calcular_flujo_ac_nodo(demands_kw):
    i_po = max(0.0, demands_kw.get('SER PO', 0.0)) * 1000 / (1.732 * V_NOMINAL_AC * 0.95)
    i_es = max(0.0, demands_kw.get('SER ES', 0.0)) * 1000 / (1.732 * V_NOMINAL_AC * 0.95)
    i_eb = max(0.0, demands_kw.get('SER EB', 0.0)) * 1000 / (1.732 * V_NOMINAL_AC * 0.95)
    i_va = max(0.0, demands_kw.get('SER VA', 0.0)) * 1000 / (1.732 * V_NOMINAL_AC * 0.95)
    dv_es = 1.732 * (i_po + i_es) * Z_EFF_44KV * abs(24.3 - 12.7)
    v_ac_es, v_ac_po = V_NOMINAL_AC - dv_es, V_NOMINAL_AC - dv_es - (1.732 * i_po * Z_EFF_44KV * abs(12.7 - 4.9))
    dv_eb = 1.732 * (i_eb + i_va) * Z_EFF_44KV * abs(25.5 - 24.3)
    v_ac_eb, v_ac_va = V_NOMINAL_AC - dv_eb, V_NOMINAL_AC - dv_eb - (1.732 * i_va * Z_EFF_44KV * abs(28.7 - 25.5))
    loss = (3 * ((i_po + i_es)**2) * R_AC_44KV * abs(24.3 - 12.7) / 1000.0) + (3 * (i_po**2) * R_AC_44KV * abs(12.7 - 4.9) / 1000.0) + (3 * ((i_eb + i_va)**2) * R_AC_44KV * abs(25.5 - 24.3) / 1000.0) + (3 * (i_va**2) * R_AC_44KV * abs(28.7 - 25.5) / 1000.0)
    return {'SER PO': {'Vac': v_ac_po, 'Vdc': 3000.0 * (v_ac_po / V_NOMINAL_AC)}, 'SER ES': {'Vac': v_ac_es, 'Vdc': 3000.0 * (v_ac_es / V_NOMINAL_AC)}, 'SER EB': {'Vac': v_ac_eb, 'Vdc': 3000.0 * (v_ac_eb / V_NOMINAL_AC)}, 'SER VA': {'Vac': v_ac_va, 'Vdc': 3000.0 * (v_ac_va / V_NOMINAL_AC)}, 'P_loss_kw': loss}

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
                result[idx] = 0.10
                continue
            hw = min(headways)
            if hw < 5.0: eta = 0.90
            elif hw < 10.0: eta = 0.75 - ((hw - 5.0) / 5.0) * 0.45
            else: eta = max(0.10, 0.30 - ((hw - 10.0) / 20.0) * 0.20)
            result[idx] = min(eta, 0.90)
    return result

@st.cache_data(show_spinner="Simulando malla eléctrica y receptividad...")
def precalcular_red_electrica_v111(df_dia, pct_trac, use_rm, estacion_anio="primavera"):
    regen_util_per_trip = {idx: 0.0 for idx in df_dia.index}
    braking_ticks_per_trip = {idx: 0.0 for idx in df_dia.index} 
    if df_dia.empty: return regen_util_per_trip
    t_min, t_max = int(df_dia['t_ini'].min()), int(df_dia['t_fin'].max())
    time_steps = np.arange(t_min, t_max + 1, 10.0 / 60.0)
    for via_ in [1, 2]:
        via_trains = df_dia[df_dia['Via'] == via_]
        if via_trains.empty: continue
        trains_data = []
        for idx, r in via_trains.iterrows():
            nodos = r.get('nodos')
            trains_data.append({
                'idx': idx, 't_ini': r['t_ini'], 't_fin': r['t_fin'], 'Via': r['Via'],
                'km_orig': r['km_orig'], 'km_dest': r['km_dest'], 'nodos': nodos,
                't_arr': [n[0] for n in nodos] if nodos and len(nodos) >= 2 else None,
                'tipo_tren': r.get('tipo_tren', 'XT-100'), 'doble': r.get('doble', False), 'pax_abordo': r.get('pax_abordo', 0)
            })
        braking_by_idx, accel_by_idx = [[] for _ in range(len(time_steps))], [[] for _ in range(len(time_steps))]
        for tr in trains_data:
            idx_start, idx_end = np.searchsorted(time_steps, max(t_min, tr['t_ini'])), np.searchsorted(time_steps, min(t_max, tr['t_fin']), side='right')
            f, n_uni = FLOTA.get(tr['tipo_tren'], FLOTA["XT-100"]), 2 if tr['doble'] else 1
            masa_kg = ((f['tara_t'] + f['m_iner_t']) * 1000 * n_uni) + (tr['pax_abordo'] * PAX_KG)
            eta_m = f.get('eta_motor', 0.92)
            for i in range(idx_start, idx_end):
                m = time_steps[i]
                state, v_kmh = get_train_state_and_speed(m, tr['Via'], use_rm, tr['km_orig'], tr['km_dest'], tr['nodos'], tr['t_arr'])
                pos = km_at_t(tr['t_ini'], tr['t_fin'], m, tr['Via'], use_rm, tr['km_orig'], tr['km_dest'], tr['nodos'], tr['t_arr'])
                v_ms = v_kmh / 3.6
                p_aux_kw = calcular_aux_dinamico(f['aux_kw'] * n_uni, m / 60.0, tr['pax_abordo'], f.get('cap_max', 398) * n_uni, estacion_anio, state)
                f_davis = ((f['davis_A'] * 2) + (f['davis_B'] * 2 * v_kmh) + (f['davis_C'] * 1.35 * (v_kmh**2))) if n_uni == 2 else (f['davis_A'] + f['davis_B']*v_kmh + f['davis_C']*(v_kmh**2))
                if state in ("BRAKE", "BRAKE_STATION", "BRAKE_OVERSPEED"):
                    f_req_freno = max(0.0, masa_kg * (f['a_freno_ms2'] * 0.9) - f_davis)
                    f_disp_freno = min(f['f_freno_max_kn']*1000*n_uni, (f.get('p_freno_max_kw', f['p_max_kw']*1.2)*1000*n_uni)/max(0.1, v_ms)) if v_kmh >= f['v_freno_min'] else 0.0
                    p_gen_kw = ((min(f_req_freno, f_disp_freno) * v_ms) / 1000.0 * ETA_REGEN_NETA) - p_aux_kw
                    if p_gen_kw > 0: braking_by_idx[i].append((tr['idx'], pos, p_gen_kw))
                    braking_ticks_per_trip[tr['idx']] += 1
                elif state in ("ACCEL", "CRUISE"):
                    p_dem_kw = p_aux_kw
                    if state == "ACCEL": 
                        p_dem_kw += (((min(f['f_trac_max_kn']*1000*n_uni*(pct_trac/100.0), (f['p_max_kw']*1000*n_uni*(pct_trac/100.0))/max(0.1, v_ms)) if v_ms > 0 else f['f_trac_max_kn']*1000*n_uni*(pct_trac/100.0)) * v_ms) / 1000.0 / eta_m)
                    elif state == "CRUISE" and f_davis > 0: 
                        p_dem_kw += (((f_davis * v_ms) / 1000.0) / eta_m)
                    accel_by_idx[i].append((tr['idx'], pos, p_dem_kw))
        for i in range(len(time_steps)):
            if not braking_by_idx[i] or not accel_by_idx[i]: continue
            current_demands = {a[0]: a[2] for a in accel_by_idx[i]}
            for b_idx, b_pos, p_gen in braking_by_idx[i]:
                available = [a for a in accel_by_idx[i] if current_demands[a[0]] > 0]
                if not available: break 
                a_idx, a_pos, _ = min(available, key=lambda x: abs(x[1] - b_pos))
                if abs(a_pos - b_pos) <= LAMBDA_REGEN_KM * 2:
                    p_transferred = min(p_gen * (ETA_MAX * np.exp(-abs(a_pos - b_pos) / LAMBDA_REGEN_KM)), current_demands[a_idx])
                    current_demands[a_idx] -= p_transferred
                    regen_util_per_trip[b_idx] += (p_transferred / p_gen)
    for idx in df_dia.index: 
        regen_util_per_trip[idx] = min(1.0, regen_util_per_trip[idx] / braking_ticks_per_trip[idx]) if braking_ticks_per_trip[idx] > 0 else 0.0
    return regen_util_per_trip

@st.cache_data(show_spinner="Integrando Termodinámica de Flota...")
def calcular_termodinamica_flota_v111(df_dia, pct_trac, use_pend, use_rm, use_regen, dict_regen, estacion_anio="primavera"):
    df_e = df_dia.copy()
    if df_e.empty: return df_e
    def _wrapper_energia(r):
        trc, aux, reg_panto_max, _, _, t_h = simular_tramo_termodinamico(
            r['tipo_tren'], r.get('doble', False), r['km_orig'], r['km_dest'], r['Via'], 
            pct_trac, use_rm, use_pend, r.get('nodos'), r.get('pax_d', {}), r.get('pax_abordo', 0), 
            None, r.get('maniobra'), estacion_anio, r.get('t_ini', 0.0)
        )
        reg_util = reg_panto_max * dict_regen.get(r.name, 1.0) if use_regen else 0.0
        return pd.Series([trc, aux, reg_util, max(0.0, reg_panto_max - reg_util), max(0.0, trc + aux - reg_util)])
    df_e[['kwh_viaje_trac', 'kwh_viaje_aux', 'kwh_viaje_regen', 'kwh_reostato', 'kwh_viaje_neto']] = df_e.apply(_wrapper_energia, axis=1)
    return df_e

def procesar_thdr(data, fname, via_param=1):
    try:
        ext = fname.lower()
        if ext.endswith('.csv'):
            try: raw = pd.read_csv(BytesIO(data), header=None, sep=',', encoding='utf-8', dtype=str)
            except: raw = pd.read_csv(BytesIO(data), header=None, sep=';', encoding='latin-1', dtype=str)
        else:
            eng = "xlrd" if ext.endswith(".xls") else "openpyxl"
            raw = pd.read_excel(BytesIO(data), header=None, engine=eng, dtype=str)

        if raw is None or raw.empty: return pd.DataFrame(), f"Archivo vacío o ilegible: {fname}"
        if raw.shape[0] < 6: return pd.DataFrame(), f"Archivo muy corto: {fname}"
        
        fecha_str = extraer_fecha_segura(raw, fname)
        
        header_idx = 1
        for i in range(min(15, len(raw))):
            row_vals = [str(x).upper() for x in raw.iloc[i].values if pd.notna(x)]
            row_str = ' '.join(row_vals)
            if ('VIAJE' in row_str or 'N°' in row_str or 'NRO' in row_str) and ('TREN' in row_str or 'MOTRIZ' in row_str or 'SFE' in row_str or 'SERVICIO' in row_str) and ('SALIDA' in row_str or 'HORA' in row_str or 'PARTIDA' in row_str):
                header_idx = i
                break
                
        r0 = raw.iloc[header_idx - 1].copy() if header_idx > 0 else raw.iloc[0].copy()
        r0.iloc[0] = np.nan 
        h1 = r0.ffill().astype(str)
        h2 = raw.iloc[header_idx].fillna('').astype(str)
        
        cols = []
        for s, t in zip(h1, h2):
            s_val, t_val = str(s).strip(), str(t).strip()
            if s_val.lower() == 'nan' or not s_val: cols.append(t_val)
            elif t_val: cols.append(f"{s_val}_{t_val}")
            else: cols.append(s_val)
            
        df = raw.iloc[header_idx + 1:].copy().reset_index(drop=True)
        n = len(df.columns)
        if len(cols) >= n: df.columns = cols[:n]
        else: df.columns = cols + [f"_C{j}" for j in range(n - len(cols))]
            
        df = make_unique(df).dropna(how='all').reset_index(drop=True)
        if df.empty: return pd.DataFrame(), f"Sin filas tras limpiar: {fname}"

        for col in df.columns:
            if any(k in str(col).upper() for k in ['LLEGADA','SALIDA','HORA']):
                try: df[f"{col}_min"] = df[col].apply(parse_time_to_mins)
                except: pass

        est_cols = {c: _col_to_est_idx(c) for c in df.columns if '_min' in str(c).lower() and 'program' not in str(c).lower()}

        def _safe_get(r, col):
            try: return r.get(col, np.nan)
            except: return np.nan

        df['t_ini'] = df.apply(lambda row: min([_safe_get(row, c) for c in est_cols.keys() if pd.notna(_safe_get(row, c))] or [np.nan]), axis=1)
        df['t_fin'] = df.apply(lambda row: max([_safe_get(row, c) for c in est_cols.keys() if pd.notna(_safe_get(row, c))] or [np.nan]), axis=1)

        c_m1 = next((c for c in df.columns if 'motriz' in str(c).lower() and '1' in str(c).lower()), None)
        c_m2 = next((c for c in df.columns if 'motriz' in str(c).lower() and '2' in str(c).lower()), None)
        tren_col = next((c for c in df.columns if str(c).strip().upper() == 'TREN' or str(c).strip().upper() == 'SERVICIO'), None)

        def _get_fleet_info(r):
            def extract_n(col_name):
                if col_name and pd.notna(r.get(col_name)):
                    val = str(r.get(col_name)).strip()
                    if val.lower() not in ('nan', '', '0', '0.0'):
                        m = re.search(r'(\d+)', val)
                        if m: return int(m.group(1))
                return None
            
            n1 = extract_n(c_m1)
            n2 = extract_n(c_m2)
            tipo = "XT-100"
            motriz_str = ""
            n_eval = None
            
            if (n1 is not None and n1 != 0) and (n2 is not None and n2 != 0): 
                motriz_str = f"{n1}+{n2}"
                n_eval = n1
            elif (n1 is not None and n1 != 0): 
                motriz_str = f"{n1}"
                n_eval = n1
            elif (n2 is not None and n2 != 0): 
                motriz_str = f"{n2}"
                n_eval = n2
            else:
                n_tren = extract_n(tren_col)
                if n_tren is not None and n_tren != 0: 
                    motriz_str = f"{n_tren}"
                    n_eval = n_tren
            
            if n_eval is not None:
                if 1 <= n_eval <= 27: tipo = "XT-100"
                elif 28 <= n_eval <= 35: tipo = "XT-M"
                elif n_eval >= 36: tipo = "SFE" 
                else: tipo = "XT-100" 
            return pd.Series([motriz_str, tipo])
            
        df[['motriz_num', 'tipo_tren']] = df.apply(_get_fleet_info, axis=1)

        if 'Unidad' in df.columns: df['Unidad'] = df['Unidad'].fillna('S').replace('nan','S').replace('','S')
        else: df['Unidad'] = df[c_m2].apply(lambda x: 'M' if pd.notna(x) and str(x).strip() not in ('0','0.0','','nan') else 'S') if c_m2 else 'S'
            
        df['doble'] = df['Unidad'].astype(str).str.strip() == 'M'
        df['Via'] = via_param
        df['Fecha_str'] = fecha_str

        def _get_real_orig_dest(row):
            valid_est = []
            for col, e_idx in est_cols.items():
                val = _safe_get(row, col)
                if pd.notna(val) and val > 0:
                    valid_est.append(e_idx)
            if not valid_est:
                return pd.Series([0.0 if via_param == 1 else KM_TOTAL, KM_TOTAL if via_param == 1 else 0.0])
            
            if via_param == 1:
                return pd.Series([KM_ACUM[min(valid_est)], KM_ACUM[max(valid_est)]])
            else:
                return pd.Series([KM_ACUM[max(valid_est)], KM_ACUM[min(valid_est)]])

        df[['km_orig', 'km_dest']] = df.apply(_get_real_orig_dest, axis=1)
        df = df.dropna(subset=['t_ini'])
        
        df['km_viaje'] = abs(df['km_dest'] - df['km_orig'])
        df['svc_type'] = df.apply(lambda r: svc_label(r['km_orig'], r['km_dest']), axis=1)

        def calc_dwell_dynamic(row):
            try:
                idx_orig = int(np.argmin([abs(row['km_orig'] - k) for k in KM_ACUM]))
                idx_dest = int(np.argmin([abs(row['km_dest'] - k) for k in KM_ACUM]))
                n_stops = max(0, abs(idx_dest - idx_orig) - 1)
                return round(n_stops * (8.0 / 19.0), 3)
            except: return 8.0 
                
        df['dwell_min'] = df.apply(calc_dwell_dynamic, axis=1)
        df['dwell_cabecera_min'] = 0.0
        
        def _extract_nodos(row):
            nodos_temp = []
            for col, e_idx in est_cols.items():
                val = _safe_get(row, col)
                if pd.notna(val) and val > 0:
                    nodos_temp.append((val, KM_ACUM[e_idx]))
            
            nodos_validos = [n for n in nodos_temp if pd.notna(n[0])]
            nodos_validos.sort(key=lambda x: (x[1], x[0]))
            unique_nodos = []
            seen_km = set()
            for t, km in nodos_validos:
                if km not in seen_km:
                    unique_nodos.append((t, km))
                    seen_km.add(km)
                    
            unique_nodos.sort(key=lambda x: x[0])
            return unique_nodos if len(unique_nodos) > 1 else None
            
        df['nodos'] = df.apply(_extract_nodos, axis=1)

        viaje_col_idx = None
        for r in range(min(15, raw.shape[0])):
            for c in range(raw.shape[1]):
                val_raw = str(raw.iloc[r, c]).strip().upper()
                val_norm = unicodedata.normalize('NFD', val_raw).encode('ascii', 'ignore').decode()
                if ('VIAJE' in val_norm or 'N°' in val_norm or 'NRO' in val_norm) and 'TIEMPO' not in val_norm and 'MIN' not in val_norm and viaje_col_idx is None:
                    viaje_col_idx = c
                    break
                    
        if viaje_col_idx is not None and viaje_col_idx < len(df.columns):
            col_name_v = df.columns[viaje_col_idx]
            df['nro_viaje'] = df[col_name_v].apply(clean_primary_key)
        else: df['nro_viaje'] = ''

        serv_col = next((c for c in df.columns if 'servicio' in str(c).lower()), None)
        if serv_col: df['num_servicio'] = df[serv_col].apply(clean_primary_key)
        elif 'nro_viaje' in df.columns: df['num_servicio'] = df['nro_viaje']
        else: df['num_servicio'] = ''

        df['_id'] = df['Fecha_str'] + "_" + df['num_servicio'] + "_" + df['t_ini'].astype(str)
        df['t_fin'] = df['t_fin'].fillna(df['t_ini'] + df['km_viaje'] / 35.0 * 60.0)
        return df, "ok"
    except Exception as e: return pd.DataFrame(), str(e)

def calcular_dwell(df1, df2):
    if df1.empty or df2.empty: return df1, df2
    if 'num_servicio' not in df1.columns or 'num_servicio' not in df2.columns: return df1, df2
    for fecha in df1['Fecha_str'].unique():
        d1 = df1[df1['Fecha_str']==fecha]
        d2 = df2[df2['Fecha_str']==fecha]
        if d2.empty: continue
        for idx1, r1 in d1.iterrows():
            s = r1.get('num_servicio')
            if pd.isna(s) or s == '': continue
            m = d2[(d2['num_servicio']==s) & (d2['t_ini']>r1['t_fin'])]
            if not m.empty:
                dw = m['t_ini'].min()-r1['t_fin']
                if 0<dw<60: df2.at[m['t_ini'].idxmin(),'dwell_cabecera_min']=round(dw,1)
        for idx2, r2 in d2.iterrows():
            s = r2.get('num_servicio')
            if pd.isna(s) or s == '': continue
            m = d1[(d1['num_servicio']==s) & (d1['t_ini']>r2['t_fin'])]
            if not m.empty:
                dw = m['t_ini'].min()-r2['t_fin']
                if 0<dw<60: df1.at[m['t_ini'].idxmin(),'dwell_cabecera_min']=round(dw,1)
    return df1, df2

def cargar_pax(data, fname, via_param=1):
    try:
        ext = fname.lower()
        if ext.endswith('.csv'):
            try: full = pd.read_csv(BytesIO(data), header=None, sep=',', encoding='utf-8', dtype=str)
            except: full = pd.read_csv(BytesIO(data), header=None, sep=';', encoding='latin-1', dtype=str)
        else: 
            eng = "xlrd" if ext.endswith(".xls") else "openpyxl"
            full = pd.read_excel(BytesIO(data), header=None, engine=eng, dtype=str)

        if full is None or full.empty or len(full) <= 10: return pd.DataFrame()

        header_idx = 9
        EXACT_MAP = {'PUE':'PUE','PUERTO':'PUE','PU':'PUE','BEL':'BEL','BELLAVISTA':'BEL','BE':'BEL','FRA':'FRA','FRANCIA':'FRA','FR':'FRA','BAR':'BAR','BARON':'BAR','BA':'BAR','POR':'POR','PORTALES':'POR','PO':'POR','REC':'REC','RECREO':'REC','RE':'REC','MIR':'MIR','MIRAMAR':'MIR','MI':'MIR','VIN':'VIN','VINA DEL MAR':'VIN','VIÑA DEL MAR':'VIN','VM':'VIN','HOS':'HOS','HOSPITAL':'HOS','HO':'HOS','CHO':'CHO','CHORRILLOS':'CHO','CH':'CHO','SLT':'SLT','SALTO':'SLT','EL SALTO':'SLT','ES':'SLT','ELS':'SLT','VAL':'VAL','VALENCIA':'VAL','QUI':'QUI','QUILPUE':'QUI','QUILPUÉ':'QUI','QU':'QUI','SOL':'SOL','EL SOL':'SOL','SO':'SOL','ESO':'SOL','BTO':'BTO','EL BELLOTO':'BTO','BELLOTO':'BTO','EB':'BTO','ELB':'BTO','AME':'AME','LAS AMERICAS':'AME','AMERICAS':'AME','LAS':'AME','LAM':'AME','AM':'AME','CON':'CON','LA CONCEPCION':'CON','CONCEPCION':'CON','LAC':'CON','LCO':'CON','CO':'CON','VAM':'VAM','VILLA ALEMANA':'VAM','ALEMANA':'VAM','VIL':'VAM','VALE':'VAM','VL':'VAM','SGA':'SGA','SARGENTO ALDEA':'SGA','ALDEA':'SGA','SAR':'SGA','SA':'SGA','PEN':'PEN','PENABLANCA':'PEN','PEÑABLANCA':'PEN','PENA BLANCA':'PEN','PENA':'PEN','PE':'PEN','LIM':'LIM','LIMACHE':'LIM','LI':'LIM'}
        col_mapping = {}
        keys_sorted = sorted(EXACT_MAP.keys(), key=len, reverse=True)
        
        for c_idx in range(full.shape[1]):
            vals = [str(full.iloc[r, c_idx]).strip().upper() for r in range(max(0, header_idx-4), header_idx+1)]
            combo = " ".join(vals)
            combo_norm = unicodedata.normalize('NFD', combo).encode('ascii', 'ignore').decode().replace('.', '').replace(':', '')

            mapped = False
            for k in keys_sorted:
                if k == vals[-1] or k == vals[-2] or f" {k} " in f" {combo_norm} " or f"_{k}_" in f"_{combo_norm}_":
                    col_mapping[col_mapping.get(c_idx, '')] = EXACT_MAP[k] 
                    col_mapping[c_idx] = EXACT_MAP[k]
                    mapped = True
                    break
            
            if mapped: continue
            if 'HORA' in combo_norm and 'ORIG' in combo_norm: col_mapping[c_idx] = 'Hora Origen'
            elif 'THDR' in combo_norm and 'TREN' not in combo_norm: col_mapping[c_idx] = 'Nro_THDR_raw'
            elif 'TREN' in combo_norm or 'SERVICIO' in combo_norm: col_mapping[c_idx] = 'Tren'
            elif 'CargaMax' not in col_mapping.values():
                if any(w in combo_norm for w in ['TOTAL', 'BORDO', 'CARGA', 'PASAJERO']) and not any(exc in combo_norm for exc in ['THDR', 'TREN', 'HORA', 'VIA']):
                    col_mapping[c_idx] = 'CargaMax'

        data_rows = full.iloc[header_idx + 1:].copy()
        df = pd.DataFrame()
        for c_idx, col_name in col_mapping.items():
            if isinstance(c_idx, int) and c_idx < full.shape[1]: 
                df[col_name] = data_rows.iloc[:, c_idx].values
                
        fecha_global = extraer_fecha_segura(full, fname)
        if full.shape[1] > 3:
            df['Fecha_Excel_Raw'] = data_rows.iloc[:, 3].values
            df['Fecha_s'] = df['Fecha_Excel_Raw'].apply(parse_excel_date).fillna(fecha_global).replace('', fecha_global).ffill()
        else:
            df['Fecha_s'] = fecha_global
                
        for col in ['Hora Origen', 'Nro_THDR_raw', 'Tren']:
            if col not in df.columns: df[col] = ''
        if 'CargaMax' not in df.columns: df['CargaMax'] = '0'
        for c in PAX_COLS:
            if c not in df.columns: df[c] = '0'

        df['Nro_THDR'] = df['Nro_THDR_raw'].apply(clean_primary_key)
        df['Tren_Clean'] = df['Tren'].apply(clean_id)
        df['t_ini_p'] = df['Hora Origen'].apply(parse_time_to_mins)
        df['Via'] = via_param
        df = df.dropna(subset=['t_ini_p'])
        if df.empty: return pd.DataFrame()
        for c in PAX_COLS + ['CargaMax']: df[c] = df[c].apply(clean_pax_number)
        return df
    except Exception as e: return pd.DataFrame()

def match_pax(row, df_pax):
    EMPTY = ({c: 0 for c in PAX_COLS}, 0, '--:--:--', 'No Detectado', -1)
    if df_pax.empty: return EMPTY
    def _to_int(v):
        try: return int(float(v)) if pd.notna(v) else 0
        except: return 0
        
    t_i = row.get('t_ini')
    via = row.get('via_op', row.get('Via', 1))
    nro_viaje = clean_primary_key(row.get('nro_viaje', ''))
    thdr_date = row.get('Fecha_str')
    
    sub = df_pax[df_pax['Via'] == via].copy()
    if sub.empty: return EMPTY
    
    if 'Fecha_s' in sub.columns and thdr_date and thdr_date != '2026-01-01':
        sub_date = sub[sub['Fecha_s'] == thdr_date]
        if not sub_date.empty: 
            sub = sub_date
        else: 
            return EMPTY 

    sub['diff'] = sub['t_ini_p'].apply(lambda x: min(abs(float(x) - float(t_i)), 1440 - abs(float(x) - float(t_i))) if pd.notna(x) and pd.notna(t_i) else 9999)
    if nro_viaje != '' and 'Nro_THDR' in sub.columns:
        sub['Nro_THDR_cmp'] = sub['Nro_THDR'].apply(clean_primary_key)
        match_exacto = sub[(sub['Nro_THDR_cmp'] == nro_viaje) & (sub['Nro_THDR_cmp'] != '')]
        if not match_exacto.empty:
            best = match_exacto.iloc[0]
            return {c: _to_int(best.get(c, 0)) for c in PAX_COLS}, _to_int(best.get('CargaMax', 0)), mins_to_time_str(best.get('t_ini_p')), str(best.get('Nro_THDR', '')), best.name

    if pd.notna(t_i):
        best_match = sub.loc[sub['diff'].idxmin()]
        if best_match['diff'] <= 15: 
            return {c: _to_int(best_match.get(c, 0)) for c in PAX_COLS}, _to_int(best_match.get('CargaMax', 0)), mins_to_time_str(best_match.get('t_ini_p')), str(best.get('Nro_THDR', '')), best_match.name

    return EMPTY

def parsear_planilla_maestra(data, fname):
    try:
        ext = fname.lower()
        dfs = {}
        if ext.endswith('.csv'):
            try: raw = pd.read_csv(BytesIO(data), header=None, sep=',', encoding='utf-8', dtype=str)
            except: raw = pd.read_csv(BytesIO(data), header=None, sep=';', encoding='latin-1', dtype=str)
            dfs["CSV"] = raw
        else:
            eng = "xlrd" if ext.endswith(".xls") else "openpyxl"
            dfs = pd.read_excel(BytesIO(data), header=None, engine=eng, dtype=str, sheet_name=None)
            
        viajes = []
        for sheet_name, df in dfs.items():
            if not ext.endswith('.csv'):
                sheet_upper = str(sheet_name).upper()
                if not any(k in sheet_upper for k in ['V1', 'VIA 1', 'VÍA 1', 'V2', 'VIA 2', 'VÍA 2']):
                    continue
                    
            header_idx = -1
            for i in range(min(20, len(df))):
                row_str = ' '.join(df.iloc[i].fillna('').astype(str).str.upper())
                if ('VIAJE' in row_str or 'N°' in row_str or 'N ' in row_str) and ('SERVICIO' in row_str or 'TREN' in row_str) and ('HR PARTIDA' in row_str or 'HORA' in row_str or 'PARTIDA' in row_str or 'SALIDA' in row_str):
                    header_idx = i
                    break
                    
            if header_idx != -1:
                headers = df.iloc[header_idx].fillna('').astype(str).str.upper()
                viaje_cols = [c for c, val in enumerate(headers) if 'VIAJE' in val or val == 'N°' or val == 'N']
                srv_cols = [c for c, val in enumerate(headers) if 'SERV' in val or 'TREN' in val]
                hora_cols = [c for c, val in enumerate(headers) if 'HR PARTIDA' in val or 'HORA' in val or 'PARTIDA' in val or 'SALIDA' in val]
                config_cols = [c for c, val in enumerate(headers) if 'CONF' in val or 'TIPO' in val or 'FORMA' in val or 'UNIDAD' in val or 'OBS' in val]

                pairs = []
                for vc in viaje_cols:
                    sc_cands = [sc for sc in srv_cols if sc > vc and sc - vc <= 2]
                    if sc_cands:
                        sc = sc_cands[0]
                        hc_cands = [hc for hc in hora_cols if hc > sc and hc - sc <= 3]
                        if hc_cands:
                            hc = hc_cands[0]
                            cc_cands = [cc for cc in config_cols if cc > sc and cc - sc <= 6]
                            pairs.append((vc, sc, hc, cc_cands[0] if cc_cands else None))

                for i in range(header_idx + 1, len(df)):
                    row = df.iloc[i]
                    if len(row) <= max(c_viaje, c_srv, c_hora): continue
                    hora_str = str(row[c_hora]).strip()
                    srv_str = str(row[c_srv]).strip()
                    viaje_str = str(row[c_viaje]).strip()
                    config_str = str(row[c_unidad]).strip().upper() if len(row) > c_unidad else ''

                    m_viaje = re.search(r'(\d+)', viaje_str)
                    m_srv = re.search(r'(\d+)', srv_str)
                    if not m_viaje or not m_srv or not re.match(r'^\d{1,2}:\d{2}(:\d{2})?$', hora_str): continue
                    
                    viaje_num = int(m_viaje.group(1))
                    servicio_num = int(m_srv.group(1))
                    t_ini = parse_time_to_mins(hora_str)
                    if t_ini is None: continue

                    es_doble = False
                    if 'MÚLT' in config_str or 'MULT' in config_str or 'DOB' in config_str or '2' in config_str:
                        es_doble = True

                    via = 1 if viaje_num % 2 == 0 else 2
                    if via == 1:
                        km_orig = KM_ACUM[0] 
                        if servicio_num >= 600: km_dest = KM_ACUM[20] 
                        elif 400 <= servicio_num <= 599: km_dest = KM_ACUM[18] 
                        elif 200 <= servicio_num <= 399: km_dest = KM_ACUM[14] 
                        else: km_dest = KM_ACUM[20] 
                    else:
                        km_dest = KM_ACUM[0] 
                        if servicio_num >= 600: km_orig = KM_ACUM[20] 
                        elif 400 <= servicio_num <= 599: km_orig = KM_ACUM[18] 
                        elif 200 <= servicio_num <= 399: km_orig = KM_ACUM[14] 
                        else: km_orig = KM_ACUM[20] 
                        
                    ruta = f"{EC[KM_ACUM.index(km_orig)]}-{EC[KM_ACUM.index(km_dest)]}"
                    nodos_via = [(0.0, k) for k in (KM_ACUM[KM_ACUM.index(km_orig):KM_ACUM.index(km_dest)+1] if via==1 else KM_ACUM[KM_ACUM.index(km_dest):KM_ACUM.index(km_orig)+1][::-1])]
                    
                    viajes.append({
                        '_id': f"PLAN_{servicio_num}_{int(t_ini)}", 't_ini': t_ini, 'Via': via,
                        'km_orig': km_orig, 'km_dest': km_dest, 'nodos': nodos_via,
                        'tipo_tren': 'XT-100', 'doble': es_doble, 'num_servicio': str(servicio_num), 'svc_type': ruta,
                        'maniobra': None
                    })
            else:
                for i in range(len(df)):
                    row_vals = df.iloc[i].fillna('').astype(str).tolist()
                    if len(row_vals) <= 2: continue
                    for c_idx, val in enumerate(row_vals):
                        val = val.strip()
                        if re.match(r'^\d{1,2}:\d{2}(:\d{2})?$', val):
                            t_ini = parse_time_to_mins(val)
                            if t_ini is None: continue
                            
                            servicio_num, sc_idx = None, -1
                            for offset in range(1, 5):
                                if c_idx - offset >= 0:
                                    check_val = row_vals[c_idx - offset].strip()
                                    if check_val.isdigit() and 200 <= int(check_val) <= 1999:
                                        servicio_num = int(check_val)
                                        sc_idx = c_idx - offset
                                        break
                            
                            viaje_num = None
                            if sc_idx != -1:
                                for offset in range(1, 3):
                                    if sc_idx - offset >= 0:
                                        check_val = row_vals[sc_idx - offset].strip()
                                        if check_val.isdigit() and 1 <= int(check_val) <= 300:
                                            viaje_num = int(check_val)
                                            break
                                        
                            if servicio_num is None: continue

                            es_doble = False
                            for offset_unidad in range(1, 3):
                                if c_idx + offset_unidad < len(row_vals):
                                    val_unidad = row_vals[c_idx + offset_unidad].strip().upper()
                                    if 'MÚLT' in val_unidad or 'MULT' in val_unidad or 'DOB' in val_unidad or '2' in val_unidad:
                                        es_doble = True
                                        break

                            if viaje_num is None:
                                sheet_upper = str(sheet_name).upper()
                                if 'V1' in sheet_upper or 'VIA 1' in sheet_upper: via = 1
                                elif 'V2' in sheet_upper or 'VIA 2' in sheet_upper: via = 2
                                else: via = 1 if servicio_num % 2 == 0 else 2
                            else: via = 1 if viaje_num % 2 == 0 else 2
                            
                            if via == 1:
                                km_orig = KM_ACUM[0] 
                                if servicio_num >= 600: km_dest = KM_ACUM[20] 
                                elif 400 <= servicio_num <= 599: km_dest = KM_ACUM[18] 
                                elif 200 <= servicio_num <= 399: km_dest = KM_ACUM[14] 
                                else: km_dest = KM_ACUM[14] 
                            else:
                                km_dest = KM_ACUM[0] 
                                if servicio_num >= 600: km_orig = KM_ACUM[20] 
                                elif 400 <= servicio_num <= 599: km_orig = KM_ACUM[18] 
                                elif 200 <= servicio_num <= 399: km_orig = KM_ACUM[14] 
                                else: km_orig = KM_ACUM[14] 
                                
                            ruta = f"{EC[KM_ACUM.index(km_orig)]}-{EC[KM_ACUM.index(km_dest)]}"
                            nodos_via = [(0.0, k) for k in (KM_ACUM[KM_ACUM.index(km_orig):KM_ACUM.index(km_dest)+1] if via==1 else KM_ACUM[KM_ACUM.index(km_dest):KM_ACUM.index(km_orig)+1][::-1])]
                            viajes.append({'_id': f"PLAN_{servicio_num}_{int(t_ini)}", 't_ini': t_ini, 'Via': via, 'km_orig': km_orig, 'km_dest': km_dest, 'nodos': nodos_via, 'tipo_tren': 'XT-100', 'doble': es_doble, 'num_servicio': str(servicio_num), 'svc_type': ruta, 'maniobra': None})
                            
        df_viajes = pd.DataFrame(viajes)
        if not df_viajes.empty: df_viajes = df_viajes.drop_duplicates(subset=['_id'])
        return df_viajes, "ok"
    except Exception as e: return pd.DataFrame(), str(e)

# =============================================================================
# 12. DRAW DIAGRAM Y DASHBOARDS UI
# =============================================================================

def draw_diagram(df_act_plot, ser_accum_plot, seat_accum_plot, hora_str, titulo_extra="", active_sers_list=SER_DATA, gap_vias=200):
    W = 1200
    KM_SCALE = W / KM_TOTAL
    def xkm(km): return km * KM_SCALE

    Y_V2 = 260
    Y_V1 = Y_V2 - gap_vias
    MARGIN = 90
    Y_44KV = Y_V2 + 90
    Y_SER = Y_V2 + 40
    y_min = Y_V1 - MARGIN
    y_max = Y_V2 + 150
    H = max(320, y_max - y_min)
    y_mid = (Y_V1 + Y_V2) / 2

    fig = go.Figure()
    fig.update_layout(
        height=H, margin=dict(l=10, r=10, t=45, b=10),
        xaxis=dict(range=[0, W], showgrid=False, zeroline=False, showticklabels=False, fixedrange=True),
        yaxis=dict(range=[y_min, y_max], showgrid=False, zeroline=False, showticklabels=False, fixedrange=True),
        plot_bgcolor='white', paper_bgcolor='white',
        font=dict(color='black'), showlegend=False, hovermode='closest',
        title=dict(text=f"MERVAL - {hora_str} {titulo_extra}  |  🔴 V2 LI→PU   🔵 V1 PU→LI", font=dict(size=12, color='black'), x=0.5)
    )

    fig.add_shape(type='line', x0=0, x1=W, y0=Y_V2, y1=Y_V2, line=dict(color='#c62828', width=5))
    fig.add_shape(type='line', x0=0, x1=W, y0=Y_V1, y1=Y_V1, line=dict(color='#1565c0', width=5))
    fig.add_shape(type='line', x0=0, x1=W, y0=Y_44KV, y1=Y_44KV, line=dict(color='#FBC02D', width=3, dash='dash'))
    fig.add_annotation(x=W/2, y=Y_44KV+10, text="<b>Línea AC 44kV</b>", showarrow=False, font=dict(size=10, color='#FBC02D'))

    for i, (ec, km) in enumerate(zip(EC, KM_ACUM[:N_EST])):
        xp = xkm(km)
        fig.add_shape(type='line', x0=xp, x1=xp, y0=Y_V1-20, y1=Y_V2+20, line=dict(color='#bbb', width=1, dash='dot'))
        fig.add_annotation(x=xp, y=y_mid + (12 if i % 2 == 0 else -12), text=ec, showarrow=False, font=dict(size=8, color='#555'), xanchor='center', yanchor='middle')

    seat_x = xkm(SEAT_KM)
    fig.add_trace(go.Scatter(
        x=[seat_x], y=[Y_44KV + 30], mode='markers+text',
        marker=dict(symbol='triangle-up', size=22, color='#FBC02D', line=dict(color='black', width=2)),
        text=f"<b>⚡ SEAT EL SOL<br>{seat_accum_plot:,.0f} kWh</b>", textposition="top center",
        textfont=dict(size=10, color='black'), showlegend=False, hoverinfo='skip'
    ))
    fig.add_shape(type='line', x0=seat_x, x1=seat_x, y0=Y_44KV+30, y1=Y_44KV, line=dict(color='#FBC02D', width=4))

    for skm, nombre_ser in SER_DATA:
        xp = xkm(skm)
        is_active = nombre_ser in [s[1] for s in active_sers_list]
        val = ser_accum_plot.get(nombre_ser, 0.0)
        
        if is_active:
            color, fill, dash_st, txt_color = '#FBC02D', '#FFF3E0', 'dot', '#E65100'
            fig.add_shape(type='line', x0=xp, x1=xp, y0=Y_SER-15, y1=Y_V1, line=dict(color='#E65100', width=2))
            lbl = f"<b>{nombre_ser}</b><br><span style='font-size:8px'>{val:,.0f} kWh</span>"
        else:
            color, fill, dash_st, txt_color = '#9E9E9E', '#F5F5F5', 'dash', '#757575'
            fig.add_annotation(x=xp, y=Y_SER-25, text="❌ FALLA", showarrow=False, font=dict(size=10, color='red'))
            lbl = f"<b>{nombre_ser}</b><br><span style='font-size:8px'>OFF</span>"

        fig.add_shape(type='line', x0=xp, x1=xp, y0=Y_44KV, y1=Y_SER+15, line=dict(color=color, width=2, dash=dash_st))
        fig.add_shape(type='rect', x0=xp-30, x1=xp+30, y0=Y_SER-15, y1=Y_SER+15, line=dict(color=color, width=2), fillcolor=fill)
        fig.add_annotation(x=xp, y=Y_SER, text=lbl, showarrow=False, font=dict(size=9, color=txt_color), align='center')

    if df_act_plot.empty: return fig

    COLL_PX = 100
    label_side = {}
    for via_ in [1, 2]:
        sub = df_act_plot[df_act_plot['Via'] == via_].copy()
        if sub.empty: continue
        sub_sorted = sub.sort_values('km_pos')
        indices = list(sub_sorted.index)
        for i, idx in enumerate(indices):
            xp_i = xkm(sub_sorted.loc[idx, 'km_pos'])
            close = False
            if i > 0 and abs(xp_i - xkm(sub_sorted.loc[indices[i-1], 'km_pos'])) < COLL_PX: close = True
            if i < len(indices) - 1 and abs(xp_i - xkm(sub_sorted.loc[indices[i+1], 'km_pos'])) < COLL_PX: close = True
            label_side[idx] = ('up' if i % 2 == 0 else 'down') if close else 'up'

    for idx, row in df_act_plot.iterrows():
        via, xp, y_ln, color = row['Via'], xkm(row['km_pos']), Y_V2 if row['Via'] == 2 else Y_V1, '#c62828' if row['Via'] == 2 else '#1565c0'
        
        doble_tramo = row.get('doble', False)
        man = row.get('maniobra')
        if man in ['CORTE_BTO', 'CORTE_PU_SA_BTO']: doble_tramo = True if row['km_pos'] <= KM_ACUM[14] else False
        elif man == 'ACOPLE_BTO': doble_tramo = False if row['km_pos'] > KM_ACUM[14] else True
        elif man == 'CORTE_SA': doble_tramo = True if row['km_pos'] <= KM_ACUM[18] else False
        elif man == 'ACOPLE_SA': doble_tramo = False if row['km_pos'] > KM_ACUM[18] else True
            
        r_c = 18 if doble_tramo else 11
        serv, motriz, tipo = str(row.get('num_servicio', '')), str(row.get('motriz_num', '')), str(row.get('tipo_tren', 'XT-100'))
        
        if tipo == 'SFE': xt_lbl = f"SFE [U-{motriz}]" if motriz else "SFE"
        elif tipo == 'XT-M': xt_lbl = f"Modular [U-{motriz}]" if motriz else "Modular"
        else: xt_lbl = f"X'Trapolis 100 [U-{motriz}]" if motriz else "X'Trapolis 100"

        kwh_n, pax_v = float(row.get('kwh_neto', 0)), int(row.get('pax_inst', 0)) 
        sep_r = row.get('sep_next', '—')
        sep_s = f"↔ {sep_r} min" if sep_r != '—' else ''

        side = label_side.get(idx, 'up')
        dy_mot, dy_svc, dy_sep = +(r_c + 18) if side == 'up' else -(r_c + 18), -(r_c + 16) if side == 'up' else +(r_c + 16), -(r_c + 32) if side == 'up' else +(r_c + 32)

        fig.add_trace(go.Scatter(x=[xp], y=[y_ln], mode='markers', marker=dict(size=r_c*2, color=color, line=dict(color='black', width=2)), hovertext=row.get('tooltip', ''), hovertemplate='%{hovertext}<extra></extra>', showlegend=False))
        fig.add_annotation(x=xp, y=y_ln + dy_mot, text=f"<b>{xt_lbl}</b>", showarrow=False, font=dict(size=11, color='#111'), bgcolor='rgba(255,255,255,0.7)')
        fig.add_annotation(x=xp, y=y_ln + dy_svc, text=f"<b>Serv. {serv}</b>", showarrow=False, font=dict(size=10, color='#111'), bgcolor='rgba(255,255,255,0.7)')
        fig.add_annotation(x=xp - r_c - 18, y=y_ln, text=f"{kwh_n:.0f} kWh", showarrow=False, font=dict(size=9, color='#2E7D32'), xanchor='right')
        fig.add_annotation(x=xp + r_c + 18, y=y_ln, text=f"{pax_v} pax", showarrow=False, font=dict(size=9, color='#1565c0'), xanchor='left')
        if sep_s: fig.add_annotation(x=xp, y=y_ln + dy_sep, text=f"<b>{sep_s}</b>", showarrow=False, font=dict(size=12, color='#111'))

    return fig

def render_dashboard_energia_v112(df_dia_e, active_sers, fecha_sel, hora_m1):
    if df_dia_e is None or df_dia_e.empty: st.info("Sin datos."); return
    t_trac, t_aux = df_dia_e['kwh_viaje_trac'].sum(), df_dia_e['kwh_viaje_aux'].sum()
    t_regen, t_reostat = df_dia_e['kwh_viaje_regen'].sum(), df_dia_e['kwh_reostato'].sum()
    t_neto = df_dia_e['kwh_viaje_neto'].sum()
    tren_km = df_dia_e['tren_km'].sum() if 'tren_km' in df_dia_e.columns else 0.1
    hora_str = f"{int(hora_m1)//60:02d}:{int(hora_m1)%60:02d}"
    st.markdown(f"### ⚡ Balance Energético Integral — {fecha_sel} (Acumulado {hora_str})")
    k1,k2,k3,k4,k5 = st.columns(5)
    k1.metric("🔋 Tracción", f"{t_trac:,.0f} kWh")
    k2.metric("❄️ Auxiliar", f"{t_aux:,.0f} kWh")
    k3.metric("✅ Regen Útil", f"{t_regen:,.0f} kWh")
    k4.metric("🔥 Reóstato", f"{t_reostat:,.0f} kWh")
    k5.metric("💡 IDE Neto", f"{t_neto/max(0.1, tren_km):.3f} kWh/km")
    st.divider()

def render_gemelo_digital(df_dia, df_dia_e, active_sers, fecha_sel, pct_trac, use_rm, use_pend, estacion_anio, prefix_key, gap_vias, pax_dia_total=0):
    if f'min_slider_{prefix_key}' not in st.session_state: st.session_state[f'min_slider_{prefix_key}'] = 480.0
    c1,c2,c3,c4,c5 = st.columns(5)
    if c1.button("−15m", key=f"m15_{prefix_key}"): st.session_state[f'min_slider_{prefix_key}'] -= 15
    if c2.button("−1m", key=f"m1_{prefix_key}"): st.session_state[f'min_slider_{prefix_key}'] -= 1
    if c4.button("+1m", key=f"p1_{prefix_key}"): st.session_state[f'min_slider_{prefix_key}'] += 1
    if c5.button("+15m", key=f"p15_{prefix_key}"): st.session_state[f'min_slider_{prefix_key}'] += 15
    hora_m1 = st.slider("Timeline", 0.0, 1439.0, st.session_state[f'min_slider_{prefix_key}'], 0.1, key=f"sl_ui_{prefix_key}")
    st.session_state[f'min_slider_{prefix_key}'] = hora_m1
    hora_s1 = mins_to_time_str(hora_m1)
    st.markdown(f"## ⏱️ {hora_s1[:5]}")
    df_act = df_dia_e[(df_dia_e['t_ini'] <= hora_m1) & (df_dia_e['t_fin'] > hora_m1)].copy()
    
    instant_ser_demands_kw = {s[1]: 0.0 for s in active_sers}
    ser_accum_visual = {s[1]: 0.0 for s in active_sers}
    if not df_act.empty:
        df_act['km_pos'] = df_act.apply(lambda r: km_at_t(r['t_ini'], r['t_fin'], hora_m1, r['Via'], use_rm, r['km_orig'], r['km_dest'], r.get('nodos')), axis=1)
        df_act['pax_inst'] = df_act.apply(lambda r: get_pax_at_km(r.get('pax_d', {}), r['km_pos'], r['Via'], r.get('pax_abordo', 0)), axis=1)
        for _, row in df_act.iterrows():
            st_m, v_k = get_train_state_and_speed(hora_m1, row['Via'], use_rm, row['km_orig'], row['km_dest'], row.get('nodos'))
            f_fl = FLOTA.get(row['tipo_tren'], FLOTA["XT-100"])
            n_u = 2 if row.get('doble', False) else 1
            p_ax = calcular_aux_dinamico(f_fl['aux_kw']*n_u, hora_m1/60, row['pax_inst'], f_fl['cap_max']*n_u, estacion_anio, st_m)
            p_mc = f_fl['p_max_kw']*n_u*0.8 if st_m=="ACCEL" else (-f_fl['p_freno_max_kw']*n_u*0.5 if st_m=="BRAKE" else 0)
            p_el = (p_mc/0.92 + p_ax) if p_mc>=0 else (p_mc*0.72 + p_ax)
            dist_k = distribuir_potencia_sers_kw(p_el, row['km_pos'], active_sers)
            for sn, vk in dist_k.items(): instant_ser_demands_kw[sn] += vk
        for _, r in df_dia_e[df_dia_e['t_ini'] <= hora_m1].iterrows():
            t_ev = min(hora_m1, r['t_fin'])
            e_nt = r['kwh_viaje_neto'] * ((t_ev - r['t_ini']) / max(0.001, r['t_fin'] - r['t_ini']))
            dist_e = distribuir_energia_sers(e_nt, (t_ev-r['t_ini'])/60.0, r['km_orig'], r['km_dest'], active_sers)
            for sn, ve in dist_e.items(): ser_accum_visual[sn] += ve
    
    seat_acc_vis = sum(ser_accum_visual.values()) / ETA_SER_RECTIFICADOR / 0.99
    st.plotly_chart(draw_diagram(df_act, ser_accum_visual, seat_acc_vis, hora_s1[:5], "", active_sers, gap_vias), use_container_width=True)
    if active_sers:
        st.markdown("#### 🔌 Cargabilidad Instantánea")
        cols = st.columns(len(active_sers))
        flujo = calcular_flujo_ac_nodo(instant_ser_demands_kw)
        for i, s in enumerate(active_sers):
            sn = s[1]
            p_kw = instant_ser_demands_kw[sn]
            v_dc = flujo.get(sn, {}).get('Vdc', 3000.0)
            cols[i].metric(sn, f"{p_kw:,.0f} kW", f"{v_dc:.0f} Vcc")

# =============================================================================
# 14. FUNCIÓN MAIN
# =============================================================================
def main():
    with st.sidebar:
        st.header("⚙️ Parámetros")
        pct_trac = st.slider("% Tracción", 30, 100, 90)
        use_rm, use_pend, use_regen = st.checkbox("Velocidades RM"), st.toggle("Pendientes", True), st.toggle("Regeneración", True)
        tipo_regen = st.radio("Modelo Regen", ["Físico (Load Flow)", "Probabilístico (THDR)"])
        mes_op = st.selectbox("Mes", ["Enero","Febrero","Marzo","Abril","Mayo","Junio","Julio","Agosto","Septiembre","Octubre","Noviembre","Diciembre"], 3)
        _M = {"Enero":"verano","Febrero":"verano","Marzo":"otoño","Abril":"otoño","Mayo":"otoño","Junio":"invierno","Julio":"invierno","Agosto":"invierno","Septiembre":"primavera","Octubre":"primavera","Noviembre":"primavera","Diciembre":"verano"}
        estacion = _M[mes_op]
        act_s_n = st.multiselect("SERs", [s[1] for s in SER_DATA], default=[s[1] for s in SER_DATA])
        act_sers = [s for s in SER_DATA if s[1] in act_s_n] or [SER_DATA[0]]
        gap_vias = st.slider("Separación Vías", 120, 350, 200)
        st.divider()
        f_v1 = st.file_uploader("THDR V1", accept_multiple_files=True, key="h1")
        f_v2 = st.file_uploader("THDR V2", accept_multiple_files=True, key="h2")
        f_pax_ref = st.file_uploader("Pasajeros Ref", accept_multiple_files=True, key="px_r")

    df1, df2, _ = build_thdr_v71(leer(f_v1), leer(f_v2)) if (f_v1 and f_v2) else (pd.DataFrame(), pd.DataFrame(), [])
    df_px, _ = build_pax_v71(leer(f_pax_ref), []) if f_pax_ref else (pd.DataFrame(), [])
    df_all = pd.concat([df1, df2], ignore_index=True) if not df1.empty or not df2.empty else pd.DataFrame()
    
    if not df_all.empty:
        df_all['tren_km'] = df_all.apply(calc_tren_km_real_general, axis=1)
        if not df_px.empty:
            p_res = df_all.apply(lambda r: match_pax(r, df_px), axis=1)
            df_all['pax_d'], df_all['pax_abordo'] = [x[0] for x in p_res], [x[1] for x in p_res]

    t_map, t_pax, t_vac, t_plan = st.tabs(["🗺️ Mapa Operativo", "📋 Auditoría THDR", "🚉 Vacíos", "🔮 Planificador"])

    with t_map:
        if df_all.empty: st.warning("Carga THDR")
        else:
            f_sel = st.selectbox("Fecha", sorted(df_all['Fecha_str'].unique()))
            dia = df_all[df_all['Fecha_str'] == f_sel].copy()
            dia_e = calcular_termodinamica_flota_v111(dia, pct_trac, use_pend, use_rm, use_regen, {}, estacion)
            render_gemelo_digital(dia, dia_e, act_sers, f_sel, pct_trac, use_rm, use_pend, estacion, "map", gap_vias)
            render_dashboard_energia_v112(dia_e, act_sers, f_sel, st.session_state.get('sl_ui_map', 480.0))

    with t_pax:
        st.subheader("📋 Auditoría de Datos: Carga de Pasajeros y Base THDR")
        if df_px.empty: 
            st.info("Sin datos de Pasajeros.")
        else: 
            with st.expander("Ver Tabla de Pasajeros Original", expanded=False):
                st.dataframe(df_px, use_container_width=True)
        
        # 💡 RESTAURACIÓN DE TABLA AUDITORÍA THDR HISTÓRICO
        st.divider()
        st.markdown("### 🚄 Auditoría de Base de Datos THDR (Histórico)")
        st.caption("Esta tabla muestra cómo el sistema parseó y entendió el archivo Excel crudo del THDR Histórico subido.")
        if df_all.empty:
            st.info("Sube planillas THDR en la barra lateral para ver la auditoría de la flota operada.")
        else:
            df_hist_show = df_all.copy()
            df_hist_show['Hora_Salida'] = df_hist_show['t_ini'].apply(mins_to_time_str)
            df_hist_show['Hora_Llegada'] = df_hist_show['t_fin'].apply(mins_to_time_str)
            df_hist_show['Configuración'] = df_hist_show['doble'].apply(lambda x: 'Doble' if x else 'Simple')
            
            # Ordenar columnas para mayor legibilidad
            cols_hist = ['Fecha_str', 'num_servicio', 'motriz_num', 'tipo_tren', 'Configuración', 'Via', 'svc_type', 'Hora_Salida', 'Hora_Llegada', 'pax_abordo']
            # Filtramos sólo las columnas que existan
            cols_hist_exist = [c for c in cols_hist if c in df_hist_show.columns]
            
            st.dataframe(df_hist_show[cols_hist_exist], use_container_width=True)

    with t_vac:
        if df_all.empty: st.info("Requiere THDR.")
        else: st.dataframe(pd.DataFrame(get_vacios_dia(df_all)), use_container_width=True)

    with t_plan:
        st.subheader("Planificador Avanzado V118")
        tipo_dia = st.selectbox("Día", ["Laboral", "Sábado", "Domingo/Festivo"])
        f_pl = st.file_uploader("Planilla (xlsx)")
        if f_pl:
            df_s, _ = parsear_planilla_maestra(f_pl.read(), f_pl.name)
            if not df_s.empty:
                if st.button("🚀 Simular Plan"):
                    df_px_f = df_px[df_px['Fecha_s'].apply(clasificar_dia) == tipo_dia] if not df_px.empty else pd.DataFrame()
                    res, res_e = procesar_planificador_reactivo(df_s, df_px_f, estacion, pct_trac, use_rm, use_pend, use_regen, tipo_regen)
                    
                    # 1. Mostrar Gemelo Digital Visual
                    render_gemelo_digital(res, res_e, act_sers, f"Sim: {tipo_dia}", pct_trac, use_rm, use_pend, estacion, "plan", gap_vias)
                    
                    # 💡 RESTAURACIÓN DE LA TABLA THDR SINTÉTICO OFICIAL
                    st.divider()
                    st.markdown("### 📋 THDR Sintético (Malla Operativa Generada)")
                    st.caption("Esta tabla es el equivalente matemático al THDR de EFE. Contiene los tiempos **exactos** de llegada calculados por el simulador considerando la masa, curvas, y límites eléctricos de la red.")
                    
                    df_sint_show = res.copy()
                    df_sint_show['Hora_Salida'] = df_sint_show['t_ini'].apply(mins_to_time_str)
                    df_sint_show['Hora_Llegada'] = df_sint_show['t_fin'].apply(mins_to_time_str)
                    df_sint_show['Configuración'] = df_sint_show['doble'].apply(lambda x: 'Doble' if x else 'Simple')
                    
                    cols_sint_export = ['_id', 'num_servicio', 'svc_type', 'tipo_tren', 'Configuración', 'Via', 'Hora_Salida', 'Hora_Llegada', 'pax_abordo']
                    cols_sint_exist = [c for c in cols_sint_export if c in df_sint_show.columns]
                    
                    # Muestra interactiva para buscar y filtrar
                    st.dataframe(df_sint_show[cols_sint_exist], use_container_width=True)
                    
                    # Botón de Descarga Profesional para el CTC
                    csv_sintetico = df_sint_show[cols_sint_exist].to_csv(index=False).encode('utf-8')
                    st.download_button(
                        label="📥 Descargar THDR Sintético Oficial (CSV)",
                        data=csv_sintetico,
                        file_name=f"THDR_Sintetico_V118_{tipo_dia}.csv",
                        mime='text/csv'
                    )

                    # 3. Proyección Mensual Estratégica (Capex/Opex)
                    st.divider()
                    st.markdown("### 📅 Proyección Estratégica Mensual (Capex/Opex)")
                    c_m1, c_m2, c_m3 = st.columns(3)
                    with c_m1: d_lab = st.number_input("Días Laborales en el mes", 0, 31, 22)
                    with c_m2: d_sab = st.number_input("Sábados en el mes", 0, 5, 4)
                    with c_m3: d_dom = st.number_input("Domingos/Festivos", 0, 10, 4)
                    
                    total_dias_mes = d_lab + d_sab + d_dom
                    ser_acc_p = {n: 0.0 for _, n in act_sers}
                    for _, r in res_e.iterrows():
                        dist = distribuir_energia_sers(r['kwh_viaje_neto'], (r['t_fin']-r['t_ini'])/60.0, r['km_orig'], r['km_dest'], act_sers)
                        for sn, ev in dist.items(): ser_acc_p[sn] += ev
                    tot_44 = sum(ser_acc_p.values()) / ETA_SER_RECTIFICADOR
                    t_elap = (res_e['t_fin'].max() - res_e['t_ini'].min()) / 60.0
                    loss_p = calcular_flujo_ac_nodo({k: v/t_elap for k,v in ser_acc_p.items()})['P_loss_kw'] * (1.15**2) * t_elap
                    seat_d = (tot_44 + loss_p) / 0.99
                    
                    m1, m2, m3, m4 = st.columns(4)
                    m1.metric("⚡ Energía Facturable Mensual", f"{seat_d * total_dias_mes:,.0f} kWh")
                    m2.metric("💡 IDE Promedio Mensual", f"{seat_d / max(1.0, res_e['tren_km'].sum()):.3f} kWh/km")
                    m3.metric("🧑‍🤝‍🧑 Pasajeros Mensuales", f"{int(res['pax_abordo'].sum()) * total_dias_mes:,} pax")
                    m4.metric("💰 Costo Energía Mensual", f"${seat_d * total_dias_mes * 100:,.0f} CLP", help="Considerando 100 CLP por kWh")

if __name__ == "__main__": 
    main()
