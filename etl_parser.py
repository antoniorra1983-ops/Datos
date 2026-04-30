import pandas as pd
import numpy as np
import re
import unicodedata
from io import BytesIO
from datetime import datetime, date, timedelta
import streamlit as st
from config import *

EST_NORM = sorted({re.sub(r'[^a-z0-9]','', e.lower().replace('á','a').replace('é','e').replace('í','i').replace('ó','o').replace('ú','u').replace('ñ','n')): i for i, e in enumerate(ESTACIONES)}.items(), key=lambda x: -len(x[0]))

def clasificar_dia(d):
    str_d = d.strftime('%Y-%m-%d')
    if str_d in feriados_2026 or d.weekday() == 6: return 'Domingo/Festivo'
    if d.weekday() == 5: return 'Sábado'
    return 'Laboral'

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
        h = int(m.group(1)); m_min = int(m.group(2)); s_sec = int(m.group(3)) / 60.0 if m.group(3) else 0.0
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
                d, mon, y = int(s_pad[0:2]), int(s_pad[2:4]), int(s_pad[4:6])
                if 1 <= d <= 31 and 1 <= mon <= 12: return f"{2000+y if y<100 else y:04d}-{mon:02d}-{d:02d}"
            except: pass
    m1 = re.search(r'\b(\d{1,2})[-/](\d{1,2})[-/](\d{4})\b', v_str)
    if m1:
        d, mon, y = int(m1.group(1)), int(m1.group(2)), int(m1.group(3))
        if mon > 12 and d <= 12: d, mon = mon, d 
        if 1 <= d <= 31 and 1 <= mon <= 12: return f"{y:04d}-{mon:02d}-{d:02d}"
    m2 = re.search(r'\b(\d{4})[-/](\d{1,2})[-/](\d{1,2})\b', v_str)
    if m2:
        y, mon, d = int(m2.group(1)), int(m2.group(2)), int(m2.group(3))
        if mon > 12 and d <= 12: d, mon = mon, d
        if 1 <= d <= 31 and 1 <= mon <= 12: return f"{y:04d}-{mon:02d}-{d:02d}"
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
    except: return str(x).strip().upper()

def clean_pax_number(x):
    if pd.isna(x): return 0
    s = str(x).strip().lower()
    if s == '' or s == 'nan': return 0
    s = re.sub(r'\.0+$', '', s)
    s = s.replace('.', '').replace(',', '')
    s = re.sub(r'[^\d]', '', s)
    try: return int(s) if s else 0
    except: return 0

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

def _col_to_est_idx(col):
    cu = re.sub(r'[^a-z0-9]','', col.lower().replace('á','a').replace('é','e').replace('í','i').replace('ó','o').replace('ú','u').replace('ñ','n'))
    if 'americas' in cu: return ESTACIONES.index('Las Americas')
    if 'vina' in cu: return ESTACIONES.index('Viña del Mar')
    if 'aldea' in cu: return ESTACIONES.index('Sargento Aldea')
    if 'belloto' in cu: return ESTACIONES.index('El Belloto')
    if 'concepcion' in cu: return ESTACIONES.index('La Concepcion')
    if 'villaalem' in cu: return ESTACIONES.index('Villa Alemana')
    if 'salto' in cu: return ESTACIONES.index('El Salto')
    for nk, idx in EST_NORM:
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

@st.cache_data(show_spinner="Calculando perfiles promedio de pasajeros por tipo de día...")
def get_perfiles_pax(df_px):
    if df_px.empty: return {}
    df_p = df_px.copy()
    df_p['Fecha_dt'] = pd.to_datetime(df_p['Fecha_s'], errors='coerce')
    df_p = df_p.dropna(subset=['Fecha_dt'])
    if df_p.empty: return {}
    df_p['Tipo_Dia'] = df_p['Fecha_dt'].apply(clasificar_dia)
    for c in PAX_COLS + ['CargaMax']:
        if c in df_p.columns: df_p[c] = pd.to_numeric(df_p[c], errors='coerce').fillna(0)
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

@st.cache_data(show_spinner="Calculando Carrusel de Cocheras...")
def get_vacios_dia(df_dia):
    vacios = []
    if df_dia.empty: return vacios
    agrupador = 'motriz_num' if 'motriz_num' in df_dia.columns else 'num_servicio'
    def _get_est_name(km):
        if pd.isna(km): return "Desconocido"
        dists = [abs(km - k) for k in KM_ACUM]
        idx = int(np.argmin(dists))
        if dists[idx] <= 1.5:
            return ESTACIONES[idx]
        return f"km {km:.1f}"
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
            actual = viajes[i]
            sig = viajes[i+1]
            k_o = actual.get('km_dest', 0)
            k_d = sig.get('km_orig', 0)
            dist = abs(k_o - k_d)
            if 0.1 < dist <= 20.0:
                vacios.append({'t_asigned': actual['t_fin'] + 5, 'tipo': actual.get('tipo_tren', 'XT-100'), 'doble': actual.get('doble', False), 'cochera': False, 'km_orig': k_o, 'km_dest': k_d, 'dist': dist, 'motriz_num': tren, 'origen_txt': _get_est_name(k_o), 'destino_txt': _get_est_name(k_d), 'servicio_previo': str(actual.get('num_servicio', '')), 'servicio_siguiente': str(sig.get('num_servicio', ''))})
        u = viajes[-1]
        if abs(u.get('km_dest', 0) - KM_ACUM[14]) < 0.1:
            vacios.append({'t_asigned': u['t_fin'] + 5, 'tipo': u.get('tipo_tren', 'XT-100'), 'doble': u.get('doble', False), 'cochera': True, 'km_orig': KM_ACUM[14], 'km_dest': KM_ACUM[14], 'dist': 2.0, 'motriz_num': tren, 'origen_txt': 'El Belloto', 'destino_txt': 'Taller / Cochera', 'servicio_previo': str(u.get('num_servicio', '')), 'servicio_siguiente': '—'})
        elif abs(u.get('km_dest', 0) - KM_ACUM[18]) < 0.1:
            vacios.append({'t_asigned': u['t_fin'] + 5, 'tipo': u.get('tipo_tren', 'XT-100'), 'doble': u.get('doble', False), 'cochera': True, 'km_orig': KM_ACUM[18], 'km_dest': KM_ACUM[14], 'dist': 2.0 + abs(KM_ACUM[18]-KM_ACUM[14]), 'motriz_num': tren, 'origen_txt': 'Sargento Aldea', 'destino_txt': 'Taller / Cochera', 'servicio_previo': str(u.get('num_servicio', '')), 'servicio_siguiente': '—'})
    return vacios

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
            if (n1 is not None and n1 != 0) and (n2 is not None and n2 != 0): motriz_str = f"{n1}+{n2}"; n_eval = n1
            elif (n1 is not None and n1 != 0): motriz_str = f"{n1}"; n_eval = n1
            elif (n2 is not None and n2 != 0): motriz_str = f"{n2}"; n_eval = n2
            else:
                n_tren = extract_n(tren_col)
                if n_tren is not None and n_tren != 0: motriz_str = f"{n_tren}"; n_eval = n_tren
            if n_eval is not None:
                if 1 <= n_eval <= 27: tipo = "XT-100"
                elif 28 <= n_eval <= 35: tipo = "XT-M"
                elif 410 <= n_eval <= 414: tipo = "SFE"
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
                if 'VIAJE' in row_str and ('SERV' in row_str or 'TREN' in row_str) and 'PARTIDA' in row_str:
                    header_idx = i
                    break
                    
            if header_idx != -1:
                headers = df.iloc[header_idx].fillna('').astype(str).str.upper()
                c_viaje = next((i for i, h in enumerate(headers) if 'VIAJE' in h or h == 'N°' or h == 'N'), 0)
                c_srv = next((i for i, h in enumerate(headers) if 'SERV' in h or 'TREN' in h), 1)
                c_hora = next((i for i, h in enumerate(headers) if 'PARTIDA' in h or 'HORA' in h), 2)
                c_unidad = next((i for i, h in enumerate(headers) if 'UNIDAD' in h or 'CONF' in h), 5)

                for i in range(header_idx + 1, len(df)):
                    row = df.iloc[i]
                    if len(row) <= max(c_viaje, c_srv, c_hora): continue
                    hora_str = str(row[c_hora]).strip()
                    srv_str = str(row[c_srv]).strip()
                    viaje_str = str(row[c_viaje]).strip()
                    config_str = str(row[c_unidad]).strip().upper() if len(row) > c_unidad else ''

                    m_viaje = re.search(r'(\d+)', viaje_str)
                    m_srv = re.search(r'(\d+)', srv_str)
                    if not m_viaje or not m_srv: continue
                    viaje_num = int(m_viaje.group(1))
                    servicio_num = int(m_srv.group(1))
                    t_ini = parse_time_to_mins(hora_str)
                    if t_ini is None: continue

                    es_doble = True if 'MÚLTIPLE' in config_str or 'MULT' in config_str else False
                    via = 1 if viaje_num % 2 == 0 else 2
                    
                    # Asignación de rutas según numeración operativa (EFE)
                    if via == 1:
                        km_orig = KM_ACUM[0] # Puerto
                        if servicio_num >= 600: km_dest = KM_ACUM[20] # Limache
                        elif 400 <= servicio_num <= 599: km_dest = KM_ACUM[18] # Sargento Aldea
                        elif 200 <= servicio_num <= 399: km_dest = KM_ACUM[14] # El Belloto
                        else: km_dest = KM_ACUM[20] # Fallback
                    else:
                        km_dest = KM_ACUM[0] # Puerto
                        if servicio_num >= 600: km_orig = KM_ACUM[20] # Limache
                        elif 400 <= servicio_num <= 599: km_orig = KM_ACUM[18] # Sargento Aldea
                        elif 200 <= servicio_num <= 399: km_orig = KM_ACUM[14] # El Belloto
                        else: km_orig = KM_ACUM[20] # Fallback
                        
                    ruta = f"{EC[KM_ACUM.index(km_orig)]}-{EC[KM_ACUM.index(km_dest)]}"
                    nodos_via = [(0.0, k) for k in (KM_ACUM[KM_ACUM.index(km_orig):KM_ACUM.index(km_dest)+1] if via==1 else KM_ACUM[KM_ACUM.index(km_dest):KM_ACUM.index(km_orig)+1][::-1])]
                    viajes.append({'_id': f"PLAN_{servicio_num}_{int(t_ini)}", 't_ini': t_ini, 'Via': via, 'km_orig': km_orig, 'km_dest': km_dest, 'nodos': nodos_via, 'tipo_tren': 'XT-100', 'doble': es_doble, 'num_servicio': str(servicio_num), 'svc_type': ruta, 'maniobra': None})
            else:
                for i in range(len(df)):
                    row = df.iloc[i].fillna('').astype(str).tolist()
                    if len(row) <= 2: continue
                    viaje_str = row[0].strip()
                    srv_str = row[1].strip()
                    hora_str = row[2].strip()
                    config_str = row[5].strip().upper() if len(row) > 5 else ''

                    m_viaje = re.search(r'(\d+)', viaje_str)
                    m_srv = re.search(r'(\d+)', srv_str)
                    if not m_viaje or not m_srv: continue
                    viaje_num = int(m_viaje.group(1))
                    servicio_num = int(m_srv.group(1))
                    t_ini = parse_time_to_mins(hora_str)
                    if t_ini is None: continue

                    es_doble = True if 'MÚLTIPLE' in config_str or 'MULT' in config_str else False
                    via = 1 if viaje_num % 2 == 0 else 2
                    
                    # Asignación de rutas según numeración operativa (EFE)
                    if via == 1:
                        km_orig = KM_ACUM[0] # Puerto
                        if servicio_num >= 600: km_dest = KM_ACUM[20] # Limache
                        elif 400 <= servicio_num <= 599: km_dest = KM_ACUM[18] # Sargento Aldea
                        elif 200 <= servicio_num <= 399: km_dest = KM_ACUM[14] # El Belloto
                        else: km_dest = KM_ACUM[20] # Fallback
                    else:
                        km_dest = KM_ACUM[0] # Puerto
                        if servicio_num >= 600: km_orig = KM_ACUM[20] # Limache
                        elif 400 <= servicio_num <= 599: km_orig = KM_ACUM[18] # Sargento Aldea
                        elif 200 <= servicio_num <= 399: km_orig = KM_ACUM[14] # El Belloto
                        else: km_orig = KM_ACUM[20] # Fallback
                        
                    ruta = f"{EC[KM_ACUM.index(km_orig)]}-{EC[KM_ACUM.index(km_dest)]}"
                    nodos_via = [(0.0, k) for k in (KM_ACUM[KM_ACUM.index(km_orig):KM_ACUM.index(km_dest)+1] if via==1 else KM_ACUM[KM_ACUM.index(km_dest):KM_ACUM.index(km_orig)+1][::-1])]
                    viajes.append({'_id': f"PLAN_{servicio_num}_{int(t_ini)}", 't_ini': t_ini, 'Via': via, 'km_orig': km_orig, 'km_dest': km_dest, 'nodos': nodos_via, 'tipo_tren': 'XT-100', 'doble': es_doble, 'num_servicio': str(servicio_num), 'svc_type': ruta, 'maniobra': None})
                        
        df_viajes = pd.DataFrame(viajes)
        if not df_viajes.empty: df_viajes = df_viajes.drop_duplicates(subset=['_id'])
        return df_viajes, "ok"
    except Exception as e: return pd.DataFrame(), str(e)
