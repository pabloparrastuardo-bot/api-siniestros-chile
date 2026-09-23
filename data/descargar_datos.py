#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
descargar_datos.py — Descarga la base de siniestros de tránsito de CONASET
desde el servicio ArcGIS REST y la deja en un CSV plano.

Por qué existe este script y no un link directo:
el endpoint /query de ArcGIS devuelve como máximo `maxRecordCount` filas por
llamada (2000 en este servicio). Un link con f=csv y sin paginación o bien
falla (Bad Request) o bien te entrega solo las primeras 2000 filas sin avisar.
Este script pagina con resultOffset/resultRecordCount usando f=json, que es la
combinación que el servicio acepta de forma estable, y arma el CSV completo.

Uso básico:
    pip install requests pandas
    python descargar_datos.py

Opciones:
    python descargar_datos.py --desde-anio 2023      # filtra por año (menos peso)
    python descargar_datos.py --salida data/siniestros.csv
    python descargar_datos.py --paso 1000            # si la red va lenta
    python descargar_datos.py --solo-contar          # cuántas filas hay, sin bajar

Salida: un CSV con las columnas crudas del servicio (AÑO, FECHA, REGION,
COMUNA, ZONA, TIPO_SINIE, CAUSA_NUEV, FALLECIDOS, GRAVES, ...). La limpieza y
la creación del target se hacen después, en train.py, no aquí: así queda
trazable qué vino del origen y qué agregamos nosotros.
"""

import argparse
import csv
import os
import sys
import time

try:
    import requests
except ImportError:
    sys.exit("Falta la librería requests.  Instálala con:  pip install requests")

# ---------------------------------------------------------------------------
# Configuración del servicio
# ---------------------------------------------------------------------------
URL = (
    "https://services3.arcgis.com/vaJl1B5HEzZj7154/arcgis/rest/services/"
    "Base_SINIESTROS_2020_2025/FeatureServer/0/query"
)

# Campo estable para ordenar la paginación. Sin orderByFields el servicio NO
# garantiza el mismo orden entre llamadas y podrías repetir o perder filas.
ORDEN = "FID"

TIMEOUT = 120          # segundos por request
REINTENTOS = 4         # reintentos ante error de red / 500 del servidor


def _get(params, intentos=REINTENTOS):
    """GET con reintentos y backoff. Devuelve el JSON ya parseado."""
    ultimo_error = None
    for i in range(intentos):
        try:
            r = requests.get(URL, params=params, timeout=TIMEOUT)
            r.raise_for_status()
            data = r.json()
            # ArcGIS responde 200 con un objeto {"error": {...}} cuando algo
            # está mal en los parámetros. Hay que revisarlo a mano.
            if isinstance(data, dict) and "error" in data:
                raise RuntimeError(f"ArcGIS devolvió error: {data['error']}")
            return data
        except Exception as e:                      # noqa: BLE001
            ultimo_error = e
            espera = 2 ** i
            print(f"   ...reintento {i + 1}/{intentos} en {espera}s ({e})")
            time.sleep(espera)
    raise RuntimeError(f"No se pudo consultar el servicio: {ultimo_error}")


def contar(where):
    data = _get({"where": where, "returnCountOnly": "true", "f": "json"})
    return int(data.get("count", 0))


def descargar(where, paso):
    """Pagina el servicio y devuelve (lista_de_dicts, lista_de_columnas)."""
    total = contar(where)
    if total == 0:
        raise SystemExit("El servicio devolvió 0 filas para ese filtro. "
                         "Revisa el valor de --desde-anio.")
    print(f"Filas a descargar: {total:,}".replace(",", "."))

    filas, columnas, offset = [], None, 0
    while offset < total:
        data = _get({
            "where": where,
            "outFields": "*",
            "returnGeometry": "false",
            "orderByFields": ORDEN,
            "resultOffset": offset,
            "resultRecordCount": paso,
            "f": "json",
        })

        feats = data.get("features", [])
        if not feats:
            print("   El servicio dejó de entregar filas antes de lo esperado; "
                  "se guarda lo descargado hasta aquí.")
            break

        if columnas is None:
            # Orden de columnas según lo declara el propio servicio.
            columnas = [c["name"] for c in data.get("fields", [])]

        filas.extend(f["attributes"] for f in feats)
        offset += len(feats)
        pct = 100 * offset / total
        print(f"   {offset:>7,} / {total:,}  ({pct:5.1f} %)".replace(",", "."))

    if columnas is None:
        columnas = sorted({k for f in filas for k in f})
    return filas, columnas


def escribir_csv(filas, columnas, salida):
    carpeta = os.path.dirname(os.path.abspath(salida))
    os.makedirs(carpeta, exist_ok=True)
    # utf-8-sig para que Excel en Windows no destroce las tildes de REGION/COMUNA.
    with open(salida, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=columnas, extrasaction="ignore")
        w.writeheader()
        w.writerows(filas)
    mb = os.path.getsize(salida) / 1024 / 1024
    print(f"\nListo: {salida}  ({len(filas):,} filas, {mb:.1f} MB)".replace(",", "."))


def main():
    ap = argparse.ArgumentParser(description="Descarga la base CONASET de siniestros.")
    ap.add_argument("--desde-anio", type=int, default=None,
                    help="Solo siniestros de ese año en adelante (ej. 2023).")
    ap.add_argument("--salida", default="data/siniestros.csv",
                    help="Ruta del CSV de salida (por defecto data/siniestros.csv).")
    ap.add_argument("--paso", type=int, default=2000,
                    help="Filas por llamada (máximo del servicio: 2000).")
    ap.add_argument("--solo-contar", action="store_true",
                    help="Solo informa cuántas filas hay y termina.")
    args = ap.parse_args()

    # El campo del año se llama "AÑO" (con eñe) en este servicio. requests
    # codifica bien el carácter, pero lo dejamos entre comillas dobles porque
    # ArcGIS exige comillas para identificadores no ASCII.
    if args.desde_anio:
        where = f'"AÑO" >= {args.desde_anio}'
    else:
        where = "1=1"

    print(f"Servicio : {URL}")
    print(f"Filtro   : {where}")

    if args.solo_contar:
        print(f"Filas disponibles: {contar(where):,}".replace(",", "."))
        return

    filas, columnas = descargar(where, min(args.paso, 2000))
    escribir_csv(filas, columnas, args.salida)

    print("\nColumnas obtenidas:")
    print("  " + ", ".join(columnas))
    print("\nSiguiente paso: súbeme ese CSV al chat.")


if __name__ == "__main__":
    main()
