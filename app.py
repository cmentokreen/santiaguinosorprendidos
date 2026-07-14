import streamlit as st
import pandas as pd
import requests
import folium
from streamlit_folium import st_folium
import plotly.express as px
from datetime import datetime

# ==========================================
# 1. CONFIGURACIÓN DE LA PÁGINA Y ESTILOS CSS
# ==========================================
st.set_page_config(
    page_title="Monitoreo de Frentes de Lluvia - Chile",
    page_icon="🌧️",
    layout="wide"
)

# Estilos CSS avanzados para una interfaz premium y moderna
st.markdown("""
    <style>
    /* Fondo general y fuentes */
    .main {
        background-color: #0f172a; /* Slate 900 (Fondo oscuro profesional) */
        color: #f8fafc;
    }
    
    /* Encabezados */
    h1, h2, h3 {
        color: #f1f5f9 !important;
        font-family: 'Segoe UI', system-ui, sans-serif;
        font-weight: 700;
    }
    
    /* Contenedores de tarjetas */
    .metric-card {
        background-color: #1e293b;
        border-radius: 12px;
        padding: 20px;
        border: 1px solid #334155;
        box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1);
        margin-bottom: 20px;
    }
    
    /* Modificar elementos de Streamlit */
    .stSlider > div [data-baseweb="slider"] {
        background: linear-gradient(90deg, #38bdf8, #818cf8);
        height: 8px;
        border-radius: 4px;
    }
    
    /* Pie de página elegante */
    .custom-footer {
        text-align: center;
        padding: 30px 10px;
        margin-top: 50px;
        border-top: 1px solid #334155;
        color: #94a3b8;
        font-size: 14px;
        letter-spacing: 0.5px;
    }
    .custom-footer strong {
        color: #38bdf8;
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
    "Monday": "Lun", "Tuesday": "Mar", "Wednesday": "Mié", 
    "Thursday": "Jue", "Friday": "Vie", "Saturday": "Sáb", "Sunday": "Dom"
}

def format_date_es(dt):
    dt_p = pd.to_datetime(dt)
    dia_eng = dt_p.strftime("%A")
    dia_trad = dias_es.get(dia_eng, dia_eng)
    return f"{dia_trad} {dt_p.strftime('%d/%m - %H:00')}"

# Generar lista de marcas de tiempo ordenadas
horas_disponibles = sorted(df["Fecha_Hora"].unique())

# ==========================================
# 5. CONTROLADOR DE LÍNEA DE TIEMPO (ST.SELECT_SLIDER)
# ==========================================
st.title("🌧️ Panel de Evolución Atmosférica y Frente de Lluvia")
st.write("Visualización interactiva de la propagación de frentes nubosos y precipitaciones estimadas para la próxima semana en Chile.")

st.markdown("<div class='metric-card'>", unsafe_allow_html=True)
st.subheader("🕐 Control Maestro del Frente (Línea de Tiempo)")
st.write("Arrastra el deslizador para ver cómo avanza el frente hora a hora por el territorio nacional:")

# Deslizador semántico usando st.select_slider
selected_time = st.select_slider(
    label="Selecciona fecha y hora de simulación",
    options=horas_disponibles,
    value=horas_disponibles[0],
    format_func=format_date_es,
    label_visibility="collapsed"
)

# Mostrar fecha destacada
st.markdown(f"### 📍 Simulación activa para el: <span style='color:#38bdf8;'>{format_date_es(selected_time)}</span>", unsafe_allow_html=True)
st.markdown("</div>", unsafe_allow_html=True)

# Filtrar datos de la hora seleccionada para el mapa
df_actual = df[df["Fecha_Hora"] == selected_time]

# ==========================================
# 6. GRÁFICO 1: MAPA ESPACIAL COMPLETO (ANCHO TOTAL)
# ==========================================
st.subheader("🗺️ 1. Posición Espacial del Frente de Mal Tiempo")
st.write("El tamaño y brillo de las burbujas indican la intensidad de la lluvia (mm/h) en tiempo real sobre la geografía de Chile.")

# Paleta de colores para las burbujas del mapa
def get_hex_color(val):
    if val == 0:
         return "#334155" # Gris oscuro (Sin precipitación)
    elif val <= 1.0:
         return "#06b6d4" # Turquesa claro (Lluvia débil)
    elif val <= 5.0:
         return "#3b82f6" # Azul medio
    elif val <= 15.0:
         return "#6366f1" # Indigo intenso (Lluvia fuerte)
    else:
         return "#a855f7" # Morado neón (Frente severo / Temporal)

# Generar mapa interactivo
m = folium.Map(
    location=[-38.5, -72.0], 
    zoom_start=5, 
    tiles="CartoDB dark_matter", # Estilo oscuro para resaltar la paleta de colores
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
        fill_opacity=0.85,
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
    color_continuous_scale=["#334155", "#06b6d4", "#3b82f6", "#6366f1", "#a855f7"],
    labels={
        "Fecha_Hora": "Día y Hora del Pronóstico", 
        "Precipitacion": "Precipitación (mm/h)", 
        "Ciudad": "Ciudad (Ordenada de Sur a Norte)"
    },
    height=550
)

# Línea vertical indicadora del tiempo actual
selected_time_ms = pd.to_datetime(selected_time).timestamp() * 1000
fig_burbujas.add_vline(
    x=selected_time_ms, 
    line_width=3, 
    line_dash="dash", 
    line_color="#f43f5e" # Rojo neón para máxima visibilidad
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
    color_continuous_scale=["#06b6d4", "#3b82f6", "#a855f7"],
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
