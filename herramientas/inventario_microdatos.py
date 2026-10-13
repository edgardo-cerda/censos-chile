"""Inventario de los microdatos censales originales.

Para cada tabla declarada en config.yaml:
  1. calcula el SHA-256 del archivo original (para registrar la procedencia),
  2. la convierte a Parquet en la carpeta de caché (todas las columnas como texto,
     para no perder códigos como "01" ni valores especiales),
  3. genera un resumen por variable y tablas de frecuencia para las variables con
     pocas categorías.

Salidas (en metadatos/inventario/):
  <censo>_<tabla>_variables.csv     una fila por variable
  <censo>_<tabla>_frecuencias.csv   valor y conteo por variable (<= MAX_CATEGORIAS)
  archivos.csv                      archivo, tamaño, sha256, filas, columnas

Uso:
  python herramientas/inventario_microdatos.py                # todas las tablas
  python herramientas/inventario_microdatos.py 1992 2002      # solo esos censos
"""

from __future__ import annotations

import csv
import hashlib
import sys
from pathlib import Path

import duckdb
import pyarrow as pa
import pyarrow.csv as pacsv
import pyarrow.parquet as pq
import yaml

RAIZ = Path(__file__).resolve().parents[1]
SALIDA = RAIZ / "metadatos" / "inventario"
MAX_CATEGORIAS = 500


def leer_config() -> dict:
    ruta = RAIZ / "config.yaml"
    if not ruta.exists():
        sys.exit("Falta config.yaml (copiar config.ejemplo.yaml y ajustar rutas).")
    return yaml.safe_load(ruta.read_text(encoding="utf-8"))


def sha256(ruta: Path) -> str:
    h = hashlib.sha256()
    with ruta.open("rb") as f:
        for bloque in iter(lambda: f.read(1 << 24), b""):
            h.update(bloque)
    return h.hexdigest()


def detectar_csv(ruta: Path) -> tuple[str, str, list[str]]:
    """Devuelve (codificación, separador, columnas) mirando la primera línea."""
    with ruta.open("rb") as f:
        cabecera = f.readline()
    try:
        cabecera.decode("utf-8")
        codificacion = "utf8"
    except UnicodeDecodeError:
        codificacion = "latin1"
    texto = cabecera.decode(codificacion).lstrip("﻿").rstrip("\r\n")
    separador = ";" if texto.count(";") > texto.count(",") else ","
    columnas = next(csv.reader([texto], delimiter=separador))
    return codificacion, separador, columnas


def csv_a_parquet(origen: Path, destino: Path) -> None:
    codificacion, separador, columnas = detectar_csv(origen)
    # Las exportaciones desde R traen una primera columna sin nombre con el número de fila.
    columnas = [c if c else "_fila" for c in columnas]
    lector = pacsv.open_csv(
        origen,
        read_options=pacsv.ReadOptions(encoding=codificacion, block_size=1 << 26,
                                       column_names=columnas, skip_rows=1),
        parse_options=pacsv.ParseOptions(delimiter=separador),
        # Todo como texto: el inventario debe mostrar los códigos tal como vienen.
        convert_options=pacsv.ConvertOptions(
            column_types={c: pa.string() for c in columnas},
            strings_can_be_null=False, null_values=[],
        ),
    )
    esquema = pa.schema([pa.field(c.name, pa.string()) for c in lector.schema])
    with pq.ParquetWriter(destino, esquema, compression="zstd") as escritor:
        for lote in lector:
            escritor.write_batch(lote.cast(esquema))


def parquet_a_texto(origen: Path, destino: Path) -> None:
    tabla = pq.read_table(origen)
    esquema = pa.schema([pa.field(c, pa.string()) for c in tabla.column_names])
    pq.write_table(tabla.cast(esquema), destino, compression="zstd")


def perfilar(con: duckdb.DuckDBPyConnection, parquet: Path, censo: str, tabla: str) -> tuple[int, int]:
    rel = f"read_parquet('{parquet.as_posix()}')"
    columnas = [r[0] for r in con.execute(f"DESCRIBE SELECT * FROM {rel}").fetchall()]
    n_filas = con.execute(f"SELECT count(*) FROM {rel}").fetchone()[0]

    resumen, frecuencias = [], []
    for orden, col in enumerate(columnas, start=1):
        q = f'"{col}"'
        n_dist, n_vacios, n_na, n_num, vmin, vmax = con.execute(f"""
            SELECT count(DISTINCT {q}),
                   count(*) FILTER (WHERE {q} IS NULL OR trim({q}) = ''),
                   count(*) FILTER (WHERE {q} IN ('NA', 'NaN', 'NULL')),
                   count(TRY_CAST({q} AS DOUBLE)),
                   min(TRY_CAST({q} AS DOUBLE)),
                   max(TRY_CAST({q} AS DOUBLE))
            FROM {rel}""").fetchone()
        n_validos = n_filas - n_vacios - n_na
        resumen.append({
            "censo": censo, "tabla": tabla, "orden": orden, "variable": col,
            "n_filas": n_filas, "n_distintos": n_dist, "n_vacios": n_vacios, "n_na": n_na,
            "tipo_observado": "numerico" if n_validos and n_num == n_validos else "texto",
            "min": vmin, "max": vmax,
            "con_frecuencias": n_dist <= MAX_CATEGORIAS,
        })
        if n_dist <= MAX_CATEGORIAS:
            for valor, n in con.execute(f"""
                SELECT {q}, count(*) FROM {rel} GROUP BY 1
                ORDER BY TRY_CAST({q} AS DOUBLE) NULLS LAST, 1""").fetchall():
                frecuencias.append({"censo": censo, "tabla": tabla, "variable": col,
                                    "valor": valor, "n": n})

    escribir(SALIDA / f"{censo}_{tabla}_variables.csv", resumen)
    escribir(SALIDA / f"{censo}_{tabla}_frecuencias.csv", frecuencias)
    return n_filas, len(columnas)


def escribir(ruta: Path, filas: list[dict]) -> None:
    if not filas:
        return
    with ruta.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(filas[0]))
        w.writeheader()
        w.writerows(filas)


def main() -> None:
    config = leer_config()
    origen_base = Path(config["datos_originales"])
    cache = Path(config["cache"])
    cache.mkdir(parents=True, exist_ok=True)
    SALIDA.mkdir(parents=True, exist_ok=True)
    filtro = set(sys.argv[1:])

    con = duckdb.connect()
    con.execute(f"SET memory_limit = '{config.get('memoria_duckdb', '4GB')}'")
    con.execute(f"SET temp_directory = '{(cache / 'tmp').as_posix()}'")

    registro_ruta = SALIDA / "archivos.csv"
    registro = {}
    if registro_ruta.exists():
        with registro_ruta.open(encoding="utf-8") as f:
            registro = {(r["censo"], r["tabla"]): r for r in csv.DictReader(f)}

    for censo, tablas in config["microdatos"].items():
        censo = str(censo)
        if filtro and censo not in filtro:
            continue
        for tabla, archivo in tablas.items():
            ruta = origen_base / archivo
            print(f"[{censo}] {tabla}: {ruta.name}", flush=True)
            destino = cache / f"{censo}_{tabla}.parquet"
            if ruta.suffix.lower() == ".csv":
                csv_a_parquet(ruta, destino)
            else:
                parquet_a_texto(ruta, destino)
            n_filas, n_cols = perfilar(con, destino, censo, tabla)
            registro[(censo, tabla)] = {
                "censo": censo, "tabla": tabla, "archivo": archivo,
                "bytes": ruta.stat().st_size, "sha256": sha256(ruta),
                "filas": n_filas, "columnas": n_cols,
            }
            print(f"    {n_filas:,} filas, {n_cols} columnas", flush=True)

    escribir(registro_ruta, sorted(registro.values(), key=lambda r: (r["censo"], r["tabla"])))


if __name__ == "__main__":
    main()
