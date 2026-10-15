"""Tabulados digitalizados de las publicaciones censales (formato largo) y sus controles aritméticos.

Cada cuadro transcrito vive en digitalizacion/<censo>/ como un par de archivos:
  - <fuente>_<cuadro>.csv: el cuadro tal como está impreso (filas y columnas del original;
    "-" = guion impreso, celda vacía = no impreso).
  - <fuente>_<cuadro>.yaml: procedencia (fuente, cuadro, páginas), mapeo de filas y columnas a
    las dimensiones del esquema, notas del cuadro y de celdas, y controles a aplicar.

Escribe productos/tabulados/tabulados_publicaciones.csv con el esquema de
metadatos/esquema_tabulados.yaml y validacion/controles_digitalizacion.csv con cada control
que no cuadra. Sale con código 1 si un control falla en una celda que no está anotada como
"inconsistente" en el YAML (es decir, un posible error de transcripción).

Uso:
  python pipelines/tabulados_publicaciones.py
"""

from __future__ import annotations

import csv
import json
import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

import yaml

sys.stdout.reconfigure(encoding="utf-8")

RAIZ = Path(__file__).resolve().parents[1]
ENTRADA = RAIZ / "digitalizacion"
SALIDA = RAIZ / "productos" / "tabulados" / "tabulados_publicaciones.csv"
CONTROLES = RAIZ / "validacion" / "controles_digitalizacion.csv"

ESQUEMA = [c["nombre"] for c in
           yaml.safe_load((RAIZ / "metadatos" / "esquema_tabulados.yaml").read_text(encoding="utf-8"))["campos"]]
DIMENSIONES = {"area", "sexo", "edad_min", "edad_max", "edad_estado"}


def codigo(nombre: str) -> str:
    """Código asignado por el proyecto cuando la fuente no trae uno: nombre sin tildes, en minúsculas."""
    s = unicodedata.normalize("NFKD", nombre).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")


def valor(texto: str) -> tuple[int | None, str]:
    texto = texto.strip()
    if texto == "-":
        return None, "guion"
    if texto == "":
        return None, "no_publicado"
    return int(texto.replace(".", "").replace(" ", "")), "ok"


def procesar(meta_ruta: Path) -> tuple[list[dict], list[dict]]:
    meta = yaml.safe_load(meta_ruta.read_text(encoding="utf-8"))
    with meta_ruta.with_suffix(".csv").open(encoding="utf-8") as f:
        filas = list(csv.DictReader(f))

    terr = meta["territorio"]
    niveles = terr["nivel"]
    notas = {(n["territorio"], n["area"], n["columna"]): n for n in meta.get("notas_celdas", [])}
    paginas = meta["paginas"]
    inicio_pagina = {p["desde"]: p for p in paginas if "desde" in p}

    salida = []
    pagina = paginas[0]
    for fila in filas:
        nombre = fila[terr["columna"]]
        pagina = inicio_pagina.get(nombre, pagina)
        dims_fila = {}
        for dim, regla in meta.get("filas", {}).items():
            dims_fila[dim] = regla["valores"][fila[regla["columna"]]]
        for col, dims_col in meta["columnas"].items():
            v, estado = valor(fila[col])
            nota = notas.get((nombre, fila.get("area"), col), {})
            dims = {**meta.get("fijas", {}), **dims_fila, **dims_col}
            censo = dims.pop("censo")
            otras = {k: dims.pop(k) for k in list(dims) if k not in DIMENSIONES}
            salida.append({
                "censo": censo,
                "indicador": meta["indicador"],
                "unidad": meta["unidad"],
                "territorio_nivel": niveles.get(nombre, niveles.get("_otro")),
                "territorio_cod_orig": codigo(nombre),
                "territorio_nombre_orig": nombre,
                "dpa_version": terr["dpa_version"].format(censo=censo),
                "territorio_cod_dpa2024": "",
                "area": dims.get("area", "_T"),
                "sexo": dims.get("sexo", "_T"),
                "edad_min": dims.get("edad_min", ""),
                "edad_max": dims.get("edad_max", ""),
                "edad_estado": dims.get("edad_estado", ""),
                "dimensiones": json.dumps(otras, ensure_ascii=False) if otras else "",
                "valor": "" if v is None else v,
                "estado_valor": nota.get("estado_valor", estado),
                "fuente_id": meta["fuente_id"],
                "cuadro": meta["cuadro"],
                "pagina_impresa": pagina.get("impresa", ""),
                "pagina_pdf": pagina.get("pdf", ""),
                "metodo": meta["metodo"],
                "verificacion": meta["verificacion"],
                "nota": " ".join(nota.get("nota", "").split()),
            })
    return salida, controlar(meta, salida)


def controlar(meta: dict, filas: list[dict]) -> list[dict]:
    """Aplica los controles del YAML; devuelve las diferencias encontradas."""
    fallas = []

    def clave(f, sin):
        return tuple((k, f[k]) for k in ("censo", "territorio_cod_orig", "area", "sexo", "edad_min", "dimensiones") if k not in sin)

    for c in meta.get("controles", []):
        grupos: dict = defaultdict(lambda: {"total": None, "partes": 0, "celdas": []})
        for f in filas:
            if c["tipo"] == "suma_dimension":
                d = c["dimension"]
                k = clave(f, {d})
                es_total, es_parte = f[d] == c["total"], f[d] in c["partes"]
            else:  # suma_territorio
                k = clave(f, {"territorio_cod_orig"})
                es_total, es_parte = f["territorio_nivel"] == c["total"], f["territorio_nivel"] == c["partes"]
            g = grupos[k]
            if es_total:
                g["total"] = f
            elif es_parte:
                g["partes"] += f["valor"] or 0
                g["celdas"].append(f)
        for k, g in grupos.items():
            t = g["total"]
            if t is None or t["valor"] == "":
                continue
            if g["partes"] != t["valor"]:
                celdas = [t] + g["celdas"]
                fallas.append({
                    "fuente_id": meta["fuente_id"], "cuadro": meta["cuadro"], "control": c["tipo"],
                    "censo": t["censo"], "territorio": t["territorio_nombre_orig"] if c["tipo"] == "suma_dimension" else "(partes)",
                    "area": t["area"], "sexo": t["sexo"],
                    "total": t["valor"], "suma_partes": g["partes"], "diferencia": g["partes"] - t["valor"],
                    "explicada": any(x["estado_valor"] == "inconsistente" for x in celdas),
                })
    return fallas


def main() -> None:
    filas, fallas = [], []
    for meta in sorted(ENTRADA.rglob("*.yaml")):
        f, c = procesar(meta)
        print(f"{meta.relative_to(RAIZ).as_posix()}: {len(f)} cifras, {len(c)} controles con diferencias")
        filas += f
        fallas += c

    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    with SALIDA.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, ESQUEMA, lineterminator="\n")
        w.writeheader()
        w.writerows(filas)
    campos = ["fuente_id", "cuadro", "control", "censo", "territorio", "area", "sexo", "total", "suma_partes", "diferencia", "explicada"]
    with CONTROLES.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, campos, lineterminator="\n")
        w.writeheader()
        w.writerows(fallas)

    sin_explicar = [f for f in fallas if not f["explicada"]]
    for f in fallas:
        marca = "anotada" if f["explicada"] else "REVISAR"
        print(f"  [{marca}] {f['fuente_id']} c{f['cuadro']} {f['control']} {f['censo']} {f['territorio']} "
              f"{f['area']}: {f['suma_partes']} vs {f['total']} ({f['diferencia']:+})")
    print(f"{len(filas)} cifras -> {SALIDA.relative_to(RAIZ).as_posix()}")
    sys.exit(1 if sin_explicar else 0)


if __name__ == "__main__":
    main()
