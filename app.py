import streamlit as st
import pandas as pd
import numpy as np

from config import *
from etl_parser import (
    procesar_thdr, calcular_dwell, cargar_pax, match_pax, 
    get_perfiles_pax, parsear_planilla_maestra, 
    calc_tren_km_real_general, clean_id, mins_to_time_str
)
from motor_fisico import calcular_termodinamica_flota_v111, calcular_receptividad_por_headway, precalcular_red_electrica_v111, simular_tramo_termodinamico
from ui_dashboards import render_gemelo_digital, render_dashboard_energia_v112
from red_electrica import distribuir_energia_sers, calcular_flujo_ac_nodo

st.set_page_config(page_title="Simulador MERVAL", layout="wide", page_icon="🗺️")

def leer(files): 
    return [(f.name, f.read()) for f in (files or []) if f]

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
    all_parts, err = [], []
    for blobs, via_default in [(blobs_v1, 1), (blobs_v2, 2)]:
        for nm, data in blobs:
            df, msg = procesar_thdr(data, nm, via_default)
            if not df.empty: all_parts.append(df)
            else: err.append(f"[{nm}]: {msg}")
    
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
            try: parts.append(cargar_pax(data, nm, via_default))
            except Exception as e: err.append(f"[{nm}]: {e}")
    if len(parts) > 0: return pd.concat(parts, ignore_index=True), err
    return pd.DataFrame(), err

def main():
    # =========================================================================
    # CALLBACK DE INVALIDACIÓN DE ESTADO (STATE DESYNC FIX)
    # Destruye la caché del planificador si se alteran parámetros físicos
    # =========================================================================
    def reset_plan_state():
        keys_to_clear = [
            'plan_ready', 'plan_sint_final', 'plan_sint_e',
            'simulacion_plan_lista', 'raw_plan_df'
        ]
        for key in keys_to_clear:
            if key in st.session_state:
                del st.session_state[key]

    with st.sidebar:
        st.header("📂 Archivos Base")
        with st.expander("🔗 Cargar desde GitHub (Batch)", expanded=False):
            urls_txt = st.text_area("Lista de URLs", placeholder="https://github.com/...", height=100)
            gh_via = st.radio("Tipo manual", ["Detección Automática", "THDR V1", "THDR V2", "Pasajeros V1", "Pasajeros V2"], horizontal=False, index=0)
            if st.button("⬇️ Descargar Todo", use_container_width=True): 
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
        f_v1 = st.file_uploader("THDR Vía 1", accept_multiple_files=True, key="t1")
        f_v2 = st.file_uploader("THDR Vía 2", accept_multiple_files=True, key="t2")
        st.divider()
        st.subheader("Carga de Pasajeros")
        f_px1 = st.file_uploader("Pax Vía 1 (Puerto→Limache)", accept_multiple_files=True, key="px1")
        f_px2 = st.file_uploader("Pax Vía 2 (Limache→Puerto)", accept_multiple_files=True, key="px2")
        st.divider()
        st.subheader("✂️ Gestión de Flota (Split & Merge)")
        n_cortes_v1       = st.slider("Doble→Simple en El Belloto (V1, PU-LI)",0,20,0, on_change=reset_plan_state)
        n_cortes_pu_sa_v1 = st.slider("Doble→Simple en El Belloto (V1, PU-SA)",0,20,0, on_change=reset_plan_state)
        n_acoples_v2      = st.slider("Simple→Doble en El Belloto (V2)",0,20,0, on_change=reset_plan_state)
        n_cortes_sa_v1    = st.slider("Doble→Simple en S. Aldea (V1)",0,20,0, on_change=reset_plan_state)
        n_acoples_sa_v2   = st.slider("Simple→Doble en S. Aldea (V2)",0,20,0, on_change=reset_plan_state)
        st.divider()
        st.subheader("⚙️ Parámetros de Simulación")
        use_rm      = st.checkbox("🚦 Velocidades RM", value=False, on_change=reset_plan_state)
        pct_trac    = st.slider("⚙️ % Tracción Nominal",30,100,90,5, on_change=reset_plan_state)
        use_pend    = st.toggle("⛰️ Pendientes Físicas", value=True, on_change=reset_plan_state)
        use_regen   = st.toggle("⚡ Activar Regeneración", value=True, on_change=reset_plan_state)
        tipo_regen  = st.radio("Modelo de Regeneración", ["Físico (Load Flow / Squeeze Control)", "Probabilístico (Headway Real THDR)"], on_change=reset_plan_state)
        st.divider()
        st.subheader("🌡️ Perfil de Auxiliares Dinámicos")
        mes_sel = st.selectbox("Mes de operación", ["Enero","Febrero","Marzo","Abril","Mayo","Junio","Julio","Agosto","Septiembre","Octubre","Noviembre","Diciembre"], index=3, on_change=reset_plan_state)
        estacion_anio = MES_A_ESTACION[mes_sel]
        st.divider()
        st.subheader("🔌 Contingencias Eléctricas")
        all_ser_names = [s[1] for s in SER_DATA]
        active_ser_names = st.multiselect("SERs Activas", all_ser_names, default=all_ser_names, on_change=reset_plan_state)
        active_sers = [s for s in SER_DATA if s[1] in active_ser_names]
        if not active_sers: active_sers = [SER_DATA[0]]
        st.divider()
        gap_vias = st.slider("Separación Visual Vías (px)", 120, 350, 200, 10)

    def _all_blobs_internal(f_uploader, gh_key): 
        return tuple(leer(f_uploader) + st.session_state.get(gh_key, []))

    b1 = _all_blobs_internal(f_v1, "gh_blobs_v1")
    b2 = _all_blobs_internal(f_v2, "gh_blobs_v2")
    bx1 = _all_blobs_internal(f_px1, "gh_blobs_px1")
    bx2 = _all_blobs_internal(f_px2, "gh_blobs_px2")
    
    df1, df2, err_t = build_thdr_v71(b1, b2)
    df_px, err_p = build_pax_v71(bx1, bx2)
    
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


    # =========================================================================
    # ESTRUCTURA DE TABS (SIEMPRE VISIBLE) - EMPTY STATES APLICADOS
    # =========================================================================
    tab_mapa, tab_datos, tab_vacios, tab_planificador = st.tabs(["🗺️ Mapa Operativo Histórico", "📋 Reporte Pasajeros", "🚉 Maniobras en Vacío", "🔮 Planificador Inteligente"])
    
    with tab_planificador:
        st.subheader("🔮 Planificador Avanzado: Gemelo Digital de Inyecciones (V117)")
        st.markdown("El algoritmo ruteará los trenes de la Planilla Maestra basándose en el N° de Servicio y calculará los tiempos de llegada usando Física Pura.")
        
        col_p1, col_p2 = st.columns([1, 2])
        with col_p1:
            tipo_dia_plan = st.selectbox("📅 Tipo de Día para Perfil de Demanda", ["Laboral", "Sábado", "Domingo/Festivo"], key="td_plan", on_change=reset_plan_state)
            pax_promedio_viaje = {"Laboral": 280, "Sábado": 160, "Domingo/Festivo": 110}[tipo_dia_plan]
            estacion_anio_plan = st.selectbox("🌡️ Estación del Año (HVAC)", ["verano", "otoño", "invierno", "primavera"], index=3, key="est_plan", on_change=reset_plan_state)
            
            if perfiles_pax:
                st.success("✅ Perfiles de pasajeros cargados. El Gemelo variará la masa del tren en cada estación.")
            else:
                st.warning(f"⚠️ Sin datos de pasajeros cargados. Se usará perfil estático: {pax_promedio_viaje} pax")
            
        with col_p2:
            modo_plan = st.radio("Fuente de Datos", ["Planilla Maestra (Subir CSV/Excel)", "Matriz Sintética"], horizontal=True, on_change=reset_plan_state)
            archivo_planilla = None
            
            if modo_plan == "Matriz Sintética":
                if 'df_plan' not in st.session_state:
                    st.session_state['df_plan'] = pd.DataFrame([
                        {"Ruta": "PU-LI", "Flota": "XT-100", "Configuración": "Doble", "Cantidad": 40},
                        {"Ruta": "LI-PU", "Flota": "XT-100", "Configuración": "Doble", "Cantidad": 40},
                    ])
                df_plan_edit = st.data_editor(st.session_state['df_plan'], num_rows="dynamic", use_container_width=True)
            else:
                archivo_planilla = st.file_uploader("📂 Sube tu Planilla Maestra (.csv, .xlsx, .xls)", type=['csv', 'xlsx', 'xls'])
                df_plan_edit = pd.DataFrame()
                if archivo_planilla: st.success("Planilla detectada. Lista para simular.")
            
        # =====================================================================
        # EJECUCIÓN DESACOPLADA (Botón guarda en memoria RAM el cálculo)
        # =====================================================================
        if st.button("🚀 Ejecutar Gemelo Digital del Planificador", use_container_width=True, type="primary", key="btn_plan_full"):
            with st.spinner("Decodificando Planilla e inyectando al Motor Cinemático Termodinámico..."):
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
                        st.stop()
                    df_sint, msg = parsear_planilla_maestra(archivo_planilla.read(), archivo_planilla.name)
                    if df_sint.empty:
                        st.error(f"Error procesando: {msg}")
                        st.stop()

                if df_sint.empty:
                    st.warning("No hay viajes para simular.")
                    st.stop()

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
                
                # Guardamos en Memoria (Session State)
                st.session_state['plan_ready'] = True
                st.session_state['plan_sint_final'] = df_sint_final
                st.session_state['plan_sint_e'] = df_sint_e

        # RENDERIZADO CONTINUO (Fuera del botón)
        if st.session_state.get('plan_ready', False):
            st.divider()
            st.success("✅ Malla Operativa Físicamente Validada y Calculada con Perfiles Dinámicos de Masa")
            
            df_final_mem = st.session_state['plan_sint_final']
            df_e_mem = st.session_state['plan_sint_e']
            
            render_gemelo_digital(df_final_mem, df_e_mem, active_sers, f"Planificador: {tipo_dia_plan} ({estacion_anio_plan.capitalize()})", pct_trac, use_rm, use_pend, estacion_anio_plan, prefix_key="plan", gap_vias=gap_vias, pax_dia_total=int(df_final_mem['pax_abordo'].sum()))

    with tab_mapa:
        if df_all.empty:
            st.warning("⚠️ El Mapa Operativo y Termodinámico requiere la carga de los archivos **THDR Históricos** para funcionar. Por favor, súbelos en la barra lateral.")
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
            
            render_gemelo_digital(df_dia, df_dia_e, active_sers, fecha_sel, pct_trac, use_rm, use_pend, estacion_anio, prefix_key="mapa", gap_vias=gap_vias, pax_dia_total=pax_dia_tot)

    with tab_datos:
        st.subheader("📋 Auditoría de Datos: Carga de Pasajeros (Fuente Pura y Transparente)")
        st.markdown("Esta vista te permite verificar exactamente qué leyó el sistema de tu archivo de Excel, fila por fila.")
        
        if df_px.empty:
            st.warning("⚠️ No hay datos de pasajeros cargados. Sube la **Carga de Pasajeros** en la barra lateral para generar la auditoría.")
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
        st.markdown("Esta tabla audita todos los movimientos de los trenes sin pasajeros detectados en el sistema.")
        
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
