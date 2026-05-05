# config.py - Variables Globales e Infraestructura MERVAL
# Calibración XT-100 basada en Reporte ALSTOM TRA-305 (Plena Carga)

# =============================================================================
# 1. INFRAESTRUCTURA Y RED
# =============================================================================
ESTACIONES = [
    'Puerto','Bellavista','Francia','Baron','Portales','Recreo','Miramar',
    'Viña del Mar','Hospital','Chorrillos','El Salto','Valencia','Quilpue',
    'El Sol','El Belloto','Las Americas','La con-cepcion','Villa Alemana',
    'Sargento Aldea','Peñablanca','Limache'
]

EC = ['PU','BE','FR','BA','PO','RE','MI','VM','HO','CH',
      'ES','VAL','QU','SO','EB','AM','CO','VL','SA','PE','LI']

PAX_COLS = ['PUE','BEL','FRA','BAR','POR','REC','MIR','VIN','HOS','CHO',
            'SLT','VAL','QUI','SOL','BTO','AME','CON','VAM','SGA','PEN','LIM']

KM_TRAMO = [0.7, 0.7, 0.8, 1.7, 2.1, 1.4, 0.9, 0.9, 1.0, 1.5, 7.4, 2.3, 1.9, 2.0, 1.1, 1.2, 0.9, 0.6, 1.3, 12.73]
KM_ACUM  = [0.0]
for _k in KM_TRAMO: 
    KM_ACUM.append(round(KM_ACUM[-1] + _k, 2))
KM_TOTAL = KM_ACUM[-1]
N_EST    = len(ESTACIONES)

_ELEV_KM = [0.0, 0.7, 1.4, 2.2, 3.9, 6.0, 7.4, 8.3, 9.2, 10.2, 11.7, 19.1, 21.4, 23.3, 25.3, 26.4, 27.6, 28.5, 29.1, 30.4, 43.13]
_ELEV_M  = [12, 10, 10, 10, 18, 15, 12, 15, 35, 50, 55, 88, 122, 132, 142, 148, 155, 162, 175, 198, 216]
ELEV_KM, ELEV_M = _ELEV_KM, _ELEV_M

# =============================================================================
# 2. RED ELÉCTRICA (Catenaria y Subestaciones)
# =============================================================================
SER_DATA = [
    (KM_ACUM[4] + 1.0, "SER PO"),
    (KM_ACUM[10] + 1.0, "SER ES"),
    (KM_ACUM[14] + 0.2, "SER EB"),
    (KM_ACUM[17] + 0.2, "SER VA")
]
SEAT_KM = KM_ACUM[13] + 1.0
V_NOMINAL_DC = 3000.0
ETA_SER_RECTIFICADOR = 0.96 
ETA_REGEN_NETA = 0.85  # Calibrado por eficiencia IGBT
LAMBDA_REGEN_KM = 5.0     

# =============================================================================
# 3. MODELO TÉRMICO Y AUXILIARES
# =============================================================================
PAX_KG    = 75.0
DWELL_DEF = 8.0  
DAVIS_E_N_PERMIL = 9.81

# Factores de utilización horaria (Duty Cycle HVAC)
_AUX_HVAC_HORA = {
    "verano": [0.45,0.40,0.40,0.40,0.45,0.55, 0.65,0.75,0.85,0.90,0.95,0.98, 1.00,1.00,1.00,0.98,0.95,0.85, 0.75,0.65,0.55,0.50,0.48,0.45],
    "otoño": [0.30,0.28,0.25,0.25,0.28,0.35, 0.45,0.50,0.55,0.60,0.63,0.65, 0.66,0.66,0.65,0.63,0.60,0.55, 0.50,0.45,0.40,0.35,0.33,0.31],
    "invierno": [0.65,0.65,0.68,0.68,0.70,0.75, 0.82,0.85,0.88,0.85,0.80,0.75, 0.70,0.68,0.68,0.70,0.75,0.80, 0.82,0.78,0.75,0.72,0.70,0.68],
    "primavera": [0.35,0.32,0.30,0.30,0.32,0.40, 0.50,0.58,0.65,0.70,0.72,0.75, 0.78,0.80,0.78,0.74,0.70,0.60, 0.55,0.50,0.45,0.40,0.38,0.36],
}

# 💡 Proporciones según auditoría image_cb80de: Base+Ventilacion es ~40-45% de la carga total
_FRAC_BASE = 0.45
_FRAC_HVAC = 0.55

# =============================================================================
# 4. DICCIONARIO DE FLOTA (Fuente: ALSTOM TRA-305)
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
        "davis_A"      : 1615.0,
        "davis_B"      : 0.00,
        "davis_C"      : 0.5458,     
        "f_trac_max_kn": 110.0,
        "f_freno_max_kn": 105.0,
        "p_max_kw"     : 720.0,
        "p_freno_max_kw": 600.0,
        "aux_kw_cool"  : 58.76,         # ❄️ Plena Carga Verano (Calculado)
        "aux_kw_heat"  : 65.16,         # 🔥 Plena Carga Invierno (Calculado)
        "f_compresor_dwell": 1.03       # +3% Base (Puertas/Frenos)
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
        "aux_kw_cool"  : 68.0,         
        "aux_kw_heat"  : 78.0,         
        "f_compresor_dwell": 1.06       
    },
    "SFE": {
        "tara_t"       : 141.0,  
        "m_iner_t"     : 11.2,  
        "coches"       : 3,
        "cap_sent"     : 0,     # Valor de referencia opcional
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
        "aux_kw_cool"  : 180.0,        
        "aux_kw_heat"  : 210.0,        
        "f_compresor_dwell": 1.08       
    },
}

feriados_2026 = ['2026-01-01', '2026-05-01', '2026-09-18', '2026-12-25']

__all__ = ['ESTACIONES', 'EC', 'PAX_COLS', 'KM_ACUM', 'KM_TOTAL', 'FLOTA', 
           '_AUX_HVAC_HORA', '_FRAC_BASE', '_FRAC_HVAC', 'V_NOMINAL_DC', 
           'ETA_REGEN_NETA', 'LAMBDA_REGEN_KM', 'PAX_KG', 'DAVIS_E_N_PERMIL',
           'SER_DATA', 'SEAT_KM', 'feriados_2026']
