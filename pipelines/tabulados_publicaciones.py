"""Tabulados digitalizados de las publicaciones censales (formato largo) y sus controles aritméticos.

Cada cuadro transcrito vive en digitalizacion/<censo>/ como un par de archivos:
  - <fuente>_<cuadro>.csv: el cuadro tal como está impreso (filas y columnas del original;
    "-" = guion impreso, ".." = dos puntos impresos (sin dato), celda vacía = no impreso).
  - <fuente>_<cuadro>.yaml: procedencia (fuente, cuadro, páginas), mapeo de filas y columnas a
    las dimensiones del esquema, notas del cuadro y de celdas, y controles a aplicar.

Escribe productos/tabulados/tabulados_publicaciones.csv con el esquema de
metadatos/esquema_tabulados.yaml y validacion/controles_digitalizacion.csv con cada control
que no cuadra, y validacion/contraste_fuentes.csv con las cifras que aparecen en más de un cuadro
(mismo censo, división territorial, unidad y dimensiones) y difieren entre ellos. Sale con código 1 si un control falla en una celda que no está anotada como
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
CONTRASTE = RAIZ / "validacion" / "contraste_fuentes.csv"

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
    if texto in ("", ".."):
        return None, "no_publicado"
    return int(texto.replace(".", "").replace(" ", "")), "ok"


def ubicar(filas: list[dict], terr: dict) -> list[tuple[str, str, str]]:
    """(nivel, código del padre, código) de cada fila.

    Sin columna de nivel, el nivel sale del diccionario territorio.nivel. Con columna de nivel
    (cuadros jerárquicos), las filas de cada unidad siguen a su unidad superior; con
    totales_al_final la unidad superior viene después de sus unidades (se recorre al revés).
    El código es la ruta de nombres normalizados (p. ej. tarapaca/arica/arica).
    """
    col_nivel = terr.get("columna_nivel")
    if not col_nivel:
        niveles = terr.get("nivel", {})
        return [(niveles.get(f[terr["columna"]], niveles.get("_otro")), "", codigo(f[terr["columna"]])) for f in filas]
    orden = terr.get("niveles", [])
    al_reves = terr.get("totales_al_final", False)
    ancestros: dict[str, str] = {}
    resultado = []
    for fila in (reversed(filas) if al_reves else filas):
        nombre, nivel = fila[terr["columna"]], fila[col_nivel]
        if nivel not in orden:
            # Nivel fuera de la jerarquía (p. ej. el total país al final del cuadro).
            resultado.append((nivel, "", codigo(nombre)))
            continue
        i = orden.index(nivel)
        padre = ancestros.get(orden[i - 1], "") if i > 0 else ""
        cod = f"{padre}/{codigo(nombre)}" if padre else codigo(nombre)
        ancestros[nivel] = cod
        for inferior in orden[i + 1:]:
            ancestros.pop(inferior, None)
        resultado.append((nivel, padre, cod))
    return resultado[::-1] if al_reves else resultado


def procesar(meta_ruta: Path) -> tuple[list[dict], list[dict]]:
    meta = yaml.safe_load(meta_ruta.read_text(encoding="utf-8"))
    with meta_ruta.with_suffix(".csv").open(encoding="utf-8") as f:
        filas = list(csv.DictReader(f))

    terr = meta["territorio"]
    ubicacion = ubicar(filas, terr)

    def nota_de(nombre, nivel, fila, col):
        """Nota de una celda: territorio, columna, columnas "area" y "sexo" si existen, nivel si se
        indica y cualquier otra columna del CSV que la nota nombre (p. ej. "grupo")."""
        for n in meta.get("notas_celdas", []):
            claves = {"area", "sexo"} | (set(n) - {"territorio", "columna", "nivel", "estado_valor", "nota"})
            if ((n["territorio"], n["columna"]) == (nombre, col) and n.get("nivel", nivel) == nivel
                    and all(n.get(k) == fila.get(k) for k in claves)):
                return n
        return {}
    # Páginas por filas ("desde") y, si el cuadro sigue en otra página con más columnas, por columnas.
    paginas = [p for p in meta["paginas"] if "columnas" not in p]
    pagina_col = {c: p for p in meta["paginas"] for c in p.get("columnas", [])}

    salida = []
    n_pagina = 0
    for fila, (nivel, padre, cod) in zip(filas, ubicacion):
        nombre = fila[terr["columna"]]
        # La página cambia en la primera fila indicada como "desde" de la página siguiente.
        if n_pagina + 1 < len(paginas) and paginas[n_pagina + 1].get("desde") == nombre:
            n_pagina += 1
        pagina = paginas[n_pagina]
        dims_fila = {}
        for dim, regla in meta.get("filas", {}).items():
            crudo = fila[regla["columna"]]
            dims_fila[dim] = regla["valores"][crudo] if "valores" in regla else (int(crudo) if crudo.isdigit() else crudo)
        for col, dims_col in meta["columnas"].items():
            v, estado = valor(fila[col])
            nota = nota_de(nombre, nivel, fila, col)
            dims = {**meta.get("fijas", {}), **dims_fila, **dims_col}
            censo = dims.pop("censo")
            indicador = dims.pop("indicador", meta["indicador"])
            unidad = dims.pop("unidad", meta["unidad"])
            otras = {k: dims.pop(k) for k in list(dims) if k not in DIMENSIONES}
            salida.append({
                "censo": censo,
                "indicador": indicador,
                "unidad": unidad,
                "territorio_nivel": nivel,
                "territorio_cod_orig": cod,
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
                "pagina_impresa": pagina_col.get(col, pagina).get("impresa", ""),
                "pagina_pdf": pagina_col.get(col, pagina).get("pdf", ""),
                "metodo": meta["metodo"],
                "verificacion": meta["verificacion"],
                "nota": " ".join(nota.get("nota", "").split()),
                "_padre": padre,
            })
    return salida, controlar(meta, salida)


def controlar(meta: dict, filas: list[dict]) -> list[dict]:
    """Aplica los controles del YAML; devuelve las diferencias encontradas."""
    fallas = []

    def clave(f, sin):
        return tuple((k, f[k]) for k in ("censo", "indicador", "territorio_cod_orig", "area", "sexo", "edad_min", "edad_estado",
                                         "dimensiones") if k not in sin)

    for c in meta.get("controles", []):
        grupos: dict = defaultdict(lambda: {"total": None, "partes": 0, "celdas": []})
        for f in filas:
            if c["tipo"] == "suma_dimension":
                # Una dimensión, o varias como lista (p. ej. [edad_min, edad_estado]) con valores en listas.
                d = c["dimension"]
                dims = d if isinstance(d, list) else [d]
                val = tuple(f[x] for x in dims) if isinstance(d, list) else f[d]
                comparar = (lambda x: tuple(x)) if isinstance(d, list) else (lambda x: x)
                k = clave(f, set(dims))
                es_total = val == comparar(c["total"])
                es_parte = val in [comparar(x) for x in c["partes"]]
            elif c["tipo"] == "suma_territorio":
                k = clave(f, {"territorio_cod_orig"})
                es_total, es_parte = f["territorio_nivel"] == c["total"], f["territorio_nivel"] == c["partes"]
            else:  # jerarquia: cada unidad = suma de sus unidades inmediatamente inferiores
                base = clave(f, {"territorio_cod_orig"})
                grupos[base + (("u", f["territorio_cod_orig"]),)]["total"] = f
                if f["_padre"] and f["valor"] != "":  # las partes sin dato no se suman
                    g = grupos[base + (("u", f["_padre"]),)]
                    g["partes"] += f["valor"] or 0
                    g["celdas"].append(f)
                continue
            g = grupos[k]
            if es_total:
                g["total"] = f
            elif es_parte and f["valor"] != "":
                g["partes"] += f["valor"]
                g["celdas"].append(f)
        for k, g in grupos.items():
            t = g["total"]
            if t is None or t["valor"] == "" or not g["celdas"]:
                continue
            if g["partes"] != t["valor"]:
                celdas = [t] + g["celdas"]
                fallas.append({
                    "fuente_id": meta["fuente_id"], "cuadro": meta["cuadro"], "control": c["tipo"],
                    "censo": t["censo"], "territorio": t["territorio_nombre_orig"] if c["tipo"] != "suma_territorio" else "(partes)",
                    "area": t["area"], "sexo": t["sexo"],
                    "total": t["valor"], "suma_partes": g["partes"], "diferencia": g["partes"] - t["valor"],
                    "explicada": any(x["estado_valor"] == "inconsistente" for x in celdas),
                })
    return fallas


def contrastar(filas: list[dict]) -> tuple[int, list[dict]]:
    """Compara las cifras que publican varios cuadros; devuelve (n.º de pares, pares distintos)."""
    por_clave = defaultdict(list)
    for f in filas:
        if f["valor"] == "":
            continue
        k = tuple(f[c] for c in ("censo", "indicador", "dpa_version", "territorio_nivel", "territorio_cod_orig", "area", "sexo",
                                  "edad_min", "edad_max", "edad_estado", "dimensiones"))
        por_clave[k].append(f)
    pares, distintos = 0, []
    for grupo in por_clave.values():
        for i, a in enumerate(grupo):
            for b in grupo[i + 1:]:
                if (a["fuente_id"], a["cuadro"]) == (b["fuente_id"], b["cuadro"]):
                    continue
                pares += 1
                if a["valor"] != b["valor"]:
                    distintos.append({
                        "censo": a["censo"], "territorio": a["territorio_nombre_orig"], "nivel": a["territorio_nivel"],
                        "area": a["area"], "sexo": a["sexo"],
                        "fuente_a": f"{a['fuente_id']} c{a['cuadro']}", "valor_a": a["valor"], "estado_a": a["estado_valor"],
                        "fuente_b": f"{b['fuente_id']} c{b['cuadro']}", "valor_b": b["valor"], "estado_b": b["estado_valor"],
                    })
    return pares, distintos


def main() -> None:
    filas, fallas = [], []
    for meta in sorted(ENTRADA.rglob("*.yaml")):
        f, c = procesar(meta)
        print(f"{meta.relative_to(RAIZ).as_posix()}: {len(f)} cifras, {len(c)} controles con diferencias")
        filas += f
        fallas += c

    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    with SALIDA.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, ESQUEMA, extrasaction="ignore", lineterminator="\n")
        w.writeheader()
        w.writerows(filas)
    campos = ["fuente_id", "cuadro", "control", "censo", "territorio", "area", "sexo", "total", "suma_partes", "diferencia", "explicada"]
    with CONTROLES.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, campos, lineterminator="\n")
        w.writeheader()
        w.writerows(fallas)

    pares, distintos = contrastar(filas)
    with CONTRASTE.open("w", newline="", encoding="utf-8") as fh:
        campos = ["censo", "territorio", "nivel", "area", "sexo", "fuente_a", "valor_a", "estado_a", "fuente_b", "valor_b", "estado_b"]
        w = csv.DictWriter(fh, campos, lineterminator="\n")
        w.writeheader()
        w.writerows(distintos)
    print(f"Contraste entre cuadros: {pares} pares de cifras repetidas, {len(distintos)} distintas "
          f"-> {CONTRASTE.relative_to(RAIZ).as_posix()}")

    sin_explicar = [f for f in fallas if not f["explicada"]]
    for f in fallas:
        marca = "anotada" if f["explicada"] else "REVISAR"
        print(f"  [{marca}] {f['fuente_id']} c{f['cuadro']} {f['control']} {f['censo']} {f['territorio']} "
              f"{f['area']}: {f['suma_partes']} vs {f['total']} ({f['diferencia']:+})")
    print(f"{len(filas)} cifras -> {SALIDA.relative_to(RAIZ).as_posix()}")
    sys.exit(1 if sin_explicar else 0)


if __name__ == "__main__":
    main()
