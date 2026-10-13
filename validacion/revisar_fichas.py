"""Aplica la recodificación de las fichas de variables a las frecuencias del inventario.

Para cada ficha de metadatos/variables/ con `recodificacion` por censo:
  - verifica que todos los códigos observados en la base tengan categoría armonizada,
  - muestra la distribución de la categoría general en cada censo, lado a lado.

No lee los microdatos: usa metadatos/inventario/<censo>_<tabla>_frecuencias.csv.

Uso:
  python validacion/revisar_fichas.py                  # todas las fichas con recodificación
  python validacion/revisar_fichas.py parentesco       # una ficha
Sale con código 1 si algún código observado queda sin categoría.
"""

import csv
import sys
from collections import defaultdict
from pathlib import Path

import yaml

sys.stdout.reconfigure(encoding="utf-8")

RAIZ = Path(__file__).resolve().parents[1]
FICHAS = RAIZ / "metadatos" / "variables"
INVENTARIO = RAIZ / "metadatos" / "inventario"
VACIOS = {"", "NA"}


def frecuencias(censo, tabla: str, variable: str) -> dict[str, int]:
    ruta = INVENTARIO / f"{censo}_{tabla}_frecuencias.csv"
    with ruta.open(encoding="utf-8", newline="") as f:
        return {r["valor"]: int(r["n"]) for r in csv.DictReader(f) if r["variable"] == variable}


def general(destino) -> int:
    return destino[0] if isinstance(destino, list) else destino


def revisar(ficha: dict) -> int:
    print(f"\n=== {ficha['nombre']}: {ficha['etiqueta']}")
    etiquetas = {c["codigo"]: c["etiqueta"] for c in ficha["categorias"]}
    conteos = defaultdict(dict)
    errores = 0
    for censo, regla in ficha["censos"].items():
        if "recodificacion" not in regla:
            continue
        tabla = regla["tabla"].split(" /")[0].strip()
        variable = regla.get("recodificacion_variable", regla["variables_originales"][0])
        obs = frecuencias(censo, tabla, variable)
        mapa = {str(k): general(v) for k, v in regla["recodificacion"].items()}
        cubiertos_por_operativo = 0
        if "recodificacion_operativo" in regla:
            # Registros sin la variable principal, clasificados por el tipo de operativo.
            operativo = frecuencias(censo, tabla, "tipo_operativo")
            for codigo, destino in regla["recodificacion_operativo"].items():
                n = operativo.get(str(codigo), 0)
                conteos[general(destino)][censo] = conteos[general(destino)].get(censo, 0) + n
                cubiertos_por_operativo += n
        for codigo, n in obs.items():
            if codigo in mapa:
                g = mapa[codigo]
                conteos[g][censo] = conteos[g].get(censo, 0) + n
            elif codigo in VACIOS and n == cubiertos_por_operativo:
                continue
            else:
                errores += 1
                print(f"  SIN CATEGORÍA: {censo} {variable}={codigo!r} ({n:,} registros)")
        sin_uso = sorted(set(mapa) - set(obs), key=lambda c: int(c) if c.lstrip("-").isdigit() else 0)
        if sin_uso:
            print(f"  aviso: {censo} {variable} códigos de la ficha que no aparecen en la base: {', '.join(sin_uso)}")

    censos = sorted({c for fila in conteos.values() for c in fila})
    totales = {c: sum(fila.get(c, 0) for fila in conteos.values()) for c in censos}
    print(f"  {'categoría':52}" + "".join(f"{c:>20}" for c in censos))
    for codigo in sorted(conteos):
        celdas = "".join(
            f"{conteos[codigo].get(c, 0):>12,} {conteos[codigo].get(c, 0) / totales[c]:>6.1%}" if c in conteos[codigo] else f"{'—':>20}"
            for c in censos)
        print(f"  {codigo:>3} {etiquetas.get(codigo, '?')[:48]:48}{celdas}")
    print(f"  {'total':52}" + "".join(f"{totales[c]:>12,}{'':8}" for c in censos))
    return errores


def main() -> None:
    nombres = sys.argv[1:]
    errores = 0
    for ruta in sorted(FICHAS.glob("*.yaml")):
        if ruta.name.startswith("_") or (nombres and ruta.stem not in nombres):
            continue
        ficha = yaml.safe_load(ruta.read_text(encoding="utf-8"))
        if any("recodificacion" in r for r in ficha.get("censos", {}).values()):
            errores += revisar(ficha)
    sys.exit(1 if errores else 0)


if __name__ == "__main__":
    main()
