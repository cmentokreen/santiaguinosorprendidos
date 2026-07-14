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
# 3. FUENTES DE DATOS (MULTI-MODELO)
# ==========================================
# Open-Meteo: gratis, sin clave. El parámetro models= permite elegir y comparar
# modelos individuales; "best_match" es la combinación óptima por defecto.
MODELOS_OPENMETEO = {
    "Open-Meteo · Best match": "best_match",
    "ECMWF IFS (europeo)": "ecmwf_ifs025",
    "NOAA GFS (EE.UU.)": "gfs_seamless",
    "DWD ICON (alemán)": "icon_seamless",
    "Météo-France ARPEGE": "meteofrance_seamless",
    "Environment Canada GEM": "gem_seamless",
}


def _fetch_openmeteo(modelo: str = "best_match") -> pd.DataFrame:
    lats = [str(c["lat"]) for c in CITIES.values()]
    lons = [str(c["lon"]) for c in CITIES.values()]
    params = {
        "latitude": ",".join(lats),
        "longitude": ",".join(lons),
        "hourly": "precipitation",
        "timezone": "America/Santiago",
        "forecast_days": 7,
    }
    if modelo and modelo != "best_match":
        params["models"] = modelo
    r = requests.get("https://api.open-meteo.com/v1/forecast",
                     params=params, timeout=25)
    r.raise_for_status()
    data = r.json()
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


def _fetch_meteomatics(usuario: str, clave: str) -> pd.DataFrame:
    """Meteomatics requiere autenticación (cuenta gratuita 'Basic' sirve).
    Consulta precip_1h por puntos, que es lo que permite el plan gratuito."""
    inicio = pd.Timestamp.utcnow().floor("h")
    fin = inicio + pd.Timedelta(days=7)
    rango = (f"{inicio.strftime('%Y-%m-%dT%H:%M:%SZ')}--"
             f"{fin.strftime('%Y-%m-%dT%H:%M:%SZ')}:PT1H")
    puntos = "+".join(f"{c['lat']},{c['lon']}" for c in CITIES.values())
    url = f"https://api.meteomatics.com/{rango}/precip_1h:mm/{puntos}/json?model=mix"
    r = requests.get(url, auth=(usuario, clave), timeout=30)
    r.raise_for_status()
    payload = r.json()

    ciudades = list(CITIES.keys())
    records = []
    for serie in payload.get("data", [])[:1]:  # un solo parámetro: precip_1h
        for i, coord in enumerate(serie.get("coordinates", [])):
            ciudad = ciudades[i]
            for punto in coord.get("dates", []):
                records.append({
                    "Ciudad": ciudad,
                    "Latitud": CITIES[ciudad]["lat"],
                    "Longitud": CITIES[ciudad]["lon"],
                    "Fecha_Hora": pd.to_datetime(punto["date"]).tz_localize(None),
                    "Precipitacion": float(punto["value"] or 0.0),
                })
    return pd.DataFrame(records)


def cargar_datos(fuente: str, modelo: str):
    """Devuelve (df, aviso). Enruta a la fuente elegida con caché por clave."""
    if fuente == "meteomatics":
        cred = st.secrets.get("meteomatics", {}) if hasattr(st, "secrets") else {}
        usuario, clave = cred.get("username"), cred.get("password")
        if not usuario or not clave:
            return None, "sin_credenciales"
        fn = st.cache_data(ttl=3600, show_spinner="Consultando Meteomatics…")(
            _fetch_meteomatics)
        return fn(usuario, clave), None

    fn = st.cache_data(ttl=3600, show_spinner="Consultando Open-Meteo…")(
        _fetch_openmeteo)
    return fn(modelo), None


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
# 6bis. VISOR WINDY (SUDAMÉRICA, MULTI-MODELO)
# ==========================================
MODELOS_WINDY = {
    "ECMWF (europeo)": "ecmwf",
    "NOAA GFS (EE.UU.)": "gfs",
    "ICON": "icon",
}
CAPAS_WINDY = {
    "Lluvia + trueno": "rain",
    "Lluvia acumulada": "rainAccu",
    "Viento": "wind",
    "Nubosidad": "clouds",
    "Temperatura": "temp",
    "Presión": "pressure",
}


def url_windy(producto: str, overlay: str) -> str:
    return (
        "https://embed.windy.com/embed2.html"
        "?lat=-36.5&lon=-76&zoom=3&level=surface"
        f"&overlay={overlay}&product={producto}"
        "&menu=&message=true&marker=&calendar=now&pressure="
        "&type=map&location=coordinates&detail="
        "&metricWind=km%2Fh&metricTemp=%C2%B0C&metricRain=mm&radarRange=-1"
    )


# ==========================================
# 6ter. PROYECCIÓN CLIMÁTICA (OPEN-METEO CMIP6 / CORDEX)
# ==========================================
# Open-Meteo Climate API entrega CMIP6 reescalado a ~10 km (1950-2050) sin clave:
# es la vía práctica y liviana para el contexto climático que en rigor entrega
# CORDEX-SAM del CDS. Para CORDEX nativo, ver el script cordex_fetch.py.
MODELOS_CLIMA = {
    "MRI-AGCM3-2-S (Japón, 20 km)": "MRI_AGCM3_2_S",
    "EC-Earth3P-HR (Europa)": "EC_Earth3P_HR",
    "CMCC-CM2-VHR4 (Italia)": "CMCC_CM2_VHR4",
}


def _fetch_clima(lat: float, lon: float, modelo: str) -> pd.DataFrame:
    params = {
        "latitude": lat, "longitude": lon,
        "start_date": "1950-01-01", "end_date": "2050-12-31",
        "models": modelo,
        "daily": "precipitation_sum",
        "timezone": "America/Santiago",
    }
    r = requests.get("https://climate-api.open-meteo.com/v1/climate",
                     params=params, timeout=40)
    r.raise_for_status()
    d = r.json().get("daily", {})
    df = pd.DataFrame({
        "Fecha": pd.to_datetime(d.get("time", [])),
        "Precip": d.get("precipitation_sum", []),
    }).dropna()
    df["Año"] = df["Fecha"].dt.year
    return df.groupby("Año", as_index=False)["Precip"].sum().rename(
        columns={"Precip": "Precip_anual"})


def build_clima(df_anual: pd.DataFrame, ciudad: str) -> go.Figure:
    df_anual = df_anual[df_anual["Año"] <= 2050]
    media = df_anual["Precip_anual"].rolling(10, center=True, min_periods=3).mean()
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=df_anual["Año"], y=df_anual["Precip_anual"],
        marker=dict(color=df_anual["Precip_anual"], colorscale=ESCALA_ACUM,
                    line_width=0),
        name="Anual", hovertemplate="%{x}: %{y:.0f} mm<extra></extra>"))
    fig.add_trace(go.Scatter(
        x=df_anual["Año"], y=media, mode="lines",
        line=dict(color="#f472b6", width=2.5),
        name="Media móvil 10 años",
        hovertemplate="%{x}: %{y:.0f} mm<extra></extra>"))
    fig.add_vline(x=2026, line_width=1, line_dash="dot", line_color="#64748b")
    fig.update_layout(
        height=420, margin=dict(l=10, r=10, t=30, b=10),
        title=dict(text=f"Precipitación anual proyectada · {ciudad}",
                   font=dict(size=14)),
        legend=dict(orientation="h", y=1.12, x=0, font=dict(size=11)),
        xaxis=dict(gridcolor="#1e293b"),
        yaxis=dict(title="mm/año", gridcolor="#1e293b"),
        **FONT_LAYOUT)
    return fig


# ==========================================
# 7. APLICACIÓN
# ==========================================
def main():
    st.markdown(CSS, unsafe_allow_html=True)
    st.title("🌧️ Evolución del Frente de Mal Tiempo")
    st.caption("Pronóstico horario a 7 días · 17 ciudades entre Punta Arenas y La Serena")

    from streamlit.components.v1 import iframe as st_iframe

    tab_frente, tab_windy, tab_mm, tab_clima = st.tabs(
        ["🌀 Frente en tiempo real", "🛰️ Sudamérica · Windy",
         "🌍 Meteomatics", "📈 Proyección climática"])

    # =========================================================
    # PESTAÑA 1 · FRENTE EN TIEMPO REAL (Open-Meteo / Meteomatics)
    # =========================================================
    with tab_frente:
        etiquetas = list(MODELOS_OPENMETEO.keys()) + ["Meteomatics (requiere clave)"]
        col_sel, col_info = st.columns([2, 3])
        eleccion = col_sel.selectbox("Modelo / fuente de datos", etiquetas, index=0)
        col_info.caption("Todos los modelos de Open-Meteo son gratuitos y sin clave. "
                         "Cámbialos para comparar cómo cada centro pronostica el frente.")

        if eleccion.startswith("Meteomatics"):
            fuente, modelo = "meteomatics", None
        else:
            fuente, modelo = "openmeteo", MODELOS_OPENMETEO[eleccion]

        try:
            df_raw, aviso = cargar_datos(fuente, modelo)
        except Exception as e:
            st.error(f"Error al conectar con el servidor meteorológico: {e}")
            st.stop()

        if aviso == "sin_credenciales":
            st.info("**Meteomatics necesita credenciales.** Crea una cuenta gratuita "
                    "*Basic* en meteomatics.com y agrégalas en los *Secrets* de la app "
                    "(menú ⋮ → Settings → Secrets) con este formato:\n\n"
                    "```toml\n[meteomatics]\nusername = \"tu_usuario\"\n"
                    "password = \"tu_clave\"\n```\n\n"
                    "Mientras tanto, se muestra Open-Meteo Best match.")
            df_raw, _ = cargar_datos("openmeteo", "best_match")
        if df_raw is None or df_raw.empty:
            st.warning("No se pudieron cargar los datos de pronóstico.")
            st.stop()

        df, df_anim, orden_cuadros = preparar_datos(df_raw)

        tot_ciudad = df.groupby("Ciudad")["Precipitacion"].sum()
        idx_max = df["Precipitacion"].idxmax()
        k1, k2, k3 = st.columns(3)
        k1.metric("Ciudad más lluviosa (7 días)",
                  tot_ciudad.idxmax(), f"{tot_ciudad.max():.0f} mm")
        k2.metric("Santiago (7 días)", f"{tot_ciudad.get('Santiago', 0):.0f} mm")
        k3.metric("Intensidad máxima",
                  f"{df.loc[idx_max, 'Precipitacion']:.1f} mm/h",
                  f"{df.loc[idx_max, 'Ciudad']} · "
                  f"{etiqueta_es(df.loc[idx_max, 'Fecha_Hora'])}",
                  delta_color="off")

        if "zoom" not in st.session_state:
            st.session_state.zoom = 5.0
        cz1, cz2, cz3 = st.columns([1, 1, 3])
        if cz1.button("➕ Acercar", use_container_width=True):
            st.session_state.zoom = min(st.session_state.zoom + 0.7, 9.0)
        if cz2.button("➖ Alejar", use_container_width=True):
            st.session_state.zoom = max(st.session_state.zoom - 0.7, 3.0)
        cz3.caption("Vista inicial en Santiago y regiones adyacentes. "
                    "También funcionan el pinch y el scroll; arrastra para moverte.")

        st.plotly_chart(build_mapa(df_anim, orden_cuadros, st.session_state.zoom),
                        use_container_width=True,
                        config={"displayModeBar": False, "scrollZoom": True})
        st.caption("El **tamaño** de cada burbuja es el agua acumulada hasta ese "
                   "momento; su **color**, la intensidad de la lluvia en ese instante. "
                   "Presiona ▶ o arrastra la barra: la animación corre en tu navegador.")

        st.markdown("---")
        st.subheader("El frente visto en el tiempo")
        st.caption("Cada fila es una ciudad (sur abajo, norte arriba); cada columna, "
                   "una hora. La banda diagonal luminosa es el frente subiendo al norte.")
        st.plotly_chart(build_hovmoller(df), use_container_width=True,
                        config={"displayModeBar": False})

        st.markdown("---")
        st.subheader("Agua caída estimada · próximos 7 días")
        st.plotly_chart(build_acumulado(df), use_container_width=True,
                        config={"displayModeBar": False})

    # =========================================================
    # PESTAÑA 2 · WINDY (SUDAMÉRICA, MULTI-MODELO)
    # =========================================================
    with tab_windy:
        st.subheader("El frente sobre Sudamérica")
        cw1, cw2 = st.columns(2)
        cap = cw1.selectbox("Capa", list(CAPAS_WINDY.keys()), index=0)
        mod = cw2.selectbox("Modelo", list(MODELOS_WINDY.keys()), index=0)
        st.caption("Visor interactivo de Windy. Presiona el play de **su** línea de "
                   "tiempo (bajo el visor) para ver los frentes avanzando desde el "
                   "Pacífico. El modelo por defecto de Windy es ECMWF.")
        st_iframe(url_windy(MODELOS_WINDY[mod], CAPAS_WINDY[cap]),
                  height=520, scrolling=False)
        st.caption("Fuente: Windy.com.")

    # =========================================================
    # PESTAÑA 3 · METEOMATICS
    # =========================================================
    with tab_mm:
        st.subheader("Meteomatics · datos de alta resolución")
        st.caption("Meteomatics es una API comercial con muy buen desempeño en "
                   "Sudamérica, pero **requiere autenticación**. Con una cuenta "
                   "gratuita *Basic* puedes alimentar el mapa del frente con sus datos "
                   "desde el selector de la primera pestaña.")
        cred = st.secrets.get("meteomatics", {}) if hasattr(st, "secrets") else {}
        if cred.get("username") and cred.get("password"):
            st.success("Credenciales detectadas. Selecciona **Meteomatics** en la "
                       "pestaña «Frente en tiempo real» para visualizar sus datos.")
        else:
            st.info("Aún no hay credenciales configuradas. Agrégalas en los *Secrets* "
                    "de la app:\n\n```toml\n[meteomatics]\nusername = \"tu_usuario\"\n"
                    "password = \"tu_clave\"\n```")
        st.markdown(
            "- **Cuenta gratuita:** pronóstico a 10 días, resolución horaria, "
            "uso no comercial.\n"
            "- **Prueba gratuita:** 1.000 consultas / 2 semanas con catálogo completo.\n"
            "- Regístrate en meteomatics.com y usa el parámetro `precip_1h:mm`.")

    # =========================================================
    # PESTAÑA 4 · PROYECCIÓN CLIMÁTICA (CMIP6 / CORDEX)
    # =========================================================
    with tab_clima:
        st.subheader("Proyección climática · 1950–2050")
        st.caption("Esto **no** es pronóstico del frente, sino contexto climático de "
                   "largo plazo. CORDEX-SAM del Copernicus CDS entrega este tipo de "
                   "proyección regional, pero su acceso es asíncrono, con clave y en "
                   "formato NetCDF. Aquí se usa la vía equivalente y liviana de "
                   "Open-Meteo (CMIP6 reescalado a ~10 km, sin clave); el script "
                   "`cordex_fetch.py` incluido permite bajar CORDEX nativo del CDS.")
        cc1, cc2 = st.columns(2)
        ciudad_cl = cc1.selectbox("Ciudad", list(CITIES.keys()),
                                  index=list(CITIES.keys()).index("Santiago"))
        modelo_cl = cc2.selectbox("Modelo climático", list(MODELOS_CLIMA.keys()),
                                  index=0)
        c = CITIES[ciudad_cl]
        try:
            fn = st.cache_data(ttl=86400, show_spinner="Consultando proyección…")(
                _fetch_clima)
            df_cl = fn(c["lat"], c["lon"], MODELOS_CLIMA[modelo_cl])
            st.plotly_chart(build_clima(df_cl, ciudad_cl),
                            use_container_width=True,
                            config={"displayModeBar": False})
            st.caption("La línea punteada marca 2026. La media móvil de 10 años "
                       "resalta la tendencia sobre la variabilidad interanual. "
                       "Fuente: Open-Meteo Climate API (CMIP6).")
        except Exception as e:
            st.error(f"No se pudo cargar la proyección climática: {e}")

    st.markdown(
        """
        <div class="custom-footer">
            Sitio desarrollado por <strong>Carlos Mendoza - CMENTO</strong> - para un grupo privado.<br>
            Todos los derechos reservados &copy; 2026. Datos: Open-Meteo, Windy, Meteomatics, Copernicus C3S.
        </div>
        """,
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
