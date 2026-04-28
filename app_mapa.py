# app_mapa.py
# Controlador UI y Orquestador del Simulador MERVAL v117

import streamlit as st
import pandas as pd
import numpy as np
import time
import plotly.graph_objects as go

# =============================================================================
# IMPORTACIÓN DE LA ARQUITECTURA MODULAR (SOLID)
# =============================================================================
from config import (
    ESTACIONES, EC, KM_ACUM, SER_DATA, SER_CAPACITY_KW, 
    V_NOMINAL_AC, ETA_SER_RECTIFICADOR, FLOTA, PAX_KG, PAX_COLS
)
from motor_fisico import (
    km_at_t, vel_at_km, get_train_state_and_speed, calcular_aux_dinamico,
    calcular_flujo_ac_nodo, distribuir_energia_sers, distribuir_potencia_sers_kw,
    get_vacios_dia, calcular_receptividad_por_headway,
    precalcular_red_electrica_v111, calcular_termodinamica_flota_v111,
    procesar_planificador_reactivo, simular_tramo_termodinamico,
    calc_tren_km_real_general, get_pax_at_km
)
from datos_parser import (
    procesar_thdr, calcular_dwell, cargar_pax, match_pax, 
    parsear_planilla_maestra, mins_to_time_str, clean_id, clean_primary_key
)
from graficos import draw_diagram

# =============================================================================
# CONFIGURACIÓN DE PÁGINA Y CACHÉS
# =============================================================================
st.set_page_config(page_title="Simulador MERVAL", layout="wide", page_icon="🗺️")

def leer(files): 
    return [(f.name, f.read()) for f in (files or []) if f]

def leer_github(url):
    try:
        import urllib.request
        url = url.replace('github.com','raw.githubusercontent.com').replace('/blob/','/') if 'github.com' in url.strip() and 'raw.githubusercontent' not in url else url.strip()
        with urllib.request.urlopen(url, timeout=15) as r: 
            return url.split('/')[-1], r.read()
    except Exception as e: 
        return None, str(e)

@st.cache_data(show_spinner="Procesando THDR Estándar…")
def build_thdr_v71(blobs_v1, blobs_v2):
    all_parts, err = [], []
    for blobs_list, via_default in [(blobs_v1, 1), (blobs_v2, 2)]:
        for nm, data in blobs_list:
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
    for blobs_list, via_default in [(blobs_v1, 1), (blobs_v2, 2)]:
        for nm, data in blobs_list:
            try: 
                parts.append(cargar_pax(data, nm, via_default))
            except Exception as e: 
                err.append(f"[{nm}]: {e}")
    if len(parts) > 0: 
        return pd.concat(parts, ignore_index=True), err
    return pd.DataFrame(), err

# =============================================================================
# GEMELO DIGITAL Y DASHBOARDS
# =============================================================================
def render_gemelo_digital(df_dia, df_dia_e, active_sers, fecha_sel, pct_trac, use_rm, use_pend, estacion_anio, prefix_key, gap_vias, pax_dia_total=0):
    if 'maniobra' not in df_dia.columns: df_dia['maniobra'] = None
    if 'maniobra' not in df_dia_e.columns: df_dia_e['maniobra'] = None
        
    cf, cm = st.columns([3,2])
    with cm: 
        modo = st.radio("Modo", ["🔒 Estático","▶️ Animado"], horizontal=True, key=f"modo_{prefix_key}")

    if f'min_slider_{prefix_key}' not in st.session_state: st.session_state[f'min_slider_{prefix_key}'] = 480.0
    if f'play_{prefix_key}' not in st.session_state: st.session_state[f'play_{prefix_key}'] = False
    if modo != "▶️ Animado": st.session_state[f'play_{prefix_key}'] = False

    if st.session_state[f'play_{prefix_key}']:
        step_size = 0.2 * float(st.session_state.get(f'vs1_{prefix_key}', 1.0))
        st.session_state[f'min_slider_{prefix_key}'] = min(1439.0, st.session_state[f'min_slider_{prefix_key}'] + step_size)
        if st.session_state[f'min_slider_{prefix_key}'] >= 1439.0: 
            st.session_state[f'play_{prefix_key}'] = False

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

    st.markdown(f"<span style='font-size:2.2rem;font-weight:700;letter-spacing:2px;'>⏱ {hora_s1}</span><span style='font-size:0.9rem;color:#666;'> &nbsp;·&nbsp; {fecha_sel} &nbsp;·&nbsp; ⚙️ {pct_trac}% Tracción</span>", unsafe_allow_html=True)

    df_act = df_dia_e[(df_dia_e['t_ini'] <= hora_m1) & (df_dia_e['t_fin'] > hora_m1)].copy()
    instant_ser_demands_kw = {s[1]: 0.0 for s in active_sers}
    
    if not df_act.empty:
        frac_act = (hora_m1 - df_act['t_ini']) / np.maximum(0.001, df_act['t_fin'] - df_act['t_ini'])
        df_act['kwh_neto'] = df_act['kwh_viaje_neto'] * frac_act
        
        df_act['km_pos'] = df_act.apply(lambda r: km_at_t(r['t_ini'], r['t_fin'], hora_m1, r['Via'], use_rm, r['km_orig'], r['km_dest'], r.get('nodos')), axis=1)
        
        def _vel_real(r):
            km_now = r['km_pos']
            km_next = km_at_t(r['t_ini'], r['t_fin'], hora_m1 + 0.01, r['Via'], use_rm, r['km_orig'], r['km_dest'], r.get('nodos'))
            if abs(km_next - km_now) < 0.0001: 
                return 0.0 
            return vel_at_km(km_now, r['Via'], use_rm)
            
        df_act['vel'] = df_act.apply(_vel_real, axis=1)
        df_act['km_rec'] = df_act.apply(lambda r: max(0.0, abs(r['km_pos'] - r['km_orig'])), axis=1)
        df_act['pax_inst'] = df_act.apply(lambda r: get_pax_at_km(r.get('pax_d', {}), r['km_pos'], r['Via'], r.get('pax_abordo', 0)), axis=1)

        def _sep_next(row, df_via):
            km = row['km_pos']
            vel = row['vel']
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
            
            doble_tramo = row.get('doble', False)
            man = row.get('maniobra')
            if man in ['CORTE_BTO', 'CORTE_PU_SA_BTO']: 
                doble_tramo = True if row['km_pos'] <= KM_ACUM[14] else False
            elif man == 'ACOPLE_BTO': 
                doble_tramo = False if row['km_pos'] > KM_ACUM[14] else True
            elif man == 'CORTE_SA': 
                doble_tramo = True if row['km_pos'] <= KM_ACUM[18] else False
            elif man == 'ACOPLE_SA': 
                doble_tramo = False if row['km_pos'] > KM_ACUM[18] else True
            
            state, v_kmh = get_train_state_and_speed(hora_m1, row['Via'], use_rm, row['km_orig'], row['km_dest'], row.get('nodos'))
            
            f_flota = FLOTA.get(tipo, FLOTA["XT-100"])
            n_unidades = 2 if doble_tramo else 1
            tara_base = (f_flota['tara_t'] + f_flota['m_iner_t']) * n_unidades
            pax_v = int(row.get('pax_inst', 0))
            pax_tot = int(row.get('pax_abordo', 0))
            masa_total = tara_base + (pax_v * PAX_KG) / 1000.0
            
            v_ms = v_kmh / 3.6
            if n_unidades == 2: 
                f_davis = (f_flota['davis_A'] * 2) + (f_flota['davis_B'] * 2 * v_kmh) + (f_flota['davis_C'] * 1.35 * (v_kmh**2))
            else: 
                f_davis = f_flota['davis_A'] + f_flota['davis_B'] * v_kmh + f_flota['davis_C'] * (v_kmh**2)
            
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

            # Devolvemos el texto enriquecido para Tooltip
            cab = f"<b>{tipo} [U-{m_num}] (Serv. {serv})</b><br>"
            cab += f"Vía {row['Via']} | km {row['km_pos']:.2f} | {int(row['vel'])} km/h<br>"
            cab += f"<b>🧑 Pax Tramo: {pax_v}</b> | Total: {pax_tot}<br>"
            cab += f"⚡ Neto: {row['kwh_neto']:.1f} kWh<br>"
            return cab

        df_act['tooltip'] = df_act.apply(_make_tooltip_and_power, axis=1)

    vacios_dia = get_vacios_dia(df_dia)
    for idx, row in df_dia[df_dia['maniobra'].notnull()].iterrows():
        man = row['maniobra']
        t_arr_bto = row['t_ini'] + 40.0 if row['Via'] == 1 else row['t_ini'] + 20.0
        t_arr_sa = row['t_ini'] + 47.0 if row['Via'] == 1 else row['t_ini'] + 13.0
        dist_sa_eb = abs(KM_ACUM[18] - KM_ACUM[14])
        
        if man in ['CORTE_BTO', 'CORTE_PU_SA_BTO']:
            vacios_dia.append({'t_asigned': t_arr_bto, 'tipo': row['tipo_tren'], 'doble': False, 'cochera': True, 'dist': 2.0, 'motriz_num': f"{row.get('motriz_num', '')}-B", 'origen_txt': 'El Belloto', 'destino_txt': 'Taller EB', 'servicio_previo': row.get('num_servicio', ''), 'servicio_siguiente': '—', 'km_orig': KM_ACUM[14], 'km_dest': KM_ACUM[14]})
        elif man == 'ACOPLE_BTO':
            vacios_dia.append({'t_asigned': t_arr_bto - 5.0, 'tipo': row['tipo_tren'], 'doble': False, 'cochera': True, 'dist': 2.0, 'motriz_num': f"{row.get('motriz_num', '')}-B", 'origen_txt': 'Taller EB', 'destino_txt': 'El Belloto', 'servicio_previo': '—', 'servicio_siguiente': row.get('num_servicio', ''), 'km_orig': KM_ACUM[14], 'km_dest': KM_ACUM[14]})
        elif man == 'CORTE_SA':
            vacios_dia.append({'t_asigned': t_arr_sa, 'tipo': row['tipo_tren'], 'doble': False, 'cochera': True, 'dist': dist_sa_eb + 2.0, 'motriz_num': f"{row.get('motriz_num', '')}-B", 'origen_txt': 'Sargento Aldea', 'destino_txt': 'Taller EB', 'servicio_previo': row.get('num_servicio', ''), 'servicio_siguiente': '—', 'km_orig': KM_ACUM[18], 'km_dest': KM_ACUM[14]})
        elif man == 'ACOPLE_SA':
            vacios_dia.append({'t_asigned': t_arr_sa - 20.0, 'tipo': row['tipo_tren'], 'doble': False, 'cochera': True, 'dist': dist_sa_eb + 2.0, 'motriz_num': f"{row.get('motriz_num', '')}-B", 'origen_txt': 'Taller EB', 'destino_txt': 'Sargento Aldea', 'servicio_previo': '—', 'servicio_siguiente': row.get('num_servicio', ''), 'km_orig': KM_ACUM[14], 'km_dest': KM_ACUM[18]})

    vacios_hasta_ahora = [v for v in vacios_dia if v['t_asigned'] <= hora_m1]
    vacio_count = len(vacios_hasta_ahora)
    vacio_km_total = sum(v['dist'] * (2 if v.get('doble', False) else 1) for v in vacios_hasta_ahora)
    vacio_kwh_total = 0.0

    ser_accum_1 = {name: 0.0 for _, name in active_sers}
    energy_by_fleet = {'XT-100': 0.0, 'XT-M': 0.0, 'SFE': 0.0}
    
    for v in vacios_hasta_ahora:
        is_local_move = (v.get('km_orig') == v.get('km_dest'))
        km_fake_fin = v['km_orig'] + v['dist'] if is_local_move else v['km_dest']
        via_vacia = 1 if v['km_orig'] <= km_fake_fin else 2
        
        trc_v, aux_v, reg_v, _, _, t_horas_v = simular_tramo_termodinamico(
            v['tipo'], v.get('doble', False), v['km_orig'], km_fake_fin, 
            via_vacia, pct_trac, use_rm, use_pend if not is_local_move else False, 
            None, {}, 0, 20.0 if is_local_move else None, None, estacion_anio, v.get('t_asigned', 480.0), True
        )
        
        e_pant_vacio = trc_v + aux_v - reg_v
        
        if active_sers:
            distrib_sers = distribuir_energia_sers(e_pant_vacio, t_horas_v, v['km_orig'], km_fake_fin, active_sers)
            for s_name, e_val in distrib_sers.items(): 
                ser_accum_1[s_name] += e_val
                
        vacio_kwh_total += e_pant_vacio
        energy_by_fleet[v['tipo']] += e_pant_vacio

    t_regen_acum = 0.0
    t_trac, t_aux, t_regen, t_reostato = 0.0, 0.0, 0.0, 0.0

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
        t_trac = df_acum['kwh_viaje_trac'].sum()
        t_aux = df_acum['kwh_viaje_aux'].sum()
        t_regen = df_acum['kwh_viaje_regen'].sum()
        t_reostato = df_acum['kwh_reostato'].sum()
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

    st.divider()
    st.markdown("#### 🔌 Cargabilidad Instantánea de Subestaciones (Squeeze Control)")
    st.caption("Muestra la demanda real en kW que los trenes exigen a la red en este mismo segundo.")
    
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

        km_comercial_inic = df_inic['tren_km'].sum() if not df_inic.empty else 0.0
        km_total_red = km_comercial_inic + vacio_km_total

        st.markdown("##### ⚡ Consumo Acumulado por Subestación Rectificadora (SER a 44kV)")
        if active_sers:
            ser_cols = st.columns(len(active_sers))
            for i, ser_info in enumerate(active_sers):
                s_name = ser_info[1]
                e_ser_panto = ser_accum_1.get(s_name, 0.0)
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
            e_hora = df_dia_e.groupby('hora')[['kwh_viaje_trac', 'kwh_viaje_aux', 'kwh_viaje_regen', 'kwh_viaje_neto']].sum().reset_index()

            fig_hora = go.Figure()
            fig_hora.add_trace(go.Bar(x=e_hora['hora'], y=e_hora['kwh_viaje_trac'], name='Tracción', marker_color='#1565C0'))
            fig_hora.add_trace(go.Bar(x=e_hora['hora'], y=e_hora['kwh_viaje_aux'], name='Auxiliar', marker_color='#F9A825'))
            fig_hora.add_trace(go.Bar(x=e_hora['hora'], y=-e_hora['kwh_viaje_regen'], name='Regeneración Útil', marker_color='#2E7D32'))
            fig_hora.add_trace(go.Scatter(x=e_hora['hora'], y=e_hora['kwh_viaje_neto'] / ETA_SER_RECTIFICADOR, mode='lines', name='Demanda Est. SER', line=dict(color='red', width=2, dash='dot')))
            fig_hora.update_layout(barmode='relative', title="Energía por Hora con Demanda SER", xaxis_title="Hora", yaxis_title="kWh")

            ec1, ec2 = st.columns(2)
            with ec1: st.plotly_chart(fig_pie, use_container_width=True)
            with ec2: st.plotly_chart(fig_hora, use_container_width=True)

# =============================================================================
# MAIN ORCHESTRATOR
# =============================================================================
def main():
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
                                if "v1" in lnm or "via1" in lnm: k = "gh_blobs_px1" if "pax" in lnm or "pasajero" in lnm or "export" in lnm else "gh_blobs_v1"
                                elif "v2" in lnm or "via2" in lnm: k = "gh_blobs_px2" if "pax" in lnm or "pasajero" in lnm or "export" in lnm else "gh_blobs_v2"
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
                        st.session_state[key] = []
                        st.rerun()

        st.subheader("Planillas THDR")
        f_v1 = st.file_uploader("THDR Vía 1", accept_multiple_files=True, key="t1")
        f_v2 = st.file_uploader("THDR Vía 2", accept_multiple_files=True, key="t2")
        st.divider()
        st.subheader("Carga de Pasajeros")
        f_px1 = st.file_uploader("Pax Vía 1 (Puerto→Limache)", accept_multiple_files=True, key="px1")
        f_px2 = st.file_uploader("Pax Vía 2 (Limache→Puerto)", accept_multiple_files=True, key="px2")
        st.divider()
        st.subheader("✂️ Gestión de Flota (Split & Merge)")
        n_cortes_v1 = st.slider("Doble→Simple en El Belloto (V1, PU-LI)", 0, 20, 0)
        n_cortes_pu_sa_v1 = st.slider("Doble→Simple en El Belloto (V1, PU-SA)", 0, 20, 0)
        n_acoples_v2 = st.slider("Simple→Doble en El Belloto (V2)", 0, 20, 0)
        n_cortes_sa_v1 = st.slider("Doble→Simple en S. Aldea (V1)", 0, 20, 0)
        n_acoples_sa_v2 = st.slider("Simple→Doble en S. Aldea (V2)", 0, 20, 0)
        st.divider()
        st.subheader("⚙️ Parámetros de Simulación")
        use_rm = st.checkbox("🚦 Velocidades RM", value=False)
        pct_trac = st.slider("⚙️ % Tracción Nominal", 30, 100, 90, 5)
        use_pend = st.toggle("⛰️ Pendientes Físicas", value=True)
        use_regen = st.toggle("⚡ Activar Regeneración", value=True)
        tipo_regen = st.radio("Modelo de Regeneración", ["Físico (Load Flow / Squeeze Control)", "Probabilístico (Headway Real THDR)"])
        st.divider()
        st.subheader("🌡️ Perfil de Auxiliares Dinámicos")
        mes_sel = st.selectbox("Mes de operación", ["Enero","Febrero","Marzo","Abril","Mayo","Junio","Julio","Agosto","Septiembre","Octubre","Noviembre","Diciembre"], index=3)
        _MES_A_ESTACION = {"Enero":"verano","Febrero":"verano","Marzo":"otoño","Abril":"otoño","Mayo":"otoño","Junio":"invierno","Julio":"invierno","Agosto":"invierno","Septiembre":"primavera","Octubre":"primavera","Noviembre":"primavera","Diciembre":"verano"}
        estacion_anio = _MES_A_ESTACION[mes_sel]
        st.divider()
        st.subheader("🔌 Contingencias Eléctricas")
        all_ser_names = [s[1] for s in SER_DATA]
        active_ser_names = st.multiselect("SERs Activas", all_ser_names, default=all_ser_names)
        active_sers = [s for s in SER_DATA if s[1] in active_ser_names]
        if not active_sers: active_sers=[SER_DATA[0]]
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
                    df_all['pax_d'] = [x[0] for x in pax_res]
                    df_all['pax_abordo'] = [x[1] for x in pax_res]
                    df_all['hora_origen_pax'] = [x[2] for x in pax_res]
                    df_all['nro_thdr_pax'] = [x[3] for x in pax_res]
                    df_all['pax_row_idx'] = [x[4] for x in pax_res]
                    df_all['pax_max'] = df_all['pax_abordo']
            else:
                df_all['pax_d'] = [{}] * len(df_all)
                df_all['pax_max'] = 0
                df_all['pax_abordo'] = 0
                df_all['hora_origen_pax'] = '--:--:--'
                df_all['nro_thdr_pax'] = 'No Detectado'
                df_all['pax_row_idx'] = -1
                
            df_all['maniobra'] = None
            if n_cortes_v1 > 0:
                v1_cands = df_all[(df_all['Via'] == 1) & (df_all['doble'] == True) & (df_all['km_orig'] < 25.0) & (df_all['km_dest'] > 26.0) & (df_all['maniobra'].isnull())].copy()
                if not v1_cands.empty:
                    v1_cands['dist_valle'] = v1_cands['t_ini'].apply(lambda t: min(abs(t - 600), abs(t - 1230)))
                    df_all.loc[df_all['_id'].isin(v1_cands.sort_values('dist_valle').head(n_cortes_v1)['_id'].values), 'maniobra'] = 'CORTE_BTO'
            if n_cortes_pu_sa_v1 > 0:
                v1_pu_sa_cands = df_all[(df_all['Via'] == 1) & (df_all['doble'] == True) & (df_all['km_orig'] < 25.0) & (df_all['km_dest'] >= 28.5) & (df_all['km_dest'] <= 29.5) & (df_all['maniobra'].isnull())].copy()
                if not v1_pu_sa_cands.empty:
                    v1_pu_sa_cands['dist_valle'] = v1_pu_sa_cands['t_ini'].apply(lambda t: min(abs(t - 600), abs(t - 1230)))
                    df_all.loc[df_all['_id'].isin(v1_pu_sa_cands.sort_values('dist_valle').head(n_cortes_pu_sa_v1)['_id'].values), 'maniobra'] = 'CORTE_PU_SA_BTO'
            if n_acoples_v2 > 0:
                v2_cands = df_all[(df_all['Via'] == 2) & (df_all['km_orig'] > 26.0) & (df_all['km_dest'] < 25.0) & (df_all['maniobra'].isnull())].copy()
                if not v2_cands.empty:
                    v2_cands['dist_punta'] = v2_cands['t_ini'].apply(lambda t: min(abs(t - 390), abs(t - 1050)))
                    df_all.loc[df_all['_id'].isin(v2_cands.sort_values('dist_punta').head(n_acoples_v2)['_id'].values), 'maniobra'] = 'ACOPLE_BTO'
            if n_cortes_sa_v1 > 0:
                v1_sa_cands = df_all[(df_all['Via'] == 1) & (df_all['doble'] == True) & (df_all['km_orig'] < 29.0) & (df_all['km_dest'] > 30.0) & (df_all['maniobra'].isnull())].copy()
                if not v1_sa_cands.empty:
                    v1_sa_cands['dist_valle'] = v1_sa_cands['t_ini'].apply(lambda t: min(abs(t - 600), abs(t - 1230)))
                    df_all.loc[df_all['_id'].isin(v1_sa_cands.sort_values('dist_valle').head(n_cortes_sa_v1)['_id'].values), 'maniobra'] = 'CORTE_SA'
            if n_acoples_sa_v2 > 0:
                v2_sa_cands = df_all[(df_all['Via'] == 2) & (df_all['km_orig'] > 30.0) & (df_all['km_dest'] < 29.0) & (df_all['maniobra'].isnull())].copy()
                if not v2_sa_cands.empty:
                    v2_sa_cands['dist_punta'] = v2_sa_cands['t_ini'].apply(lambda t: min(abs(t - 390), abs(t - 1050)))
                    df_all.loc[df_all['_id'].isin(v2_sa_cands.sort_values('dist_punta').head(n_acoples_sa_v2)['_id'].values), 'maniobra'] = 'ACOPLE_SA'

            df_all['tren_km'] = df_all.apply(calc_tren_km_real_general, axis=1)
            st.success(f"✅ {len(df_all)} despachos operativos históricos cargados.")
        else:
            df_all = pd.DataFrame()

    fechas = sorted(list(set([str(d) for d in df_all['Fecha_str'].unique() if str(d) != '2026-01-01' and pd.notna(d)]))) if not df_all.empty else []

    tab_mapa, tab_datos, tab_vacios, tab_planificador = st.tabs(["🗺️ Mapa Operativo Histórico", "📋 Reporte Pasajeros", "🚉 Maniobras en Vacío", "🔮 Planificador Inteligente"])
    
    with tab_planificador:
        st.subheader("🔮 Planificador Avanzado: Gemelo Digital de Inyecciones (V117)")
        st.markdown("El algoritmo ruteará los trenes de la Planilla Maestra basándose en el N° de Servicio y calculará los tiempos de llegada usando Física Pura.")
        
        col_p1, col_p2 = st.columns([1, 2])
        with col_p1:
            estacion_anio_plan = st.selectbox("🌡️ Estación del Año (HVAC)", ["verano", "otoño", "invierno", "primavera"], index=3, key="est_plan")
            df_px_filtered = pd.DataFrame()
            nombre_perfil = "Estático (150 pax)"
            
            if not df_px.empty:
                fechas_disp = sorted([str(x) for x in df_px['Fecha_s'].dropna().unique() if str(x).strip() and str(x).lower() not in ["none", "nan", "fecha no detectada"]])
                fechas_sel_plan = st.multiselect("📅 Fechas para Perfil de Demanda (Promedio)", fechas_disp, default=[fechas_disp[0]] if fechas_disp else None, key="ms_pax_plan")
                if fechas_sel_plan:
                    st.success(f"✅ Extrayendo demanda operativa de {len(fechas_sel_plan)} día(s).")
                    nombre_perfil = f"Pax Real ({len(fechas_sel_plan)} días)"
                    df_px_filtered = df_px[df_px['Fecha_s'].isin(fechas_sel_plan)].copy()
                    for c in PAX_COLS + ['CargaMax', 't_ini_p']: 
                        df_px_filtered[c] = pd.to_numeric(df_px_filtered[c], errors='coerce').fillna(0)
                else: 
                    st.warning("⚠️ Selecciona al menos una fecha.")
            else: 
                st.warning("⚠️ Sin datos de pasajeros cargados. Usando perfil estático: 150 pax")
            
        with col_p2:
            modo_plan = st.radio("Fuente de Datos", ["Planilla Maestra (Subir CSV/Excel)", "Matriz Sintética", "Laboratorio (Tramo Único)"], horizontal=True)
            if modo_plan == "Matriz Sintética":
                if 'df_plan' not in st.session_state: 
                    st.session_state['df_plan'] = pd.DataFrame([{"Origen": "Puerto", "Destino": "Limache", "Flota": "XT-100", "Configuración": "Doble", "Cantidad": 40}])
                df_plan_edit = st.data_editor(st.session_state['df_plan'], num_rows="dynamic", use_container_width=True)
            
            elif modo_plan == "Planilla Maestra (Subir CSV/Excel)":
                archivo_planilla = st.file_uploader("📂 Sube tu Planilla Maestra (.csv, .xlsx, .xls)", type=['csv', 'xlsx', 'xls'])
                if archivo_planilla:
                    df_temp, msg = parsear_planilla_maestra(archivo_planilla.getvalue(), archivo_planilla.name)
                    if df_temp.empty: 
                        st.error(f"Error procesando: {msg}")
                    else:
                        st.success("✅ Planilla decodificada. Distribuye la cantidad de flota por trayecto (Rolling Stock Rostering):")
                        rutas_unicas = list(df_temp['svc_type'].value_counts().keys())
                        if 'flota_map_v2' not in st.session_state or set(st.session_state['flota_map_v2']['Ruta']) != set(rutas_unicas):
                            st.session_state['flota_map_v2'] = pd.DataFrame([{"Ruta": r, "Total Viajes": df_temp['svc_type'].value_counts()[r], "XT-100": df_temp['svc_type'].value_counts()[r], "XT-M": 0, "SFE": 0} for r in rutas_unicas])
                        
                        df_flota_edit = st.data_editor(st.session_state['flota_map_v2'], hide_index=True, use_container_width=True)
                        if not df_flota_edit[df_flota_edit['XT-100'] + df_flota_edit['XT-M'] + df_flota_edit['SFE'] != df_flota_edit['Total Viajes']].empty: 
                            st.warning("⚠️ Hay trayectos donde la suma no coincide con el total. El remanente será XT-100.")
                        
                        st.session_state['temp_df_plan'] = df_temp
                        st.session_state['temp_flota_edit'] = df_flota_edit
            
            elif modo_plan == "Laboratorio (Tramo Único)":
                tipo_mov_lab = st.radio("Modo de Operación", ["Servicio Comercial (Con Paradas)", "Maniobra en Vacío (Pasa de largo a 30 km/h)"], horizontal=True)
                col_s1, col_s2, col_s3, col_s4 = st.columns(4)
                with col_s1: sb_orig = st.selectbox("Estación Origen", ESTACIONES, key="sb_o")
                with col_s2: sb_dest = st.selectbox("Estación Destino", ESTACIONES, index=len(ESTACIONES)-1, key="sb_d")
                with col_s3: sb_flota = st.selectbox("Tipo de Tren", ["XT-100", "XT-M", "SFE"], key="sb_f")
                with col_s4: sb_pax = 0 if "Vacío" in tipo_mov_lab else st.number_input("Pasajeros a bordo", 0, 1000, 150)
                
                if st.button("⚡ Simular Tramo", use_container_width=True):
                    if sb_orig != sb_dest:
                        idx_o, idx_d = ESTACIONES.index(sb_orig), ESTACIONES.index(sb_dest)
                        km_o, km_d = KM_ACUM[idx_o], KM_ACUM[idx_d]
                        via_sb = 1 if idx_o < idx_d else 2
                        es_vacio_flag = "Vacío" in tipo_mov_lab
                        nodos_sb = [(0.0, KM_ACUM[idx_o]), (0.0, KM_ACUM[idx_d])] if es_vacio_flag else [(0.0, KM_ACUM[i]) for i in (range(idx_o, idx_d + 1) if via_sb == 1 else range(idx_o, idx_d - 1, -1))]
                        
                        with st.spinner("Calculando termodinámica..."):
                            trc_sb, aux_sb, reg_sb, _, neto_sb, th_sb = simular_tramo_termodinamico(sb_flota, False, km_o, km_d, via_sb, pct_trac, use_rm, use_pend, nodos_sb, {}, sb_pax, None, None, estacion_anio_plan, 480.0, es_vacio_flag)
                        
                        distrib_sb = distribuir_energia_sers(neto_sb, th_sb, km_o, km_d, active_sers)
                        tot_ser_sb = sum(max(0.0, v) for v in distrib_sb.values()) / ETA_SER_RECTIFICADOR
                        avg_dem_sb = {k: max(0.0, v) / ETA_SER_RECTIFICADOR / max(0.001, th_sb) for k, v in distrib_sb.items()}
                        loss_sb = calcular_flujo_ac_nodo(avg_dem_sb)['P_loss_kw'] * (1.15**2) * max(0.001, th_sb)
                        seat_sb = (tot_ser_sb + loss_sb) / 0.99
                        ide_sb = seat_sb / max(0.001, abs(km_d - km_o))
                        
                        st.success(f"Simulación exitosa: {sb_orig} ➔ {sb_dest} | Distancia: {abs(km_d - km_o):.2f} km")
                        c_sb1, c_sb2, c_sb3 = st.columns(3)
                        c_sb1.metric("⏱️ Tiempo de Viaje", f"{th_sb * 60:.1f} min")
                        c_sb2.metric("⚡ Energía Neta (SEAT)", f"{seat_sb:.1f} kWh")
                        c_sb3.metric("💡 IDE del Tramo (SEAT)", f"{ide_sb:.3f} kWh/km")
        
        if modo_plan in ["Matriz Sintética", "Planilla Maestra (Subir CSV/Excel)"] and st.button("🚀 Ejecutar Gemelo Digital del Planificador", use_container_width=True, type="primary"):
            st.session_state['simulacion_plan_lista'] = False
            with st.spinner("Decodificando Planilla e inyectando al Motor Cinemático Termodinámico..."):
                if modo_plan == "Matriz Sintética":
                    df_sintetico_list = []
                    for idx, row in df_plan_edit.iterrows():
                        if row['Cantidad'] <= 0 or row['Origen'] == row['Destino']: continue
                        i_o, i_d = ESTACIONES.index(row['Origen']), ESTACIONES.index(row['Destino'])
                        via = 1 if i_o < i_d else 2
                        nodos_sint = [(0.0, KM_ACUM[i]) for i in (range(i_o, i_d + 1) if via==1 else range(i_o, i_d - 1, -1))]
                        k_o, k_d = KM_ACUM[i_o], KM_ACUM[i_d]
                        svc_t = f"{EC[i_o]}-{EC[i_d]}"
                        interval = (1350 - 360) / row['Cantidad']
                        
                        for i in range(int(row['Cantidad'])):
                            df_sintetico_list.append({
                                '_id': f"SINT_{idx}_{i}", 't_ini': 360 + i * interval, 'Via': via, 
                                'km_orig': k_o, 'km_dest': k_d, 'nodos': nodos_sint, 
                                'tipo_tren': row['Flota'], 'doble': row['Configuración'] == "Doble", 
                                'num_servicio': f"VIRT_{idx}_{i}", 'maniobra': None, 'svc_type': svc_t
                            })
                    df_sint = pd.DataFrame(df_sintetico_list)
                else:
                    if 'temp_df_plan' not in st.session_state: st.stop()
                    df_sint = st.session_state['temp_df_plan'].copy().sort_values('t_ini')
                    
                    asignaciones = {}
                    for _, r in st.session_state['temp_flota_edit'].iterrows():
                        asignaciones[r['Ruta']] = ['XT-100']*int(r.get('XT-100', 0)) + ['XT-M']*int(r.get('XT-M', 0)) + ['SFE']*int(r.get('SFE', 0))
                        
                    def asignar_tren(ruta):
                        if ruta in asignaciones and len(asignaciones[ruta]) > 0: return asignaciones[ruta].pop(0)
                        return 'XT-100'
                        
                    df_sint['tipo_tren'] = df_sint['svc_type'].apply(asignar_tren)

                if df_sint.empty: st.stop()
                st.session_state['raw_plan_df'] = df_sint
                st.session_state['simulacion_plan_lista'] = True

        if st.session_state.get('simulacion_plan_lista', False) and 'raw_plan_df' in st.session_state:
            df_sint_final, df_sint_e = procesar_planificador_reactivo(st.session_state['raw_plan_df'], df_px_filtered, estacion_anio_plan, pct_trac, use_rm, use_pend, use_regen, tipo_regen)
            st.divider()
            render_gemelo_digital(df_sint_final, df_sint_e, active_sers, f"Planificador: {nombre_perfil}", pct_trac, use_rm, use_pend, estacion_anio_plan, prefix_key="plan", gap_vias=gap_vias, pax_dia_total=int(df_sint_final['pax_abordo'].sum()))
            
            st.divider()
            st.markdown("### 📅 Proyección Estratégica Mensual (Capex/Opex)")
            c1, c2, c3 = st.columns(3)
            with c1: d_lab = st.number_input("Días Laborales en el mes", 0, 31, 22)
            with c2: d_sab = st.number_input("Sábados en el mes", 0, 5, 4)
            with c3: d_dom = st.number_input("Domingos/Festivos", 0, 10, 4)
            
            total_dias_mes = d_lab + d_sab + d_dom
            ser_accum_plan = {name: 0.0 for _, name in active_sers}
            for _, r in df_sint_e.iterrows():
                for s, v in distribuir_energia_sers(r['kwh_viaje_neto'], (r['t_fin']-r['t_ini'])/60.0, r['km_orig'], r['km_dest'], active_sers).items(): 
                    ser_accum_plan[s] += v
            
            tot_44_plan = sum(max(0.0, v) for v in ser_accum_plan.values()) / ETA_SER_RECTIFICADOR
            t_elap_plan = max(0.001, (df_sint_e['t_fin'].max() - df_sint_e['t_ini'].min()) / 60.0)
            
            loss_plan = calcular_flujo_ac_nodo({k: max(0.0, v) / ETA_SER_RECTIFICADOR / t_elap_plan for k, v in ser_accum_plan.items()})['P_loss_kw'] * (1.15**2) * t_elap_plan
            seat_dia = (tot_44_plan + loss_plan) / 0.99
            
            cm1, cm2, cm3, cm4 = st.columns(4)
            cm1.metric("⚡ Energía Facturable Mensual", f"{seat_dia * total_dias_mes:,.0f} kWh")
            cm2.metric("💡 IDE Promedio Mensual", f"{seat_dia / max(1.0, df_sint_e['tren_km'].sum()):.3f} kWh/km")
            cm3.metric("🧑‍🤝‍🧑 Pasajeros Mensuales", f"{int(df_sint_final['pax_abordo'].sum()) * total_dias_mes:,} pax")
            cm4.metric("💰 Costo Energía Mensual", f"${seat_dia * total_dias_mes * 100:,.0f} CLP")

    with tab_mapa:
        if df_all.empty: 
            st.warning("⚠️ Requiere carga de THDR.")
        else:
            fecha_sel = st.selectbox("📅 Fecha Operativa (THDR)", fechas, key="fs_hist")
            df_dia = df_all[df_all['Fecha_str'] == fecha_sel].copy()
            
            dict_regen = calcular_receptividad_por_headway(df_dia) if use_regen and "Probabilístico" in tipo_regen else (precalcular_red_electrica_v111(df_dia, pct_trac, use_rm, estacion_anio) if use_regen else {})
            df_dia_e = calcular_termodinamica_flota_v111(df_dia, pct_trac, use_pend, use_rm, use_regen, dict_regen, estacion_anio)
            
            df_dia_px_total = df_px[df_px['Fecha_s'] == fecha_sel] if not df_px.empty and 'Fecha_s' in df_px.columns else pd.DataFrame()
            pax_dia_tot = int(pd.to_numeric(df_dia_px_total['CargaMax'], errors='coerce').fillna(0).sum()) if not df_dia_px_total.empty else 0
            
            render_gemelo_digital(df_dia, df_dia_e, active_sers, fecha_sel, pct_trac, use_rm, use_pend, estacion_anio, "mapa", gap_vias, pax_dia_tot)

    with tab_datos:
        if df_px.empty: 
            st.warning("⚠️ Sin datos de pasajeros.")
        else:
            fechas_disp = sorted([str(x) for x in df_px['Fecha_s'].dropna().unique() if str(x).strip() and str(x).lower() not in ["none", "nan", "fecha no detectada"]])
            fecha_sel_pax = st.multiselect("📅 Selecciona Fechas a evaluar (Si eliges varias, se promediarán)", fechas_disp, default=[fechas_disp[0]] if fechas_disp else None)
            
            if not fecha_sel_pax: 
                st.info("Selecciona al menos una fecha.")
            else:
                df_dia_pax = df_px[df_px['Fecha_s'].isin(fecha_sel_pax)].copy()
                df_dia_pax['t_ini_p'] = pd.to_numeric(df_dia_pax['t_ini_p'], errors='coerce')
                for c in PAX_COLS + ['CargaMax']: 
                    df_dia_pax[c] = pd.to_numeric(df_dia_pax[c], errors='coerce').fillna(0)
                
                if len(fecha_sel_pax) > 1:
                    agg_dict = {c: 'mean' for c in PAX_COLS}
                    agg_dict['CargaMax'] = 'mean'
                    df_dia_pax = df_dia_pax.groupby(['Via', 't_ini_p']).agg(agg_dict).reset_index()
                    for c in PAX_COLS + ['CargaMax']: 
                        df_dia_pax[c] = df_dia_pax[c].round().astype(int)
                    df_dia_pax['Fecha'] = f"Promedio ({len(fecha_sel_pax)} días)"
                    df_dia_pax['N° THDR Pax'] = 'Promedio Varios Días'
                    df_dia_pax['Servicio'] = '—'
                else:
                    df_dia_pax.rename(columns={'Fecha_s': 'Fecha', 'Nro_THDR': 'N° THDR Pax', 'Tren': 'Servicio'}, inplace=True)
                    for c in PAX_COLS + ['CargaMax']: 
                        df_dia_pax[c] = df_dia_pax[c].astype(int)

                df_dia_pax = df_dia_pax.sort_values(by=['Via', 't_ini_p'])
                df_dia_pax['Hora Origen'] = df_dia_pax['t_ini_p'].apply(mins_to_time_str)
                df_dia_pax.rename(columns={'CargaMax': 'Total a Bordo'}, inplace=True)
                
                t_v1 = df_dia_pax[df_dia_pax['Via']==1]['Total a Bordo'].sum()
                t_v2 = df_dia_pax[df_dia_pax['Via']==2]['Total a Bordo'].sum()
                
                st.markdown(f"### 📊 Resumen de Pasajeros {'(PROMEDIO)' if len(fecha_sel_pax) > 1 else ''}")
                cc1, cc2, cc3 = st.columns(3)
                cc1.metric("Total Pasajeros V1", f"{int(t_v1):,}")
                cc2.metric("Total Pasajeros V2", f"{int(t_v2):,}")
                cc3.metric("Total Ambas Vías", f"{int(t_v1+t_v2):,}")
                
                cols_v = ['Fecha', 'N° THDR Pax', 'Servicio', 'Hora Origen', 'Total a Bordo']
                df_v1 = df_dia_pax[df_dia_pax['Via']==1][cols_v + PAX_COLS]
                df_v2 = df_dia_pax[df_dia_pax['Via']==2][cols_v + list(reversed(PAX_COLS))]
                
                if not df_v1.empty: 
                    st.subheader("🔵 V1 (PU → LI)")
                    st.dataframe(df_v1, use_container_width=True)
                if not df_v2.empty: 
                    st.subheader("🔴 V2 (LI → PU)")
                    st.dataframe(df_v2, use_container_width=True)
                if not df_v1.empty or not df_v2.empty:
                    out_name = f"Pax_Promedio_{len(fecha_sel_pax)}dias.csv" if len(fecha_sel_pax) > 1 else f"Pax_{fecha_sel_pax[0]}.csv"
                    st.download_button("📥 Descargar CSV", pd.concat([df_v1, df_v2]).to_csv(index=False).encode('utf-8'), out_name, 'text/csv')

    with tab_vacios:
        if df_all.empty: 
            st.warning("⚠️ Requiere carga de THDR.")
        else:
            fecha_sel_vacios = st.selectbox("📅 Filtrar Fecha Operativa", fechas, key="fs_vacios")
            vacios_list = get_vacios_dia(df_all[df_all['Fecha_str'] == fecha_sel_vacios].copy())
            
            for idx, row in df_all[(df_all['Fecha_str'] == fecha_sel_vacios) & (df_all['maniobra'].notnull())].iterrows():
                man, t_ini = row['maniobra'], row['t_ini']
                if man in ['CORTE_BTO', 'CORTE_PU_SA_BTO']: 
                    vacios_list.append({'t_asigned': t_ini + 40.0 if row['Via'] == 1 else t_ini + 20.0, 'tipo': row['tipo_tren'], 'doble': False, 'cochera': True, 'dist': 2.0, 'motriz_num': f"{row.get('motriz_num', '')}-B", 'origen_txt': 'El Belloto', 'destino_txt': 'Taller EB', 'km_orig': KM_ACUM[14], 'km_dest': KM_ACUM[14]})
                elif man == 'ACOPLE_BTO': 
                    vacios_list.append({'t_asigned': (t_ini + 40.0 if row['Via'] == 1 else t_ini + 20.0) - 5.0, 'tipo': row['tipo_tren'], 'doble': False, 'cochera': True, 'dist': 2.0, 'motriz_num': f"{row.get('motriz_num', '')}-B", 'origen_txt': 'Taller EB', 'destino_txt': 'El Belloto', 'km_orig': KM_ACUM[14], 'km_dest': KM_ACUM[14]})
                elif man == 'CORTE_SA': 
                    vacios_list.append({'t_asigned': t_ini + 47.0 if row['Via'] == 1 else t_ini + 13.0, 'tipo': row['tipo_tren'], 'doble': False, 'cochera': True, 'dist': abs(KM_ACUM[18] - KM_ACUM[14]) + 2.0, 'motriz_num': f"{row.get('motriz_num', '')}-B", 'origen_txt': 'Sargento Aldea', 'destino_txt': 'Taller EB', 'km_orig': KM_ACUM[18], 'km_dest': KM_ACUM[14]})
                elif man == 'ACOPLE_SA': 
                    vacios_list.append({'t_asigned': (t_ini + 47.0 if row['Via'] == 1 else t_ini + 13.0) - 20.0, 'tipo': row['tipo_tren'], 'doble': False, 'cochera': True, 'dist': abs(KM_ACUM[18] - KM_ACUM[14]) + 2.0, 'motriz_num': f"{row.get('motriz_num', '')}-B", 'origen_txt': 'Taller EB', 'destino_txt': 'Sargento Aldea', 'km_orig': KM_ACUM[14], 'km_dest': KM_ACUM[18]})
            
            if not vacios_list: 
                st.info("Sin maniobras en vacío.")
            else:
                tabla_vacios = [{"Hora Estimada": mins_to_time_str(v['t_asigned']), "Tren (Motriz)": str(v.get('motriz_num', '')), "Origen": v.get('origen_txt', ''), "Destino": v.get('destino_txt', ''), "Tren-km": round(v.get('dist', 0) * (2 if v.get('doble') else 1), 2), "Configuración": v.get('tipo', 'XT-100')} for v in vacios_list]
                df_vacios_out = pd.DataFrame(tabla_vacios).sort_values("Hora Estimada")
                st.metric("Total Movimientos", len(df_vacios_out))
                st.dataframe(df_vacios_out, use_container_width=True)

if __name__ == "__main__": 
    main()