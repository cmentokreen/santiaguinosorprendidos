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

# CSS con reglas responsive: en pantallas angostas (teléfono) se reduce el
# título, se compactan métricas y márgenes, y se evita el desborde horizontal.
CSS = """
    <style>
    .block-container { padding-top: 1.2rem !important; padding-bottom: 1rem !important; }
    #MainMenu, footer { visibility: hidden; }
    h1 { font-size: 1.6rem !important; }

    /* Cada bloque de gráfico con aire alrededor para que no "se confundan" */
    .stPlotlyChart { margin-bottom: 0.4rem; }

    .custom-footer {
        text-align: center; padding: 20px 10px; margin-top: 40px;
        border-top: 1px solid #334155; color: #64748b; font-size: 13px;
    }
    .custom-footer strong { color: #94a3b8; }

    @media (max-width: 640px) {
        h1 { font-size: 1.2rem !important; }
        .block-container {
            padding-left: 0.5rem !important;
            padding-right: 0.5rem !important;
        }
        /* Métricas más chicas para que las 3 quepan sin encimarse */
        [data-testid="stMetricValue"] { font-size: 1rem !important; }
        [data-testid="stMetricLabel"] p { font-size: 0.7rem !important; }
        [data-testid="stMetricDelta"] { font-size: 0.68rem !important; }
        /* Separación clara entre secciones apiladas */
        hr { margin: 0.6rem 0 !important; }
    }
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
    "Nacimiento": {"lat": -37.503, "lon": -72.673},
    "Concepción": {"lat": -36.827, "lon": -73.050},
    "Chillán": {"lat": -36.607, "lon": -72.103},
    "Talca": {"lat": -35.426, "lon": -71.656},
    "Rancagua": {"lat": -34.165, "lon": -70.740},
    "Santo Domingo": {"lat": -33.638, "lon": -71.630},
    "San Antonio": {"lat": -33.593, "lon": -71.607},
    "Santiago": {"lat": -33.449, "lon": -70.662},
    "Valparaíso": {"lat": -33.047, "lon": -71.613},
    "La Serena": {"lat": -29.902, "lon": -71.252},
}

ESCALA_ACUM = ["#334155", "#38bdf8", "#4f46e5", "#7c3aed"]
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
    autosize=True,
)

# Config de Plotly: responsive=True es clave para que el gráfico se
# reajuste al ancho real del teléfono al rotar o cambiar de tamaño.
PLOTLY_CFG = {"displayModeBar": False, "responsive": True}
MAP_CFG = {"displayModeBar": False, "responsive": True, "scrollZoom": True}


def etiqueta_es(ts: pd.Timestamp) -> str:
    dia = DIAS_ES.get(ts.strftime("%a"), ts.strftime("%a"))
    return f"{dia} {ts.strftime('%d')} · {ts.strftime('%H')}h"


# ==========================================
# 3. DATOS (OPEN-METEO, CON CACHÉ)
# ==========================================
import time


def _get_con_reintentos(url, params, timeout=25, intentos=4):
    """GET con reintentos ante 429 (límite de peticiones) y 5xx.
    Respeta el header Retry-After cuando viene; si no, espera creciente."""
    espera = 2.0
    ultimo_error = None
    for n in range(intentos):
        try:
            r = requests.get(url, params=params, timeout=timeout)
            if r.status_code == 429 or r.status_code >= 500:
                ultimo_error = requests.HTTPError(
                    f"{r.status_code} {r.reason}", response=r)
                pausa = float(r.headers.get("Retry-After", espera))
                time.sleep(min(pausa, 20))
                espera *= 2
                continue
            r.raise_for_status()
            return r
        except requests.RequestException as e:
            ultimo_error = e
            time.sleep(espera)
            espera *= 2
    raise ultimo_error


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
    response = _get_con_reintentos(url, params, timeout=25)
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
    df_anim["Impacto"] = np.sqrt(df_anim["Acumulado"])
    df_anim["Cuadro"] = df_anim["Fecha_Hora"].map(etiqueta_es)
    orden_cuadros = [etiqueta_es(t) for t in sorted(df_anim["Fecha_Hora"].unique())]
    return df, df_anim, orden_cuadros


# ==========================================
# 4. MAPA ANIMADO (CLIENT-SIDE, SIN RERUNS)
# ==========================================
def build_mapa(df_anim: pd.DataFrame, orden_cuadros: list,
               zoom: float = 5.0, altura: int = 540) -> go.Figure:
    usa_maplibre = hasattr(px, "scatter_map")
    scatter = px.scatter_map if usa_maplibre else px.scatter_mapbox
    estilo = {"map_style": "carto-darkmatter"} if usa_maplibre \
        else {"mapbox_style": "carto-darkmatter"}

    max_intens = float(df_anim["Precipitacion"].max()) or 1.0
    fig = scatter(
        df_anim,
        lat="Latitud", lon="Longitud",
        size="Impacto", size_max=52,
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
        height=altura,
        **estilo,
    )

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
        autosize=True,
        coloraxis_colorbar=dict(
            title=dict(text="mm/h<br>ahora", font=dict(size=10)),
            thickness=8, outlinewidth=0, len=0.5, y=0.7,
            tickfont=dict(size=9),
        ),
        **{k: v for k, v in FONT_LAYOUT.items() if k != "autosize"},
    )

    if fig.layout.updatemenus:
        menu = fig.layout.updatemenus[0]
        menu.bgcolor = "#1e293b"
        menu.font = dict(color="#e2e8f0", size=12)
        menu.pad = dict(r=6, t=6)
        play, pause = menu.buttons
        play.label, pause.label = "▶ Play", "⏸ Pausa"
        play.args[1]["frame"]["duration"] = 450
        play.args[1]["frame"]["redraw"] = True
        play.args[1]["transition"] = {"duration": 0}
        pause.args[1]["frame"]["redraw"] = True
    if fig.layout.sliders:
        slider = fig.layout.sliders[0]
        slider.currentvalue = dict(prefix="", font=dict(size=12, color="#94a3b8"))
        slider.pad = dict(t=4, b=2)
        slider.tickcolor = "#334155"
        slider.font = dict(size=9)
        for step in slider.steps:
            step.args[1]["frame"]["duration"] = 0
            step.args[1]["frame"]["redraw"] = True
            step.args[1]["mode"] = "immediate"
            step.args[1]["transition"] = {"duration": 0}

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
def build_hovmoller(df: pd.DataFrame, altura: int = 460) -> go.Figure:
    orden_sur_norte = list(CITIES.keys())
    pivot = (df.pivot_table(index="Ciudad", columns="Fecha_Hora",
                            values="Precipitacion")
               .reindex(orden_sur_norte))
    fig = go.Figure(go.Heatmap(
        z=pivot.values, x=pivot.columns, y=pivot.index,
        colorscale=ESCALA_INTENSIDAD, zmin=0, zsmooth="best",
        colorbar=dict(title=dict(text="mm/h", font=dict(size=10)),
                      thickness=8, outlinewidth=0, len=0.85,
                      tickfont=dict(size=9)),
        hovertemplate="%{y} · %{x|%d/%m %H:%M}<br>%{z:.1f} mm/h<extra></extra>",
    ))
    fig.update_layout(
        height=altura,
        margin=dict(l=6, r=6, t=6, b=6),
        # dtick diario (en ms) + ángulo 0 evita que las fechas se encimen en móvil
        xaxis=dict(tickformat="%a %d", dtick=86400000.0, tickangle=0,
                   tickfont=dict(size=10), showgrid=False, automargin=True),
        yaxis=dict(tickfont=dict(size=10), showgrid=False, automargin=True),
        **FONT_LAYOUT,
    )
    return fig


# ==========================================
# 6. ACUMULADO SEMANAL
# ==========================================
def build_acumulado(df: pd.DataFrame, altura: int = 460) -> go.Figure:
    resumen = (df.groupby("Ciudad")
                 .agg(Total=("Precipitacion", "sum"), Latitud=("Latitud", "first"))
                 .reset_index()
                 .sort_values("Latitud"))
    fig = go.Figure(go.Bar(
        x=resumen["Total"], y=resumen["Ciudad"], orientation="h",
        marker=dict(color=resumen["Total"], colorscale=ESCALA_ACUM,
                    cmin=0, line_width=0),
        text=[f"{v:.0f}" for v in resumen["Total"]],
        textposition="outside", textfont=dict(size=10, color="#94a3b8"),
        cliponaxis=False,
        hovertemplate="%{y}: %{x:.1f} mm<extra></extra>",
    ))
    fig.update_layout(
        height=altura,
        margin=dict(l=6, r=24, t=6, b=6),
        xaxis=dict(title="mm en 7 días", gridcolor="#1e293b", zeroline=False,
                   tickfont=dict(size=10), automargin=True),
        yaxis=dict(showgrid=False, tickfont=dict(size=10), automargin=True),
        **FONT_LAYOUT,
    )
    return fig


# ==========================================
# 7. VISOR WINDY (SUDAMÉRICA, ECMWF)
# ==========================================
def url_windy() -> str:
    return (
        "https://embed.windy.com/embed2.html"
        "?lat=-36.5&lon=-76&zoom=3&level=surface"
        "&overlay=rain&product=ecmwf"
        "&menu=&message=true&marker=&calendar=now&pressure="
        "&type=map&location=coordinates&detail="
        "&metricWind=km%2Fh&metricTemp=%C2%B0C&metricRain=mm&radarRange=-1"
    )


# ==========================================
# 8. APLICACIÓN
# ==========================================
def main():
    st.markdown(CSS, unsafe_allow_html=True)
    st.title("🌧️ Evolución del Frente de Mal Tiempo")
    st.caption("Pronóstico horario a 7 días · 17 ciudades entre Punta Arenas y La Serena")

    fetch_cacheado = st.cache_data(ttl=1800, show_spinner="Consultando pronóstico…")(
        _fetch_precipitation)
    try:
        df_raw = fetch_cacheado()
    except Exception as e:
        msg = str(e)
        if "429" in msg or "Too Many Requests" in msg:
            st.warning(
                "⏳ **Open-Meteo está limitando las peticiones (error 429).** "
                "La API gratuita permite un número acotado de consultas por minuto "
                "y por día. Espera un momento y presiona **⟳ Reintentar**; los datos "
                "quedan luego en caché por 30 minutos.")
            if st.button("⟳ Reintentar"):
                st.cache_data.clear()
                st.rerun()
        else:
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
    k1.metric("Más lluviosa (7 días)",
              tot_ciudad.idxmax(), f"{tot_ciudad.max():.0f} mm")
    k2.metric("Santiago (7 días)", f"{tot_ciudad.get('Santiago', 0):.0f} mm")
    k3.metric("Intensidad máxima",
              f"{df.loc[idx_max, 'Precipitacion']:.1f} mm/h",
              df.loc[idx_max, "Ciudad"], delta_color="off")

    # --- Mapa animado ---
    st.markdown("---")
    st.subheader("🌀 El frente, en movimiento")
    if "zoom" not in st.session_state:
        st.session_state.zoom = 5.0
    cz1, cz2 = st.columns(2)
    if cz1.button("➕ Acercar", use_container_width=True):
        st.session_state.zoom = min(st.session_state.zoom + 0.7, 9.0)
    if cz2.button("➖ Alejar", use_container_width=True):
        st.session_state.zoom = max(st.session_state.zoom - 0.7, 3.0)
    st.caption("Vista centrada en Santiago. También sirven el pinch y el scroll; "
               "arrastra para moverte al sur o al norte.")

    st.plotly_chart(build_mapa(df_anim, orden_cuadros, st.session_state.zoom),
                    use_container_width=True, config=MAP_CFG)
    st.caption("**Tamaño** = agua acumulada (la huella del evento); "
               "**color** = intensidad en ese instante. "
               "Presiona ▶ o arrastra la barra.")

    # --- Hovmöller ---
    st.markdown("---")
    st.subheader("📈 El frente visto en el tiempo")
    st.caption("Filas = ciudades (sur abajo, norte arriba); columnas = horas. "
               "La banda diagonal es el frente subiendo al norte.")
    st.plotly_chart(build_hovmoller(df), use_container_width=True, config=PLOTLY_CFG)

    # --- Acumulado ---
    st.markdown("---")
    st.subheader("💧 Agua caída estimada · 7 días")
    st.plotly_chart(build_acumulado(df), use_container_width=True, config=PLOTLY_CFG)

    # --- Visor ECMWF sobre Sudamérica (Windy) ---
    st.markdown("---")
    st.subheader("🛰️ El frente sobre Sudamérica · ECMWF")
    st.caption("Visor de Windy. Presiona el play de **su** línea de tiempo (bajo el "
               "visor) para ver los frentes avanzando desde el Pacífico.")
    from streamlit.components.v1 import iframe as st_iframe
    st_iframe(url_windy(), height=480, scrolling=False)
    st.caption("Fuente: Windy.com · modelo ECMWF.")

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
