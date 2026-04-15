import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import numpy as np
import warnings
warnings.filterwarnings('ignore')

# Cargar los datos
file_name = 'Datos Operacionales 2.xlsx - Datos.csv'
df = pd.read_csv(file_name)

# Limpieza de datos
df['Fecha'] = pd.to_datetime(df['Fecha'], errors='coerce')

# Asegurar que las columnas clave sean numéricas robustamente
numeric_cols = ['Energía Total [kWh]', 'Energía Tracción [kWh]', 'PAX', 'kWh/Km', 'Tren Km Comercial Real']
for col in numeric_cols:
    if col in df.columns:
        # Reemplazar espacios vacíos y comas si existen
        if df[col].dtype == 'O':
            df[col] = df[col].astype(str).str.replace(',', '.').str.strip()
            # Reemplazar cadenas vacías por NaN
            df[col] = df[col].replace('', np.nan)
        df[col] = pd.to_numeric(df[col], errors='coerce')

# Filtrar datos sin fecha
df = df.dropna(subset=['Fecha'])

# Crear un campo de Año-Mes para agrupaciones
df['YearMonth'] = df['Fecha'].dt.to_period('M')

# Agregaciones Mensuales
monthly_stats = df.groupby('YearMonth').agg({
    'Energía Total [kWh]': 'sum',
    'PAX': 'sum',
    'Tren Km Comercial Real': 'sum',
}).reset_index()

# Filtrar posibles meses anómalos (con 0 km o 0 energía)
monthly_stats = monthly_stats[monthly_stats['Tren Km Comercial Real'] > 0]
monthly_stats['YearMonth_str'] = monthly_stats['YearMonth'].astype(str)

# Calcular eficiencia mensual real ponderada
monthly_stats['kWh/Km_Mensual'] = monthly_stats['Energía Total [kWh]'] / monthly_stats['Tren Km Comercial Real']

# Configurar el estilo del Dashboard
sns.set_theme(style="whitegrid", rc={"axes.titlesize":14, "axes.labelsize":12})
fig, axes = plt.subplots(3, 2, figsize=(20, 18))
fig.suptitle('Dashboard de Business Intelligence - Operaciones MERVAL', fontsize=26, fontweight='bold', y=0.97)

# 1. Consumo de Energía Total por Mes
sns.lineplot(data=monthly_stats, x='YearMonth_str', y='Energía Total [kWh]', ax=axes[0, 0], marker='o', color='crimson', linewidth=2.5)
axes[0, 0].set_title('Consumo de Energía Total Mensual (kWh)')
axes[0, 0].tick_params(axis='x', rotation=45)
axes[0, 0].set_ylabel('Energía Total [kWh]')
axes[0, 0].set_xlabel('')

# 2. Total PAX por mes
sns.lineplot(data=monthly_stats, x='YearMonth_str', y='PAX', ax=axes[0, 1], marker='s', color='dodgerblue', linewidth=2.5)
axes[0, 1].set_title('Flujo Mensual de Pasajeros (PAX)')
axes[0, 1].tick_params(axis='x', rotation=45)
axes[0, 1].set_ylabel('Nº de Pasajeros')
axes[0, 1].set_xlabel('')

# 3. Eficiencia kWh/Km por mes
sns.lineplot(data=monthly_stats, x='YearMonth_str', y='kWh/Km_Mensual', ax=axes[1, 0], marker='^', color='forestgreen', linewidth=2.5)
axes[1, 0].set_title('Indicador de Eficiencia Mensual (kWh/Km)')
axes[1, 0].tick_params(axis='x', rotation=45)
axes[1, 0].set_ylabel('Eficiencia (kWh/Km)')
axes[1, 0].set_xlabel('')

# 4. Total km recorridos por mes
sns.lineplot(data=monthly_stats, x='YearMonth_str', y='Tren Km Comercial Real', ax=axes[1, 1], marker='v', color='darkorange', linewidth=2.5)
axes[1, 1].set_title('Producción Comercial Mensual (Tren-Km)')
axes[1, 1].tick_params(axis='x', rotation=45)
axes[1, 1].set_ylabel('Kilómetros Comerciales')
axes[1, 1].set_xlabel('')

# 5. Promedio Diario de PAX por Tipo de Jornada
if 'Tipo de Jornada' in df.columns:
    # Limpieza básica de 'Tipo de Jornada'
    df['Tipo de Jornada'] = df['Tipo de Jornada'].astype(str).str.strip().str.upper()
    valid_days = ['L', 'S', 'D/F']
    day_df = df[df['Tipo de Jornada'].isin(valid_days)]
    
    day_stats = day_df.groupby('Tipo de Jornada')['PAX'].mean().sort_values(ascending=False).reset_index()
    sns.barplot(data=day_stats, x='Tipo de Jornada', y='PAX', ax=axes[2, 0], palette='viridis')
    axes[2, 0].set_title('Demanda Promedio Diaria por Tipo de Jornada (L, S, D/F)')
    axes[2, 0].set_ylabel('Promedio de Pasajeros')
    axes[2, 0].set_xlabel('Tipo de Jornada')

# 6. Scatter: Correlación entre PAX y Energía Diaria
sns.scatterplot(data=day_df, x='PAX', y='Energía Total [kWh]', hue='Tipo de Jornada', ax=axes[2, 1], palette='deep', alpha=0.6, s=60)
axes[2, 1].set_title('Correlación Diaria: Pasajeros vs Consumo de Energía')
axes[2, 1].set_ylabel('Energía Total Diaria [kWh]')
axes[2, 1].set_xlabel('Total Pasajeros Diarios (PAX)')

# Ajustar las etiquetas del eje X
for i in range(2):
    for j in range(2):
        for ind, label in enumerate(axes[i, j].get_xticklabels()):
            if ind % 3 != 0:
                label.set_visible(False)

plt.tight_layout(rect=[0, 0.03, 1, 0.94])
plt.savefig('dashboard_bi.png')

# DataMart para Power BI
bi_export = day_df[['Fecha', 'Tipo de Jornada', 'Tren Km Comercial Real', 'Energía Total [kWh]', 'Energía Tracción [kWh]', 'PAX', 'kWh/Km']].copy()
bi_export.to_csv('DataMart_Operacional_Procesado.csv', index=False)
