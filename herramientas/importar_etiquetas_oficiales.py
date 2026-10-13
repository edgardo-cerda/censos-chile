"""Importa las etiquetas oficiales publicadas por el INE al diccionario del proyecto.

- 2024: diccionario_variables_censo2024.xlsx (variables, preguntas, universos y categorías).
- 2017: archivos etiquetas_*.csv incluidos en los .rar públicos de viviendas, hogares y
  personas (URL en metadatos/fuentes.yaml). Se descargan a <cache>/descargas/2017 si no
  están y se extraen con bsdtar (incluido en Windows 10+ como tar.exe; en Linux/macOS,
  instalar libarchive-tools o bsdtar).

- 1992 y 2002: tablas de códigos de la entrega (categoría de entidad, ocupación, rama).

Escribe en metadatos/diccionario/: 2024_variables.csv, 2024_categorias.csv,
2017_categorias.csv y <censo>_categorias_auxiliares.csv. Lo transcrito a mano desde los
cuestionarios (1992_*.csv, 2002_*.csv, 2017_variables.csv, 2017_categorias_adicionales.csv)
no lo toca este script.

Uso:
  python herramientas/importar_etiquetas_oficiales.py
"""

from __future__ import annotations

import csv
import os
import re
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

import openpyxl
import yaml

RAIZ = Path(__file__).resolve().parents[1]
DICCIONARIO = RAIZ / "metadatos" / "diccionario"
CAMPOS_VARIABLES = ["censo", "tabla", "variable", "etiqueta", "pregunta", "universo", "tipo", "fuente", "nota"]
CAMPOS_CATEGORIAS = ["censo", "tabla", "variable", "codigo", "etiqueta", "fuente", "nota"]

# Archivo de etiquetas 2017 -> (tabla, variables a las que aplica).
ETIQUETAS_2017 = {
    "etiquetas_vivienda_p01.csv": ("viviendas", ["P01"]),
    "etiquetas_vivienda_p02.csv": ("viviendas", ["P02"]),
    "etiquetas_vivienda_p03a.csv": ("viviendas", ["P03A"]),
    "etiquetas_vivienda_p03b.csv": ("viviendas", ["P03B"]),
    "etiquetas_vivienda_p03c.csv": ("viviendas", ["P03C"]),
    "etiquetas_vivienda_p04.csv": ("viviendas", ["P04"]),
    "etiquetas_vivienda_p05.csv": ("viviendas", ["P05"]),
    "etiquetas_hogar_tipo_hogar.csv": ("hogares", ["TIPO_HOGAR"]),
    "etiquetas_hogar_tipo_operativo.csv": ("hogares", ["TIPO_OPERATIVO"]),
    "etiquetas_persona_p07.csv": ("personas", ["P07"]),
    "etiquetas_persona_p08.csv": ("personas", ["P08"]),
    "etiquetas_persona_p10.csv": ("personas", ["P10"]),
    "etiquetas_persona_p11.csv": ("personas", ["P11"]),
    "etiquetas_persona_p12.csv": ("personas", ["P12"]),
    "etiquetas_persona_p12a_tramo.csv": ("personas", ["P12A_TRAMO"]),
    "etiquetas_persona_p13.csv": ("personas", ["P13"]),
    "etiquetas_persona_p14.csv": ("personas", ["P14"]),
    "etiquetas_persona_p15.csv": ("personas", ["P15"]),
    "etiquetas_persona_p15a.csv": ("personas", ["P15A"]),
    "etiquetas_persona_p16.csv": ("personas", ["P16"]),
    "etiquetas_persona_p16a.csv": ("personas", ["P16A"]),
    "etiquetas_persona_p16a_grupo.csv": ("personas", ["P16A_GRUPO"]),
    "etiquetas_persona_p16a_otro.csv": ("personas", ["P16A_OTRO"]),
    "etiquetas_persona_p17.csv": ("personas", ["P17"]),
    "etiquetas_persona_p18.csv": ("personas", ["P18"]),
    "etiquetas_persona_p21m.csv": ("personas", ["P21M"]),
    "etiquetas_persona_pais.csv": ("personas", ["P10PAIS", "P11PAIS", "P12PAIS"]),
    "etiquetas_persona_pais_grupo.csv": ("personas", ["P10PAIS_GRUPO", "P11PAIS_GRUPO", "P12PAIS_GRUPO"]),
    # De las comunas solo se conservan los códigos especiales (las comunas van en territorio/).
    "etiquetas_persona_comuna_16r.csv": ("personas", ["P10COMUNA", "P11COMUNA", "P12COMUNA"]),
    "etiquetas_persona_comuna_15r.csv": ("personas", ["P10COMUNA_15R", "P11COMUNA_15R", "P12COMUNA_15R"]),
}


def escribir(ruta: Path, campos: list[str], filas: list[dict]) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with ruta.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, campos, lineterminator="\n")
        w.writeheader()
        w.writerows(filas)
    print(f"  {ruta.relative_to(RAIZ)}: {len(filas)} filas")


def limpiar(texto) -> str:
    if texto is None:
        return ""
    return re.sub(r"\s+", " ", str(texto).replace("​", "").replace("\xa0", " ")).strip()


def codigo_simple(valor) -> str | None:
    """Devuelve el código si es un valor único (3, '-66', 'A', 'NA'); None si es un rango como '0:85'."""
    texto = limpiar(valor)
    return texto if re.fullmatch(r"-?\d+|[A-Z]{1,3}", texto) else None


def importar_2024(origen: Path) -> None:
    wb = openpyxl.load_workbook(origen / "cpv2024" / "diccionario_variables_censo2024.xlsx", read_only=True)
    variables: dict[tuple, dict] = {}
    categorias = []
    for hoja, tabla in (("tabla_viviendas", "viviendas"), ("tabla_hogares", "hogares"), ("tabla_personas", "personas")):
        for fila in list(wb[hoja].iter_rows(values_only=True))[1:]:
            _, nombre, descripcion, valor, etiqueta, rango, universo, *_ = fila
            if not nombre:
                continue
            nombre, etiqueta = limpiar(nombre), limpiar(etiqueta)
            clave = (tabla, nombre)
            if clave not in variables:
                descripcion = limpiar(descripcion)
                es_pregunta = re.match(r"^\d+[a-z]?\.", descripcion)
                variables[clave] = {
                    "censo": 2024, "tabla": tabla, "variable": nombre,
                    "etiqueta": re.sub(r"^\d+[a-z]?\.\s*", "", descripcion) if es_pregunta else descripcion,
                    "pregunta": descripcion if es_pregunta else "",
                    "universo": limpiar(universo), "tipo": "", "fuente": "diccionario_oficial",
                    "nota": f"Rango: {limpiar(rango)}" if rango else "",
                    "_territorial": False, "_categorias": 0, "_rango": False,
                }
            v = variables[clave]
            codigo = codigo_simple(valor)
            if etiqueta.startswith("Ver diccionario"):
                v["_territorial"] = True
            elif codigo is None:
                v["_rango"] = True
            else:
                categorias.append({"censo": 2024, "tabla": tabla, "variable": nombre, "codigo": codigo,
                                   "etiqueta": etiqueta, "fuente": "diccionario_oficial", "nota": ""})
                if not codigo.startswith("-") and codigo != "NA":
                    v["_categorias"] += 1
    for v in variables.values():
        if v["variable"].startswith("id_"):
            v["tipo"] = "identificador"
        elif v["_territorial"]:
            v["tipo"] = "territorial"
        elif v["_rango"] and v["_categorias"] == 0:
            v["tipo"] = "numerica"
        else:
            v["tipo"] = "categorica"
    filas = [{k: v[k] for k in CAMPOS_VARIABLES} for v in variables.values()]
    escribir(DICCIONARIO / "2024_variables.csv", CAMPOS_VARIABLES, filas)
    escribir(DICCIONARIO / "2024_categorias.csv", CAMPOS_CATEGORIAS, categorias)


def buscar_bsdtar() -> str:
    """bsdtar (libarchive) lee .rar; el tar de GNU no. En Windows, System32\\tar.exe es bsdtar."""
    candidatos = [shutil.which("bsdtar"), str(Path(os.environ.get("SystemRoot", "C:/Windows")) / "System32" / "tar.exe"),
                  shutil.which("tar")]
    for tar in filter(None, candidatos):
        try:
            version = subprocess.run([tar, "--version"], capture_output=True, text=True).stdout
        except OSError:
            continue
        if "bsdtar" in version:
            return tar
    sys.exit("Se necesita bsdtar (libarchive) para extraer los .rar de 2017.")


def descargar_2017(config: dict) -> Path:
    fuentes = yaml.safe_load((RAIZ / "metadatos" / "fuentes.yaml").read_text(encoding="utf-8"))
    archivos = next(m for m in fuentes["microdatos"] if m["id"] == "micro_2017")["archivos"]
    destino = Path(config["cache"]) / "descargas" / "2017"
    etiquetas = destino / "etiquetas"
    if etiquetas.exists() and any(etiquetas.glob("etiquetas_*.csv")):
        return etiquetas
    tar = buscar_bsdtar()
    etiquetas.mkdir(parents=True, exist_ok=True)
    for tabla in ("viviendas", "hogares", "personas"):
        rar = destino / f"{tabla}.rar"
        if not rar.exists():
            print(f"  descargando {tabla}.rar ...", flush=True)
            urllib.request.urlretrieve(archivos[tabla], rar)
        subprocess.run([tar, "-xf", str(rar), "-C", str(etiquetas), "etiquetas_*.csv"], check=True)
    return etiquetas


def importar_2017(config: dict) -> None:
    carpeta = descargar_2017(config)
    filas = []
    for archivo, (tabla, nombres) in ETIQUETAS_2017.items():
        solo_especiales = "comuna" in archivo
        with (carpeta / archivo).open(encoding="utf-8-sig", newline="") as f:
            for registro in csv.DictReader(f, delimiter=";"):
                codigo = limpiar(registro["valor"]).strip("'")
                if not codigo:
                    continue
                if solo_especiales and not (codigo in ("98", "99") or codigo.startswith("99")):
                    continue
                for nombre in nombres:
                    filas.append({"censo": 2017, "tabla": tabla, "variable": nombre, "codigo": codigo,
                                  "etiqueta": limpiar(registro["glosa"]), "fuente": "etiquetas_oficiales",
                                  "nota": ""})
    escribir(DICCIONARIO / "2017_categorias.csv", CAMPOS_CATEGORIAS, filas)


def importar_auxiliares(origen: Path) -> None:
    """Tablas de códigos que acompañan las entregas de 1992 y 2002 (latin-1, exportadas desde R)."""
    tablas = {
        1992: [("cpv1992/CATEGORIA_1992.csv", "portafolios", "Cod_Cat", "CODIGO", "GLOSA"),
               ("cpv1992/OCUPACION_1992.csv", "personas", "Ocupacion", "Codigo", "Glosa"),
               ("cpv1992/RAMA_ACTIVIDAD_1992.csv", "personas", "Rama_actividad", "Codigo", "Glosa_CIIU")],
        2002: [("cpv2002/CATEGORIAS_2002.csv", "portafolios", "CATEGORIA", "CATEGORIA", "NOMBRE_CATEGORIA")],
    }
    for censo, archivos in tablas.items():
        filas = []
        for archivo, tabla, variable, col_codigo, col_glosa in archivos:
            with (origen / archivo).open(encoding="latin-1", newline="") as f:
                for registro in csv.DictReader(f):
                    filas.append({"censo": censo, "tabla": tabla, "variable": variable,
                                  "codigo": limpiar(registro[col_codigo]), "etiqueta": limpiar(registro[col_glosa]),
                                  "fuente": "tabla_auxiliar", "nota": Path(archivo).name})
        filas.sort(key=lambda r: (r["variable"], int(r["codigo"])))
        escribir(DICCIONARIO / f"{censo}_categorias_auxiliares.csv", CAMPOS_CATEGORIAS, filas)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    config = yaml.safe_load((RAIZ / "config.yaml").read_text(encoding="utf-8"))
    origen = Path(config["datos_originales"])
    print("[2024]")
    importar_2024(origen)
    print("[2017]")
    importar_2017(config)
    print("[1992 y 2002: tablas auxiliares]")
    importar_auxiliares(origen)


if __name__ == "__main__":
    main()
