"""Borrador de transcripción de un cuadro escaneado: OCR asignado a las columnas del cuadro.

Detecta las líneas verticales del cuadro (proyección de píxeles oscuros), pasa la página por
OCR (RapidOCR) y asigna cada fragmento de texto a la columna entre dos líneas según su centro;
los fragmentos de una misma celda se unen (el OCR suele partir "7 860" en dos). Escribe un CSV
con una fila por línea del cuadro: y (px), c0 (rótulo), c1..cN (cifras sin espacios).

Es solo un BORRADOR: el OCR confunde 8/9, 1/l, omite celdas y deja basura en los rótulos.
Las cifras se revisan contra la imagen y con los controles aritméticos del pipeline.

Uso:
  python herramientas/ocr_cuadro.py pub_1930 --pdf 49-53 --dpi 200 --zona 0.25,0.97       --plantilla 0,99,223,346,424,545,671,795,872,993,1117
  (--zona y0,y1: franja vertical de la página donde está el cuerpo del cuadro; --plantilla:
  líneas del cuadro medidas en una página buena, cuando en otras se detectan mal)
"""

from __future__ import annotations

import argparse
import csv
import io
import re
import sys
from pathlib import Path

import numpy as np
import pymupdf
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from paginas import cargar_config, rango, ruta_pdf  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")


def lineas_verticales(gris: np.ndarray, y0: int, y1: int, umbral: float) -> list[int]:
    """Posición x de las líneas verticales: columnas con alta proporción de píxeles oscuros."""
    frac = (gris[y0:y1, :] < 128).mean(axis=0)
    picos = [x for x in range(1, len(frac) - 1) if frac[x] > umbral and frac[x] >= frac[x - 1] and frac[x] >= frac[x + 1]]
    grupos: list[list[int]] = []
    for x in picos:
        if grupos and x - grupos[-1][-1] <= 6:
            grupos[-1].append(x)
        else:
            grupos.append([x])
    lineas = [round(sum(g) / len(g)) for g in grupos]
    # Bordes dobles: de dos líneas más cercanas que una columna mínima, queda la exterior (derecha).
    minimo = gris.shape[1] * 0.025
    return [x for i, x in enumerate(lineas) if i + 1 == len(lineas) or lineas[i + 1] - x >= minimo]


def ajustar_plantilla(gris: np.ndarray, y0: int, y1: int, plantilla: list[int]) -> list[int]:
    """Ubica una plantilla de líneas (posiciones relativas a la primera, en px) en la página:
    busca el desplazamiento con más píxeles oscuros sobre las líneas y afina cada una en ±8 px."""
    frac = (gris[y0:y1, :] < 128).mean(axis=0)
    ancho = len(frac)
    mejor = max(range(0, ancho - plantilla[-1]), key=lambda x0: sum(frac[x0 + p] for p in plantilla))
    cortes = []
    for p in plantilla:
        x = mejor + p
        a, b = max(0, x - 8), min(ancho, x + 9)
        cortes.append(a + int(np.argmax(frac[a:b])))
    return cortes


def filas_ocr(motor, imagen: Image.Image, cortes: list[int], y0: int, y1: int, tolerancia: int) -> list[dict]:
    """OCR columna por columna (franjas entre líneas) para que el OCR no una cifras vecinas."""
    bordes = [0] + cortes + [imagen.width]
    fragmentos = []
    for col, (xa, xb) in enumerate(zip(bordes, bordes[1:])):
        if xb - xa < 15:
            continue
        franja = imagen.crop((xa + 2, y0, xb - 2, y1))
        # margen blanco: el OCR detecta mal el texto pegado al borde de la imagen
        lienzo = Image.new("L", (franja.width + 40, franja.height + 40), 255)
        lienzo.paste(franja, (20, 20))
        buf = io.BytesIO()
        lienzo.save(buf, format="PNG")
        resultado, _ = motor(buf.getvalue())
        for caja, texto, _conf in resultado or []:
            ys = [p[1] for p in caja]
            xs = [p[0] for p in caja]
            fragmentos.append(((min(ys) + max(ys)) / 2 - 20 + y0, min(xs), col, texto))
    fragmentos.sort()
    filas: list[dict] = []
    for yc, x, col, texto in fragmentos:
        fila = next((f for f in filas if abs(f["y"] - yc) < tolerancia), None)
        if fila is None:
            fila = {"y": yc, "celdas": {}}
            filas.append(fila)
        fila["celdas"].setdefault(col, []).append((x, texto))
    return sorted(filas, key=lambda f: f["y"])


def limpiar(col: int, partes: list[tuple[float, str]]) -> str:
    texto = " ".join(t for _, t in sorted(partes))
    if col == 0:
        return texto.strip()
    if re.fullmatch(r"[\s\-—一_.]+", texto):
        return "-"
    return re.sub(r"[\s.']", "", texto)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("fuente_id")
    ap.add_argument("--pdf", required=True, help="página o rango del PDF")
    ap.add_argument("--dpi", type=int, default=200)
    ap.add_argument("--zona", default="0.2,0.97", help="y0,y1 (fracción de la página) del cuerpo del cuadro")
    ap.add_argument("--umbral", type=float, default=0.3, help="proporción mínima de píxeles oscuros para una línea")
    ap.add_argument("--tolerancia", type=int, default=0, help="px para agrupar en una fila (0 = dpi/16)")
    ap.add_argument("--plantilla", help="posiciones x de las líneas, en px a --dpi, relativas a la primera "
                    "(p. ej. 0,100,223); la última columna llega al borde de la página")
    ap.add_argument("--salida", help="CSV de salida (por defecto, en <cache>/borradores/)")
    args = ap.parse_args()

    from rapidocr_onnxruntime import RapidOCR
    motor = RapidOCR()
    config = cargar_config()
    doc = pymupdf.open(ruta_pdf(args.fuente_id, config))
    z0, z1 = (float(v) for v in args.zona.split(","))
    tolerancia = args.tolerancia or args.dpi // 16

    salida = Path(args.salida) if args.salida else Path(config["cache"]) / "borradores" / f"{args.fuente_id}_p{args.pdf}.csv"
    salida.parent.mkdir(parents=True, exist_ok=True)
    todas = []
    ncol = 0
    for n in rango(args.pdf):
        pix = doc[n - 1].get_pixmap(dpi=args.dpi, colorspace=pymupdf.csGRAY)
        imagen = Image.open(io.BytesIO(pix.tobytes("png"))).convert("L")
        gris = np.array(imagen)
        y0, y1 = int(gris.shape[0] * z0), int(gris.shape[0] * z1)
        if args.plantilla:
            cortes = ajustar_plantilla(gris, y0, y1, [int(v) for v in args.plantilla.split(",")])
        else:
            cortes = lineas_verticales(gris, y0, y1, args.umbral)
        print(f"PDF {n}: {len(cortes)} líneas verticales en x = {cortes}", flush=True)
        for fila in filas_ocr(motor, imagen, cortes, y0, y1, tolerancia):
            todas.append((n, fila))
        ncol = max(ncol, len(cortes) + 1)

    with salida.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["pdf", "y"] + [f"c{i}" for i in range(ncol)])
        for n, fila in todas:
            w.writerow([n, round(fila["y"])] + [limpiar(i, fila["celdas"][i]) if i in fila["celdas"] else "" for i in range(ncol)])
    print(f"{len(todas)} filas -> {salida}")


if __name__ == "__main__":
    main()
