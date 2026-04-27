"""
app_mapa.py - Sistema de Simulación y Gemelo Digital MERVAL
Versión INTEGRAL v117 — Restauración Total + Planificador Inteligente:
- FÍSICA: Integrador Euler Temporal (dt=1s). Escudo Aerodinámico y ATO Coasting.
- TERMODINÁMICA: Flujo Nodal AC/DC. Balance Nodal Min-Function.
- MAPA HISTÓRICO: Reproductor animado, Squeeze Control, Auditoría THDR y Pax.
- PLANIFICADOR V117: Usa Planilla Maestra (CSV/Excel) + Perfiles de Pasajeros Reales.
  Renderiza el Gemelo Digital visualmente igual que el Mapa Operativo.
- ARQUITECTURA: DRY Principle (Des-duplicado). Ejecución encapsulada en main(). Lector anti-XLRD.
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
        "davis_A"      : 1678.70, 
        "davis_B"      : 13.97,
        "davis_C"      : 0.35,     
        "f_trac_max_kn": 58.274,   
        "f_freno_max_kn": 52.976,  
        "p_max_kw"     : 504.0,
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
        "f_trac_max_kn": 65.0,   
        "f_freno_max_kn": 55.0,  
        "p_max_kw"     : 720.0,
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
        "davis_A"      : 2694.6, 
        "davis_B"      : 16.70,
        "davis_C"      : 0.35,     
        "f_trac_max_kn": 220.0,   
        "f_freno_max_kn": 190.0,  
        "p_max_kw"     : 2400.0,
        "p_freno_max_kw": 2800.0,
        "aux_kw"       : 190.0     
    },
}

# =============================================================================
# 3. FUNCIONES DE TIEMPO Y PARSEO
# =============================================================================
if 'min_slider_1' not in st.session_state:
    st.session_state['min_slider_1'] = 480.0

def mins_to_time_str(mins):
    if pd.isna(mins): return '--:--:--'
    try:
        m_val = float(mins)
        while m_val >= 1440: m_val -= 1440
        while m_val < 0: m_val += 1440
        h = int(m_val // 60); m = int(m_val % 60); s = int(round((m_val * 60) % 60))
        if s == 60: s = 0; m += 1
        if m == 60: m = 0; h += 1
        return f"{h:02d}:{m:02d}:{s:02d}"
    except: return '--:--:--'

def parse_time_to_mins(val):
    if pd.isna(val): return None
    sv = str(val).strip().lower()
    if sv == '' or sv == 'nan': return None
    if ' ' in sv: sv = sv.split(' ')[-1]
    m = re.search(r'(\d{1,2}):(\d{2})(?::(\d{2}))?', sv)
    if m:
        h = int(m.group(1)); m_min = int(m.group(2)); s_sec = int(m.group(3)) if m.group(3) else 0
        return h * 60.0 + m_min + s_sec / 60.0
    try:
        f = float(sv)
        if f < 1.0: return f * 1440.0
        if f < 2400.0: return (int(f // 100) * 60.0) + (f % 100)
    except: pass
    return None

def parse_excel_date(val):
    if pd.isna(val): return None
    if isinstance(val, (datetime, pd.Timestamp)): return val.strftime('%Y-%m-%d')
    v_str = str(val).strip()
    if not v_str or v_str.lower() in ['nan', 'none', 'fecha', 'date', 'nat']: return None
    v_str = re.sub(r'\.0+$', '', v_str).split(' ')[0]
    
    if v_str.isdigit():
        v_int = int(v_str)
        if 40000 <= v_int <= 60000:
            try: return (date(1899, 12, 30) + timedelta(days=v_int)).strftime('%Y-%m-%d')
            except: pass
        elif len(v_str) in [5, 6]:
            s_pad = v_str.zfill(6)
            try:
                d, m, y = int(s_pad[0:2]), int(s_pad[2:4]), int(s_pad[4:6])
                if 1 <= d <= 31 and 1 <= m <= 12:
                    y_full = 2000 + y if y < 100 else y
                    return f"{y_full:04d}-{m:02d}-{d:02d}"
            except: pass
            
    m1 = re.search(r'\b(\d{1,2})[-/](\d{1,2})[-/](\d{4})\b', v_str)
    if m1:
        d, m, y = int(m1.group(1)), int(m1.group(2)), int(m1.group(3))
        if m > 12 and d <= 12: d, m = m, d  
        if 1 <= d <= 31 and 1 <= m <= 12: return f"{y:04d}-{m:02d}-{d:02d}"
            
    m2 = re.search(r'\b(\d{4})[-/](\d{1,2})[-/](\d{1,2})\b', v_str)
    if m2:
        y, m, d = int(m2.group(1)), int(m2.group(2)), int(m2.group(3))
        if m > 12 and d <= 12: d, m = m, d
        if 1 <= d <= 31 and 1 <= m <= 12: return f"{y:04d}-{m:02d}-{d:02d}"
    return None

def clean_primary_key(x):
    if pd.isna(x): return ''
    s = str(x).strip().upper() 
    if s == 'NAN' or s == '': return ''
    s = re.sub(r'\.0+$', '', s) 
    s = re.sub(r'[^A-Z0-9]', '', s) 
    return s.lstrip('0') 

def clean_id(x):
    try:
        val_str = str(x).strip().lower().replace(".0", "")
        nums = re.findall(r'\d+', val_str)
        if nums: return str(int(nums[0]))
        return val_str.upper()
    except:
        return str(x).strip().upper()

def clean_pax_number(x):
    if pd.isna(x): return 0
    s = str(x).strip().lower()
    if s == '' or s == 'nan': return 0
    s = re.sub(r'\.0+$', '', s)
    s = s.replace('.', '').replace(',', '')
    s = re.sub(r'[^\d]', '', s)
    try: return int(s) if s else 0
    except: return 0

# =============================================================================
# 4. GEOGRÁFICAS
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
            if len(m.group(1)) == 4: y, mon, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
            else: d, mon, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
            if mon > 12 and d <= 12: d, mon = mon, d
            if 1 <= d <= 31 and 1 <= mon <= 12: return f"{y:04d}-{mon:02d}-{d:02d}"

    s_fname = re.sub(r'\D', '', str(fname))
    for i in range(len(s_fname) - 7):
        match = s_fname[i:i+8]
        d, mon, y = int(match[:2]), int(match[2:4]), int(match[4:])
        if 1 <= d <= 31 and 1 <= mon <= 12 and 2000 <= y <= 2100: return f"{y:04d}-{mon:02d}-{d:02d}"
        y2, mon2, d2 = int(match[:4]), int(match[4:6]), int(match[6:])
        if 1 <= d2 <= 31 and 1 <= mon2 <= 12 and 2000 <= y2 <= 2100: return f"{y2:04d}-{mon2:02d}-{d2:02d}"
        
    for i in range(len(s_fname) - 5):
        match = s_fname[i:i+6]
        d, mon, y = int(match[:2]), int(match[2:4]), int(match[4:])
        if 1 <= d <= 31 and 1 <= mon <= 12 and 20 <= y <= 35: return f"{2000+y:04d}-{mon:02d}-{d:02d}"
            
    for i in range(min(50, len(df_raw))):
        row_vals = [str(x).strip() for x in df_raw.iloc[i].values if pd.notna(x)]
        row_str = ' '.join(row_vals)
        m_dt = re.search(r'\b(\d{4})[-/\.](\d{1,2})[-/\.](\d{1,2})\b', row_str)
        if m_dt:
            y, mon, d = int(m_dt.group(1)), int(m_dt.group(2)), int(m_dt.group(3))
            if 1 <= d <= 31 and 1 <= mon <= 12: return f"{y:04d}-{mon:02d}-{d:02d}"
        m_d = re.search(r'\b(\d{1,2})[-/\.](\d{1,2})[-/\.](\d{4})\b', row_str)
        if m_d:
            d, mon, y = int(m_d.group(1)), int(m_d.group(2)), int(m_d.group(3))
            if mon > 12 and d <= 12: d, mon = mon, d
            if 1 <= d <= 31 and 1 <= mon <= 12: return f"{y:04d}-{mon:02d}-{d:02d}"
        m_d2 = re.search(r'\b(\d{1,2})[-/\.](\d{1,2})[-/\.](\d{2})\b', row_str)
        if m_d2 and not row_str.replace(".", "").isdigit():
            d, mon, y = int(m_d2.group(1)), int(m_d2.group(2)), int(m_d2.group(3))
            if mon > 12 and d <= 12: d, mon = mon, d
            if 1 <= d <= 31 and 1 <= mon <= 12: return f"{2000+y:04d}-{mon:02d}-{d:02d}"
        for val in row_vals:
            val_clean = val.split('.')[0]
            if val_clean.isdigit() and 40000 <= int(val_clean) <= 60000:
                try: return (date(1899, 12, 30) + timedelta(days=int(val_clean))).strftime('%Y-%m-%d')
                except: pass
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
    end_idx = int(kf) + 1
    if end_idx > 45000: end_idx = 45000
    _VEL_ARRAY_NORM[start_idx:end_idx] = vn
    _VEL_ARRAY_RM[start_idx:end_idx] = vr

def vel_at_km(km_km, via, use_rm):
    idx = int(km_km * 1000.0)
    if idx < 0: return 0.0
    if idx >= 45000: return 0.0
    return _VEL_ARRAY_RM[idx] if use_rm else _VEL_ARRAY_NORM[idx]

def km_at_t(t_ini, t_fin, t, via, use_rm=False, km_orig=None, km_dest=None, nodos=None, t_arr=None):
    if nodos is not None and len(nodos) >= 2:
        if t <= nodos[0][0]: return nodos[0][1]
        if t >= nodos[-1][0]: return nodos[-1][1]
        if t_arr is None: t_arr = [n[0] for n in nodos]
        idx = np.searchsorted(t_arr, t)
        t_A, k_A = nodos[idx-1]
        t_B, k_B = nodos[idx]
        if t_A == t_B: return k_A
        if k_A == k_B: return k_A 
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
    km_arr, t_arr_prof = _PROF[(via, use_rm)]
    km_sorted, t_sorted = _PROF_SORTED[(via, use_rm)]
    
    if km_orig is None: km_orig = 0.0     if via == 1 else KM_TOTAL
    if km_dest is None: km_dest = KM_TOTAL if via == 1 else 0.0
    ko_m = km_orig * 1000.0
    kd_m = km_dest * 1000.0
    t_at_orig = float(np.interp(ko_m, km_sorted, t_sorted))
    t_at_dest = float(np.interp(kd_m, km_sorted, t_sorted))
    t_prof = t_at_orig + frac * (t_at_dest - t_at_orig)
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

# =============================================================================
# 6. AUXILIARES DINÁMICOS v113
# =============================================================================
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

# =============================================================================
# 7. FÍSICA TERMODINÁMICA Y LOAD FLOW 
# =============================================================================
def simular_tramo_termodinamico(tipo_tren, doble, km_ini, km_fin, via_op, pct_trac, use_rm, use_pend, nodos=None, pax_dict=None, pax_abordo=0, v_consigna_override=None, maniobra=None, estacion_anio="primavera", t_ini_mins=0.0):
    f = FLOTA.get(tipo_tren, FLOTA["XT-100"])
    trc, aux, reg = 0.0, 0.0, 0.0
    t_horas = 0.0
    
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
        estado_marcha = "ACCEL"
        
        while dist_recorrida < dist_total_tramo:
            dist_restante = dist_total_tramo - dist_recorrida
            if dist_restante < 0.1: break
            
            km_actual = (pos_m + dist_recorrida) / 1000.0 if via_op == 1 else (pos_m - dist_recorrida) / 1000.0
            
            es_doble = doble
            if maniobra in ['CORTE_BTO', 'CORTE_PU_SA_BTO'] and km_actual > 25.3: es_doble = False
            if maniobra == 'CORTE_SA' and km_actual > 29.1: es_doble = False
            if maniobra == 'ACOPLE_BTO' and km_actual < 25.3: es_doble = False
            if maniobra == 'ACOPLE_SA' and km_actual < 29.1: es_doble = False
            n_uni = 2 if es_doble else 1
            
            pax_mid = get_pax_at_km(pax_dict, km_actual, via_op, pax_abordo) if pax_dict else pax_abordo
            
            masa_kg = ((f['tara_t'] + f['m_iner_t']) * 1000 * n_uni) + (pax_mid * PAX_KG)
            
            v_cons_kmh = max(5.0, vel_at_km(km_actual, via_op, use_rm))
            if v_consigna_override is not None: v_cons_kmh = min(v_cons_kmh, v_consigna_override)
                
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
                        
            a_freno_max = f['a_freno_ms2']
            a_freno_op = a_freno_max * 0.9 
            d_freno_req = (v_ms**2) / (2 * a_freno_op) if v_ms > 0 else 0
            
            f_disp_trac = min(f['f_trac_max_kn']*1000*n_uni*(pct_trac/100.0), (f['p_max_kw']*1000*n_uni*(pct_trac/100.0))/max(0.1, v_ms))
            f_disp_freno = min(f['f_freno_max_kn']*1000*n_uni, (f.get('p_freno_max_kw', f['p_max_kw']*1.2)*1000*n_uni)/max(0.1, v_ms)) if v_kmh >= f['v_freno_min'] else 0.0
            
            if dist_restante <= d_freno_req + (v_ms * dt * 1.2): estado_marcha = "BRAKE_STATION"
            elif v_kmh > v_cons_kmh + 1.5: estado_marcha = "BRAKE_OVERSPEED"
            else:
                if estado_marcha == "BRAKE_OVERSPEED" and v_kmh <= v_cons_kmh: estado_marcha = "COAST"
                elif estado_marcha == "ACCEL" and v_kmh >= v_cons_kmh - 0.5: estado_marcha = "COAST"
                elif estado_marcha == "COAST":
                    if v_kmh < v_cons_kmh - 2.0: estado_marcha = "ACCEL"
                elif estado_marcha not in ["ACCEL", "COAST", "BRAKE_STATION", "BRAKE_OVERSPEED"]: estado_marcha = "ACCEL"

            f_motor, f_regen_tramo, a_net = 0.0, 0.0, 0.0
            
            if estado_marcha == "BRAKE_STATION":
                f_req_freno = max(0.0, masa_kg * a_freno_op - f_davis - f_pend)
                f_regen_tramo = min(f_req_freno, f_disp_freno)
                a_net = (-f_regen_tramo - f_davis - f_pend) / masa_kg
                if a_net > -a_freno_op: a_net = -a_freno_op 
            elif estado_marcha == "BRAKE_OVERSPEED":
                f_req_freno = max(0.0, masa_kg * 0.4 - f_davis - f_pend)
                f_regen_tramo = min(f_req_freno, f_disp_freno)
                a_net = (-f_regen_tramo - f_davis - f_pend) / masa_kg
                a_net = min(a_net, -0.15)
            elif estado_marcha == "ACCEL":
                f_motor = f_disp_trac
                a_net = (f_motor - f_davis - f_pend) / masa_kg
            elif estado_marcha == "COAST":
                f_motor = 0.0
                f_regen_tramo = 0.0
                a_net = (-f_davis - f_pend) / masa_kg
            
            v_new = v_ms + a_net * dt
            dt_actual = dt
            
            if v_new < 0:
                dt_actual = v_ms / abs(a_net) if a_net < -0.001 else dt
                v_new = 0.0
                
            if f_motor > 0 and v_new * 3.6 > v_cons_kmh:
                v_new = v_cons_kmh / 3.6
                a_req = (v_new - v_ms) / dt_actual if dt_actual > 0 else 0
                f_motor_req = masa_kg * a_req + f_davis + f_pend
                f_motor = max(0.0, min(f_motor_req, f_disp_trac))
                
            if v_new < 0.5 and dist_restante < 2.0: break
            if v_new < 0.1 and v_ms < 0.1:
                v_new = 1.0
                dt_actual = dt

            step_m = (v_ms + v_new) / 2.0 * dt_actual
            if step_m > dist_restante:
                step_m = dist_restante
                if v_ms + v_new > 0: dt_actual = step_m / ((v_ms + v_new) / 2.0)
            if step_m < 0.1: step_m = 0.5 
                
            if f_motor > 0:
                carga_pct = f_motor / max(1.0, f_disp_trac)
                eta_base = f.get('eta_motor', 0.92)
                eta_din = eta_base * (1.0 - 0.2 * (1.0 - max(0.1, carga_pct))**3)
                trc += ((f_motor * step_m) / 3_600_000.0) / eta_din
            
            if f_regen_tramo > 0 and v_kmh >= f['v_freno_min']:
                reg += ((f_regen_tramo * step_m) / 3_600_000.0) * ETA_REGEN_NETA
                
            hora_actual = (t_ini_mins + t_horas * 60.0) / 60.0
            aux_kw_inst = calcular_aux_dinamico(f['aux_kw'] * n_uni, hora_actual, pax_mid, f.get('cap_max', 398) * n_uni, estacion_anio, estado_marcha)
            aux += (aux_kw_inst * (dt_actual / 3600.0))
            t_horas += dt_actual / 3600.0
            
            dist_recorrida += step_m
            v_ms = v_new

    n_est_mid = max(0, len(paradas_km) - 2)
    dwell_h = (n_est_mid * 25.0) / 3600.0
    hora_media_dwell = (t_ini_mins + (t_horas + dwell_h / 2.0) * 60.0) / 60.0
    aux_kw_dwell = calcular_aux_dinamico(f['aux_kw'] * (2 if doble else 1), hora_media_dwell, pax_abordo, f.get('cap_max', 398) * (2 if doble else 1), estacion_anio, "DWELL")
    aux += aux_kw_dwell * dwell_h
    t_horas += dwell_h
    
    neto_ideal = max(0.0, trc + aux - reg)
    return trc, aux, reg, 0.0, neto_ideal, t_horas

def calcular_demanda_ser(e_pantografo_kwh, t_horas, km_punto, km_ser):
    if t_horas <= 0: return e_pantografo_kwh
    V_NOMINAL = 3000.0  
    if km_punto < 2.25: r_km = 0.0638       
    elif km_punto < 6.80: r_km = 0.0530     
    elif km_punto < 10.92: r_km = 0.0495    
    elif km_punto < 21.41: r_km = 0.0417    
    elif km_punto < 30.36: r_km = 0.0399    
    else: r_km = 0.0355                     
    R_total = r_km * abs(km_punto - km_ser)
    P_kW = abs(e_pantografo_kwh) / t_horas
    I = (P_kW * 1000.0) / V_NOMINAL
    P_loss_kW = (I**2 * R_total) / 1000.0
    if e_pantografo_kwh >= 0: return e_pantografo_kwh + (P_loss_kW * t_horas)
    else: return -max(0.0, abs(e_pantografo_kwh) - (P_loss_kW * t_horas))

def distribuir_energia_sers(e_pantografo, t_horas, km_ini, km_fin, active_sers):
    if not active_sers: return {}
    if len(active_sers) == 1:
        e_s = calcular_demanda_ser(e_pantografo, t_horas, (km_ini+km_fin)/2.0, active_sers[0][0])
        return {active_sers[0][1]: e_s}
    sers_sorted = sorted(active_sers, key=lambda x: x[0])
    boundaries = [0.0]
    for i in range(len(sers_sorted)-1): boundaries.append((sers_sorted[i][0] + sers_sorted[i+1][0]) / 2.0)
    boundaries.append(KM_TOTAL)
    dist_total = abs(km_fin - km_ini)
    if dist_total < 0.001:
        closest = min(active_sers, key=lambda x: abs(km_ini - x[0]))
        e_s = calcular_demanda_ser(e_pantografo, t_horas, km_ini, closest[0])
        return {closest[1]: e_s}
    k_min, k_max = min(km_ini, km_fin), max(km_ini, km_fin)
    resultados = {s[1]: 0.0 for s in sers_sorted}
    for i, ser in enumerate(sers_sorted):
        b_min, b_max = boundaries[i], boundaries[i+1]
        o_min, o_max = max(k_min, b_min), min(k_max, b_max)
        if o_max > o_min:
            frac = (o_max - o_min) / dist_total
            centroid = (o_min + o_max) / 2.0
            resultados[ser[1]] += calcular_demanda_ser(e_pantografo * frac, t_horas * frac if t_horas > 0 else 0.0, centroid, ser[0])
    return resultados

def distribuir_potencia_sers_kw(p_kw, km_punto, active_sers):
    if not active_sers: return {}
    if len(active_sers) == 1: return {active_sers[0][1]: p_kw}
    sers_sorted = sorted(active_sers, key=lambda x: x[0])
    if km_punto <= sers_sorted[0][0]: return {sers_sorted[0][1]: p_kw}
    if km_punto >= sers_sorted[-1][0]: return {sers_sorted[-1][1]: p_kw}
    for i in range(len(sers_sorted)-1):
        s1, s2 = sers_sorted[i], sers_sorted[i+1]
        if s1[0] <= km_punto <= s2[0]:
            dist_total = s2[0] - s1[0]
            d1, d2 = km_punto - s1[0], s2[0] - km_punto
            return {s1[1]: p_kw * (d2 / dist_total), s2[1]: p_kw * (d1 / dist_total)}
    return {active_sers[0][1]: p_kw}

def calcular_flujo_ac_nodo(demands_kw):
    i_po = max(0.0, demands_kw.get('SER PO', 0.0)) * 1000 / (1.732 * V_NOMINAL_AC * 0.95)
    i_es = max(0.0, demands_kw.get('SER ES', 0.0)) * 1000 / (1.732 * V_NOMINAL_AC * 0.95)
    i_eb = max(0.0, demands_kw.get('SER EB', 0.0)) * 1000 / (1.732 * V_NOMINAL_AC * 0.95)
    i_va = max(0.0, demands_kw.get('SER VA', 0.0)) * 1000 / (1.732 * V_NOMINAL_AC * 0.95)
    len_seat_es, len_es_po = abs(24.3 - 12.7), abs(12.7 - 4.9)
    dv_seat_es, dv_es_po = 1.732 * (i_po + i_es) * Z_EFF_44KV * len_seat_es, 1.732 * (i_po) * Z_EFF_44KV * len_es_po
    loss_seat_es, loss_es_po = 3 * ((i_po + i_es)**2) * R_AC_44KV * len_seat_es / 1000.0, 3 * (i_po**2) * R_AC_44KV * len_es_po / 1000.0
    v_ac_es, v_ac_po = V_NOMINAL_AC - dv_seat_es, V_NOMINAL_AC - dv_seat_es - dv_es_po
    len_seat_eb, len_eb_va = abs(25.5 - 24.3), abs(28.7 - 25.5)
    dv_seat_eb, dv_eb_va = 1.732 * (i_eb + i_va) * Z_EFF_44KV * len_seat_eb, 1.732 * (i_va) * Z_EFF_44KV * len_eb_va
    loss_seat_eb, loss_eb_va = 3 * ((i_eb + i_va)**2) * R_AC_44KV * len_seat_eb / 1000.0, 3 * (i_va**2) * R_AC_44KV * len_eb_va / 1000.0
    v_ac_eb, v_ac_va = V_NOMINAL_AC - dv_seat_eb, V_NOMINAL_AC - dv_seat_eb - dv_eb_va
    return {
        'SER PO': {'Vac': v_ac_po, 'Vdc': 3000.0 * (v_ac_po / V_NOMINAL_AC)},
        'SER ES': {'Vac': v_ac_es, 'Vdc': 3000.0 * (v_ac_es / V_NOMINAL_AC)},
        'SER EB': {'Vac': v_ac_eb, 'Vdc': 3000.0 * (v_ac_eb / V_NOMINAL_AC)},
        'SER VA': {'Vac': v_ac_va, 'Vdc': 3000.0 * (v_ac_va / V_NOMINAL_AC)},
        'P_loss_kw': loss_seat_es + loss_es_po + loss_seat_eb + loss_eb_va
    }

# =============================================================================
# 8. REGENERACIÓN Y RED v114
# =============================================================================
def calcular_receptividad_por_headway(df_dia: pd.DataFrame) -> dict:
    if df_dia.empty: return {}
    result = {}
    for via in [1, 2]:
        sub = df_dia[df_dia["Via"] == via].sort_values("t_ini").copy()
        if sub.empty: continue
        indices, t_ini_vals = list(sub.index), sub["t_ini"].values
        for i, idx in enumerate(indices):
            headways = []
            if i > 0: headways.append(t_ini_vals[i] - t_ini_vals[i-1])
            if i < len(indices)-1: headways.append(t_ini_vals[i+1] - t_ini_vals[i])
            if not headways: result[idx] = 0.10; continue
            hw = min(headways)
            if hw < 5.0: eta = 0.90
            elif hw < 10.0: eta = 0.75 - ((hw - 5.0) / 5.0) * 0.45
            else: eta = max(0.10, 0.30 - ((hw - 10.0) / 20.0) * 0.20)
            result[idx] = min(eta, 0.90)
    return result

@st.cache_data(show_spinner="Simulando malla eléctrica y receptividad V1/V2 (Balance Nodal - 5km)...")
def precalcular_red_electrica_v111(df_dia, pct_trac, use_rm, estacion_anio="primavera"):
    regen_util_per_trip = {idx: 0.0 for idx in df_dia.index}
    braking_ticks_per_trip = {idx: 0.0 for idx in df_dia.index} 
    if df_dia.empty: return regen_util_per_trip
    t_min, t_max = int(df_dia['t_ini'].min()), int(df_dia['t_fin'].max())
    dt_step = 10.0 / 60.0 
    time_steps = np.arange(t_min, t_max + 1, dt_step)
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
        braking_by_idx = [[] for _ in range(len(time_steps))]
        accel_by_idx = [[] for _ in range(len(time_steps))]
        for tr in trains_data:
            idx_start = np.searchsorted(time_steps, max(t_min, tr['t_ini']))
            idx_end = np.searchsorted(time_steps, min(t_max, tr['t_fin']), side='right')
            f = FLOTA.get(tr['tipo_tren'], FLOTA["XT-100"])
            n_uni = 2 if tr['doble'] else 1
            masa_kg = ((f['tara_t'] + f['m_iner_t']) * 1000 * n_uni) + (tr['pax_abordo'] * PAX_KG)
            eta_m = f.get('eta_motor', 0.92)
            for i in range(idx_start, idx_end):
                m = time_steps[i]
                state, v_kmh = get_train_state_and_speed(m, tr['Via'], use_rm, tr['km_orig'], tr['km_dest'], tr['nodos'], tr['t_arr'])
                pos = km_at_t(tr['t_ini'], tr['t_fin'], m, tr['Via'], use_rm, tr['km_orig'], tr['km_dest'], tr['nodos'], tr['t_arr'])
                v_ms = v_kmh / 3.6
                p_aux_kw = calcular_aux_dinamico(f['aux_kw'] * n_uni, m / 60.0, tr['pax_abordo'], f.get('cap_max', 398) * n_uni, estacion_anio, state)
                f_davis = ((f['davis_A'] * 2) + (f['davis_B'] * 2 * v_kmh) + (f['davis_C'] * 1.35 * (v_kmh**2))) if n_uni == 2 else (f['davis_A'] + f['davis_B']*v_kmh + f['davis_C']*(v_kmh**2))
                f_pend = 0.0
                if state in ("BRAKE", "BRAKE_STATION", "BRAKE_OVERSPEED"):
                    f_req_freno = max(0.0, masa_kg * (f['a_freno_ms2'] * 0.9) - f_davis - f_pend)
                    f_disp_freno = min(f['f_freno_max_kn']*1000*n_uni, (f.get('p_freno_max_kw', f['p_max_kw']*1.2)*1000*n_uni)/max(0.1, v_ms)) if v_kmh >= f['v_freno_min'] else 0.0
                    p_gen_kw = ((min(f_req_freno, f_disp_freno) * v_ms) / 1000.0 * ETA_REGEN_NETA) - p_aux_kw
                    if p_gen_kw > 0: braking_by_idx[i].append((tr['idx'], pos, p_gen_kw))
                    braking_ticks_per_trip[tr['idx']] += 1
                elif state in ("ACCEL", "CRUISE"):
                    p_dem_kw = p_aux_kw
                    if state == "ACCEL":
                        p_dem_kw += (((min(f['f_trac_max_kn']*1000*n_uni*(pct_trac/100.0), (f['p_max_kw']*1000*n_uni*(pct_trac/100.0))/max(0.1, v_ms)) if v_ms > 0 else f['f_trac_max_kn']*1000*n_uni*(pct_trac/100.0)) * v_ms) / 1000.0 / eta_m)
                        accel_by_idx[i].append((tr['idx'], pos, p_dem_kw))
                    elif state == "CRUISE" and (f_davis + f_pend > 0):
                        p_dem_kw += ((((f_davis + f_pend) * v_ms) / 1000.0) / eta_m)
                        accel_by_idx[i].append((tr['idx'], pos, p_dem_kw))
        for i in range(len(time_steps)):
            braking, accel = braking_by_idx[i], accel_by_idx[i]
            if not braking or not accel: continue
            current_demands = {a[0]: a[2] for a in accel}
            for b_idx, b_pos, p_gen in braking:
                available_sinks = [a for a in accel if current_demands[a[0]] > 0]
                if not available_sinks: break 
                best_a = min(available_sinks, key=lambda x: abs(x[1] - b_pos))
                a_idx, a_pos, _ = best_a
                d = abs(a_pos - b_pos)
                if d <= LAMBDA_REGEN_KM * 2:
                    p_transferred = min(p_gen * (ETA_MAX * np.exp(-d / LAMBDA_REGEN_KM)), current_demands[a_idx])
                    current_demands[a_idx] -= p_transferred
                    regen_util_per_trip[b_idx] += (p_transferred / p_gen)
    for idx in df_dia.index:
        ticks = braking_ticks_per_trip[idx]
        regen_util_per_trip[idx] = min(1.0, regen_util_per_trip[idx] / ticks) if ticks > 0 else 0.0
    return regen_util_per_trip

@st.cache_data(show_spinner="Integrando Termodinámica de Flota...")
def calcular_termodinamica_flota_v111(df_dia, pct_trac, use_pend, use_rm, use_regen, dict_regen, estacion_anio="primavera"):
    df_e = df_dia.copy()
    if df_e.empty: return df_e
    def _wrapper_energia(r):
        trc, aux, reg_panto_max, _, _, t_h = simular_tramo_termodinamico(
            r['tipo_tren'], r.get('doble', False), r['km_orig'], r['km_dest'], r['Via'],
            pct_trac, use_rm, use_pend, r.get('nodos'), r.get('pax_d', {}), r.get('pax_abordo', 0), None, r.get('maniobra'),
            estacion_anio, r.get('t_ini', 0.0)
        )
        if use_regen:
            if dict_regen and r.name in dict_regen:
                reg_util = reg_panto_max * dict_regen[r.name]
            else:
                reg_util = reg_panto_max
        else:
            reg_util = 0.0
            
        return pd.Series([trc, aux, reg_util, max(0.0, reg_panto_max - reg_util), max(0.0, trc + aux - reg_util)])
    df_e[['kwh_viaje_trac', 'kwh_viaje_aux', 'kwh_viaje_regen', 'kwh_reostato', 'kwh_viaje_neto']] = df_e.apply(_wrapper_energia, axis=1)
    return df_e

# =============================================================================
# 9. MANIOBRAS EN VACÍO (CARRUSELES)
# =============================================================================
@st.cache_data(show_spinner="Calculando Carrusel de Cocheras...")
def get_vacios_dia(df_dia):
    vacios = []
    if df_dia.empty: return vacios
    agrupador = 'motriz_num' if 'motriz_num' in df_dia.columns else 'num_servicio'
    def _get_est_name(km):
        if pd.isna(km): return "Desconocido"
        d = [abs(km - k) for k in KM_ACUM]
        idx = int(np.argmin(d))
        return ESTACIONES[idx] if d[idx] <= 1.5 else f"km {km:.1f}"
    for tren, group in df_dia.sort_values('t_ini').groupby(agrupador):
        if str(tren).strip() == '' or str(tren).strip() == 'nan': continue
        viajes = group.to_dict('records')
        if not viajes: continue
        p = viajes[0]
        if abs(p.get('km_orig', 0) - KM_ACUM[14]) < 0.1:
            vacios.append({'t_asigned': p['t_ini'] - 10, 'tipo': p.get('tipo_tren', 'XT-100'), 'doble': p.get('doble', False), 'cochera': True, 'km_orig': KM_ACUM[14], 'km_dest': KM_ACUM[14], 'dist': 2.0, 'motriz_num': tren, 'origen_txt': 'Taller / Cochera', 'destino_txt': 'El Belloto', 'servicio_previo': '—', 'servicio_siguiente': str(p.get('num_servicio', ''))})
        elif abs(p.get('km_orig', 0) - KM_ACUM[18]) < 0.1:
            vacios.append({'t_asigned': p['t_ini'] - 20, 'tipo': p.get('tipo_tren', 'XT-100'), 'doble': p.get('doble', False), 'cochera': True, 'km_orig': KM_ACUM[14], 'km_dest': KM_ACUM[18], 'dist': 2.0 + abs(KM_ACUM[18]-KM_ACUM[14]), 'motriz_num': tren, 'origen_txt': 'Taller / Cochera', 'destino_txt': 'Sargento Aldea', 'servicio_previo': '—', 'servicio_siguiente': str(p.get('num_servicio', ''))})
        for i in range(len(viajes) - 1):
            actual, sig = viajes[i], viajes[i+1]
            k_o, k_d = actual.get('km_dest', 0), sig.get('km_orig', 0)
            dist = abs(k_o - k_d)
            if 0.1 < dist <= 20.0:
                vacios.append({'t_asigned': actual['t_fin'] + 5, 'tipo': actual.get('tipo_tren', 'XT-100'), 'doble': actual.get('doble', False), 'cochera': False, 'km_orig': k_o, 'km_dest': k_d, 'dist': dist, 'motriz_num': tren, 'origen_txt': _get_est_name(k_o), 'destino_txt': _get_est_name(k_d), 'servicio_previo': str(actual.get('num_servicio', '')), 'servicio_siguiente': str(sig.get('num_servicio', ''))})
        u = viajes[-1]
        if abs(u.get('km_dest', 0) - KM_ACUM[14]) < 0.1:
            vacios.append({'t_asigned': u['t_fin'] + 5, 'tipo': u.get('tipo_tren', 'XT-100'), 'doble': u.get('doble', False), 'cochera': True, 'km_orig': KM_ACUM[14], 'km_dest': KM_ACUM[14], 'dist': 2.0, 'motriz_num': tren, 'origen_txt': 'El Belloto', 'destino_txt': 'Taller / Cochera', 'servicio_previo': str(u.get('num_servicio', '')), 'servicio_siguiente': '—'})
        elif abs(u.get('km_dest', 0) - KM_ACUM[18]) < 0.1:
            vacios.append({'t_asigned': u['t_fin'] + 5, 'tipo': u.get('tipo_tren', 'XT-100'), 'doble': u.get('doble', False), 'cochera': True, 'km_orig': KM_ACUM[18], 'km_dest': KM_ACUM[14], 'dist': 2.0 + abs(KM_ACUM[18]-KM_ACUM[14]), 'motriz_num': tren, 'origen_txt': 'Sargento Aldea', 'destino_txt': 'Taller / Cochera', 'servicio_previo': str(u.get('num_servicio', '')), 'servicio_siguiente': '—'})
    return vacios

# =============================================================================
# 10. PERFILES PROMEDIO DE PASAJEROS (V117)
# =============================================================================
@st.cache_data(show_spinner="Calculando perfiles promedio de pasajeros por tipo de día...")
def get_perfiles_pax(df_px):
    if df_px.empty: return {}
    df_p = df_px.copy()
    
    df_p['Fecha_dt'] = pd.to_datetime(df_p['Fecha_s'], errors='coerce')
    df_p = df_p.dropna(subset=['Fecha_dt'])
    
    if df_p.empty: return {}
    
    feriados_2026 = [
        '2026-01-01', '2026-04-03', '2026-04-04', '2026-05-01', '2026-05-21', 
        '2026-06-21', '2026-07-16', '2026-08-15', '2026-09-18', '2026-09-19', 
        '2026-10-12', '2026-10-31', '2026-12-08', '2026-12-25'
    ]
    
    def clasificar_dia(d):
        str_d = d.strftime('%Y-%m-%d')
        if str_d in feriados_2026 or d.weekday() == 6: return 'Domingo/Festivo'
        if d.weekday() == 5: return 'Sábado'
        return 'Laboral'
        
    df_p['Tipo_Dia'] = df_p['Fecha_dt'].apply(clasificar_dia)
    
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

def get_pax_at_km(pax_d, km_pos, via, pax_max_fallback=0):
    if not pax_d or not isinstance(pax_d, dict): return pax_max_fallback
    if sum(pax_d.values()) == 0 and pax_max_fallback > 0: return pax_max_fallback
    pax_val = 0
    if via == 1:
        for i in range(N_EST):
            if km_pos >= KM_ACUM[i]:
                val = pax_d.get(PAX_COLS[i])
                if val is not None: pax_val = val
            else: break
    else:
        for i in range(N_EST - 1, -1, -1):
            if km_pos <= KM_ACUM[i]:
                val = pax_d.get(PAX_COLS[i])
                if val is not None: pax_val = val
            else: break
    return int(pax_val)

# =============================================================================
# CACHÉ REACTIVO DEL PLANIFICADOR
# =============================================================================
@st.cache_data(show_spinner="Integrando variables físicas y termodinámicas de la Planilla...")
def procesar_planificador_reactivo(df_sint, tipo_dia_plan, pax_promedio_viaje, estacion_anio_plan, pct_trac, use_rm, use_pend, use_regen, tipo_regen, perfiles_pax):
    viajes_completos = []
    for idx, r in df_sint.iterrows():
        via_tren = r['Via']
        pax_dict_dinamico = perfiles_pax.get((tipo_dia_plan, via_tren), {})
        pax_abordo_base = pax_dict_dinamico.get('CargaMax_Promedio', pax_promedio_viaje)
        
        f_gauss = 0.2 + 0.8 * np.exp(-0.5 * ((r['t_ini'] - 450)/60)**2) + 0.8 * np.exp(-0.5 * ((r['t_ini'] - 1080)/90)**2)
        pax_calculado = int(pax_abordo_base * f_gauss * 1.5)
        cap_m = FLOTA[r['tipo_tren']].get('cap_max', 398) * (2 if r['doble'] else 1)
        pax_calculado = min(pax_calculado, cap_m)
        
        if pax_dict_dinamico:
            pax_arr_viaje = {k: min(int(v * f_gauss * 1.5), cap_m) for k, v in pax_dict_dinamico.items() if k != 'CargaMax_Promedio'}
        else:
            pax_arr_viaje = {}
        
        trc_v, aux_v, reg_v, _, _, t_horas_v = simular_tramo_termodinamico(
            r['tipo_tren'], r['doble'], r['km_orig'], r['km_dest'], r['Via'],
            pct_trac, use_rm, use_pend, r['nodos'], pax_arr_viaje, pax_calculado, None, None, estacion_anio_plan, r['t_ini']
        )
        
        t_fin_real = r['t_ini'] + (t_horas_v * 60.0)
        viaje_final = r.to_dict()
        viaje_final['pax_d'] = pax_arr_viaje
        viaje_final['pax_abordo'] = pax_calculado
        viaje_final['t_fin'] = t_fin_real
        viajes_completos.append(viaje_final)
        
    df_sint_final = pd.DataFrame(viajes_completos)
    df_sint_final['tren_km'] = df_sint_final.apply(calc_tren_km_real_general, axis=1)
    df_sint_final.index = df_sint_final['_id']
    
    if use_regen:
        if "Probabilístico" in tipo_regen:
            dict_regen_sint = calcular_receptividad_por_headway(df_sint_final)
        else:
            dict_regen_sint = precalcular_red_electrica_v111(df_sint_final, pct_trac, use_rm, estacion_anio_plan)
    else:
        dict_regen_sint = {}
        
    df_sint_e = calcular_termodinamica_flota_v111(df_sint_final, pct_trac, use_pend, use_rm, use_regen, dict_regen_sint, estacion_anio_plan)
    
    return df_sint_final, df_sint_e

# =============================================================================
# 11. PARSERS Y LECTORES DE DATOS BASE (THDR / PAX / PLANILLA)
# =============================================================================
def procesar_thdr(data, fname, via_param=1):
    try:
        ext = fname.lower()
        if ext.endswith('.csv'):
            try: raw = pd.read_csv(BytesIO(data), header=None, sep=',', encoding='utf-8', dtype=str)
            except: raw = pd.read_csv(BytesIO(data), header=None, sep=';', encoding='latin-1', dtype=str)
        else:
            try:
                eng = "xlrd" if ext.endswith(".xls") else "openpyxl"
                raw = pd.read_excel(BytesIO(data), header=None, engine=eng, dtype=str)
            except Exception as e:
                try: 
                    dfs = pd.read_html(BytesIO(data), header=None)
                    raw = dfs[0].astype(str)
                except:
                    try: raw = pd.read_csv(BytesIO(data), header=None, sep='\t', encoding='latin-1', dtype=str)
                    except: raw = pd.read_excel(BytesIO(data), header=None, engine="openpyxl", dtype=str)

        if raw is None or raw.empty: return pd.DataFrame(), f"Archivo vacío o ilegible: {fname}"
        if raw.shape[0] < 6: return pd.DataFrame(), f"Archivo muy corto: {fname}"
        fecha_str = extraer_fecha_segura(raw, fname)
        header_idx = 1
        for i in range(min(15, len(raw))):
            row_vals = [str(x).upper() for x in raw.iloc[i].values if pd.notna(x)]
            row_str = ' '.join(row_vals)
            if 'VIAJE' in row_str and ('TREN' in row_str or 'MOTRIZ' in row_str or 'SFE' in row_str or 'SERVICIO' in row_str) and ('SALIDA' in row_str or 'HORA' in row_str):
                header_idx = i
                break
                
        r0 = raw.iloc[header_idx - 1].copy() if header_idx > 0 else raw.iloc[0].copy()
        r0.iloc[0] = np.nan 
        h1 = r0.ffill().astype(str)
        h2 = raw.iloc[header_idx].fillna('').astype(str)
        
        cols = []
        for s, t in zip(h1, h2):
            s, t = str(s).strip(), str(t).strip()
            cols.append(t if (s.lower()=='nan' or not s) else (f"{s}_{t}" if t else s))
            
        df = raw.iloc[header_idx + 1:].copy().reset_index(drop=True)
        n = len(df.columns)
        df.columns = cols[:n] if len(cols)>=n else cols+[f"_C{j}" for j in range(n-len(cols))]
        df = make_unique(df).dropna(how='all').reset_index(drop=True)

        if df.empty: return pd.DataFrame(), f"Sin filas tras limpiar: {fname}"

        for col in df.columns:
            if any(k in str(col).upper() for k in ['LLEGADA','SALIDA','HORA']):
                try: df[f"{col}_min"] = df[col].apply(parse_time_to_mins)
                except: pass

        c_m1 = next((c for c in df.columns if 'motriz' in str(c).lower() and '1' in str(c).lower()), None)
        c_m2 = next((c for c in df.columns if 'motriz' in str(c).lower() and '2' in str(c).lower()), None)
        tren_col = next((c for c in df.columns if str(c).strip() == 'Tren'), None)

        def _get_fleet_info(r):
            def extract_n(col_name):
                if col_name and pd.notna(r.get(col_name)):
                    val = str(r.get(col_name)).strip()
                    if val.lower() not in ('nan', '', '0', '0.0'):
                        try: return int(float(val))
                        except ValueError:
                            m = re.search(r'(\d+)', val)
                            if m: return int(m.group(1))
                return None
            
            n1 = extract_n(c_m1)
            n2 = extract_n(c_m2)
            tipo = "XT-100"
            motriz_str = ""
            n_eval = None
            
            if (n1 is not None and n1 != 0) and (n2 is not None and n2 != 0):
                motriz_str = f"{n1}+{n2}"; n_eval = n1
            elif (n1 is not None and n1 != 0):
                motriz_str = f"{n1}"; n_eval = n1
            elif (n2 is not None and n2 != 0):
                motriz_str = f"{n2}"; n_eval = n2
            else:
                n_tren = extract_n(tren_col)
                if n_tren is not None and n_tren != 0:
                    motriz_str = f"{n_tren}"; n_eval = n_tren
                    
            if n_eval is not None:
                if 1 <= n_eval <= 27: tipo = "XT-100"
                elif 28 <= n_eval <= 35: tipo = "XT-M"
                elif 410 <= n_eval <= 414: tipo = "SFE"
                else: tipo = "XT-100" 
                    
            return pd.Series([motriz_str, tipo])
            
        df[['motriz_num', 'tipo_tren']] = df.apply(_get_fleet_info, axis=1)

        if 'Unidad' in df.columns:
            df['Unidad'] = df['Unidad'].fillna('S').replace('nan','S').replace('','S')
        else:
            df['Unidad'] = df[c_m2].apply(lambda x: 'M' if pd.notna(x) and str(x).strip() not in ('0','0.0','','nan') else 'S') if c_m2 else 'S'
            
        df['doble']     = df['Unidad'].astype(str).str.strip()=='M'
        df['Via']       = via_param
        df['Fecha_str'] = fecha_str

        sal_cols = [c for c in df.columns if 'salida' in str(c).lower() and '_min' in str(c).lower() and 'program' not in str(c).lower()]
        lle_cols = [c for c in df.columns if 'llegada' in str(c).lower() and '_min' in str(c).lower() and 'program' not in str(c).lower()]
        if not sal_cols or not lle_cols: return pd.DataFrame(), "Faltan columnas de hora."

        def _safe_get(r, col):
            try: return r.get(col, np.nan)
            except: return np.nan

        sal_est = {c: _col_to_est_idx(c) for c in sal_cols}
        sal_est = {c: v for c, v in sal_est.items() if v is not None}
        lle_est = {c: _col_to_est_idx(c) for c in lle_cols}
        lle_est = {c: v for c, v in lle_est.items() if v is not None}

        valid_sal_cols = list(sal_est.keys())
        valid_lle_cols = list(lle_est.keys())

        df['t_ini'] = df.apply(lambda row: min([_safe_get(row, c) for c in valid_sal_cols if pd.notna(_safe_get(row, c))] or [np.nan]), axis=1)
        df['t_fin'] = df.apply(lambda row: max([_safe_get(row, c) for c in valid_lle_cols if pd.notna(_safe_get(row, c))] or [np.nan]), axis=1)

        def _km_orig(row):
            assigned = [(sal_est.get(c), _safe_get(row, c)) for c in sal_cols if sal_est.get(c) is not None and pd.notna(_safe_get(row, c)) and _safe_get(row, c) != 0]
            if not assigned: return 0.0 if via_param == 1 else KM_TOTAL
            return KM_ACUM[(min if via_param == 1 else max)(assigned, key=lambda x: x[0])[0]]
            
        def _km_dest(row):
            assigned = [(lle_est.get(c), _safe_get(row, c)) for c in lle_cols if lle_est.get(c) is not None and pd.notna(_safe_get(row, c)) and _safe_get(row, c) != 0]
            if not assigned: return KM_TOTAL if via_param == 1 else 0.0
            return KM_ACUM[(max if via_param == 1 else min)(assigned, key=lambda x: x[0])[0]]

        df['km_orig'] = df.apply(_km_orig, axis=1)
        df['km_dest'] = df.apply(_km_dest, axis=1)

        def _extract_nodos(row):
            nodos_temp = []
            for c in lle_cols:
                idx = lle_est.get(c)
                val = _safe_get(row, c)
                if idx is not None and pd.notna(val): nodos_temp.append((val, KM_ACUM[idx]))
            for c in sal_cols:
                idx = sal_est.get(c)
                val = _safe_get(row, c)
                if idx is not None and pd.notna(val): nodos_temp.append((val, KM_ACUM[idx]))
            
            nodos_validos = [n for n in nodos_temp if pd.notna(n[0])]
            nodos_ordenados = sorted(nodos_validos, key=lambda x: x[0])
            return nodos_ordenados if len(nodos_ordenados) > 1 else None
            
        df['nodos'] = df.apply(_extract_nodos, axis=1)
        df['km_viaje'] = abs(df['km_dest'] - df['km_orig'])
        df['svc_type'] = df.apply(lambda r: svc_label(r['km_orig'], r['km_dest']), axis=1)

        def calc_dwell_dynamic(row):
            try:
                idx_orig = int(np.argmin([abs(row['km_orig'] - k) for k in KM_ACUM]))
                idx_dest = int(np.argmin([abs(row['km_dest'] - k) for k in KM_ACUM]))
                n_stops = max(0, abs(idx_dest - idx_orig) - 1)
                return round(n_stops * (8.0 / 19.0), 3)
            except:
                return 8.0 
                
        df['dwell_min'] = df.apply(calc_dwell_dynamic, axis=1)
        df['dwell_cabecera_min'] = 0.0

        viaje_col_idx = None
        for r in range(min(15, raw.shape[0])):
            for c in range(raw.shape[1]):
                val_raw = str(raw.iloc[r, c]).strip().upper()
                val_norm = unicodedata.normalize('NFD', val_raw).encode('ascii', 'ignore').decode()
                if 'VIAJE' in val_norm and 'TIEMPO' not in val_norm and 'MIN' not in val_norm and viaje_col_idx is None:
                    viaje_col_idx = c
                    break
                    
        if viaje_col_idx is not None and viaje_col_idx < len(df.columns):
            col_name_v = df.columns[viaje_col_idx]
            df['nro_viaje'] = df[col_name_v].apply(clean_primary_key)
        else: df['nro_viaje'] = ''

        df['_id'] = df['Fecha_str'] + "_" + df['num_servicio'] + "_" + df['t_ini'].astype(str)

        df = df.dropna(subset=['t_ini'])
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
            try:
                eng = "xlrd" if ext.endswith(".xls") else "openpyxl"
                full = pd.read_excel(BytesIO(data), header=None, engine=eng, dtype=str)
            except Exception as e:
                try: 
                    dfs = pd.read_html(BytesIO(data), header=None)
                    full = dfs[0].astype(str)
                except:
                    try: full = pd.read_csv(BytesIO(data), header=None, sep='\t', encoding='latin-1', dtype=str)
                    except: full = pd.read_excel(BytesIO(data), header=None, engine="openpyxl", dtype=str)

        if full is None or full.empty:
            st.error(f"El archivo {fname} está vacío o no se puede leer.")
            return pd.DataFrame()

        if len(full) <= 10:
            st.error(f"El archivo {fname} tiene menos de 10 filas.")
            return pd.DataFrame()

        header_idx = 9
        EXACT_MAP = {
            'PUE': 'PUE', 'PUERTO': 'PUE', 'PU': 'PUE',
            'BEL': 'BEL', 'BELLAVISTA': 'BEL', 'BE': 'BEL',
            'FRA': 'FRA', 'FRANCIA': 'FRA', 'FR': 'FRA',
            'BAR': 'BAR', 'BARON': 'BAR', 'BA': 'BAR',
            'POR': 'POR', 'PORTALES': 'POR', 'PO': 'POR',
            'REC': 'REC', 'RECREO': 'REC', 'RE': 'REC',
            'MIR': 'MIR', 'MIRAMAR': 'MIR', 'MI': 'MIR',
            'VIN': 'VIN', 'VINA DEL MAR': 'VIN', 'VIÑA DEL MAR': 'VIN', 'VM': 'VIN',
            'HOS': 'HOS', 'HOSPITAL': 'HOS', 'HO': 'HOS',
            'CHO': 'CHO', 'CHORRILLOS': 'CHO', 'CH': 'CHO',
            'SLT': 'SLT', 'SALTO': 'SLT', 'EL SALTO': 'SLT', 'ES': 'SLT', 'ELS': 'SLT',
            'VAL': 'VAL', 'VALENCIA': 'VAL',
            'QUI': 'QUI', 'QUILPUE': 'QUI', 'QUILPUÉ': 'QUI', 'QU': 'QUI',
            'SOL': 'SOL', 'EL SOL': 'SOL', 'SO': 'SOL', 'ESO': 'SOL',
            'BTO': 'BTO', 'EL BELLOTO': 'BTO', 'BELLOTO': 'BTO', 'EB': 'BTO', 'ELB': 'BTO',
            'AME': 'AME', 'LAS AMERICAS': 'AME', 'AMERICAS': 'AME', 'LAS': 'AME', 'LAM': 'AME', 'AM': 'AME',
            'CON': 'CON', 'LA CONCEPCION': 'CON', 'CONCEPCION': 'CON', 'LAC': 'CON', 'LCO': 'CON', 'CO': 'CON',
            'VAM': 'VAM', 'VILLA ALEMANA': 'VAM', 'ALEMANA': 'VAM', 'VIL': 'VAM', 'VALE': 'VAM', 'VL': 'VAM',
            'SGA': 'SGA', 'SARGENTO ALDEA': 'SGA', 'ALDEA': 'SGA', 'SAR': 'SGA', 'SA': 'SGA',
            'PEN': 'PEN', 'PENABLANCA': 'PEN', 'PEÑABLANCA': 'PEN', 'PENA BLANCA': 'PEN', 'PENA': 'PEN', 'PE': 'PEN',
            'LIM': 'LIM', 'LIMACHE': 'LIM', 'LI': 'LIM'
        }

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
                if any(w in combo_norm for w in ['TOTAL', 'BORDO', 'CARGA', 'PASAJERO']):
                    if not any(exc in combo_norm for exc in ['THDR', 'TREN', 'HORA', 'VIA']):
                        col_mapping[c_idx] = 'CargaMax'

        df = pd.DataFrame()
        data_rows = full.iloc[header_idx + 1:].copy()
        
        for c_idx, col_name in col_mapping.items():
            if isinstance(c_idx, int) and c_idx < full.shape[1]: df[col_name] = data_rows.iloc[:, c_idx].values
                
        fecha_global = extraer_fecha_segura(full, fname)
        if full.shape[1] > 3:
            df['Fecha_Excel_Raw'] = data_rows.iloc[:, 3].values
            df['Fecha_s'] = df['Fecha_Excel_Raw'].apply(parse_excel_date)
            df['Fecha_s'] = df['Fecha_s'].fillna(fecha_global).replace('', fecha_global).ffill()
        else:
            df['Fecha_s'] = fecha_global
                
        if 'Hora Origen' not in df.columns: df['Hora Origen'] = ''
        if 'Nro_THDR_raw' not in df.columns: df['Nro_THDR_raw'] = ''
        if 'Tren' not in df.columns: df['Tren'] = ''
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
        try:
            if pd.isna(v): return 0
            return int(float(v))
        except: return 0
    t_i = row.get('t_ini')
    via = row.get('via_op', row.get('Via', 1))
    nro_viaje = clean_primary_key(row.get('nro_viaje', ''))
    thdr_date = row.get('Fecha_str')
    sub = df_pax[df_pax['Via'] == via].copy()
    if sub.empty: return EMPTY
    if 'Fecha_s' in sub.columns and thdr_date and thdr_date != '2026-01-01':
        sub_date = sub[sub['Fecha_s'] == thdr_date]
        if not sub_date.empty: sub = sub_date
        else: return EMPTY 

    def time_diff(t1, t2):
        if pd.isna(t1) or pd.isna(t2): return 9999
        d = abs(float(t1) - float(t2))
        return min(d, 1440 - d)

    sub['diff'] = sub['t_ini_p'].apply(lambda x: time_diff(x, t_i))
    if nro_viaje != '' and 'Nro_THDR' in sub.columns:
        sub['Nro_THDR_cmp'] = sub['Nro_THDR'].apply(clean_primary_key)
        match_exacto = sub[(sub['Nro_THDR_cmp'] == nro_viaje) & (sub['Nro_THDR_cmp'] != '')]
        if not match_exacto.empty:
            best = match_exacto.iloc[0]
            pax_est_d = {c: _to_int(best.get(c, 0)) for c in PAX_COLS}
            return pax_est_d, _to_int(best.get('CargaMax', 0)), mins_to_time_str(best.get('t_ini_p')), str(best.get('Nro_THDR', '')), best.name

    if pd.notna(t_i):
        best_match = sub.loc[sub['diff'].idxmin()]
        if best_match['diff'] <= 15: 
            pax_est_d = {c: _to_int(best_match.get(c, 0)) for c in PAX_COLS}
            return pax_est_d, _to_int(best_match.get('CargaMax', 0)), mins_to_time_str(best_match.get('t_ini_p')), str(best_match.get('Nro_THDR', '')), best_match.name

    return EMPTY

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
                        'tipo_tren': 'XT-100', 'doble': es_doble, 'num_servicio': str(tren_val), 'svc_type': ruta,
                        'maniobra': None
                    })
                    
        df_viajes = pd.DataFrame(viajes)
        if not df_viajes.empty: df_viajes = df_viajes.drop_duplicates(subset=['_id'])
        return df_viajes, "ok"
    except Exception as e: return pd.DataFrame(), str(e)

# =============================================================================
# 12. CACHÉ Y CARGADORES DE STREAMLIT (UI)
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

@st.cache_data(show_spinner="Procesando THDR Estándar…")
def build_thdr_v71(blobs_v1, blobs_v2):
    all_parts = []
    err = []
    for blobs, via_default in [(blobs_v1, 1), (blobs_v2, 2)]:
        for nm, data in blobs:
            df, msg = procesar_thdr(data, nm, via_default)
            if not df.empty:
                all_parts.append(df)
            else:
                err.append(f"[{nm}]: {msg}")
    
    if len(all_parts) > 0:
        df_master = pd.concat(all_parts, ignore_index=True)
        df1 = df_master[df_master['Via'] == 1].copy()
        df2 = df_master[df_master['Via'] == 2].copy()
        if not df1.empty and not df2.empty:
            df1, df2 = calcular_dwell(df1, df2)
        return df1, df2, err
    return pd.DataFrame(), pd.DataFrame(), err

@st.cache_data(show_spinner="Cargando pasajeros…")
def build_pax_v71(blobs_v1, blobs_v2):
    parts, err = [], []
    for blobs, via_default in [(blobs_v1, 1), (blobs_v2, 2)]:
        for nm, data in blobs:
            try: 
                parts.append(cargar_pax(data, nm, via_default))
            except Exception as e: 
                err.append(f"[{nm}]: {e}")
    if len(parts) > 0: 
        return pd.concat(parts, ignore_index=True), err
    return pd.DataFrame(), err

def _all_blobs(f_uploader, gh_key): 
    return tuple(leer(f_uploader) + st.session_state.get(gh_key, []))

# =============================================================================
# 13. DIAGRAMA Y DASHBOARDS (RENDERING UI REUTILIZABLE)
# =============================================================================
def draw_diagram(df_act_plot, ser_accum_plot, seat_accum_plot, hora_str, titulo_extra="", active_sers_list=SER_DATA, gap_vias=200):
    W = 1200
    KM_SCALE = W / KM_TOTAL
    def xkm(km): return km * KM_SCALE

    Y_V2 = 260
    Y_V1 = Y_V2 - gap_vias
    MARGIN = 90
    Y_44KV = Y_V2 + 90
    Y_SER  = Y_V2 + 40
    y_min  = Y_V1 - MARGIN
    y_max  = Y_V2 + 150
    H      = max(320, y_max - y_min)
    y_mid  = (Y_V1 + Y_V2) / 2

    fig = go.Figure()
    fig.update_layout(
        height=H, margin=dict(l=10, r=10, t=45, b=10),
        xaxis=dict(range=[0, W], showgrid=False, zeroline=False, showticklabels=False, fixedrange=True),
        yaxis=dict(range=[y_min, y_max], showgrid=False, zeroline=False, showticklabels=False, fixedrange=True),
        plot_bgcolor='white', paper_bgcolor='white',
        font=dict(color='black'), showlegend=False, hovermode='closest',
        title=dict(text=f"MERVAL - {hora_str} {titulo_extra}  |  🔴 V2 LI→PU   🔵 V1 PU→LI", font=dict(size=12, color='black'), x=0.5),
    )

    fig.add_shape(type='line', x0=0, x1=W, y0=Y_V2, y1=Y_V2, line=dict(color='#c62828', width=5))
    fig.add_shape(type='line', x0=0, x1=W, y0=Y_V1, y1=Y_V1, line=dict(color='#1565c0', width=5))
    fig.add_shape(type='line', x0=0, x1=W, y0=Y_44KV, y1=Y_44KV, line=dict(color='#FBC02D', width=3, dash='dash'))
    fig.add_annotation(x=W/2, y=Y_44KV+10, text="<b>Línea AC 44kV</b>", showarrow=False, font=dict(size=10, color='#FBC02D'))

    for i, (ec, km) in enumerate(zip(EC, KM_ACUM[:N_EST])):
        xp = xkm(km)
        fig.add_shape(type='line', x0=xp, x1=xp, y0=Y_V1-20, y1=Y_V2+20, line=dict(color='#bbb', width=1, dash='dot'))
        y_ec = y_mid + (12 if i % 2 == 0 else -12)
        fig.add_annotation(x=xp, y=y_ec, text=ec, showarrow=False, font=dict(size=8, color='#555'), xanchor='center', yanchor='middle')

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
            color, fill, dash_st = '#FBC02D', '#FFF3E0', 'dot'
            txt_color = '#E65100'
            fig.add_shape(type='line', x0=xp, x1=xp, y0=Y_SER-15, y1=Y_V1, line=dict(color='#E65100', width=2))
            lbl = f"<b>{nombre_ser}</b><br><span style='font-size:8px'>{val:,.0f} kWh</span>"
        else:
            color, fill, dash_st = '#9E9E9E', '#F5F5F5', 'dash'
            txt_color = '#757575'
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
        via   = row['Via']
        xp    = xkm(row['km_pos'])
        y_ln  = Y_V2 if via == 2 else Y_V1
        color = '#c62828' if via == 2 else '#1565c0'
        
        doble_tramo = row.get('doble', False)
        man = row.get('maniobra')
        if man == 'CORTE_BTO' or man == 'CORTE_PU_SA_BTO':
            doble_tramo = True if row['km_pos'] <= KM_ACUM[14] else False
        elif man == 'ACOPLE_BTO':
            doble_tramo = False if row['km_pos'] > KM_ACUM[14] else True
        elif man == 'CORTE_SA':
            doble_tramo = True if row['km_pos'] <= KM_ACUM[18] else False
        elif man == 'ACOPLE_SA':
            doble_tramo = False if row['km_pos'] > KM_ACUM[18] else True
            
        tip   = row.get('tooltip', '')
        r_c   = 18 if doble_tramo else 11

        serv = str(row.get('num_servicio', ''))
        motriz = str(row.get('motriz_num', ''))
        tipo = str(row.get('tipo_tren', 'XT-100'))
        
        if tipo == 'SFE': xt_lbl = f"SFE-{motriz}" if motriz else "SFE"
        elif tipo == 'XT-M': xt_lbl = f"XTM-{motriz}" if motriz else "XTM"
        else: xt_lbl = f"XT-{motriz}" if motriz else "XT"

        kwh_n = float(row.get('kwh_neto', 0))
        pax_v = int(row.get('pax_inst', 0)) 
        sep_r = row.get('sep_next', '—')
        sep_s = f"↔ {sep_r} min" if sep_r != '—' else ''

        side = label_side.get(idx, 'up')
        dy_mot = +(r_c + 18) if side == 'up' else -(r_c + 18)
        dy_svc = -(r_c + 16) if side == 'up' else +(r_c + 16)
        dy_sep = -(r_c + 32) if side == 'up' else +(r_c + 32)

        fig.add_trace(go.Scatter(x=[xp], y=[y_ln], mode='markers',
            marker=dict(size=r_c*2, color=color, line=dict(color='black', width=2)),
            hovertext=tip, hovertemplate='%{hovertext}<extra></extra>', showlegend=False))

        fig.add_annotation(x=xp, y=y_ln + dy_mot, text=f"<b>{xt_lbl}</b>", showarrow=False, font=dict(size=11, color='#111'), bgcolor='rgba(255,255,255,0.7)')
        fig.add_annotation(x=xp, y=y_ln + dy_svc, text=f"<b>Serv. {serv}</b>", showarrow=False, font=dict(size=10, color='#111'), bgcolor='rgba(255,255,255,0.7)')
        fig.add_annotation(x=xp - r_c - 18, y=y_ln, text=f"{kwh_n:.0f} kWh", showarrow=False, font=dict(size=9, color='#2E7D32'), xanchor='right')
        fig.add_annotation(x=xp + r_c + 18, y=y_ln, text=f"{pax_v} pax", showarrow=False, font=dict(size=9, color='#1565c0'), xanchor='left')
        if sep_s: fig.add_annotation(x=xp, y=y_ln + dy_sep, text=f"<b>{sep_s}</b>", showarrow=False, font=dict(size=12, color='#111'))

    return fig

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
    k1.metric("🔋 Tracción", f"{t_trac:,.0f} kWh")
    k2.metric("❄️ Auxiliar", f"{t_aux:,.0f} kWh")
    k3.metric("♻️ Regen Bruta", f"{regen_bruta:,.0f} kWh", help="Energía recuperada en motores")
    k4.metric("✅ Regen Útil", f"{t_regen:,.0f} kWh", delta=f"+{tasa_global:.1f}% a red", delta_color="normal")
    k5.metric("🔥 Reóstato", f"{t_reostat:,.0f} kWh", delta=f"−{100-tasa_global:.1f}% disipado", delta_color="inverse")
    k6.metric("💡 IDE Comercial", f"{ide_global:.3f} kWh/km", help="kWh neto / Tren-km (sin vacíos)")
    st.caption(f"η̄ receptividad promedio: **{eta_prom*100:.1f}%**")
    st.divider()

def render_gemelo_digital(df_dia, df_dia_e, active_sers, fecha_sel, pct_trac, use_rm, use_pend, estacion_anio, prefix_key, gap_vias, pax_dia_total=0):
    """Función unificada que renderiza el Reproductor del Gemelo Digital (DRY Principle)"""
    
    # --- FIX V117: Saneamiento de esquema dinámico (Schema Enforcement) ---
    if 'maniobra' not in df_dia.columns:
        df_dia['maniobra'] = None
    if 'maniobra' not in df_dia_e.columns:
        df_dia_e['maniobra'] = None
        
    cf, cm = st.columns([3,2])
    with cm: modo = st.radio("Modo", ["🔒 Estático","▶️ Animado"], horizontal=True, key=f"modo_{prefix_key}")

    if f'min_slider_{prefix_key}' not in st.session_state: st.session_state[f'min_slider_{prefix_key}'] = 480.0
    if f'play_{prefix_key}' not in st.session_state: st.session_state[f'play_{prefix_key}'] = False
    if modo != "▶️ Animado": st.session_state[f'play_{prefix_key}'] = False

    if st.session_state[f'play_{prefix_key}']:
        step_size = 0.2 * float(st.session_state.get(f'vs1_{prefix_key}', 1.0))
        st.session_state[f'min_slider_{prefix_key}'] = min(1439.0, st.session_state[f'min_slider_{prefix_key}'] + step_size)
        if st.session_state[f'min_slider_{prefix_key}'] >= 1439.0: st.session_state[f'play_{prefix_key}'] = False

    c1,c2,c3,c4,c5,_ = st.columns([1,1,1,1,1,2])
    if c1.button("−15",key=f"m15_{prefix_key}"): st.session_state[f'min_slider_{prefix_key}']=max(0.0,st.session_state[f'min_slider_{prefix_key}']-15.0); st.rerun()
    if c2.button("−1", key=f"m1_{prefix_key}"):  st.session_state[f'min_slider_{prefix_key}']=max(0.0,st.session_state[f'min_slider_{prefix_key}']-1.0);  st.rerun()
    if modo == "▶️ Animado":
        if c3.button("⏸" if st.session_state[f'play_{prefix_key}'] else "▶️", key=f"pb_{prefix_key}"):
            st.session_state[f'play_{prefix_key}'] = not st.session_state[f'play_{prefix_key}']; st.rerun()
    if c4.button("+1", key=f"p1_{prefix_key}"):  st.session_state[f'min_slider_{prefix_key}']=min(1439.0,st.session_state[f'min_slider_{prefix_key}']+1.0);  st.rerun()
    if c5.button("+15",key=f"p15_{prefix_key}"): st.session_state[f'min_slider_{prefix_key}']=min(1439.0,st.session_state[f'min_slider_{prefix_key}']+15.0); st.rerun()

    hora_m1 = st.slider("🕐", 0.0, 1439.0, st.session_state[f'min_slider_{prefix_key}'], step=0.1, key=f"min_slider_ui_{prefix_key}")
    st.session_state[f'min_slider_{prefix_key}'] = hora_m1
    hora_s1 = f"{int(hora_m1)//60:02d}:{int(hora_m1)%60:02d}"

    if modo == "▶️ Animado":
        st.select_slider("Velocidad", options=[0.5, 1, 2, 5, 10], value=st.session_state.get(f'vs1_{prefix_key}', 1.0), format_func=lambda x: f"×{x}", key=f"vs1_{prefix_key}")

    st.markdown(
        f"<span style='font-size:2.2rem;font-weight:700;letter-spacing:2px;'>⏱ {hora_s1}</span>"
        f"<span style='font-size:0.9rem;color:#666;'> &nbsp;·&nbsp; {fecha_sel} &nbsp;·&nbsp; "
        f"⚙️ {pct_trac}% Tracción"
        + (" &nbsp;·&nbsp; ▶️" if st.session_state[f'play_{prefix_key}'] else "")
        + "</span>",
        unsafe_allow_html=True
    )

    df_act = df_dia_e[(df_dia_e['t_ini']<=hora_m1) & (df_dia_e['t_fin']>hora_m1)].copy()

    instant_ser_demands_kw = {s[1]: 0.0 for s in active_sers}
    
    if not df_act.empty:
        frac_act = (hora_m1 - df_act['t_ini']) / np.maximum(0.001, df_act['t_fin'] - df_act['t_ini'])
        df_act['kwh_neto'] = df_act['kwh_viaje_neto'] * frac_act
        
        df_act['km_pos'] = df_act.apply(lambda r: km_at_t(r['t_ini'], r['t_fin'], hora_m1, r['Via'], use_rm, r['km_orig'], r['km_dest'], r.get('nodos')), axis=1)
        
        def _vel_real(r):
            km_now = r['km_pos']
            km_next = km_at_t(r['t_ini'], r['t_fin'], hora_m1 + 0.01, r['Via'], use_rm, r['km_orig'], r['km_dest'], r.get('nodos'))
            if abs(km_next - km_now) < 0.0001: return 0.0 
            return vel_at_km(km_now, r['Via'], use_rm)
            
        df_act['vel'] = df_act.apply(_vel_real, axis=1)
        df_act['km_rec'] = df_act.apply(lambda r: max(0.0, abs(r['km_pos'] - r['km_orig'])), axis=1)
        df_act['pax_inst'] = df_act.apply(lambda r: get_pax_at_km(r.get('pax_d', {}), r['km_pos'], r['Via'], r.get('pax_abordo', 0)), axis=1)

        def _sep_next(row, df_via):
            km = row['km_pos']; vel = row['vel']
            if vel < 1: return '—'
            ahead = df_via[df_via['km_pos'] > km] if row['Via'] == 1 else df_via[df_via['km_pos'] < km]
            if ahead.empty: return '—'
            d = abs(ahead['km_pos'] - km).min()
            return f"{round(d/max(1, vel)*60,1)} min ({d:.1f} km)"
        
        df_act['sep_next'] = df_act.apply(lambda r: _sep_next(r, df_act[df_act['Via']==r['Via']].drop(index=r.name)), axis=1)

        def _make_tooltip_and_power(row):
            m_num = str(row.get('motriz_num', ''))
            tipo = str(row.get('tipo_tren', 'XT-100'))
            serv = str(row.get('num_servicio', ''))
            
            nombre_tren = f"{tipo}-{m_num}" if m_num else tipo
            
            doble_tramo = row.get('doble', False)
            man = row.get('maniobra')
            if man == 'CORTE_BTO':
                doble_tramo = True if row['km_pos'] <= KM_ACUM[14] else False
            elif man == 'CORTE_PU_SA_BTO':
                doble_tramo = True if row['km_pos'] <= KM_ACUM[14] else False
            elif man == 'ACOPLE_BTO':
                doble_tramo = False if row['km_pos'] > KM_ACUM[14] else True
            elif man == 'CORTE_SA':
                doble_tramo = True if row['km_pos'] <= KM_ACUM[18] else False
            elif man == 'ACOPLE_SA':
                doble_tramo = False if row['km_pos'] > KM_ACUM[18] else True
                
            cab = f"<b>{nombre_tren} (Serv. {serv})</b>  {'🚈 DOBLE' if doble_tramo else '🚃 Simple'} "
            if man == 'CORTE_BTO': cab += "(✂️ Corte en BTO)<br>"
            elif man == 'CORTE_PU_SA_BTO': cab += "(✂️ Corte en BTO, Termina SA)<br>"
            elif man == 'ACOPLE_BTO': cab += "(🔗 Acople en BTO)<br>"
            elif man == 'CORTE_SA': cab += "(✂️ Corte en SA)<br>"
            elif man == 'ACOPLE_SA': cab += "(🔗 Acople en SA)<br>"
            else: cab += "<br>"
            
            cab += f"Vía {row['Via']}  |  km {row['km_pos']:.2f}  |  {int(row['vel'])} km/h<br>"
            
            state, v_kmh = get_train_state_and_speed(hora_m1, row['Via'], use_rm, row['km_orig'], row['km_dest'], row.get('nodos'))
            state_icon = "🟢 Traccionando" if state == "ACCEL" else "🔴 Frenando (Regen)" if state == "BRAKE" else "🟡 Velocidad Crucero"
            cab += f"{state_icon}<br>─" * 35 + "<br>"
            
            f_flota = FLOTA.get(tipo, FLOTA["XT-100"])
            n_unidades = 2 if doble_tramo else 1
            tara_base = (f_flota['tara_t'] + f_flota['m_iner_t']) * n_unidades
            pax_v = int(row.get('pax_inst', 0))
            masa_pax_t = (pax_v * PAX_KG) / 1000.0
            masa_total = tara_base + masa_pax_t
            
            v_ms = v_kmh / 3.6
            if n_unidades == 2: f_davis = (f_flota['davis_A'] * 2) + (f_flota['davis_B'] * 2 * v_kmh) + (f_flota['davis_C'] * 1.35 * (v_kmh**2))
            else: f_davis = f_flota['davis_A'] + f_flota['davis_B'] * v_kmh + f_flota['davis_C'] * (v_kmh**2)
            
            p_aux_kw = calcular_aux_dinamico(f_flota['aux_kw'] * n_unidades, hora_m1 / 60.0, pax_v, f_flota.get('cap_max', 398) * n_unidades, estacion_anio, state)
            eta_m = f_flota.get('eta_motor', 0.92)
            
            if state == "ACCEL": p_mech = f_flota['p_max_kw'] * n_unidades * (pct_trac / 100.0)
            elif state == "CRUISE": p_mech = (f_davis * v_ms) / 1000.0
            elif state == "BRAKE": p_mech = -f_flota.get('p_freno_max_kw', f_flota['p_max_kw']*1.2) * n_unidades * 0.6
            else: p_mech = 0.0
            
            if p_mech > 0: p_elec_kw = (p_mech / eta_m) + p_aux_kw
            elif p_mech < 0: p_elec_kw = (p_mech * ETA_REGEN_NETA) + p_aux_kw
            else: p_elec_kw = p_aux_kw
            
            dist_kw = distribuir_potencia_sers_kw(p_elec_kw, row['km_pos'], active_sers)
            for s_n, v_kw in dist_kw.items():
                instant_ser_demands_kw[s_n] += v_kw
            
            pax_sec = f"<b>🧑 Pax a Bordo Tramo: {pax_v}</b><br>⚖️ Masa Dinámica: {masa_total:.1f} t<br>─" * 35 + "<br>"
            e_sec = f"⚡ <b>Energía acumulada:</b><br>NETO: {row['kwh_neto']:.1f} kWh<br>─" * 35 + "<br>"
            return cab + pax_sec + e_sec + f"↔️ <b>Siguiente:</b> {row['sep_next']}"

        df_act['tooltip'] = df_act.apply(_make_tooltip_and_power, axis=1)

    vacios_dia = get_vacios_dia(df_dia)
    for idx, row in df_dia[df_dia['maniobra'].notnull()].iterrows():
        man = row['maniobra']
        t_arr_bto = row['t_ini'] + 40.0 if row['Via'] == 1 else row['t_ini'] + 20.0
        t_arr_sa = row['t_ini'] + 47.0 if row['Via'] == 1 else row['t_ini'] + 13.0
        dist_sa_eb = abs(KM_ACUM[18] - KM_ACUM[14])
        
        if man == 'CORTE_BTO' or man == 'CORTE_PU_SA_BTO':
            vacios_dia.append({'t_asigned': t_arr_bto, 'tipo': row['tipo_tren'], 'doble': False, 'cochera': True, 'dist': 2.0, 'motriz_num': f"{row.get('motriz_num', '')}-B", 'origen_txt': 'El Belloto (Corte)', 'destino_txt': 'Taller EB', 'servicio_previo': row.get('num_servicio', ''), 'servicio_siguiente': '—', 'km_orig': KM_ACUM[14], 'km_dest': KM_ACUM[14]})
        elif man == 'ACOPLE_BTO':
            vacios_dia.append({'t_asigned': t_arr_bto - 5.0, 'tipo': row['tipo_tren'], 'doble': False, 'cochera': True, 'dist': 2.0, 'motriz_num': f"{row.get('motriz_num', '')}-B", 'origen_txt': 'Taller EB', 'destino_txt': 'El Belloto (Acople)', 'servicio_previo': '—', 'servicio_siguiente': row.get('num_servicio', ''), 'km_orig': KM_ACUM[14], 'km_dest': KM_ACUM[14]})
        elif man == 'CORTE_SA':
            vacios_dia.append({'t_asigned': t_arr_sa, 'tipo': row['tipo_tren'], 'doble': False, 'cochera': True, 'dist': dist_sa_eb + 2.0, 'motriz_num': f"{row.get('motriz_num', '')}-B", 'origen_txt': 'Sargento Aldea (Corte)', 'destino_txt': 'Taller EB', 'servicio_previo': row.get('num_servicio', ''), 'servicio_siguiente': '—', 'km_orig': KM_ACUM[18], 'km_dest': KM_ACUM[14]})
        elif man == 'ACOPLE_SA':
            vacios_dia.append({'t_asigned': t_arr_sa - 20.0, 'tipo': row['tipo_tren'], 'doble': False, 'cochera': True, 'dist': dist_sa_eb + 2.0, 'motriz_num': f"{row.get('motriz_num', '')}-B", 'origen_txt': 'Taller EB', 'destino_txt': 'Sargento Aldea (Acople)', 'servicio_previo': '—', 'servicio_siguiente': row.get('num_servicio', ''), 'km_orig': KM_ACUM[14], 'km_dest': KM_ACUM[18]})

    vacios_hasta_ahora = [v for v in vacios_dia if v['t_asigned'] <= hora_m1]
    vacio_count = len(vacios_hasta_ahora)
    vacio_km_total = sum(v['dist'] * (2 if v.get('doble', False) else 1) for v in vacios_hasta_ahora)
    vacio_kwh_total = 0.0

    ser_accum_1 = {name: 0.0 for _, name in active_sers}
    km_cochera_base = KM_ACUM[14]
    energy_by_fleet = {'XT-100': 0.0, 'XT-M': 0.0, 'SFE': 0.0}
    
    for v in vacios_hasta_ahora:
        is_local_move = (v.get('km_orig') == v.get('km_dest'))
        km_fake_fin = v['km_orig'] + v['dist'] if is_local_move else v['km_dest']
        via_vacia = 1 if v['km_orig'] <= km_fake_fin else 2
        
        trc_v, aux_v, reg_v, _, _, t_horas_v = simular_tramo_termodinamico(
            v['tipo'], v.get('doble', False), v['km_orig'], km_fake_fin, 
            via_vacia, pct_trac, use_rm, use_pend if not is_local_move else False, 
            None, {}, 0, 20.0 if is_local_move else None, None, estacion_anio, v.get('t_asigned', 480.0)
        )
        
        e_pant_vacio = trc_v + aux_v - reg_v
        
        if active_sers:
            km_centroid = v['km_orig'] if is_local_move else (v['km_orig'] + v['km_dest']) / 2.0
            distrib_sers = distribuir_energia_sers(e_pant_vacio, t_horas_v, v['km_orig'], km_fake_fin, active_sers)
            for s_name, e_val in distrib_sers.items():
                ser_accum_1[s_name] += e_val
                
        vacio_kwh_total += e_pant_vacio
        energy_by_fleet[v['tipo']] += e_pant_vacio

    t_regen_acum = 0.0
    t_reostato_acum = 0.0

    for idx, r in df_dia_e[df_dia_e['t_ini'] <= hora_m1].iterrows():
        t_eval = min(hora_m1, r['t_fin'])
        frac = (t_eval - r['t_ini']) / max(0.001, r['t_fin'] - r['t_ini'])
        km_now = km_at_t(r['t_ini'], r['t_fin'], t_eval, r['Via'], use_rm, r['km_orig'], r['km_dest'], r.get('nodos'))
        
        e_pantografo_frac = (r['kwh_viaje_trac'] + r['kwh_viaje_aux'] - r['kwh_viaje_regen']) * frac
        t_horas_frac = (t_eval - r['t_ini']) / 60.0
        
        distrib_sers = distribuir_energia_sers(e_pantografo_frac, t_horas_frac, r['km_orig'], km_now, active_sers)
        for s_name, e_val in distrib_sers.items():
            ser_accum_1[s_name] += e_val 

    df_acum = df_dia_e[df_dia_e['t_ini'] <= hora_m1]
    if not df_acum.empty:
        t_trac, t_aux = df_acum['kwh_viaje_trac'].sum(), df_acum['kwh_viaje_aux'].sum()
        t_regen, t_reostato = df_acum['kwh_viaje_regen'].sum(), df_acum['kwh_reostato'].sum()
        t_neto = df_acum['kwh_viaje_neto'].sum()
        t_regen_acum = t_regen

        for f_type in ['XT-100', 'XT-M', 'SFE']:
            sub = df_acum[df_acum['tipo_tren'] == f_type]
            if not sub.empty:
                energy_by_fleet[f_type] += sub['kwh_viaje_neto'].sum()

    total_ser_kwh_44kv = sum(max(0.0, val) for val in ser_accum_1.values()) / ETA_SER_RECTIFICADOR
    
    t_elapsed_h = max(0.001, hora_m1 / 60.0)
    avg_demands_kw = {k: max(0.0, v) / ETA_SER_RECTIFICADOR / t_elapsed_h for k, v in ser_accum_1.items()}
    flujo_avg = calcular_flujo_ac_nodo(avg_demands_kw)
    total_ac_loss_kwh = flujo_avg['P_loss_kw'] * (1.15**2) * t_elapsed_h

    seat_accum_1 = (total_ser_kwh_44kv + total_ac_loss_kwh) / 0.99

    st.plotly_chart(draw_diagram(df_act, {k: max(0.0, v) for k, v in ser_accum_1.items()}, seat_accum_1, hora_s1, "", active_sers, gap_vias), use_container_width=True)

    st.divider()
    n_circ = len(df_act) if not df_act.empty else 0
    n_d    = int(df_act['doble'].sum()) if not df_act.empty else 0
    n_v1   = int((df_act['Via']==1).sum()) if not df_act.empty else 0
    n_v2   = int((df_act['Via']==2).sum()) if not df_act.empty else 0
    pax_t  = int(df_act['pax_inst'].sum()) if not df_act.empty else 0
    kwh_t  = round(df_act['kwh_neto'].sum(),0) if (not df_act.empty and 'kwh_neto' in df_act.columns) else 0
    regen_t= round(t_regen_acum, 0)
    trenkm = round(df_act['tren_km'].sum(),1) if (not df_act.empty and 'tren_km' in df_act.columns) else 0.0
    km_rec = df_act['km_rec'].sum() if (not df_act.empty and 'km_rec' in df_act.columns) else 0
    ide_i  = round(kwh_t/max(1, km_rec), 3) if km_rec > 0 else 0.0

    st.markdown(f"#### 🕐 Instantáneo — {hora_s1}")
    r1a,r1b,r1c,r1d = st.columns(4)
    r1a.metric("🚆 Servicios", n_circ)
    r1b.metric("V1→Limache", n_v1)
    r1c.metric("V2←Puerto", n_v2)
    r1d.metric("🚈 Doble (Original)", n_d)
    
    r2a,r2b,r2c,r2d = st.columns(4)
    r2a.metric("🧑‍🤝‍🧑 Pax en Vía Inst.", f"{pax_t:,}")
    r2b.metric("⚡ kWh neto", f"{kwh_t:,.0f}", f"−{regen_t:,.0f} regen util")
    r2c.metric("📏 Tren-km Inst.", f"{trenkm:,.1f}")
    r2d.metric("💡 IDE inst.", f"{ide_i:.3f} kWh/km")

    # =========================================================================
    # --- V98: MONITOR SQUEEZE CONTROL (ESTRÉS ELÉCTRICO INSTANTÁNEO) ---
    # =========================================================================
    st.divider()
    st.markdown("#### 🔌 Cargabilidad Instantánea de Subestaciones (Squeeze Control)")
    st.caption("Muestra la demanda real en kW que los trenes exigen a la red en este mismo segundo. Los rectificadores son unidireccionales (Diodos): si el valor es 0 kW, la subestación está bloqueando energía inversa y el exceso se quema en las resistencias del tren (Reóstato).")
    
    if not active_sers:
        st.info("No hay SERs activas para monitorear.")
    else:
        flujo_ac_dc = calcular_flujo_ac_nodo(instant_ser_demands_kw)
        
        st.markdown(f"<div style='text-align:right; font-size:12px; color:#c62828;'>🔥 Pérdidas térmicas AC (I²R) de la red troncal en este instante: <b>{flujo_ac_dc.get('P_loss_kw', 0.0):.1f} kW</b></div>", unsafe_allow_html=True)
        
        cols_ser = st.columns(len(active_sers))
        for i, ser_info in enumerate(active_sers):
            s_name = ser_info[1]
            cap_kw = SER_CAPACITY_KW.get(s_name, 3000.0)
            
            dem_kw_bruta = instant_ser_demands_kw.get(s_name, 0.0)
            dem_kw = max(0.0, dem_kw_bruta) 
            
            vac_actual = flujo_ac_dc.get(s_name, {}).get('Vac', V_NOMINAL_AC)
            vdc_actual = flujo_ac_dc.get(s_name, {}).get('Vdc', 3000.0)
            
            pct_carga = (dem_kw / cap_kw) * 100.0
            
            if dem_kw == 0.0 and dem_kw_bruta < -10.0:
                color_bar = "#9E9E9E" 
                texto_estado = "Bloqueo Diodos (Quemando en Reóstato)"
            elif vdc_actual < 2600.0:
                color_bar = "#C62828"
                texto_estado = "⚠️ SQUEEZE CONTROL (Bajo Voltaje)"
            elif vdc_actual < 2850.0:
                color_bar = "#F9A825"
                texto_estado = "Estrés Moderado (Caída AC)"
            elif pct_carga <= 65:
                color_bar = "#1565C0"
                texto_estado = "Carga Óptima"
            else:
                color_bar = "#F9A825"
                texto_estado = "Capacidad exigida"
                
            with cols_ser[i]:
                st.markdown(f"**{s_name}** ({cap_kw/1000:.1f} MVA)")
                st.markdown(f"<div style='font-size:18px; font-weight:bold; color:{color_bar};'>{dem_kw:,.0f} kW</div>", unsafe_allow_html=True)
                st.markdown(f"<div style='font-size:13px; font-family:monospace; margin-bottom:4px;'>"
                            f"<span style='color:#666;'>Tensión AC:</span> <b>{vac_actual/1000:.2f} kV</b><br>"
                            f"<span style='color:#666;'>Barra DC:</span> <b style='color:{color_bar};'>{vdc_actual:.0f} Vcc</b></div>", unsafe_allow_html=True)
                st.markdown(f"<div style='width:100%; background-color:#e0e0e0; border-radius:4px; margin-bottom: 4px;'><div style='width:{min(100, max(0, pct_carga))}%; background-color:{color_bar}; height:8px; border-radius:4px;'></div></div>", unsafe_allow_html=True)
                st.markdown(f"<span style='font-size:11px; color:#666;'>Factor Uso: {pct_carga:.1f}% - {texto_estado}</span>", unsafe_allow_html=True)

    df_comp = df_dia_e[df_dia_e['t_fin']<=hora_m1]
    df_inic = df_dia_e[df_dia_e['t_ini']<=hora_m1]
    n_inic  = len(df_inic)
    n_comp  = len(df_comp)
    
    km_ac   = round(df_comp['tren_km'].sum(), 1) if not df_comp.empty else 0.0
    ide_ac  = round(seat_accum_1 / max(1, df_inic['tren_km'].sum()), 3) if not df_inic.empty and df_inic['tren_km'].sum() > 0 else 0.0

    # =========================================================================
    # --- DASHBOARD ACUMULADO Y AUDITORÍA ---
    # =========================================================================
    st.divider()
    st.markdown(f"#### 📊 Acumulado 00:00 → {hora_s1}")
    
    if not df_inic.empty:
        st.markdown("##### 🚆 Total de Servicios Despachados por Trayecto y Flota")
        
        trayectos = df_inic.groupby(['Via', 'svc_type', 'tipo_tren']).size().unstack(fill_value=0)
        for col in ['XT-100', 'XT-M', 'SFE']:
            if col not in trayectos.columns:
                trayectos[col] = 0
        
        cols_svc_ac = st.columns(len(trayectos))
        ci = 0
        for (via, stype), row_counts in trayectos.iterrows():
            total_t = row_counts.sum()
            xt100_c = row_counts['XT-100']
            xtm_c = row_counts['XT-M']
            sfe_c = row_counts['SFE']
            
            color = "#1565C0" if via == 1 else "#c62828"
            dot = "🔵" if via == 1 else "🔴"
            
            html_card = f"""
            <div style='border-left: 4px solid {color}; padding-left: 10px; margin-bottom: 15px;'>
                <span style='font-size:12px; color:#666; font-weight:bold;'>{dot} {stype}</span><br>
                <span style='font-size:24px; font-weight:bold; color:#111;'>{total_t}</span><br>
                <span style='font-size:11px; color:#555;'>XT-100: <b style='color:#111;'>{xt100_c}</b> | XT-M: <b style='color:#111;'>{xtm_c}</b> | SFE: <b style='color:#111;'>{sfe_c}</b></span>
            </div>
            """
            cols_svc_ac[ci].markdown(html_card, unsafe_allow_html=True)
            ci += 1
        
        st.markdown("##### ⚡ Consumo Energético Acumulado por Tipo de Tren (Neto Pantógrafo)")
        e_cols = st.columns(3)
        for i, f_type in enumerate(['XT-100', 'XT-M', 'SFE']):
            tot_e = energy_by_fleet.get(f_type, 0.0)
            subset_flota = df_inic[df_inic['tipo_tren'] == f_type]
            cnt_viajes = subset_flota.shape[0]
            km_flota = subset_flota['tren_km'].sum()
            
            avg_e = (tot_e / cnt_viajes) if cnt_viajes > 0 else 0.0
            ide_flota = (tot_e / km_flota) if km_flota > 0 else 0.0
            
            html_e = f"""
            <div style='background-color:#f9f9f9; border-radius:8px; padding:15px; text-align:center; border: 1px solid #eee;'>
                <div style='font-size:14px; font-weight:bold; color:#333;'>Flota {f_type}</div>
                <div style='font-size:22px; font-weight:bold; color:#2E7D32; margin:10px 0;'>{tot_e:,.0f} kWh</div>
                <div style='font-size:12px; color:#666;'>Viajes comerciales despachados: {cnt_viajes}</div>
                <div style='font-size:13px; color:#1565C0; font-weight:bold; margin-top:5px;'>Promedio: {avg_e:,.1f} kWh/v</div>
                <div style='font-size:14px; color:#E65100; font-weight:bold; margin-top:4px;'>IDE: {ide_flota:,.2f} kWh/km</div>
            </div>
            """
            e_cols[i].markdown(html_e, unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)

        # --- V115: INCORPORACIÓN DE PANELES DE AUDITORÍA (Km Total, SER y SEAT) ---
        km_comercial_inic = df_inic['tren_km'].sum() if not df_inic.empty else 0.0
        km_total_red = km_comercial_inic + vacio_km_total

        st.markdown("##### ⚡ Consumo Acumulado por Subestación Rectificadora (SER a 44kV)")
        if active_sers:
            ser_cols = st.columns(len(active_sers))
            for i, ser_info in enumerate(active_sers):
                s_name = ser_info[1]
                e_ser_panto = ser_accum_1.get(s_name, 0.0)
                # Expandimos a 44kV sumando las pérdidas del rectificador
                e_ser_44 = max(0.0, e_ser_panto) / ETA_SER_RECTIFICADOR
                ide_ser = e_ser_44 / max(1.0, km_total_red)
                html_ser = f"""
                <div style='background-color:#FFF3E0; border-radius:8px; padding:15px; text-align:center; border: 1px solid #FFCC80;'>
                    <div style='font-size:14px; font-weight:bold; color:#E65100;'>{s_name}</div>
                    <div style='font-size:22px; font-weight:bold; color:#E65100; margin:10px 0;'>{e_ser_44:,.0f} kWh</div>
                    <div style='font-size:12px; color:#666;'>Km Total Red: {km_total_red:,.1f} km</div>
                    <div style='font-size:14px; color:#C62828; font-weight:bold; margin-top:4px;'>Aporte IDE: {ide_ser:,.3f} kWh/km</div>
                </div>
                """
                ser_cols[i].markdown(html_ser, unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)

        st.markdown("##### ⚡ Consumo Acumulado Subestación de Alta Tensión (SEAT 110/44kV)")
        ide_seat = seat_accum_1 / max(1.0, km_total_red)
        html_seat = f"""
        <div style='background-color:#FFFDE7; border-radius:8px; padding:15px; text-align:center; border: 1px solid #FFF59D;'>
            <div style='font-size:16px; font-weight:bold; color:#F57F17;'>SEAT EL SOL (Total Red + Pérdidas AC)</div>
            <div style='font-size:26px; font-weight:bold; color:#F57F17; margin:10px 0;'>{seat_accum_1:,.0f} kWh</div>
            <div style='font-size:13px; color:#666;'>Km Comercial: {km_comercial_inic:,.1f} km | Km Vacío: {vacio_km_total:,.1f} km</div>
            <div style='font-size:14px; color:#333; font-weight:bold; margin-top:4px;'>Km Total Red: {km_total_red:,.1f} km</div>
            <div style='font-size:16px; color:#C62828; font-weight:bold; margin-top:6px;'>IDE Global Real: {ide_seat:,.3f} kWh/km</div>
        </div>
        """
        st.markdown(html_seat, unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)

    a1,a2,a3,a4,a5,a6 = st.columns(6)
    with a1: st.metric("📋 Iniciados", n_inic)
    with a2: st.metric("✅ Completados", n_comp)
    with a3: st.metric("📏 Tren-km", f"{km_ac:,.0f}")
    with a4: st.metric("⚡ kWh SERs", f"{total_ser_kwh_44kv:,.0f}")
    
    with a5: st.metric("🧑‍🤝‍🧑 Pax Despachados", f"{pax_dia_total:,}")
    with a6: st.metric("💡 IDE Promedio (SEAT)", f"{ide_ac:.3f} kWh/km")

    st.divider()
    st.markdown("#### 🚉 Maniobras en Vacío (Cochera El Belloto y Transiciones)")
    st.caption("Consumo físico por tránsitos no comerciales. Incluye el carrusel a Velocidad de Consigna y restricción a 20 km/h en patios. *La energía ya está sumada a la demanda total de las SERs.*")
    v1, v2, v3 = st.columns(3)
    v1.metric("Maniobras en Vacío (Carrusel)", vacio_count)
    v2.metric("Kilometraje Improductivo", f"{vacio_km_total:,.1f} Tren-km")
    v3.metric("Consumo Eléctrico Vacío", f"{vacio_kwh_total:,.0f} kWh")

    st.divider()
    st.subheader("📈 Consumo Total y Requerimientos Aguas Arriba (SER & SEAT)")

    if not df_dia.empty:
        with st.expander("📊 Resumen de Energía del Día y Comportamiento de Subestaciones", expanded=True):
            
            st.markdown("### 🚄 Auditoría de Consumo Operativo")
            st.caption("Análisis termodinámico detallado. Evalúa el costo energético directo separando el impacto de la tecnología (Flota) y la geografía (Trayecto).")
            
            if not df_dia_e.empty:
                def agrupar_energia(df_group):
                    res = df_group.agg(
                        viajes=('_id', 'count'),
                        trac_kwh=('kwh_viaje_trac', 'sum'),
                        regen_kwh=('kwh_viaje_regen', 'sum'),
                        neto_kwh=('kwh_viaje_neto', 'sum')
                    ).reset_index()
                    res['neto_prom'] = res['neto_kwh'] / res['viajes']
                    return res
                
                res_flota = agrupar_energia(df_dia_e.groupby('tipo_tren'))
                res_flota.rename(columns={'tipo_tren': 'Flota', 'viajes': 'N° Viajes', 'trac_kwh': 'Tracción [kWh]', 'regen_kwh': 'Regen. [kWh]', 'neto_kwh': 'Neto Total [kWh]', 'neto_prom': 'Promedio [kWh/viaje]'}, inplace=True)
                for col in ['Tracción [kWh]', 'Regen. [kWh]', 'Neto Total [kWh]', 'Promedio [kWh/viaje]']: 
                    res_flota[col] = res_flota[col].round(0).astype(int)
                
                pivot_data = []
                for (via, svc), group in df_dia_e.groupby(['Via', 'svc_type']):
                    row = {
                        'Vía': "V1" if via == 1 else "V2",
                        'Trayecto': svc,
                        'Total Viajes': len(group),
                        'Total Neto [kWh]': int(round(group['kwh_viaje_neto'].sum()))
                    }
                    
                    for flota in ['XT-100', 'XT-M', 'SFE']:
                        sub = group[group['tipo_tren'] == flota]
                        n_v = len(sub)
                        row[f'N° {flota}'] = n_v
                        if n_v > 0:
                            tot_f = sub['kwh_viaje_neto'].sum()
                            tot_km = sub['tren_km'].sum()
                            row[f'Neto {flota} [kWh]'] = int(round(tot_f))
                            row[f'Prom. {flota} [kWh/v]'] = int(round(tot_f / n_v))
                            row[f'IDE {flota} [kWh/km]'] = round(tot_f / tot_km, 2) if tot_km > 0 else 0.0
                        else:
                            row[f'Neto {flota} [kWh]'] = 0
                            row[f'Prom. {flota} [kWh/v]'] = 0
                            row[f'IDE {flota} [kWh/km]'] = 0.0
                    
                    pivot_data.append(row)
                    
                df_pivot = pd.DataFrame(pivot_data)

                st.markdown("##### 🚆 Resumen Consolidado por Familia de Tren (Flota)")
                st.dataframe(res_flota, use_container_width=True)

                st.markdown("##### 🔀 Matriz Detallada: Trayectos vs Flota (Auditoría Ejecutiva con IDE)")
                st.caption("Desglose exacto de cuántos trenes de cada familia operaron un trayecto específico, su consumo total en esa ruta, el promedio unitario y su eficiencia kilométrica (IDE).")
                st.dataframe(df_pivot, use_container_width=True)

            st.divider()
            st.markdown("### Requerimientos Aguas Arriba (SER & SEAT)")
            sr1, sr2 = st.columns(2)
            with sr1:
                st.info(f"**Demanda en bornes de las SER Activas (a 44 kV): {total_ser_kwh_44kv:,.0f} kWh** \n*Considera el despacho geográfico de energía y caída de tensión dinámica a 3000 Vcc.*")
            with sr2:
                st.error(f"**Inyección Total SEAT 110/44kV (Tracción Bruta): {seat_accum_1:,.0f} kWh** \n*Considera pérdidas dinámicas de transmisión AC 44kV (I²R) integradas y eficiencia del transformador de potencia (99%).*")

            fig_pie = go.Figure(data=[go.Pie(
                labels=['Tracción', 'Auxiliar', 'Regeneración Útil', 'Pérdida Reóstato'], 
                values=[t_trac, t_aux, t_regen, t_reostato], 
                hole=.3,
                marker_colors=['#1565C0', '#F9A825', '#2E7D32', '#C62828']
            )])
            fig_pie.update_layout(title="Distribución de Energía (Trenes + Vacíos)")

            df_dia_e['hora'] = (df_dia_e['t_ini'] // 60).astype(int)
            e_hora_comercial = df_dia_e.groupby('hora')[['kwh_viaje_trac', 'kwh_viaje_aux', 'kwh_viaje_regen', 'kwh_viaje_neto']].sum().reset_index()
            
            e_hora = e_hora_comercial

            fig_hora = go.Figure()
            fig_hora.add_trace(go.Bar(x=e_hora['hora'], y=e_hora['kwh_viaje_trac'], name='Tracción', marker_color='#1565C0'))
            fig_hora.add_trace(go.Bar(x=e_hora['hora'], y=e_hora['kwh_viaje_aux'], name='Auxiliar', marker_color='#F9A825'))
            fig_hora.add_trace(go.Bar(x=e_hora['hora'], y=-e_hora['kwh_viaje_regen'], name='Regeneración Útil', marker_color='#2E7D32'))
            fig_hora.add_trace(go.Scatter(x=e_hora['hora'], y=e_hora['kwh_viaje_neto'] / ETA_SER_RECTIFICADOR, mode='lines', name='Demanda Est. SER', line=dict(color='red', width=2, dash='dot')))
            fig_hora.update_layout(barmode='relative', title="Energía por Hora con Demanda SER", xaxis_title="Hora", yaxis_title="kWh")

            ec1, ec2 = st.columns(2)
            with ec1: st.plotly_chart(fig_pie, use_container_width=True)
            with ec2: st.plotly_chart(fig_hora, use_container_width=True)

    if st.session_state[f'play_{prefix_key}']:
        time.sleep(max(0.05, 0.3 / st.session_state.get(f'vs1_{prefix_key}', 1.0))); st.rerun()

# =============================================================================
# 14. EJECUCIÓN PRINCIPAL, SIDEBAR Y ROUTING DE TABS
# =============================================================================
def main():
    with st.sidebar:
        st.header("📂 Archivos Base")
        with st.expander("🔗 Cargar desde GitHub (Batch)",expanded=False):
            urls_txt=st.text_area("Lista de URLs",placeholder="https://github.com/...",height=100)
            gh_via=st.radio("Tipo manual",["Detección Automática","THDR V1","THDR V2","Pasajeros V1","Pasajeros V2"],horizontal=False,index=0)
            if st.button("⬇️ Descargar Todo",use_container_width=True): 
                urls = [u.strip() for u in urls_txt.split('\n') if u.strip()]
                if urls:
                    success_count = 0
                    for url in urls:
                        with st.spinner(f"Descargando {url.split('/')[-1]}..."):
                            nm, data_or_err = leer_github(url)
                        if nm and isinstance(data_or_err, bytes):
                            lnm = nm.lower()
                            if gh_via == "THDR V1": k = "gh_blobs_v1"
                            elif gh_via == "THDR V2": k = "gh_blobs_v2"
                            elif gh_via == "Pasajeros V1": k = "gh_blobs_px1"
                            elif gh_via == "Pasajeros V2": k = "gh_blobs_px2"
                            else:
                                if "v1" in lnm or "via1" in lnm: 
                                    if "pax" in lnm or "pasajero" in lnm or "export" in lnm: k = "gh_blobs_px1"
                                    else: k = "gh_blobs_v1"
                                elif "v2" in lnm or "via2" in lnm:
                                    if "pax" in lnm or "pasajero" in lnm or "export" in lnm: k = "gh_blobs_px2"
                                    else: k = "gh_blobs_v2"
                                elif "pax" in lnm or "pasajero" in lnm or "export" in lnm: k = "gh_blobs_px1"
                                else: k = "gh_blobs_v1" 
                            
                            if k not in st.session_state: st.session_state[k] = []
                            st.session_state[k].append((nm, data_or_err))
                            success_count += 1
                    if success_count > 0:
                        st.success(f"✅ Se cargaron {success_count} archivos.")
                        st.rerun()

            st.divider()
            for lbl, key in [("V1","gh_blobs_v1"),("V2","gh_blobs_v2"),("Pax V1","gh_blobs_px1"),("Pax V2","gh_blobs_px2")]:
                blobs_gh = st.session_state.get(key, [])
                if blobs_gh:
                    st.caption(f"GitHub {lbl}: {len(blobs_gh)} archivo(s)")
                    if st.button(f"🗑️ Limpiar {lbl}", key=f"gh_clear_{lbl}"):
                        st.session_state[key] = []; st.rerun()

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

    def _all_blobs_internal(f_uploader, gh_key): 
        return tuple(leer(f_uploader) + st.session_state.get(gh_key, []))

    # Procesar archivos base
    b1=_all_blobs_internal(f_v1,"gh_blobs_v1"); b2=_all_blobs_internal(f_v2,"gh_blobs_v2")
    bx1=_all_blobs_internal(f_px1,"gh_blobs_px1"); bx2=_all_blobs_internal(f_px2,"gh_blobs_px2")
    df1,df2,err_t=build_thdr_v71(b1,b2)
    df_px,err_p  =build_pax_v71(bx1,bx2)
    
    perfiles_pax = get_perfiles_pax(df_px)

    with st.sidebar:
        if err_t:
            with st.expander(f"⚠️ {len(err_t)} errores THDR"):
                for e in err_t: st.caption(e)
        if err_p:
            with st.expander(f"⚠️ {len(err_p)} errores Pax"):
                for e in err_p: st.caption(e)
                
        dfs_to_concat = [d for d in [df1, df2] if not d.empty]
        
        if len(dfs_to_concat) > 0:
            df_all = pd.concat(dfs_to_concat, ignore_index=True)
            df_all = df_all.drop_duplicates(subset=['_id', 't_ini', 'Via'])
            
            if not df_px.empty:
                if 'Tren_Clean' not in df_px.columns:
                    df_px['Tren_Clean'] = df_px['Tren'].apply(clean_id) if 'Tren' in df_px.columns else ''
                
                with st.spinner("Integrando datos reales de pasajeros..."):
                    pax_res = df_all.apply(lambda r: match_pax(r, df_px), axis=1)
                    df_all['pax_d']           = [x[0] for x in pax_res]
                    df_all['pax_abordo']      = [x[1] for x in pax_res]
                    df_all['hora_origen_pax'] = [x[2] for x in pax_res]
                    df_all['nro_thdr_pax']    = [x[3] for x in pax_res]
                    df_all['pax_row_idx']     = [x[4] for x in pax_res]
                    df_all['pax_max']         = df_all['pax_abordo']
            else:
                df_all['pax_d']           = [{}] * len(df_all)
                df_all['pax_max']         = 0
                df_all['pax_abordo']      = 0
                df_all['hora_origen_pax'] = '--:--:--'
                df_all['nro_thdr_pax']    = 'No Detectado'
                df_all['pax_row_idx']     = -1
                
            df_all['maniobra'] = None
            if n_cortes_v1 > 0:
                v1_cands = df_all[(df_all['Via'] == 1) & (df_all['doble'] == True) & (df_all['km_orig'] < 25.0) & (df_all['km_dest'] > 26.0) & (df_all['maniobra'].isnull())].copy()
                if not v1_cands.empty:
                    v1_cands['dist_valle'] = v1_cands['t_ini'].apply(lambda t: min(abs(t - 600), abs(t - 1230)))
                    corte_ids = v1_cands.sort_values('dist_valle').head(n_cortes_v1)['_id'].values
                    df_all.loc[df_all['_id'].isin(corte_ids), 'maniobra'] = 'CORTE_BTO'
                    
            if n_cortes_pu_sa_v1 > 0:
                v1_pu_sa_cands = df_all[(df_all['Via'] == 1) & (df_all['doble'] == True) & (df_all['km_orig'] < 25.0) & (df_all['km_dest'] >= 28.5) & (df_all['km_dest'] <= 29.5) & (df_all['maniobra'].isnull())].copy()
                if not v1_pu_sa_cands.empty:
                    v1_pu_sa_cands['dist_valle'] = v1_pu_sa_cands['t_ini'].apply(lambda t: min(abs(t - 600), abs(t - 1230)))
                    corte_pu_sa_ids = v1_pu_sa_cands.sort_values('dist_valle').head(n_cortes_pu_sa_v1)['_id'].values
                    df_all.loc[df_all['_id'].isin(corte_pu_sa_ids), 'maniobra'] = 'CORTE_PU_SA_BTO'
                    
            if n_acoples_v2 > 0:
                v2_cands = df_all[(df_all['Via'] == 2) & (df_all['km_orig'] > 26.0) & (df_all['km_dest'] < 25.0) & (df_all['maniobra'].isnull())].copy()
                if not v2_cands.empty:
                    v2_cands['dist_punta'] = v2_cands['t_ini'].apply(lambda t: min(abs(t - 390), abs(t - 1050)))
                    acople_ids = v2_cands.sort_values('dist_punta').head(n_acoples_v2)['_id'].values
                    df_all.loc[df_all['_id'].isin(acople_ids), 'maniobra'] = 'ACOPLE_BTO'

            if n_cortes_sa_v1 > 0:
                v1_sa_cands = df_all[(df_all['Via'] == 1) & (df_all['doble'] == True) & (df_all['km_orig'] < 29.0) & (df_all['km_dest'] > 30.0) & (df_all['maniobra'].isnull())].copy()
                if not v1_sa_cands.empty:
                    v1_sa_cands['dist_valle'] = v1_sa_cands['t_ini'].apply(lambda t: min(abs(t - 600), abs(t - 1230)))
                    corte_sa_ids = v1_sa_cands.sort_values('dist_valle').head(n_cortes_sa_v1)['_id'].values
                    df_all.loc[df_all['_id'].isin(corte_sa_ids), 'maniobra'] = 'CORTE_SA'
                    
            if n_acoples_sa_v2 > 0:
                v2_sa_cands = df_all[(df_all['Via'] == 2) & (df_all['km_orig'] > 30.0) & (df_all['km_dest'] < 29.0) & (df_all['maniobra'].isnull())].copy()
                if not v2_sa_cands.empty:
                    v2_sa_cands['dist_punta'] = v2_sa_cands['t_ini'].apply(lambda t: min(abs(t - 390), abs(t - 1050)))
                    acople_sa_ids = v2_sa_cands.sort_values('dist_punta').head(n_acoples_sa_v2)['_id'].values
                    df_all.loc[df_all['_id'].isin(acople_sa_ids), 'maniobra'] = 'ACOPLE_SA'

            df_all['tren_km'] = df_all.apply(calc_tren_km_real_general, axis=1)
            st.success(f"✅ {len(df_all)} despachos operativos históricos cargados.")
        else:
            df_all = pd.DataFrame()

    if not df_all.empty:
        fechas_validas = [str(d) for d in df_all['Fecha_str'].unique() if str(d) != '2026-01-01' and pd.notna(d)]
        fechas = sorted(list(set(fechas_validas))) if fechas_validas else sorted([str(d) for d in df_all['Fecha_str'].unique() if pd.notna(d)])
    else:
        fechas = []

    # RUTEO DE PESTAÑAS (UI PRINCIPAL)
    tab_mapa, tab_datos, tab_vacios, tab_planificador = st.tabs(["🗺️ Mapa Operativo Histórico", "📋 Reporte Pasajeros", "🚉 Maniobras en Vacío", "🔮 Planificador Inteligente"])
    
    with tab_planificador:
        st.subheader("🔮 Planificador Avanzado: Gemelo Digital de Inyecciones (V117)")
        st.markdown("El algoritmo ruteará los trenes de la Planilla Maestra basándose en el N° de Servicio y calculará los tiempos de llegada usando Física Pura. **Inyecta la masa dinámica real usando los perfiles estadísticos del archivo de pasajeros.**")
        
        col_p1, col_p2 = st.columns([1, 2])
        with col_p1:
            tipo_dia_plan = st.selectbox("📅 Tipo de Día para Perfil de Demanda", ["Laboral", "Sábado", "Domingo/Festivo"], key="td_plan")
            pax_promedio_viaje = {"Laboral": 280, "Sábado": 160, "Domingo/Festivo": 110}[tipo_dia_plan]
            estacion_anio_plan = st.selectbox("🌡️ Estación del Año (HVAC) - Plan.", ["verano", "otoño", "invierno", "primavera"], index=3, key="est_plan")
            
            if perfiles_pax:
                st.success("✅ Perfiles de pasajeros cargados. El Gemelo variará la masa del tren en cada estación.")
            else:
                st.warning(f"⚠️ Sin datos de pasajeros cargados. Se usará perfil estático: {pax_promedio_viaje} pax")
            
        with col_p2:
            modo_plan = st.radio("Fuente de Datos", ["Planilla Maestra (Subir CSV/Excel)", "Matriz Sintética"], horizontal=True)
            archivo_planilla = None
            
            if modo_plan == "Matriz Sintética":
                st.markdown("**Configuración de Rutas y Flota (Dinámica)**")
                if 'df_plan' not in st.session_state:
                    st.session_state['df_plan'] = pd.DataFrame([
                        {"Origen": "Puerto", "Destino": "Limache", "Flota": "XT-100", "Configuración": "Doble", "Cantidad": 40},
                        {"Origen": "Limache", "Destino": "Puerto", "Flota": "XT-100", "Configuración": "Doble", "Cantidad": 40},
                        {"Origen": "Puerto", "Destino": "El Belloto", "Flota": "XT-M", "Configuración": "Simple", "Cantidad": 0},
                    ])
                df_plan_edit = st.data_editor(
                    st.session_state['df_plan'], 
                    column_config={
                        "Origen": st.column_config.SelectboxColumn("Origen", options=ESTACIONES, required=True),
                        "Destino": st.column_config.SelectboxColumn("Destino", options=ESTACIONES, required=True),
                        "Flota": st.column_config.SelectboxColumn("Flota", options=["XT-100", "XT-M", "SFE"], required=True),
                        "Configuración": st.column_config.SelectboxColumn("Configuración", options=["Simple", "Doble"], required=True),
                        "Cantidad": st.column_config.NumberColumn("Cantidad", min_value=0, max_value=200, step=1)
                    },
                    num_rows="dynamic", use_container_width=True
                )
            else:
                st.markdown("**Asignación de Flota para Planilla Maestra (Rolling Stock)**")
                col_f1, col_f2 = st.columns(2)
                with col_f1: flota_largos = st.selectbox("Flota Servicios Largos (PU-LI / PU-SA)", ["XT-100", "XT-M", "SFE"], index=0)
                with col_f2: flota_cortos = st.selectbox("Flota Servicios Cortos (PU-EB)", ["XT-100", "XT-M", "SFE"], index=1)
                archivo_planilla = st.file_uploader("📂 Sube tu Planilla Maestra (.csv, .xlsx, .xls)", type=['csv', 'xlsx', 'xls'])
                df_plan_edit = pd.DataFrame()
                if archivo_planilla: st.success("Planilla detectada. Lista para simular.")
        
        if st.button("🚀 Ejecutar Gemelo Digital del Planificador", use_container_width=True, type="primary"):
            st.session_state['simulacion_plan_lista'] = False
            with st.spinner("Decodificando Planilla e inyectando al Motor Cinemático Termodinámico..."):
                if modo_plan == "Matriz Sintética":
                    df_sintetico_list = []
                    for idx, row in df_plan_edit.iterrows():
                        orig = row['Origen']; dest = row['Destino']; flota = row['Flota']
                        es_doble = row['Configuración'] == "Doble"; cant = row['Cantidad']
                        if cant <= 0 or orig == dest: continue
                        
                        idx_orig = ESTACIONES.index(orig)
                        idx_dest = ESTACIONES.index(dest)
                        via = 1 if idx_orig < idx_dest else 2
                        km_ini = KM_ACUM[idx_orig]; km_fin = KM_ACUM[idx_dest]
                        
                        if via == 1: est_idxs = range(idx_orig, idx_dest + 1)
                        else: est_idxs = range(idx_orig, idx_dest - 1, -1)
                            
                        nodos_sint = [(0.0, KM_ACUM[i]) for i in est_idxs]
                        interval_mins = (1350 - 360) / cant if cant > 1 else 0
                        ruta_str = f"{EC[idx_orig]}-{EC[idx_dest]}"
                        
                        for i in range(int(cant)):
                            t_ini_sint = 360 + i * interval_mins
                            df_sintetico_list.append({
                                '_id': f"SINT_{ruta_str}_{i}", 't_ini': t_ini_sint, 'Via': via,
                                'km_orig': km_ini, 'km_dest': km_fin, 'nodos': nodos_sint,
                                'tipo_tren': flota, 'doble': es_doble, 'num_servicio': f"VIRT_{i}",
                                'maniobra': None, 'svc_type': ruta_str
                            })
                    df_sint = pd.DataFrame(df_sintetico_list)
                else:
                    if archivo_planilla is None:
                        st.warning("Debes subir la Planilla de Operación.")
                        st.stop()
                    df_sint, msg = parsear_planilla_maestra(archivo_planilla.read(), archivo_planilla.name)
                    if df_sint.empty:
                        st.error(f"Error procesando: {msg}")
                        st.stop()
                        
                    def asignar_flota_planilla(ruta):
                        if 'EB' in str(ruta): return flota_cortos
                        return flota_largos
                    df_sint['tipo_tren'] = df_sint['svc_type'].apply(asignar_flota_planilla)

                if df_sint.empty:
                    st.warning("No hay viajes para simular.")
                    st.stop()

                st.session_state['raw_plan_df'] = df_sint
                st.session_state['simulacion_plan_lista'] = True

        if st.session_state.get('simulacion_plan_lista', False) and 'raw_plan_df' in st.session_state:
            df_sint = st.session_state['raw_plan_df']
            df_sint_final, df_sint_e = procesar_planificador_reactivo(
                df_sint, tipo_dia_plan, pax_promedio_viaje, estacion_anio_plan, 
                pct_trac, use_rm, use_pend, use_regen, tipo_regen, perfiles_pax
            )
            pax_tot = int(df_sint_final['pax_abordo'].sum())
            
            st.divider()
            st.success("✅ Malla Operativa Físicamente Validada y Calculada con Perfiles Dinámicos de Masa")
            
            render_gemelo_digital(
                df_sint_final, df_sint_e, active_sers, 
                f"Planificador: {tipo_dia_plan} ({estacion_anio_plan.capitalize()})", 
                pct_trac, use_rm, use_pend, estacion_anio_plan, 
                prefix_key="plan", gap_vias=gap_vias, pax_dia_total=pax_tot
            )
            
            st.divider()
            st.markdown("### 📅 Proyección Estratégica Mensual (Capex/Opex)")
            st.caption("Extrapola la malla unitaria diaria a un mes calendario para estimar la facturación de Alta Tensión y el volumen de pasajeros.")
            col_m1, col_m2, col_m3 = st.columns(3)
            with col_m1: dias_laborales = st.number_input("Días Laborales en el mes", min_value=0, max_value=31, value=22)
            with col_m2: dias_sabados = st.number_input("Sábados en el mes", min_value=0, max_value=5, value=4)
            with col_m3: dias_domingos = st.number_input("Domingos/Festivos", min_value=0, max_value=10, value=4)
            
            total_dias_mes = dias_laborales + dias_sabados + dias_domingos
            kwh_neto_dia = df_sint_e['kwh_viaje_neto'].sum()
            kwh_neto_mes = kwh_neto_dia * total_dias_mes
            pax_dia = pax_tot
            pax_mes = pax_dia * total_dias_mes
            
            st.info(f"**Proyección para {total_dias_mes} días (Asumiendo que la malla '{tipo_dia_plan}' se repite diariamente):**")
            cm1, cm2, cm3 = st.columns(3)
            cm1.metric("⚡ Consumo Mensual Proyectado (Neto)", f"{kwh_neto_mes:,.0f} kWh")
            cm2.metric("🧑‍🤝‍🧑 Pasajeros Mensuales Proyectados", f"{pax_mes:,} pax")
            cm3.metric("💰 Costo Energía Estimado (100 CLP/kWh)", f"${kwh_neto_mes * 100:,.0f} CLP")

    with tab_mapa:
        if df_all.empty:
            st.warning("⚠️ El Mapa Operativo requiere la carga de archivos THDR Históricos para funcionar.")
        else:
            fecha_sel = st.selectbox("📅 Fecha Operativa (THDR)", fechas, key="fs_hist")
            df_dia = df_all[df_all['Fecha_str']==fecha_sel].copy()
            
            if use_regen:
                if "Probabilístico" in tipo_regen:
                    dict_regen = calcular_receptividad_por_headway(df_dia)
                else:
                    dict_regen = precalcular_red_electrica_v111(df_dia, pct_trac, use_rm, estacion_anio)
            else:
                dict_regen = {}
                
            df_dia_e = calcular_termodinamica_flota_v111(df_dia, pct_trac, use_pend, use_rm, use_regen, dict_regen, estacion_anio)
            
            df_dia_px_total = df_px[df_px['Fecha_s'] == fecha_sel] if not df_px.empty and 'Fecha_s' in df_px.columns else pd.DataFrame()
            pax_dia_tot = int(pd.to_numeric(df_dia_px_total['CargaMax'], errors='coerce').fillna(0).sum()) if not df_dia_px_total.empty else 0
            
            render_gemelo_digital(
                df_dia, df_dia_e, active_sers, fecha_sel, pct_trac, use_rm, use_pend, estacion_anio, 
                prefix_key="mapa", gap_vias=gap_vias, pax_dia_total=pax_dia_tot
            )

    with tab_datos:
        st.subheader("📋 Auditoría de Datos: Carga de Pasajeros (Fuente Pura y Transparente)")
        st.markdown("Esta vista te permite verificar exactamente qué leyó el sistema de tu archivo de Excel, fila por fila.")
        
        if df_px.empty:
            st.warning("⚠️ No hay datos de pasajeros cargados. Verifica los archivos en la barra lateral.")
        else:
            st.success(f"✅ Se leyeron {len(df_px)} registros de pasajeros con éxito.")
            fechas_disponibles = sorted([str(x) for x in df_px['Fecha_s'].dropna().unique() if str(x).strip() and str(x).lower() not in ["none", "nan", "fecha no detectada"]])
            
            if fechas_disponibles:
                opciones_filtro = ["Todas las fechas"] + fechas_disponibles
                fecha_sel_pax = st.selectbox("📅 Filtrar por Fecha del Archivo de Pasajeros", opciones_filtro, key="fs_datos_pax_v41")
                
                df_dia_pax = df_px.copy()
                if fecha_sel_pax != "Todas las fechas":
                    df_dia_pax = df_dia_pax[df_dia_pax['Fecha_s'] == fecha_sel_pax]

                if df_dia_pax.empty:
                    st.info("No hay registros para la fecha seleccionada.")
                else:
                    df_dia_pax = df_dia_pax.sort_values(by=['Via', 't_ini_p'])
                    
                    for c in ['Nro_THDR', 'Tren', 'CargaMax']:
                        if c not in df_dia_pax.columns: df_dia_pax[c] = ''
                    
                    df_dia_pax['Hora Origen Formateada'] = df_dia_pax['t_ini_p'].apply(mins_to_time_str)
                    
                    base_cols = ['Fecha_s', 'Nro_THDR', 'Tren', 'Hora Origen Formateada', 'CargaMax']
                    renames = {'Fecha_s': 'Fecha', 'Nro_THDR': 'N° THDR Pax', 'Tren': 'Servicio', 'Hora Origen Formateada': 'Hora Origen', 'CargaMax': 'Total a Bordo'}
                    
                    for c in PAX_COLS:
                        if c not in df_dia_pax.columns: 
                            df_dia_pax[c] = 0
                        else: 
                            df_dia_pax[c] = pd.to_numeric(df_dia_pax[c], errors='coerce').fillna(0).astype(int)

                    total_v1 = df_dia_pax[df_dia_pax['Via'] == 1]['CargaMax'].sum() if 'CargaMax' in df_dia_pax.columns else 0
                    total_v2 = df_dia_pax[df_dia_pax['Via'] == 2]['CargaMax'].sum() if 'CargaMax' in df_dia_pax.columns else 0
                    total_ambos = total_v1 + total_v2

                    st.markdown("### 📊 Resumen de Pasajeros (Total a Bordo)")
                    cc1, cc2, cc3 = st.columns(3)
                    cc1.metric("Total Pasajeros V1", f"{int(total_v1):,}")
                    cc2.metric("Total Pasajeros V2", f"{int(total_v2):,}")
                    cc3.metric("Suma Total Ambas Vías", f"{int(total_ambos):,}")
                    st.divider()

                    st.subheader("🔵 Vía 1 (Puerto → Limache)")
                    df_v1 = df_dia_pax[df_dia_pax['Via'] == 1].copy()
                    if not df_v1.empty:
                        v1_cols = base_cols + PAX_COLS
                        df_v1_out = df_v1[v1_cols].rename(columns=renames)
                        st.dataframe(df_v1_out, use_container_width=True)
                    else:
                        st.info("No hay registros de pasajeros para la Vía 1 en esta selección.")

                    st.subheader("🔴 Vía 2 (Limache → Puerto)")
                    df_v2 = df_dia_pax[df_dia_pax['Via'] == 2].copy()
                    if not df_v2.empty:
                        v2_pax_cols_reversed = list(reversed(PAX_COLS))
                        v2_cols = base_cols + v2_pax_cols_reversed
                        df_v2_out = df_v2[v2_cols].rename(columns=renames)
                        st.dataframe(df_v2_out, use_container_width=True)
                    else:
                        st.info("No hay registros de pasajeros para la Vía 2 en esta selección.")
                    
                    df_export_list = []
                    if not df_v1.empty: df_export_list.append(df_v1_out)
                    if not df_v2.empty: df_export_list.append(df_v2_out)
                    
                    if df_export_list:
                        df_export = pd.concat(df_export_list, ignore_index=True)
                        csv = df_export.to_csv(index=False).encode('utf-8')
                        st.download_button(
                            label="📥 Descargar Tabla Cruda de Pasajeros CSV",
                            data=csv,
                            file_name=f'Reporte_Puro_Pasajeros_MERVAL_{fecha_sel_pax}.csv',
                            mime='text/csv',
                        )
            else:
                st.error("No se pudo extraer ninguna fecha válida del archivo de pasajeros. Verifica que la Columna D de los datos contenga la fecha correcta.")

    with tab_vacios:
        st.subheader("🚉 Auditoría de Maniobras en Vacío (Carrusel y Reposicionamientos)")
        st.markdown("Esta tabla audita todos los movimientos de los trenes sin pasajeros detectados en el sistema (entradas y salidas de cochera, y tránsitos para cubrir servicios comerciales).")
        
        if df_all.empty:
            st.warning("⚠️ No hay archivos THDR cargados para auditar maniobras en vacío.")
        else:
            fecha_sel_vacios = st.selectbox("📅 Filtrar por Fecha Operativa", fechas, key="fs_vacios")
            df_dia_vacios = df_all[df_all['Fecha_str'] == fecha_sel_vacios].copy()
            vacios_list = get_vacios_dia(df_dia_vacios)
            
            for idx, row in df_dia_vacios[df_dia_vacios['maniobra'].notnull()].iterrows():
                man = row['maniobra']
                t_arr_bto = row['t_ini'] + 40.0 if row['Via'] == 1 else row['t_ini'] + 20.0
                t_arr_sa = row['t_ini'] + 47.0 if row['Via'] == 1 else row['t_ini'] + 13.0
                dist_sa_eb = abs(KM_ACUM[18] - KM_ACUM[14])
                
                if man == 'CORTE_BTO' or man == 'CORTE_PU_SA_BTO':
                    vacios_list.append({'t_asigned': t_arr_bto, 'tipo': row['tipo_tren'], 'doble': False, 'cochera': True, 'dist': 2.0, 'motriz_num': f"{row.get('motriz_num', '')}-B", 'origen_txt': 'El Belloto (Corte)', 'destino_txt': 'Taller EB', 'servicio_previo': row.get('num_servicio', ''), 'servicio_siguiente': '—', 'km_orig': KM_ACUM[14], 'km_dest': KM_ACUM[14]})
                elif man == 'ACOPLE_BTO':
                    vacios_list.append({'t_asigned': t_arr_bto - 5.0, 'tipo': row['tipo_tren'], 'doble': False, 'cochera': True, 'dist': 2.0, 'motriz_num': f"{row.get('motriz_num', '')}-B", 'origen_txt': 'Taller EB', 'destino_txt': 'El Belloto (Acople)', 'servicio_previo': '—', 'servicio_siguiente': row.get('num_servicio', ''), 'km_orig': KM_ACUM[14], 'km_dest': KM_ACUM[14]})
                elif man == 'CORTE_SA':
                    vacios_list.append({'t_asigned': t_arr_sa, 'tipo': row['tipo_tren'], 'doble': False, 'cochera': True, 'dist': dist_sa_eb + 2.0, 'motriz_num': f"{row.get('motriz_num', '')}-B", 'origen_txt': 'Sargento Aldea (Corte)', 'destino_txt': 'Taller EB', 'servicio_previo': row.get('num_servicio', ''), 'servicio_siguiente': '—', 'km_orig': KM_ACUM[18], 'km_dest': KM_ACUM[14]})
                elif man == 'ACOPLE_SA':
                    vacios_list.append({'t_asigned': t_arr_sa - 20.0, 'tipo': row['tipo_tren'], 'doble': False, 'cochera': True, 'dist': dist_sa_eb + 2.0, 'motriz_num': f"{row.get('motriz_num', '')}-B", 'origen_txt': 'Taller EB', 'destino_txt': 'Sargento Aldea (Acople)', 'servicio_previo': '—', 'servicio_siguiente': row.get('num_servicio', ''), 'km_orig': KM_ACUM[14], 'km_dest': KM_ACUM[18]})

            if not vacios_list:
                st.info("No se detectaron maniobras en vacío para la fecha seleccionada.")
            else:
                tabla_vacios = []
                for v in vacios_list:
                    factor_flota = 2 if v.get('doble', False) else 1
                    distancia_geo = v.get('dist', 0)
                    tren_km_equivalente = distancia_geo * factor_flota
                    
                    tabla_vacios.append({
                        "Hora Estimada": mins_to_time_str(v['t_asigned']),
                        "Tren (Motriz)": str(v.get('motriz_num', '')),
                        "Viene del Servicio": v.get('servicio_previo', '—'),
                        "Va hacia Servicio": v.get('servicio_siguiente', '—'),
                        "Estación Origen": v.get('origen_txt', 'Desconocido'),
                        "Estación Destino": v.get('destino_txt', 'Desconocido'),
                        "Tren-km (Vacío)": round(tren_km_equivalente, 2),
                        "Tipo Maniobra": "Ingreso/Salida Cochera" if v.get('cochera') else "Reposicionamiento",
                        "Configuración": f"{v.get('tipo', 'XT-100')} {'(Doble)' if v.get('doble') else '(Simple)'}"
                    })
                
                df_vacios_out = pd.DataFrame(tabla_vacios).sort_values("Hora Estimada").reset_index(drop=True)
                
                total_km_v = df_vacios_out["Tren-km (Vacío)"].sum()
                total_mov_v = len(df_vacios_out)
                
                cc1, cc2 = st.columns(2)
                cc1.metric("Total Movimientos en Vacío", total_mov_v)
                cc2.metric("Kilometraje Total en Vacío (Tren-km)", f"{total_km_v:.1f} km")
                st.divider()
                
                st.dataframe(df_vacios_out, use_container_width=True)
                
                csv_v = df_vacios_out.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label="📥 Descargar Registro de Maniobras",
                    data=csv_v,
                    file_name=f'Maniobras_Vacio_MERVAL_{fecha_sel_vacios}.csv',
                    mime='text/csv'
                )

if __name__ == "__main__":
    main()
