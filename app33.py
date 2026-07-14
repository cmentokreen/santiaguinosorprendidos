import streamlit as st
import numpy as np
import pandas as pd
import requests
import plotly.express as px
import plotly.graph_objects as go

# ==========================================
# 1. CONFIGURACIÓN DE LA PÁGINA
# ==========================================
st.set_page_config(
    page_title="Frente de Lluvia - Chile",
    page_icon="🌧️",
    layout="wide",
)

CSS = """
    <style>
    .block-container { padding-top: 1.2rem !important; padding-bottom: 1rem !important; }
    #MainMenu, footer { visibility: hidden; }
    h1 { font-size: 1.6rem !important; }
    .custom-footer {
        text-align: center; padding: 20px 10px; margin-top: 40px;
        border-top: 1px solid #334155; color: #64748b; font-size: 13px;
    }
    .custom-footer strong { color: #94a3b8; }
    </style>
"""

# ==========================================
# 2. CIUDADES (SUR A NORTE) Y PALETAS
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
    "La Serena": {"lat": -29.902, "lon": -71.252},
}

# Acumulación: de casi invisible (slate) a violeta
ESCALA_ACUM = ["#334155", "#38bdf8", "#4f46e5", "#7c3aed"]
# Intensidad horaria (Hovmöller): fondo oscuro que se enciende con la lluvia
ESCALA_INTENSIDAD = [
    [0.00, "#0b1220"], [0.06, "#1e3a8a"], [0.30, "#38bdf8"],
    [0.65, "#4f46e5"], [1.00, "#c4b5fd"],
]
DIAS_ES = {"Mon": "Lun", "Tue": "Mar", "Wed": "Mié", "Thu": "Jue",
           "Fri": "Vie", "Sat": "Sáb", "Sun": "Dom"}

FONT_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(color="#cbd5e1", size=13),
)


def etiqueta_es(ts: pd.Timestamp) -> str:
    dia = DIAS_ES.get(ts.strftime("%a"), ts.strftime("%a"))
    return f"{dia} {ts.strftime('%d')} · {ts.strftime('%H')}h"


# ==========================================
# 3. DATOS (OPEN-METEO, CON CACHÉ)
# ==========================================
def _fetch_precipitation() -> pd.DataFrame:
    lats = [str(c["lat"]) for c in CITIES.values()]
    lons = [str(c["lon"]) for c in CITIES.values()]
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": ",".join(lats),
        "longitude": ",".join(lons),
        "hourly": "precipitation",
        "timezone": "America/Santiago",
        "forecast_days": 7,
    }
    response = requests.get(url, params=params, timeout=20)
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, list):
        data = [data]

    records = []
    for ciudad, payload in zip(CITIES.keys(), data):
        hourly = payload.get("hourly", {})
        for t, p in zip(hourly.get("time", []), hourly.get("precipitation", [])):
            records.append({
                "Ciudad": ciudad,
                "Latitud": CITIES[ciudad]["lat"],
                "Longitud": CITIES[ciudad]["lon"],
                "Fecha_Hora": pd.to_datetime(t),
                "Precipitacion": 0.0 if p is None else float(p),
            })
    return pd.DataFrame(records)


def preparar_datos(df: pd.DataFrame, paso_horas: int = 3):
    """Agrega acumulado por ciudad y submuestrea cada N horas para la animación."""
    df = df.sort_values(["Ciudad", "Fecha_Hora"]).reset_index(drop=True)
    df["Acumulado"] = df.groupby("Ciudad")["Precipitacion"].cumsum()

    df_anim = df[df["Fecha_Hora"].dt.hour % paso_horas == 0].copy()
    # Escala perceptual sobre el ACUMULADO: la burbuja crece con el agua
    # caída y persiste tras el paso del frente (la huella del evento).
    # La raíz cuadrada evita que las ciudades más lluviosas aplasten al resto.
    df_anim["Impacto"] = np.sqrt(df_anim["Acumulado"])
    df_anim["Cuadro"] = df_anim["Fecha_Hora"].map(etiqueta_es)
    orden_cuadros = [etiqueta_es(t) for t in sorted(df_anim["Fecha_Hora"].unique())]
    return df, df_anim, orden_cuadros


# ==========================================
# 4. MAPA ANIMADO (CLIENT-SIDE, SIN RERUNS)
# ==========================================
def build_mapa(df_anim: pd.DataFrame, orden_cuadros: list,
               zoom: float = 5.0) -> go.Figure:
    usa_maplibre = hasattr(px, "scatter_map")
    scatter = px.scatter_map if usa_maplibre else px.scatter_mapbox
    estilo = {"map_style": "carto-darkmatter"} if usa_maplibre \
        else {"mapbox_style": "carto-darkmatter"}

    max_intens = float(df_anim["Precipitacion"].max()) or 1.0
    fig = scatter(
        df_anim,
        lat="Latitud", lon="Longitud",
        size="Impacto", size_max=58,
        opacity=0.78,
        color="Precipitacion",
        color_continuous_scale=ESCALA_ACUM,
        range_color=(0, max_intens),
        animation_frame="Cuadro",
        category_orders={"Cuadro": orden_cuadros},
        hover_name="Ciudad",
        hover_data={
            "Latitud": False, "Longitud": False, "Cuadro": False,
            "Impacto": False,
            "Precipitacion": ":.1f", "Acumulado": ":.0f",
        },
        labels={"Precipitacion": "mm/h", "Acumulado": "mm acumulados"},
        zoom=zoom, center={"lat": -34.2, "lon": -71.3},
        height=560,
        **estilo,
    )

    # Puntos fijos de referencia por ciudad (persisten entre cuadros:
    # las frames solo reescriben la traza 0)
    ScatterGeo = go.Scattermap if usa_maplibre else go.Scattermapbox
    fig.add_trace(ScatterGeo(
        lat=[c["lat"] for c in CITIES.values()],
        lon=[c["lon"] for c in CITIES.values()],
        mode="markers",
        marker=dict(size=4, color="#64748b"),
        hoverinfo="skip", showlegend=False,
    ))

    fig.update_layout(
        margin=dict(l=0, r=0, t=0, b=0),
        coloraxis_colorbar=dict(
            title=dict(text="mm/h<br>ahora", font=dict(size=11)),
            thickness=10, outlinewidth=0, len=0.55, y=0.72,
        ),
        **FONT_LAYOUT,
    )

    # CLAVE: en trazas de mapa, los cuadros NO repintan tamaño/color
    # con redraw=False. Debe ser True para que la animación se vea.
    if fig.layout.updatemenus:
        menu = fig.layout.updatemenus[0]
        menu.bgcolor = "#1e293b"
        menu.font = dict(color="#e2e8f0")
        play, pause = menu.buttons
        play.label, pause.label = "▶ Play", "⏸ Pausa"
        play.args[1]["frame"]["duration"] = 450
        play.args[1]["frame"]["redraw"] = True
        play.args[1]["transition"] = {"duration": 0}
        pause.args[1]["frame"]["redraw"] = True
    if fig.layout.sliders:
        slider = fig.layout.sliders[0]
        slider.currentvalue = dict(
            prefix="", font=dict(size=13, color="#94a3b8"))
        slider.pad = dict(t=6)
        slider.tickcolor = "#334155"
        for step in slider.steps:
            step.args[1]["frame"]["duration"] = 0
            step.args[1]["frame"]["redraw"] = True
            step.args[1]["mode"] = "immediate"
            step.args[1]["transition"] = {"duration": 0}

        # Abrir el mapa en el primer cuadro con lluvia, no en uno seco
        lluvia = df_anim.groupby("Cuadro")["Precipitacion"].sum()
        con_lluvia = [i for i, c in enumerate(orden_cuadros)
                      if lluvia.get(c, 0) > 0]
        if con_lluvia:
            i0 = con_lluvia[0]
            datos_i0 = fig.frames[i0].data[0].to_plotly_json()
            datos_i0.pop("type", None)
            fig.data[0].update(datos_i0)
            slider.active = i0
    return fig


# ==========================================
# 5. HOVMÖLLER: EL FRENTE COMO BANDA DIAGONAL
# ==========================================
def build_hovmoller(df: pd.DataFrame) -> go.Figure:
    orden_sur_norte = list(CITIES.keys())
    pivot = (df.pivot_table(index="Ciudad", columns="Fecha_Hora",
                            values="Precipitacion")
               .reindex(orden_sur_norte))
    fig = go.Figure(go.Heatmap(
        z=pivot.values, x=pivot.columns, y=pivot.index,
        colorscale=ESCALA_INTENSIDAD, zmin=0, zsmooth="best",
        colorbar=dict(title=dict(text="mm/h", font=dict(size=11)),
                      thickness=10, outlinewidth=0, len=0.8),
        hovertemplate="%{y} · %{x|%d/%m %H:%M}<br>%{z:.1f} mm/h<extra></extra>",
    ))
    fig.update_layout(
        height=440,
        margin=dict(l=10, r=10, t=10, b=10),
        xaxis=dict(tickformat="%a %d", tickfont=dict(size=11),
                   showgrid=False, ticklabelmode="period"),
        yaxis=dict(tickfont=dict(size=11), showgrid=False),
        **FONT_LAYOUT,
    )
    return fig


# ==========================================
# 6. ACUMULADO SEMANAL
# ==========================================
def build_acumulado(df: pd.DataFrame) -> go.Figure:
    resumen = (df.groupby("Ciudad")
                 .agg(Total=("Precipitacion", "sum"), Latitud=("Latitud", "first"))
                 .reset_index()
                 .sort_values("Latitud"))
    fig = go.Figure(go.Bar(
        x=resumen["Total"], y=resumen["Ciudad"], orientation="h",
        marker=dict(
            color=resumen["Total"], colorscale=ESCALA_ACUM,
            cmin=0, line_width=0,
        ),
        text=[f"{v:.0f}" for v in resumen["Total"]],
        textposition="outside", textfont=dict(size=11, color="#94a3b8"),
        hovertemplate="%{y}: %{x:.1f} mm<extra></extra>",
    ))
    fig.update_layout(
        height=440,
        margin=dict(l=10, r=30, t=10, b=10),
        xaxis=dict(title="mm en 7 días", gridcolor="#1e293b", zeroline=False),
        yaxis=dict(showgrid=False),
        **FONT_LAYOUT,
    )
    return fig


# ==========================================
# 7. APLICACIÓN
# ==========================================
def main():
    st.markdown(CSS, unsafe_allow_html=True)
    st.title("🌧️ Evolución del Frente de Lluvias /Rio Atmosferico")
    st.caption("Pronóstico horario a 7 días · 14 ciudades entre Punta Arenas y La Serena")

    fetch_cacheado = st.cache_data(ttl=3600, show_spinner="Consultando pronóstico…")(
        _fetch_precipitation)
    try:
        df_raw = fetch_cacheado()
    except Exception as e:
        st.error(f"Error al conectar con el servidor meteorológico: {e}")
        st.stop()
    if df_raw.empty:
        st.warning("No se pudieron cargar los datos de pronóstico.")
        st.stop()

    df, df_anim, orden_cuadros = preparar_datos(df_raw)

    # --- Indicadores clave ---
    tot_ciudad = df.groupby("Ciudad")["Precipitacion"].sum()
    idx_max = df["Precipitacion"].idxmax()
    k1, k2, k3 = st.columns(3)
    k1.metric("Ciudad más lluviosa (7 días)",
              tot_ciudad.idxmax(), f"{tot_ciudad.max():.0f} mm")
    k2.metric("Santiago (7 días)", f"{tot_ciudad.get('Santiago', 0):.0f} mm")
    k3.metric("Intensidad máxima",
              f"{df.loc[idx_max, 'Precipitacion']:.1f} mm/h",
              f"{df.loc[idx_max, 'Ciudad']} · {etiqueta_es(df.loc[idx_max, 'Fecha_Hora'])}",
              delta_color="off")

    # --- Mapa animado con control de zoom ---
    if "zoom" not in st.session_state:
        st.session_state.zoom = 5.0
    cz1, cz2, cz3 = st.columns([1, 1, 3])
    if cz1.button("➕ Acercar", use_container_width=True):
        st.session_state.zoom = min(st.session_state.zoom + 0.7, 9.0)
    if cz2.button("➖ Alejar", use_container_width=True):
        st.session_state.zoom = max(st.session_state.zoom - 0.7, 3.0)
    cz3.caption("Vista inicial: Santiago y regiones adyacentes. "
                "También funciona el pinch en el teléfono y el scroll con el mouse; "
                "arrastra para desplazarte hacia el sur o el norte.")

    st.plotly_chart(build_mapa(df_anim, orden_cuadros, st.session_state.zoom),
                    use_container_width=True,
                    config={"displayModeBar": False, "scrollZoom": True})
    st.caption("El **tamaño** de cada burbuja es el agua acumulada hasta ese momento "
               "—crece con el paso del frente y queda como huella del evento—; "
               "su **color** es la intensidad de la lluvia en ese instante, "
               "así el borde activo del frente se ve encendido. "
               "Presiona ▶ o arrastra la barra: la animación corre en tu navegador.")

    # --- Hovmöller ---
    st.markdown("---")
    st.subheader("El frente visto en el tiempo")
    st.caption("Cada fila es una ciudad (sur abajo, norte arriba); cada columna, una hora. "
               "La banda diagonal luminosa es el frente desplazándose hacia el norte.")
    st.plotly_chart(build_hovmoller(df), use_container_width=True,
                    config={"displayModeBar": False})

    # --- Acumulado ---
    st.markdown("---")
    st.subheader("Agua caída estimada · próximos 7 días")
    st.plotly_chart(build_acumulado(df), use_container_width=True,
                    config={"displayModeBar": False})

    # --- Visor ECMWF sobre Sudamérica (Windy) ---
    st.markdown("---")
    st.subheader("El frente sobre Sudamérica · modelo ECMWF")
    st.caption("Visor interactivo de Windy con el modelo europeo. Presiona el play "
               "de **su** línea de tiempo (abajo del visor) para ver los sistemas "
               "frontales avanzando desde el Pacífico hacia el continente.")
    from streamlit.components.v1 import iframe as st_iframe
    url_windy = (
        "https://embed.windy.com/embed2.html"
        "?lat=-36.5&lon=-76&zoom=3&level=surface"
        "&overlay=rain&product=ecmwf"
        "&menu=&message=true&marker=&calendar=now&pressure="
        "&type=map&location=coordinates&detail="
        "&metricWind=km%2Fh&metricTemp=%C2%B0C&metricRain=mm&radarRange=-1"
    )
    st_iframe(url_windy, height=520, scrolling=False)
    st.caption("Fuente: Windy.com · datos del modelo ECMWF.")

    st.markdown(
        """
        <div class="custom-footer">
            Sitio desarrollado por <strong>Carlos Mendoza - CMENTO</strong> - para un grupo privado.<br>
            Todos los derechos reservados &copy; 2026. Datos provistos por Open-Meteo.
        </div>
        """,
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
