import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import date, datetime
import re

from procesamiento import *

st.set_page_config(page_title="Gestión de Energía - Dashboard SGE", layout="wide", page_icon="🚆")
ORDEN_TIPO_DIA = ["L", "S", "D/F"]

st.markdown("<style>.stMetric { background-color: #ffffff; padding: 20px; border-radius: 10px; border-left: 5px solid #005195; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }</style>", unsafe_allow_html=True)

with st.sidebar:
    st.header("📅 Filtro Global")
    today = date.today()
    date_range = st.date_input("Selecciona el período", value=(today.replace(day=1), today))
    start_date, end_date = (date_range[0], date_range[1]) if len(date_range)==2 else (date_range[0], date_range[0])
    st.divider()
    f_v1 = st.file_uploader("1. THDR Vía 1", type=["xls", "xlsx"], accept_multiple_files=True)
    f_v2 = st.file_uploader("2. THDR Vía 2", type=["xls", "xlsx"], accept_multiple_files=True)
    f_umr = st.file_uploader("3. UMR / Odómetros", type=["xlsx"], accept_multiple_files=True)
    f_seat_files = st.file_uploader("4. Energía SEAT", type=["xlsx"], accept_multiple_files=True)
    f_bill_files = st.file_uploader("5. Facturación y PRMTE", type=["xlsx"], accept_multiple_files=True)

# --- INICIALIZACIÓN CRÍTICA (PARA EVITAR NameError) ---
df_ops, df_tr, df_tr_acum, df_seat, df_energy_master = pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
df_p_d, df_f_d, df_thdr_v1, df_thdr_v2 = pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
all_ops_list, all_tr, all_tr_acum, all_seat = [], [], [], []
all_comp_full, all_prmte_15, all_fact_h = [], [], []

# --- PROCESAMIENTO DE ARCHIVOS ---
if any([f_v1, f_v2, f_umr, f_seat_files, f_bill_files]):
    if f_v1:
        v1_list = []
        for f in f_v1:
            df, _, _, _ = procesar_thdr_avanzado(f)
            if not df.empty:
                mask = (df['Fecha_Op'] >= start_date) & (df['Fecha_Op'] <= end_date)
                df = df[mask]
                if not df.empty: df['Vía'] = 'Vía 1'; v1_list.append(df)
        if v1_list: df_thdr_v1 = pd.concat(v1_list, ignore_index=True)

    if f_v2:
        v2_list = []
        for f in f_v2:
            df, _, _, _ = procesar_thdr_avanzado(f)
            if not df.empty:
                mask = (df['Fecha_Op'] >= start_date) & (df['Fecha_Op'] <= end_date)
                df = df[mask]
                if not df.empty: df['Vía'] = 'Vía 2'; v2_list.append(df)
        if v2_list: df_thdr_v2 = pd.concat(v2_list, ignore_index=True)

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

                if 'ODO' in sn_up and 'KIL' in sn_up:
                    df_tr_raw = pd.read_excel(f, sheet_name=sn, header=None)
                    headers_found = []
                    for i in range(len(df_tr_raw)-2):
                        for j in range(1, len(df_tr_raw.columns)):
                            val = pd.to_datetime(df_tr_raw.iloc[i, j], errors='coerce')
                            if pd.notna(val) and start_date <= val.date() <= end_date:
                                if i not in [h[0] for h in headers_found]: headers_found.append((i, val))
                    for idx, (row_idx, s_dt) in enumerate(headers_found):
                        is_acum = any(k in str(df_tr_raw.iloc[row_idx:row_idx+3, 0:5]).upper() for k in ['ACUM', 'LECTURA', 'TOTAL'])
                        c_map = {j: pd.to_datetime(df_tr_raw.iloc[row_idx, j], errors='coerce') for j in range(1, len(df_tr_raw.columns)) if pd.notna(pd.to_datetime(df_tr_raw.iloc[row_idx, j], errors='coerce'))}
                        for k in range(row_idx+3, min(row_idx+40, len(df_tr_raw))):
                            n_tr = str(df_tr_raw.iloc[k, 0]).strip().upper()
                            if re.match(r'^(M|XM)', n_tr):
                                for c_idx, c_fch in c_map.items():
                                    val_km = parse_latam_number(df_tr_raw.iloc[k, c_idx])
                                    d_pt = {"Tren": n_tr, "Fecha": c_fch.normalize(), "Día": c_fch.day, "Valor": val_km}
                                    if is_acum or idx > 0: all_tr_acum.append(d_pt)
                                    else: all_tr.append(d_pt)

                if 'SEAT' in sn_up and 'SER' in sn_up:
                    df_s = pd.read_excel(f, sheet_name=sn, header=None)
                    for i in range(len(df_s)):
                        fs = pd.to_datetime(df_s.iloc[i, 1], errors='coerce')
                        if pd.notna(fs) and start_date <= fs.date() <= end_date:
                            tot, tra, k12 = parse_latam_number(df_s.iloc[i, 3]), parse_latam_number(df_s.iloc[i, 5]), parse_latam_number(df_s.iloc[i, 7])
                            all_seat.append({"Fecha": fs.normalize(), "Total [kWh]": tot, "Tracción [kWh]": tra, "12 KV [kWh]": k12, "% Tracción": (tra/tot*100 if tot>0 else 0), "% 12 KV": (k12/tot*100 if tot>0 else 0)})

                if any(k in sn_up for k in ['PRMTE', 'MEDIDAS']):
                    df_pd_raw = pd.read_excel(f, sheet_name=sn, header=None)
                    h_idx = next((i for i in range(len(df_pd_raw)) if 'AÑO' in str(df_pd_raw.iloc[i]).upper()), None)
                    if h_idx is not None:
                        df_p_data = pd.read_excel(f, sheet_name=sn, header=h_idx)
                        df_p_data['Timestamp'] = pd.to_datetime(df_p_data[['AÑO', 'MES', 'DIA', 'HORA']].astype(int).rename(columns={'AÑO':'year','MES':'month','DIA':'day','HORA':'hour'})) + pd.to_timedelta(df_p_data['INICIO INTERVALO'].astype(int), unit='m')
                        cols_e = [c for c in df_p_data.columns if 'Retiro_Energia_Activa (kWhD)' in str(c)]
                        for _, r in df_p_data.iterrows():
                            ts, val_p = r['Timestamp'], sum([parse_latam_number(r[col]) for col in cols_e])
                            all_comp_full.append({"Fecha": ts.normalize(), "Hora": ts.hour, "Consumo Horario [kWh]": val_p, "Fuente": "PRMTE"})
                            if start_date <= ts.date() <= end_date: all_prmte_15.append({"Fecha y Hora": ts.strftime('%d/%m/%Y %H:%M'), "Fecha": ts.normalize(), "Energía PRMTE [kWh]": val_p})

                if any(k in sn_up for k in ['FACTURA', 'CONSUMO']):
                    df_f_raw = pd.read_excel(f, sheet_name=sn); df_f_raw.columns = ['FechaHora', 'Valor']
                    df_f_raw['Timestamp'] = pd.to_datetime(df_f_raw['FechaHora'], errors='coerce')
                    for _, r in df_f_raw.dropna(subset=['Timestamp']).iterrows():
                        ts, val_f = r['Timestamp'], abs(parse_latam_number(r['Valor']))
                        all_comp_full.append({"Fecha": ts.normalize(), "Hora": ts.hour, "Consumo Horario [kWh]": val_f, "Fuente": "Factura"})
                        if start_date <= ts.date() <= end_date: all_fact_h.append({"Fecha y Hora": ts.strftime('%d/%m/%Y %H:%M'), "Fecha": ts.normalize(), "Consumo Horario [kWh]": val_f})
        except: continue

    # --- CONSOLIDACIÓN ---
    if all_ops_list: df_ops = pd.DataFrame(all_ops_list).drop_duplicates(subset=['Fecha']).sort_values("Fecha")
    if all_tr: df_tr = pd.DataFrame(all_tr).sort_values(["Fecha", "Tren"])
    if all_tr_acum: df_tr_acum = pd.DataFrame(all_tr_acum).sort_values(["Fecha", "Tren"])
    if all_seat:
        df_seat = pd.DataFrame(all_seat).drop_duplicates(subset=['Fecha']).sort_values("Fecha")
        df_energy_master = df_seat[["Fecha", "Total [kWh]", "Tracción [kWh]", "12 KV [kWh]"]].copy().rename(columns={"Total [kWh]":"E_Total", "Tracción [kWh]":"E_Tr", "12 KV [kWh]":"E_12"})
        df_energy_master["Fuente"] = "SEAT"

    if all_prmte_15:
        df_p_d = pd.DataFrame(all_prmte_15).groupby("Fecha")["Energía PRMTE [kWh]"].sum().reset_index()
        if not df_seat.empty:
            df_p_d = pd.merge(df_p_d, df_seat[["Fecha", "% Tracción", "% 12 KV"]], on="Fecha", how="left").fillna(0)
            df_p_d["E_Tr"], df_p_d["E_12"] = df_p_d["Energía PRMTE [kWh]"]*(df_p_d["% Tracción"]/100), df_p_d["Energía PRMTE [kWh]"]*(df_p_d["% 12 KV"]/100)
            df_p_p = df_p_d.rename(columns={"Energía PRMTE [kWh]":"E_Total"})[["Fecha","E_Total","E_Tr","E_12"]]; df_p_p["Fuente"] = "PRMTE"
            df_energy_master = pd.concat([df_energy_master, df_p_p]).drop_duplicates(subset=["Fecha"], keep="last")

    if all_fact_h:
        df_f_d = pd.DataFrame(all_fact_h).groupby("Fecha")["Consumo Horario [kWh]"].sum().reset_index()
        if not df_seat.empty:
            df_f_d = pd.merge(df_f_d, df_seat[["Fecha", "% Tracción", "% 12 KV"]], on="Fecha", how="left").fillna(0)
            df_f_d["E_Tr"], df_f_d["E_12"] = df_f_d["Consumo Horario [kWh]"]*(df_f_d["% Tracción"]/100), df_f_d["Consumo Horario [kWh]"]*(df_f_d["% 12 KV"]/100)
            df_f_f = df_f_d.rename(columns={"Consumo Horario [kWh]":"E_Total"})[["Fecha","E_Total","E_Tr","E_12"]]; df_f_f["Fuente"] = "Factura"
            df_energy_master = pd.concat([df_energy_master, df_f_f]).drop_duplicates(subset=["Fecha"], keep="last")

    if not df_ops.empty and not df_energy_master.empty:
        df_ops = pd.merge(df_ops, df_energy_master, on="Fecha", how="left")
        df_ops['IDE (kWh/km)'] = df_ops.apply(lambda row: row['E_Tr'] / row['Odómetro [km]'] if row['Odómetro [km]'] > 0 else 0, axis=1)

# --- DASHBOARD ---
tabs = st.tabs(["📊 Resumen", "📑 Operaciones", "📑 Trenes", "⚡ Energía", "⚖️ Comparación Energía hr", "📈 Regresión Nocturna", "🚨 Datos Atípicos", "📋 THDR"])

with tabs[0]:
    if not df_ops.empty:
        to_val, tk_val = df_ops["Odómetro [km]"].sum(), df_ops["Tren-Km [km]"].sum()
        umr_val = (tk_val/to_val*100) if to_val>0 else 0
        c1, c2, c3 = st.columns(3)
        c1.metric("Odómetro Total", f"{to_val:,.1f} km")
        c2.metric("Tren-Km Total", f"{tk_val:,.1f} km")
        c3.metric("UMR Global", f"{umr_val:.2f} %")
        fig = make_subplots(specs=[[{"secondary_y": True}]])
        fig.add_trace(go.Bar(x=df_ops['Fecha'], y=df_ops['Odómetro [km]']/1000, name='Odómetro (kkm)', marker_color='#005195'), secondary_y=False)
        fig.add_trace(go.Scatter(x=df_ops['Fecha'], y=df_ops['UMR [%]'], name='UMR (%)', mode='lines+markers', line=dict(color='#FF5733')), secondary_y=True)
        st.plotly_chart(fig, use_container_width=True)
        if st.button("📈 Exportar XLSX"):
            m_dict = {"Odómetro": to_val, "Tren-Km": tk_val, "UMR": umr_val}
            st.download_button("Descargar", exportar_resumen_excel(m_dict, df_ops, df_ops), "Resumen_EFE.xlsx")
    else: st.info("Sube archivos y ajusta las fechas en la barra lateral.")

with tabs[1]:
    if not df_ops.empty: st.dataframe(df_ops.style.format({'Odómetro [km]': "{:,.1f}", 'Tren-Km [km]': "{:,.1f}", 'UMR [%]': "{:.2f}%", 'E_Total': "{:,.0f}", 'IDE (kWh/km)': "{:.4f}"}), use_container_width=True)

with tabs[2]:
    if not df_tr.empty:
        st.write("### Kilometraje Diario")
        st.dataframe(df_tr.pivot_table(index="Tren", columns="Día", values="Valor", aggfunc='sum').fillna(0).style.format("{:,.1f}"), use_container_width=True)
    if not df_tr_acum.empty:
        st.write("### Odómetro Acumulado")
        st.dataframe(df_tr_acum.pivot_table(index="Tren", columns="Día", values="Valor", aggfunc='max').fillna(0).style.format("{:,.0f}"), use_container_width=True)

with tabs[3]:
    sub_e = st.tabs(["SEAT", "PRMTE", "Facturación"])
    with sub_e[0]: st.dataframe(df_seat, use_container_width=True)
    with sub_e[1]: st.dataframe(df_p_d, use_container_width=True)
    with sub_e[2]: st.dataframe(df_f_d, use_container_width=True)

with tabs[4]:
    if all_comp_full:
        df_c_raw = pd.DataFrame(all_comp_full).groupby(['Fecha','Hora','Fuente'])['Consumo Horario [kWh]'].sum().reset_index()
        piv_c = df_c_raw.pivot_table(index="Hora", columns=df_c_raw['Fecha'].dt.year, values="Consumo Horario [kWh]", aggfunc='median').fillna(0)
        st.line_chart(piv_c)

with tabs[5]:
    if all_comp_full:
        df_r = pd.DataFrame(all_comp_full).groupby(['Fecha','Hora','Fuente'])['Consumo Horario [kWh]'].sum().reset_index()
        df_r = df_r[df_r['Hora'] <= 5]
        if len(df_r) > 2:
            x, y = np.arange(len(df_r)), df_r['Consumo Horario [kWh]'].values
            m, n = np.polyfit(x, y, 1)
            st.markdown(f"**Ecuación Nocturna:** $y = {m:.4f}x + {n:.2f}$")
            st.line_chart(y)

with tabs[7]:
    st.header("📋 Datos THDR")
    def mostrar_thdr_v2(df, titulo, em):
        st.subheader(f"{em} {titulo}")
        if df.empty:
            st.warning(f"No hay datos para {titulo} en el rango seleccionado.")
            return
        df_c = df.copy()
        df_c['H_Prog'] = df_c['Min_Prog'].apply(lambda x: format_hms(x))
        df_c['H_Real'] = df_c['Min_S_Real'].apply(lambda x: format_hms(x))
        st.dataframe(df_c[['Fecha_Op', 'Servicio', 'H_Prog', 'H_Real', 'Motriz 1', 'Tipo_Rec', 'Tren-Km']], use_container_width=True)
    mostrar_thdr_v2(df_thdr_v1, "Vía 1", "🟢")
    mostrar_thdr_v2(df_thdr_v2, "Vía 2", "🔵")

st.sidebar.download_button("📥 Reporte Completo", to_excel_consolidado(df_ops, df_tr, df_tr_acum, df_seat, df_p_d, pd.DataFrame(all_prmte_15), pd.DataFrame(all_fact_h), df_f_d), "Reporte_EFE_SGE.xlsx")
