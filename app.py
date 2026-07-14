import streamlit as st
import pandas as pd
import requests
import folium
from streamlit_folium import st_folium
import plotly.express as px
from datetime import datetime

# ==========================================
# 1. CONFIGURACIÓN DE LA PÁGINA
# ==========================================
st.set_page_config(
    page_title="Monitoreo de Frentes de Lluvia - Chile",
    page_icon="🌧️",
    layout="wide"
)

# Estilos CSS limpios para la firma y diseño ordenado
st.markdown("""
    <style>
    /* Pie de página elegante y legible */
    .custom-footer {
        text-align: center;
        padding: 30px 10px;
        margin-top: 50px;
        border-top: 1px solid #ddd;
        color: #64748b;
        font-size: 14px;
        letter-spacing: 0.5px;
    }
    .custom-footer strong {
        color: #1e293b;
    }
    </style>
""", unsafe_allow_html=True)

# ==========================================
# 2. DEFINICIÓN DE CIUDADES (Sur a Norte)
# ==========================================
CITIES = {
    "Punta Arenas": {"lat": -53.155, "lon": -70.909},
    "Coyhaique": {"lat": -45.575, "lon": -72.066},
    "Castro": {"lat": -42.472, "lon": -73.764},
    "Puerto Montt": {"lat": -41.469, "lon": -72.942},
    "Osorno": {"lat": -40.574, "lon": -73.125},
    "Valdivia": {"lat": -39.814, "lon": -73.246},
    "Temuco": {"lat": -38.736, "lon": -72.590},
    "Concepción": {"lat": -36.827, "lon": -73.050},
    "Chillán": {"lat": -36.607, "lon": -72.103},
    "Talca": {"lat": -35.426, "lon": -71.656},
    "Rancagua": {"lat": -34.165, "lon": -70.740},
    "Santiago": {"lat": -33.449, "lon": -70.662},
    "Valparaíso": {"lat": -33.047, "lon": -71.613},
    "La Serena": {"lat": -29.902, "lon": -71.252}
}

# ==========================================
# 3. OBTENCIÓN DE DATOS (CON CACHÉ)
# ==========================================
@st.cache_data(ttl=3600)
def fetch_precipitation_forecast():
    lats = [str(info["lat"]) for info in CITIES.values()]
    lons = [str(info["lon"]) for info in CITIES.values()]
    
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": ",".join(lats),
        "longitude": ",".join(lons),
        "hourly": "precipitation",
        "timezone": "America/Santiago",
        "forecast_days": 7
    }
    
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        
        if not isinstance(data, list):
            data = [data]
            
        records = []
        for city_name, city_data in zip(CITIES.keys(), data):
            hourly = city_data.get("hourly", {})
            times = hourly.get("time", [])
            precip = hourly.get("precipitation", [])
            
            for t, p in zip(times, precip):
                records.append({
                    "Ciudad": city_name,
                    "Latitud": CITIES[city_name]["lat"],
                    "Longitud": CITIES[city_name]["lon"],
                    "Fecha_Hora": pd.to_datetime(t),
                    "Precipitacion": p
                })
        return pd.DataFrame(records)
    except Exception as e:
        st.error(f"Error al conectar con el servidor meteorológico: {e}")
        return pd.DataFrame()

# Descarga de datos climáticos
df = fetch_precipitation_forecast()

if df.empty:
    st.warning("No se pudieron cargar los datos de pronóstico en este momento.")
    st.stop()

# ==========================================
# 4. TRADUCCIÓN Y FORMATEO DE FECHAS
# ==========================================
dias_es = {
    "Monday": "Lunes", "Tuesday": "Martes", "Wednesday": "Miércoles", 
    "Thursday": "Jueves", "Friday": "Viernes", "Saturday": "Sábado", "Sunday": "Domingo"
}

def format_only_date(d):
    dia_eng = d.strftime("%A")
    dia_trad = dias_es.get(dia_eng, dia_eng)
    return f"📅 {dia_trad} {d.strftime('%d/%m')}"

# Obtener lista única de fechas disponibles
horas_disponibles = sorted(df["Fecha_Hora"].unique())
ts_series = pd.Series(horas_disponibles)
unique_dates = sorted(ts_series.dt.date.unique())

# ==========================================
# 5. CONTROLADOR DE LÍNEA DE TIEMPO RE-DISEÑADO
# ==========================================
st.title("🌧️ Panel de Evolución Atmosférica y Frente de Lluvia")
st.write("Visualización interactiva de la propagación de frentes nubosos y precipitaciones estimadas para la próxima semana en Chile.")

# Contenedor nativo de Streamlit con borde gris elegante (Evita errores de renderizado)
with st.container(border=True):
    st.subheader("🕐 Control Maestro del Frente (Línea de Tiempo)")
    st.write("Utiliza los controles deslizantes grises para viajar en el tiempo de forma intuitiva:")
    
    # 1. Slider para seleccionar el Día
    selected_date = st.select_slider(
        "Paso 1: Selecciona el Día",
        options=unique_dates,
        format_func=format_only_date
    )
    
    # Filtrar horas correspondientes al día seleccionado
    times_for_selected_date = ts_series[ts_series.dt.date == selected_date]
    hours_for_selected_date = times_for_selected_date.dt.hour.tolist()
    
    # 2. Slider para seleccionar la Hora del día
    selected_hour = st.slider(
        "Paso 2: Selecciona la Hora del día (Formato 24h)",
        min_value=min(hours_for_selected_date),
        max_value=max(hours_for_selected_date),
        value=12 if 12 in hours_for_selected_date else min(hours_for_selected_date),
        format="%02d:00"
    )
    
    # Obtener el Timestamp exacto de la selección
    selected_time = times_for_selected_date[times_for_selected_date.dt.hour == selected_hour].iloc[0]
    
    # Mostrar la selección activa de forma limpia y destacada
    dia_semana_nombre = dias_es.get(selected_time.strftime("%A"), selected_time.strftime("%A"))
    st.info(f"📍 **Simulación activa para el:** {dia_semana_nombre} {selected_time.strftime('%d/%m a las %H:00 hrs')}")

# Filtrar datos de la hora seleccionada para el mapa
df_actual = df[df["Fecha_Hora"] == selected_time]

# ==========================================
# 6. GRÁFICO 1: MAPA ESPACIAL COMPLETO
# ==========================================
st.markdown("---")
st.subheader("🗺️ 1. Posición Espacial del Frente de Mal Tiempo")
st.write("El tamaño y color de las burbujas indican la intensidad de la lluvia (mm/h) estimada sobre la geografía de Chile.")

# Paleta de colores para las burbujas del mapa (Gris a Azul y Violeta)
def get_hex_color(val):
    if val == 0:
         return "#94a3b8" # Gris neutro (Sin lluvia)
    elif val <= 1.0:
         return "#38bdf8" # Celeste (Lluvia débil)
    elif val <= 5.0:
         return "#0284c7" # Azul medio
    elif val <= 15.0:
         return "#4f46e5" # Índigo (Lluvia fuerte)
    else:
         return "#7c3aed" # Violeta (Temporal / Lluvia severa)

# Generar mapa interactivo
m = folium.Map(
    location=[-38.5, -72.0], 
    zoom_start=5, 
    tiles="CartoDB dark_matter", # Mantiene el estilo tecnológico oscuro de fondo
    control_scale=True
)

for _, row in df_actual.iterrows():
    val = row["Precipitacion"]
    color = get_hex_color(val)
    radius = 6 + min(val * 3.5, 30) # Escala de tamaño dinámica
    
    popup_html = f"""
    <div style="font-family: Arial, sans-serif; color: #1e293b; padding: 5px;">
        <strong style="font-size: 14px;">{row['Ciudad']}</strong><br/>
        <span style="font-size: 12px;">Precipitación: <b>{val:.1f} mm/h</b></span>
    </div>
    """
    
    folium.CircleMarker(
        location=[row["Latitud"], row["Longitud"]],
        radius=radius,
        color=color,
        fill=True,
        fill_color=color,
        fill_opacity=0.8,
        weight=1.5,
        popup=folium.Popup(popup_html, max_width=250)
    ).add_to(m)

# Desplegar mapa a pantalla completa
st_folium(m, width="100%", height=550, returned_objects=[])

# ==========================================
# 7. GRÁFICO 2: EVOLUCIÓN LATITUDINAL (BURBUJAS)
# ==========================================
st.markdown("---")
st.subheader("📊 2. Evolución Temporal del Frente (Desplazamiento Sur a Norte)")
st.write("Este gráfico permite ver de forma continua cómo ascienden las lluvias desde el extremo sur (abajo) hacia la zona central y norte (arriba) a lo largo de los días.")

# Ordenar geográficamente las ciudades de Sur a Norte
df_sorted = df.sort_values(by="Latitud", ascending=True)

# Gráfico de burbujas interactivo
fig_burbujas = px.scatter(
    df_sorted,
    x="Fecha_Hora",
    y="Ciudad",
    size="Precipitacion",
    color="Precipitacion",
    color_continuous_scale=["#94a3b8", "#38bdf8", "#0284c7", "#4f46e5", "#7c3aed"],
    labels={
        "Fecha_Hora": "Día y Hora del Pronóstico", 
        "Precipitacion": "Precipitación (mm/h)", 
        "Ciudad": "Ciudad (Ordenada de Sur a Norte)"
    },
    height=550
)

# Línea vertical indicadora del tiempo actual (en gris/azul claro para mayor armonía)
selected_time_ms = pd.to_datetime(selected_time).timestamp() * 1000
fig_burbujas.add_vline(
    x=selected_time_ms, 
    line_width=3, 
    line_dash="dash", 
    line_color="#38bdf8"
)

fig_burbujas.update_layout(
    plot_bgcolor="rgba(15,23,42,1)",
    paper_bgcolor="rgba(0,0,0,0)",
    font=dict(color="#cbd5e1"),
    margin=dict(l=40, r=40, t=20, b=40),
    coloraxis_colorbar=dict(title="mm/h")
)

st.plotly_chart(fig_burbujas, use_container_width=True)

# ==========================================
# 8. GRÁFICO 3: ACUMULADO SEMANAL TOTAL
# ==========================================
st.markdown("---")
st.subheader("📈 3. Estimación de Agua Caída Acumulada para la Semana")
st.write("Suma total de milímetros de lluvia proyectados por ciudad para los próximos 7 días.")

df_acumulado = df.groupby("Ciudad").agg({
    "Precipitacion": "sum",
    "Latitud": "first"
}).reset_index().sort_values(by="Latitud", ascending=True)

fig_barras = px.bar(
    df_acumulado,
    x="Precipitacion",
    y="Ciudad",
    orientation='h',
    color="Precipitacion",
    color_continuous_scale=["#38bdf8", "#0284c7", "#7c3aed"],
    labels={"Precipitacion": "Agua acumulada (mm en 7 días)", "Ciudad": "Ciudad"},
    height=450
)

fig_barras.update_layout(
    plot_bgcolor="rgba(15,23,42,1)",
    paper_bgcolor="rgba(0,0,0,0)",
    font=dict(color="#cbd5e1"),
    margin=dict(l=40, r=40, t=20, b=40)
)

st.plotly_chart(fig_barras, use_container_width=True)

# ==========================================
# 9. PIE DE PÁGINA / CIERRE INSTITUCIONAL
# ==========================================
st.markdown(
    """
    <div class="custom-footer">
        Sitio desarrollado por <strong>Carlos Mendoza - CMENTO</strong> - para un grupo privado.<br>
        Todos los derechos reservados &copy; 2026. Datos de simulación provistos en tiempo real por Open-Meteo.
    </div>
    """, 
    unsafe_allow_html=True
)
