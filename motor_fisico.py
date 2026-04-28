# motor_fisico.py
# Módulo de física, cinemática y termodinámica del simulador MERVAL.

import streamlit as st
import pandas as pd
import numpy as np
from config import (
    FLOTA, SPEED_PROFILE, KM_ACUM, KM_TOTAL, ESTACIONES, EC, PAX_COLS,
    _ELEV_KM, _ELEV_M, SER_DATA, SEAT_KM, SER_CAPACITY_KW, SEAT_CAPACITY_KW,
    Z_EFF_44KV, R_AC_44KV, V_NOMINAL_AC, PAX_KG, DWELL_DEF, DAVIS_E_N_PERMIL,
    ETA_TRAC_SISTEMA, ETA_REGEN_NETA, LAMBDA_REGEN_KM, ETA_SER_RECTIFICADOR,
    ETA_MAX, V_NOMINAL_DC, V_SQUEEZE_WARN, _AUX_HVAC_HORA, _FRAC_HVAC,
    _FRAC_BASE, _FACTOR_DWELL_COMPRESOR, N_EST
)

def calc_tren_km_real_general(row):
    k_s = min(row['km_orig'], row['km_dest'])
    k_e = max(row['km_orig'], row['km_dest'])
    man = row.get('maniobra')
    
    if man in ['CORTE_BTO', 'ACOPLE_BTO', 'CORTE_PU_SA_BTO']:
        km_man = KM_ACUM[14]
        if k_s <= km_man <= k_e: 
            return abs(km_man - k_s) * 2.0 + abs(k_e - km_man) * 1.0
    elif man in ['CORTE_SA', 'ACOPLE_SA']:
        km_man = KM_ACUM[18]
        if k_s <= km_man <= k_e: 
            return abs(km_man - k_s) * 2.0 + abs(k_e - km_man) * 1.0
            
    factor = 2.0 if row.get('doble', False) else 1.0
    return abs(k_e - k_s) * factor

def get_pax_at_km(pax_d, km_pos, via, pax_max_fallback=0):
    if not pax_d or not isinstance(pax_d, dict): 
        return pax_max_fallback
    if sum(pax_d.values()) == 0 and pax_max_fallback > 0: 
        return pax_max_fallback
        
    pax_val = 0
    if via == 1:
        for i in range(N_EST):
            if km_pos >= KM_ACUM[i]:
                val = pax_d.get(PAX_COLS[i])
                if val is not None: 
                    pax_val = val
            else: 
                break
    else:
        for i in range(N_EST - 1, -1, -1):
            if km_pos <= KM_ACUM[i]:
                val = pax_d.get(PAX_COLS[i])
                if val is not None: 
                    pax_val = val
            else: 
                break
    return int(pax_val)

def _build_profile(use_rm, via):
    segs = SPEED_PROFILE if via == 1 else list(reversed(SPEED_PROFILE))
    km_pts = []
    t_pts = []
    cum_t = 0.0
    
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
    if k[0] == 1: 
        _PROF_SORTED[k] = (v[0], v[1])
    else: 
        _PROF_SORTED[k] = (v[0][::-1].copy(), v[1][::-1].copy())

_VEL_ARRAY_NORM = np.zeros(45000, dtype=float)
_VEL_ARRAY_RM = np.zeros(45000, dtype=float)

for ki, kf, _, vn, vr in SPEED_PROFILE:
    start_idx = int(ki)
    end_idx = min(int(kf) + 1, 45000)
    _VEL_ARRAY_NORM[start_idx:end_idx] = vn
    _VEL_ARRAY_RM[start_idx:end_idx] = vr

def vel_at_km(km_km, via, use_rm):
    idx = int(km_km * 1000.0)
    if 0 <= idx < 45000:
        return _VEL_ARRAY_RM[idx] if use_rm else _VEL_ARRAY_NORM[idx]
    return 0.0

def km_at_t(t_ini, t_fin, t, via, use_rm=False, km_orig=None, km_dest=None, nodos=None, t_arr=None):
    if nodos is not None and len(nodos) >= 2:
        if t <= nodos[0][0]: return nodos[0][1]
        if t >= nodos[-1][0]: return nodos[-1][1]
        
        if t_arr is None: 
            t_arr = [n[0] for n in nodos]
            
        idx = np.searchsorted(t_arr, t)
        t_A, k_A = nodos[idx-1]
        t_B, k_B = nodos[idx]
        
        if t_A == t_B or k_A == k_B: 
            return k_A 
            
        frac = (t - t_A) / (t_B - t_A)
        km_sorted, t_sorted = _PROF_SORTED[(via, use_rm)]
        t_prof_A = float(np.interp(k_A * 1000.0, km_sorted, t_sorted))
        t_prof_B = float(np.interp(k_B * 1000.0, km_sorted, t_sorted))
        t_prof_target = t_prof_A + frac * (t_prof_B - t_prof_A)
        
        km_arr, t_prof_arr = _PROF[(via, use_rm)]
        km_m = float(np.interp(t_prof_target, t_prof_arr, km_arr))
        return max(0.0, min(km_m / 1000.0, KM_TOTAL))
        
    dur = t_fin - t_ini
    if dur <= 0: 
        return km_orig if km_orig is not None else (0.0 if via==1 else KM_TOTAL)
        
    frac = max(0.0, min(1.0, (t - t_ini) / dur))
    
    if km_orig is None: 
        km_orig = 0.0 if via == 1 else KM_TOTAL
    if km_dest is None: 
        km_dest = KM_TOTAL if via == 1 else 0.0
    
    km_sorted, t_sorted = _PROF_SORTED[(via, use_rm)]
    t_at_orig = float(np.interp(km_orig * 1000.0, km_sorted, t_sorted))
    t_at_dest = float(np.interp(km_dest * 1000.0, km_sorted, t_sorted))
    t_prof = t_at_orig + frac * (t_at_dest - t_at_orig)
    
    km_arr, t_arr_prof = _PROF[(via, use_rm)]
    km_m = float(np.interp(t_prof, t_arr_prof, km_arr))
    return max(0.0, min(km_m / 1000.0, KM_TOTAL))

def get_train_state_and_speed(t, r_via, use_rm, km_orig, km_dest, nodos, t_arr=None):
    if not nodos or len(nodos) < 2: 
        return "CRUISE", 60.0
    if t_arr is None: 
        t_arr = [n[0] for n in nodos]
    if t <= t_arr[0] or t >= t_arr[-1]: 
        return "DWELL", 0.0
        
    idx = np.searchsorted(t_arr, t)
    t_A, t_B = t_arr[idx-1], t_arr[idx]
    dt_from_A, dt_to_B = t - t_A, t_B - t
    
    km_now = km_at_t(t_A, t_B, t, r_via, use_rm, km_orig, km_dest, nodos, t_arr)
    vel_max = vel_at_km(km_now, r_via, use_rm)
    
    if dt_from_A <= 1.0: 
        return "ACCEL", vel_max
    elif dt_to_B <= 1.0: 
        return "BRAKE", vel_max
    else: 
        return "CRUISE", vel_max

def calcular_aux_dinamico(aux_kw_nominal, hora_decimal, pax_abordo, cap_max, estacion_anio, estado_marcha="CRUISE"):
    hora_int = int(hora_decimal) % 24
    perfil = _AUX_HVAC_HORA.get(estacion_anio, _AUX_HVAC_HORA["primavera"])
    f_hvac = perfil[hora_int]
    
    if cap_max > 0:
        ocup = min(1.0, pax_abordo / cap_max)
        if estacion_anio == "verano": 
            f_ocup = 1.0 + 0.05 * ocup
        elif estacion_anio == "invierno": 
            f_ocup = 1.0 - 0.12 * ocup
        else: 
            f_ocup = 1.0 - 0.06 * ocup
    else:
        f_ocup = 1.0
        
    f_marcha = _FACTOR_DWELL_COMPRESOR if estado_marcha == "DWELL" else 1.0
    aux_base = aux_kw_nominal * _FRAC_BASE
    aux_hvac = aux_kw_nominal * _FRAC_HVAC * f_hvac * f_ocup * f_marcha
    return aux_base + aux_hvac

def simular_tramo_termodinamico(tipo_tren, doble, km_ini, km_fin, via_op, pct_trac, use_rm, use_pend, nodos=None, pax_dict=None, pax_abordo=0, v_consigna_override=None, maniobra=None, estacion_anio="primavera", t_ini_mins=0.0, es_vacio=False):
    f = FLOTA.get(tipo_tren, FLOTA["XT-100"])
    trc = 0.0
    aux = 0.0
    reg = 0.0
    t_horas = 0.0
    
    k_s, k_e = km_ini, km_fin
    dst = abs(k_e - k_s)
    if dst <= 0: 
        return 0.0, 0.0, 0.0, 0.0, 0.0, 0.0
    
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
        p_ini = paradas_km[i]
        p_fin = paradas_km[i+1]
        dist_total_tramo = abs(p_fin - p_ini) * 1000.0
        
        if dist_total_tramo <= 0: 
            continue
        
        pos_m = p_ini * 1000.0
        dist_recorrida = 0.0
        v_ms = 0.0
        estado_marcha = "ACCEL"
        
        while dist_recorrida < dist_total_tramo:
            dist_restante = dist_total_tramo - dist_recorrida
            if dist_restante < 0.1: 
                break
            
            km_actual = (pos_m + dist_recorrida) / 1000.0 if via_op == 1 else (pos_m - dist_recorrida) / 1000.0
            
            es_doble = doble
            if maniobra in ['CORTE_BTO', 'CORTE_PU_SA_BTO'] and km_actual > 25.3: 
                es_doble = False
            elif maniobra == 'CORTE_SA' and km_actual > 29.1: 
                es_doble = False
            elif maniobra == 'ACOPLE_BTO' and km_actual < 25.3: 
                es_doble = False
            elif maniobra == 'ACOPLE_SA' and km_actual < 29.1: 
                es_doble = False
            
            n_uni = 2 if es_doble else 1
            pax_mid = get_pax_at_km(pax_dict, km_actual, via_op, pax_abordo) if pax_dict else pax_abordo
            masa_kg = ((f['tara_t'] + f['m_iner_t']) * 1000 * n_uni) + (pax_mid * PAX_KG)
            
            v_cons_kmh = max(5.0, vel_at_km(km_actual, via_op, use_rm))
            if v_consigna_override is not None: 
                v_cons_kmh = min(v_cons_kmh, v_consigna_override)
            
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
            if n_uni == 2: 
                f_davis = (f['davis_A'] * 2) + (f['davis_B'] * 2 * v_kmh) + (f['davis_C'] * 1.35 * (v_kmh**2))
            else: 
                f_davis = f['davis_A'] + f['davis_B']*v_kmh + f['davis_C']*(v_kmh**2)
                
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
            
            if dist_restante <= d_freno_req + (v_ms * dt * 1.2): 
                estado_marcha = "BRAKE_STATION"
            elif v_kmh > v_cons_kmh + 1.5: 
                estado_marcha = "BRAKE_OVERSPEED"
            else:
                if estado_marcha == "BRAKE_OVERSPEED" and v_kmh <= v_cons_kmh: 
                    estado_marcha = "COAST"
                elif estado_marcha == "ACCEL" and v_kmh >= v_cons_kmh - 0.5: 
                    estado_marcha = "COAST"
                elif estado_marcha == "COAST":
                    if v_kmh < v_cons_kmh - 2.0: 
                        estado_marcha = "ACCEL"
                elif estado_marcha not in ["ACCEL", "COAST", "BRAKE_STATION", "BRAKE_OVERSPEED"]: 
                    estado_marcha = "ACCEL"

            f_motor = 0.0
            f_regen_tramo = 0.0
            a_net = 0.0
            
            if estado_marcha == "BRAKE_STATION":
                f_req_freno = max(0.0, masa_kg * a_freno_op - f_davis - f_pend)
                f_regen_tramo = min(f_req_freno, f_disp_freno)
                a_net = (-f_regen_tramo - f_davis - f_pend) / masa_kg
                if a_net > -a_freno_op: 
                    a_net = -a_freno_op 
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
                
            if v_new < 0.5 and dist_restante < 2.0: 
                break
            if v_new < 0.1 and v_ms < 0.1:
                v_new = 1.0
                dt_actual = dt

            step_m = (v_ms + v_new) / 2.0 * dt_actual
            if step_m > dist_restante:
                step_m = dist_restante
                if v_ms + v_new > 0: 
                    dt_actual = step_m / ((v_ms + v_new) / 2.0)
            if step_m < 0.1: 
                step_m = 0.5 
                
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
    if t_horas <= 0: 
        return e_pantografo_kwh
    
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
    
    if e_pantografo_kwh >= 0: 
        return e_pantografo_kwh + (P_loss_kW * t_horas)
    else: 
        return -max(0.0, abs(e_pantografo_kwh) - (P_loss_kW * t_horas))

def distribuir_energia_sers(e_pantografo, t_horas, km_ini, km_fin, active_sers):
    if not active_sers: 
        return {}
    if len(active_sers) == 1:
        e_s = calcular_demanda_ser(e_pantografo, t_horas, (km_ini+km_fin)/2.0, active_sers[0][0])
        return {active_sers[0][1]: e_s}
        
    sers_sorted = sorted(active_sers, key=lambda x: x[0])
    boundaries = [0.0]
    for i in range(len(sers_sorted)-1): 
        boundaries.append((sers_sorted[i][0] + sers_sorted[i+1][0]) / 2.0)
    boundaries.append(KM_TOTAL)
    
    dist_total = abs(km_fin - km_ini)
    if dist_total < 0.001:
        closest = min(active_sers, key=lambda x: abs(km_ini - x[0]))
        e_s = calcular_demanda_ser(e_pantografo, t_horas, km_ini, closest[0])
        return {closest[1]: e_s}
        
    k_min = min(km_ini, km_fin)
    k_max = max(km_ini, km_fin)
    resultados = {s[1]: 0.0 for s in sers_sorted}
    
    for i, ser in enumerate(sers_sorted):
        b_min = boundaries[i]
        b_max = boundaries[i+1]
        o_min = max(k_min, b_min)
        o_max = min(k_max, b_max)
        
        if o_max > o_min:
            frac = (o_max - o_min) / dist_total
            centroid = (o_min + o_max) / 2.0
            resultados[ser[1]] += calcular_demanda_ser(
                e_pantografo * frac, 
                t_horas * frac if t_horas > 0 else 0.0, 
                centroid, 
                ser[0]
            )
            
    return resultados

def distribuir_potencia_sers_kw(p_kw, km_punto, active_sers):
    if not active_sers: 
        return {}
    if len(active_sers) == 1: 
        return {active_sers[0][1]: p_kw}
        
    sers_sorted = sorted(active_sers, key=lambda x: x[0])
    if km_punto <= sers_sorted[0][0]: 
        return {sers_sorted[0][1]: p_kw}
    if km_punto >= sers_sorted[-1][0]: 
        return {sers_sorted[-1][1]: p_kw}
        
    for i in range(len(sers_sorted)-1):
        s1 = sers_sorted[i]
        s2 = sers_sorted[i+1]
        if s1[0] <= km_punto <= s2[0]:
            dist_total = s2[0] - s1[0]
            d1 = km_punto - s1[0]
            d2 = s2[0] - km_punto
            return {
                s1[1]: p_kw * (d2 / dist_total), 
                s2[1]: p_kw * (d1 / dist_total)
            }
            
    return {active_sers[0][1]: p_kw}

def calcular_flujo_ac_nodo(demands_kw):
    i_po = max(0.0, demands_kw.get('SER PO', 0.0)) * 1000 / (1.732 * V_NOMINAL_AC * 0.95)
    i_es = max(0.0, demands_kw.get('SER ES', 0.0)) * 1000 / (1.732 * V_NOMINAL_AC * 0.95)
    i_eb = max(0.0, demands_kw.get('SER EB', 0.0)) * 1000 / (1.732 * V_NOMINAL_AC * 0.95)
    i_va = max(0.0, demands_kw.get('SER VA', 0.0)) * 1000 / (1.732 * V_NOMINAL_AC * 0.95)
    
    len_seat_es = abs(24.3 - 12.7)
    len_es_po = abs(12.7 - 4.9)
    dv_seat_es = 1.732 * (i_po + i_es) * Z_EFF_44KV * len_seat_es
    dv_es_po = 1.732 * (i_po) * Z_EFF_44KV * len_es_po
    loss_seat_es = 3 * ((i_po + i_es)**2) * R_AC_44KV * len_seat_es / 1000.0
    loss_es_po = 3 * (i_po**2) * R_AC_44KV * len_es_po / 1000.0
    v_ac_es = V_NOMINAL_AC - dv_seat_es
    v_ac_po = V_NOMINAL_AC - dv_seat_es - dv_es_po
    
    len_seat_eb = abs(25.5 - 24.3)
    len_eb_va = abs(28.7 - 25.5)
    dv_seat_eb = 1.732 * (i_eb + i_va) * Z_EFF_44KV * len_seat_eb
    dv_eb_va = 1.732 * (i_va) * Z_EFF_44KV * len_eb_va
    loss_seat_eb = 3 * ((i_eb + i_va)**2) * R_AC_44KV * len_seat_eb / 1000.0
    loss_eb_va = 3 * (i_va**2) * R_AC_44KV * len_eb_va / 1000.0
    v_ac_eb = V_NOMINAL_AC - dv_seat_eb
    v_ac_va = V_NOMINAL_AC - dv_seat_eb - dv_eb_va
    
    return {
        'SER PO': {'Vac': v_ac_po, 'Vdc': 3000.0 * (v_ac_po / V_NOMINAL_AC)},
        'SER ES': {'Vac': v_ac_es, 'Vdc': 3000.0 * (v_ac_es / V_NOMINAL_AC)},
        'SER EB': {'Vac': v_ac_eb, 'Vdc': 3000.0 * (v_ac_eb / V_NOMINAL_AC)},
        'SER VA': {'Vac': v_ac_va, 'Vdc': 3000.0 * (v_ac_va / V_NOMINAL_AC)},
        'P_loss_kw': loss_seat_es + loss_es_po + loss_seat_eb + loss_eb_va
    }

def calcular_receptividad_por_headway(df_dia: pd.DataFrame) -> dict:
    if df_dia.empty: 
        return {}
    result = {}
    for via in [1, 2]:
        sub = df_dia[df_dia["Via"] == via].sort_values("t_ini")
        if sub.empty: 
            continue
            
        indices = list(sub.index)
        t_ini_vals = sub["t_ini"].values
        
        for i, idx in enumerate(indices):
            headways = []
            if i > 0: 
                headways.append(t_ini_vals[i] - t_ini_vals[i-1])
            if i < len(indices)-1: 
                headways.append(t_ini_vals[i+1] - t_ini_vals[i])
                
            if not headways: 
                result[idx] = 0.10
                continue
                
            hw = min(headways)
            if hw < 5.0: 
                eta = 0.90
            elif hw < 10.0: 
                eta = 0.75 - ((hw - 5.0) / 5.0) * 0.45
            else: 
                eta = max(0.10, 0.30 - ((hw - 10.0) / 20.0) * 0.20)
                
            result[idx] = min(eta, 0.90)
    return result

@st.cache_data(show_spinner="Simulando malla eléctrica y receptividad...")
def precalcular_red_electrica_v111(df_dia, pct_trac, use_rm, estacion_anio="primavera"):
    regen_util_per_trip = {idx: 0.0 for idx in df_dia.index}
    braking_ticks_per_trip = {idx: 0.0 for idx in df_dia.index} 
    if df_dia.empty: 
        return regen_util_per_trip
    
    t_min = int(df_dia['t_ini'].min())
    t_max = int(df_dia['t_fin'].max())
    dt_step = 10.0 / 60.0 
    time_steps = np.arange(t_min, t_max + 1, dt_step)
    
    for via_ in [1, 2]:
        via_trains = df_dia[df_dia['Via'] == via_]
        if via_trains.empty: continue
        
        trains_data = []
        for idx, r in via_trains.iterrows():
            nodos = r.get('nodos')
            trains_data.append({
                'idx': idx, 
                't_ini': r['t_ini'], 
                't_fin': r['t_fin'], 
                'Via': r['Via'],
                'km_orig': r['km_orig'], 
                'km_dest': r['km_dest'], 
                'nodos': nodos,
                't_arr': [n[0] for n in nodos] if nodos and len(nodos) >= 2 else None,
                'tipo_tren': r.get('tipo_tren', 'XT-100'), 
                'doble': r.get('doble', False), 
                'pax_abordo': r.get('pax_abordo', 0)
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
                
                if n_uni == 2:
                    f_davis = (f['davis_A'] * 2) + (f['davis_B'] * 2 * v_kmh) + (f['davis_C'] * 1.35 * (v_kmh**2))
                else:
                    f_davis = f['davis_A'] + f['davis_B']*v_kmh + f['davis_C']*(v_kmh**2)
                
                if state in ("BRAKE", "BRAKE_STATION", "BRAKE_OVERSPEED"):
                    f_req_freno = max(0.0, masa_kg * (f['a_freno_ms2'] * 0.9) - f_davis)
                    f_disp_freno = min(f['f_freno_max_kn']*1000*n_uni, (f.get('p_freno_max_kw', f['p_max_kw']*1.2)*1000*n_uni)/max(0.1, v_ms)) if v_kmh >= f['v_freno_min'] else 0.0
                    p_gen_kw = ((min(f_req_freno, f_disp_freno) * v_ms) / 1000.0 * ETA_REGEN_NETA) - p_aux_kw
                    
                    if p_gen_kw > 0: 
                        braking_by_idx[i].append((tr['idx'], pos, p_gen_kw))
                    braking_ticks_per_trip[tr['idx']] += 1
                    
                elif state in ("ACCEL", "CRUISE"):
                    p_dem_kw = p_aux_kw
                    if state == "ACCEL": 
                        p_trac_disp = f['p_max_kw']*1000*n_uni*(pct_trac/100.0)
                        f_trac_disp = min(f['f_trac_max_kn']*1000*n_uni*(pct_trac/100.0), p_trac_disp/max(0.1, v_ms)) if v_ms > 0 else f['f_trac_max_kn']*1000*n_uni*(pct_trac/100.0)
                        p_dem_kw += ((f_trac_disp * v_ms) / 1000.0 / eta_m)
                    elif state == "CRUISE" and f_davis > 0: 
                        p_dem_kw += (((f_davis * v_ms) / 1000.0) / eta_m)
                        
                    accel_by_idx[i].append((tr['idx'], pos, p_dem_kw))
                    
        for i in range(len(time_steps)):
            if not braking_by_idx[i] or not accel_by_idx[i]: 
                continue
                
            current_demands = {a[0]: a[2] for a in accel_by_idx[i]}
            
            for b_idx, b_pos, p_gen in braking_by_idx[i]:
                available = [a for a in accel_by_idx[i] if current_demands[a[0]] > 0]
                if not available: 
                    break 
                    
                a_idx, a_pos, _ = min(available, key=lambda x: abs(x[1] - b_pos))
                dist = abs(a_pos - b_pos)
                
                if dist <= LAMBDA_REGEN_KM * 2:
                    p_transferred = min(p_gen * (ETA_MAX * np.exp(-dist / LAMBDA_REGEN_KM)), current_demands[a_idx])
                    current_demands[a_idx] -= p_transferred
                    regen_util_per_trip[b_idx] += (p_transferred / p_gen)
                    
    for idx in df_dia.index: 
        if braking_ticks_per_trip[idx] > 0:
            regen_util_per_trip[idx] = min(1.0, regen_util_per_trip[idx] / braking_ticks_per_trip[idx])
        else:
            regen_util_per_trip[idx] = 0.0
            
    return regen_util_per_trip

@st.cache_data(show_spinner="Integrando Termodinámica de Flota...")
def calcular_termodinamica_flota_v111(df_dia, pct_trac, use_pend, use_rm, use_regen, dict_regen, estacion_anio="primavera"):
    df_e = df_dia.copy()
    if df_e.empty: 
        return df_e
        
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

# =============================================================================
# 9. MANIOBRAS EN VACÍO (CARRUSELES)
# =============================================================================
@st.cache_data(show_spinner="Calculando Carrusel de Cocheras...")
def get_vacios_dia(df_dia):
    vacios = []
    if df_dia.empty: 
        return vacios
        
    agrupador = 'motriz_num' if 'motriz_num' in df_dia.columns else 'num_servicio'
    
    def _get_est_name(km):
        if pd.isna(km): return "Desconocido"
        dists = [abs(km - k) for k in KM_ACUM]
        idx = int(np.argmin(dists))
        if dists[idx] <= 1.5:
            return ESTACIONES[idx]
        return f"km {km:.1f}"
        
    for tren, group in df_dia.sort_values('t_ini').groupby(agrupador):
        if str(tren).strip() == '' or str(tren).strip() == 'nan': 
            continue
            
        viajes = group.to_dict('records')
        if not viajes: 
            continue
        
        p = viajes[0]
        if abs(p.get('km_orig', 0) - KM_ACUM[14]) < 0.1:
            vacios.append({
                't_asigned': p['t_ini'] - 10, 'tipo': p.get('tipo_tren', 'XT-100'), 
                'doble': p.get('doble', False), 'cochera': True, 'km_orig': KM_ACUM[14], 
                'km_dest': KM_ACUM[14], 'dist': 2.0, 'motriz_num': tren, 
                'origen_txt': 'Taller / Cochera', 'destino_txt': 'El Belloto', 
                'servicio_previo': '—', 'servicio_siguiente': str(p.get('num_servicio', ''))
            })
        elif abs(p.get('km_orig', 0) - KM_ACUM[18]) < 0.1:
            vacios.append({
                't_asigned': p['t_ini'] - 20, 'tipo': p.get('tipo_tren', 'XT-100'), 
                'doble': p.get('doble', False), 'cochera': True, 'km_orig': KM_ACUM[14], 
                'km_dest': KM_ACUM[18], 'dist': 2.0 + abs(KM_ACUM[18]-KM_ACUM[14]), 
                'motriz_num': tren, 'origen_txt': 'Taller / Cochera', 'destino_txt': 'Sargento Aldea', 
                'servicio_previo': '—', 'servicio_siguiente': str(p.get('num_servicio', ''))
            })
            
        for i in range(len(viajes) - 1):
            actual = viajes[i]
            sig = viajes[i+1]
            k_o = actual.get('km_dest', 0)
            k_d = sig.get('km_orig', 0)
            dist = abs(k_o - k_d)
            if 0.1 < dist <= 20.0:
                vacios.append({
                    't_asigned': actual['t_fin'] + 5, 'tipo': actual.get('tipo_tren', 'XT-100'), 
                    'doble': actual.get('doble', False), 'cochera': False, 'km_orig': k_o, 
                    'km_dest': k_d, 'dist': dist, 'motriz_num': tren, 
                    'origen_txt': _get_est_name(k_o), 'destino_txt': _get_est_name(k_d), 
                    'servicio_previo': str(actual.get('num_servicio', '')), 
                    'servicio_siguiente': str(sig.get('num_servicio', ''))
                })
                
        u = viajes[-1]
        if abs(u.get('km_dest', 0) - KM_ACUM[14]) < 0.1:
            vacios.append({
                't_asigned': u['t_fin'] + 5, 'tipo': u.get('tipo_tren', 'XT-100'), 
                'doble': u.get('doble', False), 'cochera': True, 'km_orig': KM_ACUM[14], 
                'km_dest': KM_ACUM[14], 'dist': 2.0, 'motriz_num': tren, 
                'origen_txt': 'El Belloto', 'destino_txt': 'Taller / Cochera', 
                'servicio_previo': str(u.get('num_servicio', '')), 'servicio_siguiente': '—'
            })
        elif abs(u.get('km_dest', 0) - KM_ACUM[18]) < 0.1:
            vacios.append({
                't_asigned': u['t_fin'] + 5, 'tipo': u.get('tipo_tren', 'XT-100'), 
                'doble': u.get('doble', False), 'cochera': True, 'km_orig': KM_ACUM[18], 
                'km_dest': KM_ACUM[14], 'dist': 2.0 + abs(KM_ACUM[18]-KM_ACUM[14]), 
                'motriz_num': tren, 'origen_txt': 'Sargento Aldea', 'destino_txt': 'Taller / Cochera', 
                'servicio_previo': str(u.get('num_servicio', '')), 'servicio_siguiente': '—'
            })
            
    return vacios

# =============================================================================
# CACHÉ REACTIVO DEL PLANIFICADOR (V117 - Integración de Pax Avanzada)
# =============================================================================
@st.cache_data(show_spinner="Integrando física y demanda de pasajeros...")
def procesar_planificador_reactivo(df_sint, df_px_filtered, estacion_anio_plan, pct_trac, use_rm, use_pend, use_regen, tipo_regen):
    viajes_completos = []
    
    for idx, r in df_sint.iterrows():
        via_tren = r['Via']
        t_ini_tren = r['t_ini']
        num_serv = str(r.get('num_servicio', ''))
        
        pax_arr_viaje = {c: 0 for c in PAX_COLS}
        pax_calculado = 0
        
        if not df_px_filtered.empty:
            sub = df_px_filtered[df_px_filtered['Via'] == via_tren].copy()
            if not sub.empty:
                exact = pd.DataFrame()
                if num_serv and 'Nro_THDR' in sub.columns:
                    sub['Nro_THDR_cmp'] = sub['Nro_THDR'].apply(clean_primary_key)
                    exact = sub[(sub['Nro_THDR_cmp'] == num_serv) & (sub['Nro_THDR_cmp'] != '')]
                
                if not exact.empty:
                    for c in PAX_COLS: 
                        pax_arr_viaje[c] = int(round(exact[c].mean()))
                    pax_calculado = int(round(exact['CargaMax'].mean()))
                else:
                    sub['diff'] = sub['t_ini_p'].apply(lambda x: min(abs(float(x) - float(t_ini_tren)), 1440 - abs(float(x) - float(t_ini_tren))) if pd.notna(x) else 9999)
                    cercanos = sub[sub['diff'] <= 30]
                    if cercanos.empty: 
                        cercanos = sub.loc[[sub['diff'].idxmin()]]
                        
                    for c in PAX_COLS: 
                        pax_arr_viaje[c] = int(round(cercanos[c].mean()))
                    pax_calculado = int(round(cercanos['CargaMax'].mean()))
        else:
            pax_calculado = 150 
        
        cap_m = FLOTA[r['tipo_tren']].get('cap_max', 398) * (2 if r['doble'] else 1)
        pax_calculado = min(pax_calculado, cap_m)
        pax_arr_viaje = {k: min(v, cap_m) for k, v in pax_arr_viaje.items()}
        
        trc_v, aux_v, reg_v, _, _, t_h = simular_tramo_termodinamico(
            r['tipo_tren'], r['doble'], r['km_orig'], r['km_dest'], r['Via'], 
            pct_trac, use_rm, use_pend, r['nodos'], pax_arr_viaje, pax_calculado, 
            None, None, estacion_anio_plan, r['t_ini']
        )
        
        viaje_final = r.to_dict()
        viaje_final['pax_d'] = pax_arr_viaje
        viaje_final['pax_abordo'] = pax_calculado
        viaje_final['t_fin'] = r['t_ini'] + (t_h * 60.0)
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