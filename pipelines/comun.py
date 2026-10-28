"""Utilidades comunes de los pipelines de microdatos (DuckDB).

Uso desde otros scripts del repositorio:
  sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
  from pipelines.comun import RAIZ, conectar, leer_config, ...
"""

from __future__ import annotations

import csv
import re
import subprocess
import sys
import unicodedata
from datetime import datetime
from pathlib import Path

import duckdb
import yaml

RAIZ = Path(__file__).resolve().parents[1]


def leer_config() -> dict:
    ruta = RAIZ / "config.yaml"
    if not ruta.exists():
        sys.exit("Falta config.yaml (copiar config.ejemplo.yaml y ajustar rutas).")
    return yaml.safe_load(ruta.read_text(encoding="utf-8"))


def leer_yaml(ruta: Path) -> dict:
    return yaml.safe_load(ruta.read_text(encoding="utf-8"))


def conectar(config: dict, archivo: Path | None = None) -> duckdb.DuckDBPyConnection:
    """Conexión a DuckDB. Con `archivo`, la base queda en disco (tablas intermedias grandes)."""
    temporal = Path(config["temporal"])
    temporal.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(archivo) if archivo else ":memory:")
    con.execute(f"SET memory_limit = '{config.get('memoria_duckdb', '4GB')}'")
    con.execute(f"SET temp_directory = {ruta_sql(temporal / 'desborde')}")
    con.execute("SET preserve_insertion_order = true")
    return con


# --- SQL ------------------------------------------------------------------------------------

def literal(x) -> str:
    return "'" + str(x).replace("'", "''") + "'"


def ident(x: str) -> str:
    return '"' + x.replace('"', '""') + '"'


def ruta_sql(ruta) -> str:
    return literal(Path(ruta).as_posix())


def uno(con: duckdb.DuckDBPyConnection, sql: str):
    """Primer valor de la primera fila."""
    return con.execute(sql).fetchone()[0]


def escribir_parquet(con: duckdb.DuckDBPyConnection, select_sql: str, destino: Path) -> None:
    """Escribe el resultado de una consulta como Parquet con zstd (vía archivo temporal)."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    temporal = destino.with_suffix(".parquet.tmp")
    con.execute(f"COPY ({select_sql}) TO {ruta_sql(temporal)} (FORMAT PARQUET, COMPRESSION ZSTD)")
    temporal.replace(destino)


# --- Nombres y archivos ---------------------------------------------------------------------

def nombre_estandar(nombre: str) -> str:
    """Minúsculas, ASCII y guion bajo: Agua_cañeria -> agua_caneria, P18 -> p18."""
    ascii_ = unicodedata.normalize("NFKD", nombre).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "_", ascii_.lower()).strip("_")


def leer_csv(ruta: Path) -> list[dict]:
    with ruta.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def escribir_csv(ruta: Path, filas: list[dict], campos: list[str] | None = None) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    campos = campos or list(filas[0])
    with ruta.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=campos)
        w.writeheader()
        w.writerows(filas)


def actualizar_csv(ruta: Path, nuevas: list[dict], censos: set[str]) -> None:
    """Reemplaza en un CSV acumulado las filas de los censos indicados."""
    previas = [f for f in leer_csv(ruta) if f["censo"] not in censos] if ruta.exists() else []
    filas = sorted(previas + [{k: "" if v is None else str(v) for k, v in f.items()} for f in nuevas],
                   key=lambda f: int(f["censo"]))
    escribir_csv(ruta, filas, list(nuevas[0]) if nuevas else None)


def commit_actual() -> str:
    try:
        return subprocess.run(["git", "-C", str(RAIZ), "rev-parse", "--short", "HEAD"],
                              capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return ""


def mensaje(texto: str) -> None:
    print(f"{datetime.now():%H:%M:%S} {texto}", flush=True)
