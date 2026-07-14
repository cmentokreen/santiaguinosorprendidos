"""
cordex_fetch.py — Descarga CORDEX South America del Copernicus CDS y lo
resume a un CSV liviano que la app de Streamlit puede leer.

POR QUÉ ESTE SCRIPT ES SEPARADO Y NO VIVE DENTRO DE app.py
-----------------------------------------------------------
CORDEX-SAM NO es un pronóstico del tiempo: son proyecciones climáticas
regionales (escenarios de décadas, no el frente de los próximos días). Además,
el acceso del CDS es fundamentalmente distinto al de Windy u Open-Meteo:

  1. Requiere una cuenta gratuita y un Personal Access Token del CDS.
  2. Las solicitudes son ASÍNCRONAS: se encolan y pueden tardar minutos u horas.
  3. Los datos llegan en NetCDF/GRIB y hay que procesarlos (xarray).
  4. Hay que aceptar la licencia del dataset una vez, de forma manual, en la web.

Por eso no se puede incrustar como un iframe. El flujo correcto es:
correr ESTE script offline (una vez, o por cron), dejar el CSV resultante en el
repo, y que la app lo lea. La app ya trae, para uso interactivo, la vía liviana
equivalente vía Open-Meteo Climate API (CMIP6 reescalado), que no requiere clave.

USO
---
1) pip install "cdsapi>=0.7" xarray netCDF4 pandas
2) Crea ~/.cdsapirc con tu token (https://cds.climate.copernicus.eu/how-to-api):
       url: https://cds.climate.copernicus.eu/api
       key: <TU-PERSONAL-ACCESS-TOKEN>
3) Acepta la licencia del dataset CORDEX en la web del CDS (una vez).
4) python cordex_fetch.py

Genera 'cordex_sam_precip_anual.csv' con columnas: Año, Precip_anual_mm.
Ajusta el recorte 'area', el modelo y el experimento según tu necesidad.
"""

import cdsapi
import xarray as xr
import pandas as pd

# Recorte aproximado en torno a Chile central (N, O, S, E)
AREA = [-29.0, -74.0, -38.0, -69.0]
SALIDA_NC = "cordex_sam_precip.nc"
SALIDA_CSV = "cordex_sam_precip_anual.csv"


def descargar():
    """Descarga precipitación diaria de CORDEX South America desde el CDS.

    El nombre corto del dataset y las claves pueden variar según la versión
    del catálogo; verifícalos con el botón 'Show API request' del dataset
    en la web del CDS antes de correr en producción.
    """
    c = cdsapi.Client()
    c.retrieve(
        "projections-cordex-domains-single-levels",
        {
            "domain": "south_america",
            "experiment": "rcp_8_5",
            "horizontal_resolution": "0_44_degree_x_0_44_degree",
            "temporal_resolution": "daily_mean",
            "variable": "mean_precipitation_flux",
            "gcm_model": "mpi_m_mpi_esm_lr",
            "rcm_model": "ictp_regcm4_7",
            "ensemble_member": "r1i1p1",
            "start_year": ["2021"],
            "end_year": ["2050"],
            "area": AREA,
            "format": "zip",
        },
        SALIDA_NC,
    )


def resumir():
    """Convierte el NetCDF a un CSV anual promediado sobre el recorte."""
    ds = xr.open_dataset(SALIDA_NC)
    # 'pr' suele venir como flujo (kg m-2 s-1). A mm/día: * 86400.
    pr = ds["pr"] * 86400.0
    serie = pr.mean(dim=[d for d in pr.dims if d != "time"])
    df = serie.to_dataframe(name="precip_mm_dia").reset_index()
    df["Año"] = pd.to_datetime(df["time"]).dt.year
    anual = (df.groupby("Año")["precip_mm_dia"].sum()
               .rename("Precip_anual_mm").reset_index())
    anual.to_csv(SALIDA_CSV, index=False)
    print(f"Escrito {SALIDA_CSV} con {len(anual)} años.")


if __name__ == "__main__":
    descargar()
    resumir()
