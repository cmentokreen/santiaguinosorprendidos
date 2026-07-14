import streamlit as st
import pandas as pd
import requests
import folium
from streamlit_folium import st_folium
import plotly.express as px

# 1. Configuración de la interfaz de la página
st.set_page_config(
    page_title="Pronóstico de Precipitación - Chile",
    page_icon="🌧️",
    layout="wide"
)

# Diseño estético personalizado
st.markdown("""
    <style>
    .main { background-color: #f8f9fa; }
    h1 { color: #1e3d59; font-family: 'Segoe UI', Arial, sans-serif; }
    h3 { color: #17b978; }
    </style>
""", unsafe_allow_html=True)

st.title("🌧️ Visualizador de Frentes y Pronóstico de Precipitación")
st.write("Esta aplicación muestra en tiempo real la evolución espacial y temporal de las lluvias en Chile para los próximos 7 días.")

# 2. Definir las ciudades (Perfil latitudinal de Chile, de Norte a Sur)
CITIES = {
    "La Serena": {"lat": -29.902, "lon": -71.252},
    "Valparaíso": {"lat": -33.047, "lon": -71.613},
    "Santiago": {"lat": -33.449, "lon": -70.662},
    "Rancagua": {"lat": -34.165, "lon": -70.740},
    "Talca": {"lat": -35.426, "lon": -71.656},
    "Chillán": {"lat": -36.607, "lon": -72.103},
    "Concepción": {"lat": -36.827, "lon": -73.050},
    "Temuco": {"lat": -38.736, "lon": -72.590},
    "Valdivia": {"lat": -39.814, "lon": -73.246},
    "Osorno": {"lat": -40.574, "lon": -73.125},
    "Puerto Montt": {"lat": -41.469, "lon": -72.942},
    "Castro": {"lat": -42.472, "lon": -73.764},
    "Coyhaique": {"lat": -45.575, "lon": -72.066},
    "Punta Arenas": {"lat": -53.155, "lon": -70.909}
}

# 3. Función para descargar datos desde Open-Meteo API (con Caché para velocidad)
@st.cache_data(ttl=3600)  # Guarda la información en caché por 1 hora para no saturar la API
def fetch_forecast_data():
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
        
        # Open-Meteo devuelve una lista si hay múltiples coordenadas
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
        st.error(f"Error al conectar con la API de clima: {e}")
        return pd.DataFrame()

# Descarga de datos
df = fetch_forecast_data()

if df.empty:
    st.stop()

# Helper para formatear fechas a español
dias_es = {
    "Monday": "Lunes", "Tuesday": "Martes", "Wednesday": "Miércoles", 
    "Thursday": "Jueves", "Friday": "Viernes", "Saturday": "Sábado", "Sunday": "Domingo"
}

def format_es(dt):
    dia_eng = dt.strftime("%A")
    dia_traducido = dias_es.get(dia_eng, dia_eng)
    return f"{dia_traducido} {dt.strftime('%d/%m - %H:00')}"

# Lista ordenada de horas para el slider
horas_unicas = sorted(df["Fecha_Hora"].unique())

# 4. Barra lateral interactiva para controlar el tiempo
st.sidebar.header("🛠️ Panel de Control")
st.sidebar.write("Usa el deslizador para ver avanzar el frente de mal tiempo hora por hora:")

selected_time_index = st.sidebar.slider(
    "Línea de tiempo:",
    min_value=0,
    max_value=len(horas_unicas) - 1,
    value=0,
    format="" 
)

selected_time = horas_unicas[selected_time_index]
st.sidebar.info(f"📅 Visualizando: **{format_es(pd.to_datetime(selected_time))}**")

# Filtrar datos para la hora seleccionada
df_actual = df[df["Fecha_Hora"] == selected_time]

# 5. Definición de la paleta de colores para la lluvia (Escala Blues / PuBu)
def get_color(val):
    if val == 0:
        return "#e0e8f5"  # Gris azulado muy tenue (sin lluvia)
    elif val <= 1.0:
        return "#a1dab4"  # Verde agua claro (lluvia muy débil)
    elif val <= 5.0:
        return "#41b6c4"  # Celeste intermedio
    elif val <= 15.0:
        return "#2c7fb8"  # Azul fuerte
    else:
        return "#253494"  # Azul marino profundo (lluvia intensa/frente activo)

# 6. Distribución de pantalla en dos columnas principales
col1, col2 = st.columns([1, 1.2])

with col1:
    st.subheader("🗺️ Mapa Espacial del Frente")
    st.write("El tamaño y oscuridad del círculo representan la intensidad del agua:")
    
    # Mapa centrado en el centro-sur de Chile
    m = folium.Map(location=[-37.5, -72.5], zoom_start=5.5, tiles="cartodbpositron")
    
    for _, row in df_actual.iterrows():
        val = row["Precipitacion"]
        color = get_color(val)
        radius = 7 + min(val * 2.5, 25) # Escala dinámica
        
        popup_text = f"<b>{row['Ciudad']}</b><br>Intensidad: {val:.1f} mm/h"
        
        folium.CircleMarker(
            location=[row["Latitud"], row["Longitud"]],
            radius=radius,
            color=color,
            fill=True,
            fill_color=color,
            fill_opacity=0.75,
            weight=1.5,
            popup=folium.Popup(popup_text, max_width=200)
        ).add_to(m)
        
    st_folium(m, width="100%", height=500, returned_objects=[])

with col2:
    st.subheader("📊 Evolución Temporal (Sur a Norte)")
    st.write("Dado que en Chile los frentes suben desde el sur (altas latitudes), este gráfico de burbujas te muestra cómo se desplaza la lluvia en el tiempo:")
    
    # Ordenar geográficamente para el eje Y de sur a norte
    df_chart = df.sort_values(by="Latitud", ascending=True)
    
    # Gráfico interactivo de burbujas
    fig = px.scatter(
        df_chart,
        x="Fecha_Hora",
        y="Ciudad",
        size="Precipitacion",
        color="Precipitacion",
        color_continuous_scale="PuBu",
        labels={"Fecha_Hora": "Tiempo", "Precipitacion": "Lluvia (mm/h)", "Ciudad": "Ciudad (Sur a Norte)"},
        height=500
    )
    
    fig.update_layout(
        margin=dict(l=20, r=20, t=20, b=20),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        coloraxis_colorbar=dict(title="mm/h")
    )
    
    # Añade una línea roja que se mueve dinámicamente con el slider del mapa
    fig.add_vline(x=selected_time.timestamp() * 1000, line_width=2, line_dash="dash", line_color="red")
    
    st.plotly_chart(fig, use_container_width=True)

# 7. Resumen de Agua Acumulada Semanal (Parte Inferior)
st.markdown("---")
st.subheader("📈 Proyección de Agua Acumulada para la Semana (Total)")

df_acumulado = df.groupby("Ciudad").agg({
    "Precipitacion": "sum",
    "Latitud": "first"
}).reset_index().sort_values(by="Latitud", ascending=True)

fig_bar = px.bar(
    df_acumulado,
    x="Precipitacion",
    y="Ciudad",
    orientation='h',
    color="Precipitacion",
    color_continuous_scale="PuBu",
    labels={"Precipitacion": "Milímetros Acumulados (7 días)", "Ciudad": "Ciudad"},
    height=400
)
fig_bar.update_layout(plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
st.plotly_chart(fig_bar, use_container_width=True)