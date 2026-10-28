"""Correspondencia de comunas entre las codificaciones de las entregas de microdatos y la DPA2018.

Escribe metadatos/territorio/comunas.csv: una fila por comuna de la DPA2018 (346) con su
provincia, región (DPA2018 y DPA1974) y el código con que aparece en cada entrega:
  - comuna_15r: DPA de 15 regiones de 2010 (columna COMUNA_15R de 2017).
  - comuna_1992: codificación "Origen 3" de la entrega de 1992 (DPA de 15 regiones de 2007,
    anterior a la provincia de Marga Marga). Es la de 2010 salvo cuatro comunas que pasaron
    de las provincias de Valparaíso y Quillota a Marga Marga.
  - 2002, 2017 y 2024 vienen en DPA2018.
La correspondencia se comprueba por nombre contra las tablas COMUNAS_1992 y COMUNAS_2002 de
las entregas.

Requiere la capa 1 de 1992 y 2017 (pipelines/estandarizar_microdatos.py 1992 2017).

Uso:
  python herramientas/correspondencia_comunas.py
"""

from __future__ import annotations

import csv
import re
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipelines.comun import RAIZ, conectar, escribir_csv, leer_config, mensaje, ruta_sql  # noqa: E402

SALIDA = RAIZ / "metadatos" / "territorio" / "comunas.csv"

# Comunas de la provincia de Marga Marga (creada en 2010): código de 1992 -> código de 2010.
MARGA_MARGA = {5106: 5801,  # Quilpué (provincia de Valparaíso)
               5108: 5804,  # Villa Alemana (provincia de Valparaíso)
               5505: 5802,  # Limache (provincia de Quillota)
               5507: 5803}  # Olmué (provincia de Quillota)

# Nombres de COMUNAS_1992 que difieren de COMUNAS_2002 solo en la grafía (comuna DPA2018 -> nombre 1992).
VARIANTES_1992 = {6105: "DOÑIGUE", 9103: "CIUNCO", 11101: "COIHAIQUE", 11201: "AISEN", 12201: "CABO DE HORNO"}

# Regiones creadas después de 1974 -> región de la que se separaron.
REGION_DPA1974 = {15: 1, 14: 10, 16: 8}


def leer_nombres(ruta: Path, col_codigo: str, col_nombre: str) -> dict[int, str]:
    """Tablas de nombres de las entregas: CSV de R con codificación mezclada (latin-1 y UTF-8)."""
    lineas = []
    for crudo in ruta.read_bytes().splitlines():
        try:
            lineas.append(crudo.decode("utf-8"))
        except UnicodeDecodeError:
            lineas.append(crudo.decode("latin-1"))
    return {int(f[col_codigo]): f[col_nombre].strip() for f in csv.DictReader(lineas)}


def normalizar(nombre: str) -> str:
    ascii_ = unicodedata.normalize("NFKD", nombre).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Z]", "", ascii_.upper())


def main() -> None:
    config = leer_config()
    estandarizado = Path(config["estandarizado"])
    originales = Path(config["datos_originales"])
    con = conectar(config)

    viv2017 = estandarizado / "2017" / "viviendas.parquet"
    if not viv2017.exists():
        sys.exit("Falta la capa 1 de 2017: python pipelines/estandarizar_microdatos.py 2017")
    puente = dict(con.execute(f"SELECT DISTINCT comuna, comuna_15r FROM read_parquet({ruta_sql(viv2017)})").fetchall())
    if len(set(puente.values())) != len(puente):
        sys.exit("COMUNA_15R no es 1 a 1 con COMUNA.")

    nombres2002 = leer_nombres(originales / "cpv2002" / "COMUNAS_2002.csv", "COMUNA", "NOMBRE_COMUNA")
    nombres1992 = leer_nombres(originales / "cpv1992" / "COMUNAS_1992.csv", "Codigo", "Nombre")
    desde_2010 = {v: k for k, v in MARGA_MARGA.items()}

    filas = []
    for comuna, c15r in sorted(puente.items()):
        region = comuna // 1000
        filas.append({
            "comuna": comuna,
            "nombre": nombres2002.get(comuna),       # tal como en COMUNAS_2002
            "provincia": comuna // 100,
            "region": region,
            "region_dpa1974": REGION_DPA1974.get(region, region),
            "comuna_15r": c15r,
            "comuna_1992": desde_2010.get(c15r, c15r),  # código de 2010, salvo Marga Marga
        })

    # Controles.
    sin_nombre = [f["comuna"] for f in filas if f["nombre"] is None]
    if sin_nombre:
        sys.exit(f"Comunas de 2017 sin nombre en COMUNAS_2002: {sin_nombre}")
    if {f["comuna_1992"] for f in filas} != set(nombres1992):
        sys.exit("Los códigos de 1992 no coinciden con COMUNAS_1992.")
    distintos, variantes = [], 0
    for f in filas:
        nombre_1992 = nombres1992[f["comuna_1992"]]
        if VARIANTES_1992.get(f["comuna"]) == nombre_1992:
            variantes += 1
        elif normalizar(f["nombre"]) != normalizar(nombre_1992):
            distintos.append((f["comuna"], f["nombre"], f["comuna_1992"], nombre_1992))
    if distintos:
        sys.exit("Nombres distintos entre 1992 y la DPA2018:\n" + "\n".join(map(str, distintos)))
    if variantes != len(VARIANTES_1992):
        sys.exit("Alguna variante de nombre declarada ya no aparece.")
    portafolios = estandarizado / "1992" / "portafolios.parquet"
    usadas = {r[0] for r in con.execute(f"SELECT DISTINCT comuna FROM read_parquet({ruta_sql(portafolios)})").fetchall()}
    if not usadas <= {f["comuna_1992"] for f in filas}:
        sys.exit("Comunas de los microdatos de 1992 sin correspondencia.")

    escribir_csv(SALIDA, filas)
    mensaje(f"{len(filas)} comunas; {sum(f['comuna_1992'] != f['comuna'] for f in filas)} con código distinto "
            f"en 1992 y {sum(f['comuna_15r'] != f['comuna'] for f in filas)} en la DPA de 15 regiones")


if __name__ == "__main__":
    main()
