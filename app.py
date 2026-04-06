import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import date, datetime
import re

from procesamiento import *

st.set_page_config(page_title="Gestión de Energía - Dashboard SGE", layout="wide", page_icon="🚆")

# --- 1. INICIALIZACIÓN (PARA EVITAR NameError) ---
df_ops, df_tr, df_tr_acum, df_seat, df_energy_master = pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
df_p_d, df_f_d, df_thdr_v1, df_thdr_v2 = pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
all_ops_list, all_tr, all_tr_acum, all_seat = [], [], [], []
all_comp_full, all_prmte_15, all_fact_h = [], [], []

with st.sidebar:
    st.header("📅 Filtro Global")
    # Tip: Ajusta este filtro si tus archivos son de meses distintos
    date_range = st.date_input("Selecciona el período", value=(date(2026,1,1), date.today()))
    start_date, end_date = (date_range[0], date_range[1]) if len(date_range)==2 else (date_range[0], date_range[0])
    
    st.divider()
    f_v1 = st.file_uploader("1. THDR Vía 1", type=["xls", "xlsx"], accept_multiple_files=True)
    f_v2 = st.file_uploader("2. THDR Vía 2", type=["xls", "xlsx"], accept_multiple_files=True)
    f_umr = st.file_uploader("3. UMR / Odómetros", type=["xlsx"], accept_multiple_files=True)
    f_seat_files = st.file_uploader("4. Energía SEAT", type=["xlsx"], accept_multiple_files=True)
    f_bill_files = st.file_uploader("5. Facturación y PRMTE", type=["xlsx"], accept_multiple_files=True)

# --- 2. PROCESAMIENTO ---
if any([f_v1, f_v2, f_umr, f_seat_files, f_bill_files]):
    if f_v1:
        v1_list = []
        for f in f_v1:
            df, _, _, _ = procesar_thdr_avanzado(f)
            if not df.empty and df['Fecha_Op'].iloc[0] is not None:
                f_fch = df['Fecha_Op'].iloc[0]
                if start_date <= f_fch <= end_date:
                    df['Vía'] = 'Vía 1'
                    v1_list.append(df)
        if v1_list: df_thdr_v1 = pd.concat(v1_list, ignore_index=True)

    if f_v2:
        v2_list = []
        for f in f_v2:
            df, _, _, _ = procesar_thdr_avanzado(f)
            if not df.empty and df['Fecha_Op'].iloc[0] is not None:
                f_fch = df['Fecha_Op'].iloc[0]
                if start_date <= f_fch <= end_date:
                    df['Vía'] = 'Vía 2'
                    v2_list.append(df)
        if v2_list: df_thdr_v2 = pd.concat(v2_list, ignore_index=True)

    # Procesamiento UMR / Energía (Igual al anterior pero verificado)
    todos = (f_umr or []) + (f_seat_files or []) + (f_bill_files or [])
    for f in todos:
        try:
            xl = pd.ExcelFile(f)
            for sn in xl.sheet_names:
                sn_up = sn.upper()
                if any(k in sn_up for k in ['UMR', 'RESUMEN']):
                    df_p_raw = pd.read_excel(f, sheet_name=sn, header=None)
                    h_r = next((i for i in range(min(100, len(df_p_raw))) if any(k in str(df_p_raw.iloc[i]).upper() for k in ['ODO', 'FECHA'])), None)
                    if h_r is not None:
                        df_p_p = pd.read_excel(f, sheet_name=sn, header=h_r)
                        df_p_p.columns = [re.sub(r'[^A-Z]', '', str(c).upper().replace('Ó','O')) for c in df_p_p.columns]
                        idx_f, idx_o, idx_t = next((c for c in df_p_p.columns if 'FECHA' in c), None), next((c for c in df_p_p.columns if 'ODO' in c and 'ACUM' not in c), None), next((c for c in df_p_p.columns if 'TREN' in c and 'KM' in c), None)
                        if idx_f and idx_o:
                            df_p_p['_dt'] = pd.to_datetime(df_p_p[idx_f], errors='coerce')
                            mask = (df_p_p['_dt'].dt.date >= start_date) & (df_p_p['_dt'].dt.date <= end_date)
                            for _, r in df_p_p[mask].dropna(subset=['_dt']).iterrows():
                                all_ops_list.append({"Fecha": r['_dt'].normalize(), "Tipo Día": get_tipo_dia(r['_dt']), "N° Semana": r['_dt'].isocalendar()[1], "Odómetro [km]": parse_latam_number(r[idx_o]), "Tren-Km [km]": parse_latam_number(r[idx_t]), "UMR [%]": (parse_latam_number(r[idx_t])/parse_latam_number(r[idx_o])*100 if parse_latam_number(r[idx_o])>0 else 0)})
                
                # ... (resto de lógica de ODO, SEAT, PRMTE igual)
                if 'ODO' in sn_up and 'KIL' in sn_up:
                    df_tr_raw = pd.read_excel(f, sheet_name=sn, header=None)
                    for i in range(len(df_tr_raw)-2):
                        for j in range(1, len(df_tr_raw.columns)):
                            val = pd.to_datetime(df_tr_raw.iloc[i, j], errors='coerce')
                            if pd.notna(val) and start_date <= val.date() <= end_date:
                                is_acum = any(k in str(df_tr_raw.iloc[i:i+3, 0:5]).upper() for k in ['ACUM', 'TOTAL'])
                                for k in range(i+3, min(i+40, len(df_tr_raw))):
                                    n_tr = str(df_tr_raw.iloc[k, 0]).strip().upper()
                                    if re.match(r'^(M|XM)', n_tr):
                                        val_km = parse_latam_number(df_tr_raw.iloc[k, j])
                                        d_pt = {"Tren": n_tr, "Fecha": val.normalize(), "Día": val.day, "Valor": val_km}
                                        if is_acum: all_tr_acum.append(d_pt)
                                        else: all_tr.append(d_pt)
        except: continue

    # --- 3. CONSOLIDACIÓN FINAL ---
    if all_ops_list: df_ops = pd.DataFrame(all_ops_list).drop_duplicates(subset=['Fecha']).sort_values("Fecha")
    if all_tr: df_tr = pd.DataFrame(all_tr).sort_values(["Fecha", "Tren"])
    if all_tr_acum: df_tr_acum = pd.DataFrame(all_tr_acum).sort_values(["Fecha", "Tren"])

# --- 4. TABS ---
tabs = st.tabs(["📊 Resumen", "📑 Operaciones", "📑 Trenes", "⚡ Energía", "📈 Regresión Nocturna", "📋 THDR"])

with tabs[5]:
    st.header("📋 Datos THDR")
    def mostrar_v2(df, tit, em):
        st.subheader(f"{em} {tit}")
        if df.empty:
            st.warning(f"No hay datos para {tit} en el rango {start_date} a {end_date}.")
        else:
            df_c = df.copy()
            df_c['H_Prog'] = df_c['Min_Prog'].apply(lambda x: format_hms(x))
            df_c['H_Real'] = df_c['Min_S_Real'].apply(lambda x: format_hms(x))
            st.dataframe(df_c[['Fecha_Op', 'Servicio', 'H_Prog', 'H_Real', 'Motriz 1', 'Tipo_Rec', 'Tren-Km']], use_container_width=True)

    mostrar_v2(df_thdr_v1, "Vía 1", "🟢")
    mostrar_v2(df_thdr_v2, "Vía 2", "🔵")

st.sidebar.download_button("📥 Reporte Excel", to_excel_consolidado(df_ops, df_tr, df_tr_acum, df_seat, df_p_d, pd.DataFrame(all_prmte_15), pd.DataFrame(all_fact_h), df_f_d), "Reporte_EFE.xlsx")
