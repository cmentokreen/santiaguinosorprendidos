import streamlit as st
import pandas as pd
import requests
import folium
from streamlit_folium import st_folium
import plotly.express as px
import time

# ==========================================
# 1. CONFIGURACIÓN DE LA PÁGINA
# ==========================================
st.set_page_config(
    page_title="Frente de Lluvia - Chile",
    page_icon="🌧️",
    layout="wide"
)

# Estilos CSS limpios y optimizados para móviles
st.markdown("""
    <style>
    /* Compactar márgenes superiores para que todo suba en la pantalla */
    .block-container {
        padding-top: 1.5rem !important;
        padding-bottom: 1rem !important;
    }
    
    /* Caja de fecha activa estilo "Badge" tecnológico */
    .time-badge {
        background-color: #1e293b;
        border: 1px solid #334155;
        border-radius: 8px;
        padding: 6px 12px;
        text-align: center;
        font-family: monospace;
        font-size: 14px;
        color: #38bdf8;
        font-weight: bold;
    }

    /* Pie de página elegante */
    .custom-footer {
        text-align: center;
        padding: 20px 10px;
        margin-top: 40px;
        border-top: 1px solid #334155;
        color: #64748b;
        font-size: 13px;
    }
    .custom-footer strong {
        color: #94a3b8;
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

df = fetch_precipitation_forecast()

if df.empty:
    st.warning("No se pudieron cargar los datos de pronóstico.")
    st.stop()

# Ordenar las horas disponibles de la simulación
horas_disponibles = sorted(df["Fecha_Hora"].unique())

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

# ==========================================
# 5. CONTROLADOR DE REPRODUCCIÓN AUTOMÁTICA (STATE)
# ==========================================
if "current_index" not in st.session_state:
    st.session_state.current_index = 0
if "playing" not in st.session_state:
    st.session_state.playing = False

# Título compacto
st.title("🌧️ Evolución de Frente Atmosférico")

# Fila de control ultra-compacta (Súper amigable con celulares)
ctrl_col1, ctrl_col2, ctrl_col3 = st.columns([1, 1, 2])

with ctrl_col1:
    # Botón de Play / Pausa interactivo
    button_label = "⏸️ Pausar" if st.session_state.playing else "▶️ Play"
    if st.button(button_label, use_container_width=True):
        st.session_state.playing = not st.session_state.playing
        st.rerun()

with ctrl_col2:
    # Botón para volver al inicio de la simulación
    if st.button("🔄 Reiniciar", use_container_width=True):
        st.session_state.current_index = 0
        st.session_state.playing = False
        st.rerun()

with ctrl_col3:
    # Mostrar la fecha y hora activa de forma muy estilizada
    active_time = horas_disponibles[st.session_state.current_index]
    st.markdown(
        f'<div class="time-badge">📍 {format_date_es(active_time)}</div>', 
        unsafe_allow_html=True
    )

# Filtrar datos de la hora seleccionada para el mapa
df_actual = df[df["Fecha_Hora"] == active_time]

# ==========================================
# 6. GRÁFICO 1: MAPA ESPACIAL COMPLETO
# ==========================================
# Paleta de colores para las burbujas del mapa
def get_hex_color(val):
    if val == 0:
         return "#475569" # Gris (Sin lluvia)
    elif val <= 1.0:
         return "#38bdf8" # Celeste (Lluvia débil)
    elif val <= 5.0:
         return "#0284c7" # Azul
    elif val <= 15.0:
         return "#4f46e5" # Índigo (Lluvia fuerte)
    else:
         return "#7c3aed" # Violeta (Temporal)

# Generar mapa interactivo
m = folium.Map(
    location=[-38.5, -72.0], 
    zoom_start=5, 
    tiles="CartoDB dark_matter", 
    control_scale=True
)

for _, row in df_actual.iterrows():
    val = row["Precipitacion"]
    color = get_hex_color(val)
    radius = 6 + min(val * 3.5, 30)
    
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

# Desplegar mapa inmediatamente abajo de los controles
st_folium(m, width="100%", height=500, returned_objects=[])

# ==========================================
# 7. GRÁFICO 2: EVOLUCIÓN LATITUDINAL (BURBUJAS)
# ==========================================
st.markdown("---")
st.subheader("📊 Evolución del Frente (Desplazamiento Sur a Norte)")
st.write("Evolución temporal continua del frente frío subiendo por la latitud del territorio chileno.")

df_sorted = df.sort_values(by="Latitud", ascending=True)

fig_burbujas = px.scatter(
    df_sorted,
    x="Fecha_Hora",
    y="Ciudad",
    size="Precipitacion",
    color="Precipitacion",
    color_continuous_scale=["#475569", "#38bdf8", "#0284c7", "#4f46e5", "#7c3aed"],
    labels={
        "Fecha_Hora": "Fecha y Hora del Pronóstico", 
        "Precipitacion": "Precipitación (mm/h)", 
        "Ciudad": "Ciudad"
    },
    height=500
)

# Línea de tiempo que se mueve sola al ritmo del Playback
selected_time_ms = pd.to_datetime(active_time).timestamp() * 1000
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
    margin=dict(l=20, r=20, t=10, b=20),
    coloraxis_colorbar=dict(title="mm/h")
)

st.plotly_chart(fig_burbujas, use_container_width=True)

# ==========================================
# 8. GRÁFICO 3: ACUMULADO SEMANAL
# ==========================================
st.markdown("---")
st.subheader("📈 Agua Caída Estimada para los Próximos 7 Días")

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
    labels={"Precipitacion": "Acumulado (mm)", "Ciudad": "Ciudad"},
    height=450
)

fig_barras.update_layout(
    plot_bgcolor="rgba(15,23,42,1)",
    paper_bgcolor="rgba(0,0,0,0)",
    font=dict(color="#cbd5e1"),
    margin=dict(l=20, r=20, t=10, b=20)
)

st.plotly_chart(fig_barras, use_container_width=True)

# ==========================================
# 9. PIE DE PÁGINA (Firma Solicitada)
# ==========================================
st.markdown(
    """
    <div class="custom-footer">
        Sitio desarrollado por <strong>Carlos Mendoza - CMENTO</strong> - para un grupo privado.<br>
        Todos los derechos reservados &copy; 2026. Datos provistos por Open-Meteo.
    </div>
    """, 
    unsafe_allow_html=True
)

# ==========================================
# 10. BUCLE DE ANIMACIÓN (LOOP)
# ==========================================
if st.session_state.playing:
    time.sleep(0.6)  # Velocidad de avance de la tormenta (0.6 segundos por hora)
    # Incrementar el paso del tiempo y volver a cargar el mapa
    st.session_state.current_index = (st.session_state.current_index + 1) % len(horas_disponibles)
    st.rerun()
