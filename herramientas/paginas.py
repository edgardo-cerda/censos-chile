"""Renderiza páginas de las publicaciones censales escaneadas (y opcionalmente las pasa por OCR).

Los PDF históricos no tienen capa de texto: para transcribir un cuadro se renderiza la página
(o un recorte a mayor resolución) y se lee la imagen. La página se indica en numeración del
PDF (--pdf) o impresa (--impresa); la conversión usa metadatos/paginacion.csv.

Las imágenes quedan en <cache>/paginas/<fuente_id>/. Con --ocr se escribe además un .tsv
con una línea de texto por fila de la página (RapidOCR); el OCR confunde 8/9, 1/l y los
separadores de miles, así que solo sirve para ubicarse o como borrador a verificar.

Uso:
  python herramientas/paginas.py pub_1952 --pdf 40
  python herramientas/paginas.py pub_1960 --impresa 124 --dpi 220 --recorte 0.2,0.5
  python herramientas/paginas.py pub_1940 --pdf 82-121 --ocr --dpi 130
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

import pymupdf
import yaml

RAIZ = Path(__file__).resolve().parents[1]


def cargar_config() -> dict:
    return yaml.safe_load((RAIZ / "config.yaml").read_text(encoding="utf-8"))


def ruta_pdf(fuente_id: str, config: dict) -> Path:
    fuentes = yaml.safe_load((RAIZ / "metadatos" / "fuentes.yaml").read_text(encoding="utf-8"))
    pub = next((p for p in fuentes["publicaciones"] if p["id"] == fuente_id), None)
    if pub is None:
        raise SystemExit(f"Fuente desconocida: {fuente_id}")
    carpeta = Path(config.get("publicaciones") or Path(config["datos_originales"]) / "censos previos")
    return carpeta / pub["archivo"]


def impresa_a_pdf(fuente_id: str, impresa: int) -> int:
    with (RAIZ / "metadatos" / "paginacion.csv").open(encoding="utf-8") as f:
        for fila in csv.DictReader(f):
            if fila["fuente_id"] == fuente_id and int(fila["impresa_desde"]) <= impresa <= int(fila["impresa_hasta"]):
                return impresa + int(fila["desfase"])
    raise SystemExit(f"Sin desfase registrado para {fuente_id}, página impresa {impresa}; usar --pdf.")


def rango(texto: str) -> list[int]:
    if "-" in texto:
        a, b = texto.split("-")
        return list(range(int(a), int(b) + 1))
    return [int(texto)]


def recorte(pagina: pymupdf.Page, texto: str | None) -> pymupdf.Rect | None:
    """'y0,y1' o 'y0,y1,x0,x1' como fracciones (0-1) del alto y ancho de la página."""
    if not texto:
        return None
    v = [float(x) for x in texto.split(",")]
    y0, y1 = v[0], v[1]
    x0, x1 = (v[2], v[3]) if len(v) == 4 else (0.0, 1.0)
    r = pagina.rect
    return pymupdf.Rect(r.x0 + r.width * x0, r.y0 + r.height * y0, r.x0 + r.width * x1, r.y0 + r.height * y1)


def ocr_filas(motor, png: bytes, tolerancia: int = 12) -> list[str]:
    """Agrupa los textos del OCR por fila (|y - y_fila| < tolerancia px) y los ordena por x."""
    resultado, _ = motor(png)
    filas: list[tuple[float, list[tuple[float, str]]]] = []
    for caja, texto, _conf in resultado or []:
        x, y = caja[0]
        for fila in filas:
            if abs(fila[0] - y) < tolerancia:
                fila[1].append((x, texto))
                break
        else:
            filas.append((y, [(x, texto)]))
    filas.sort(key=lambda f: f[0])
    return [" | ".join(t for _, t in sorted(celdas)) for _, celdas in filas]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("fuente_id")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--pdf", help="página o rango del PDF (base 1), p. ej. 40 o 82-121")
    g.add_argument("--impresa", help="página o rango en numeración impresa")
    ap.add_argument("--dpi", type=int, default=120)
    ap.add_argument("--recorte", help="y0,y1[,x0,x1] como fracciones de la página")
    ap.add_argument("--rotar", type=int, default=0, choices=[0, 90, 180, 270])
    ap.add_argument("--color", action="store_true", help="renderizar en color (por defecto, grises)")
    ap.add_argument("--ocr", action="store_true", help="escribir también el texto OCR por filas (.tsv)")
    args = ap.parse_args()

    config = cargar_config()
    doc = pymupdf.open(ruta_pdf(args.fuente_id, config))
    paginas = rango(args.pdf) if args.pdf else [impresa_a_pdf(args.fuente_id, n) for n in rango(args.impresa)]
    destino = Path(config["cache"]) / "paginas" / args.fuente_id
    destino.mkdir(parents=True, exist_ok=True)

    motor = None
    if args.ocr:
        from rapidocr_onnxruntime import RapidOCR
        motor = RapidOCR()

    for n in paginas:
        if not 1 <= n <= doc.page_count:
            raise SystemExit(f"Página {n} fuera del PDF (1-{doc.page_count}).")
        pagina = doc[n - 1]
        if args.rotar:
            pagina.set_rotation((pagina.rotation + args.rotar) % 360)
        clip = recorte(pagina, args.recorte)
        pix = pagina.get_pixmap(dpi=args.dpi, clip=clip, colorspace=pymupdf.csRGB if args.color else pymupdf.csGRAY)
        sufijo = f"_r{args.recorte.replace(',', '-')}" if args.recorte else ""
        png = destino / f"p{n:04d}{sufijo}_{args.dpi}dpi.png"
        pix.save(png)
        print(png)
        if motor:
            lineas = ocr_filas(motor, pix.tobytes("png"))
            tsv = png.with_suffix(".tsv")
            tsv.write_text("\n".join(lineas) + "\n", encoding="utf-8")
            print(tsv, f"({len(lineas)} filas)", flush=True)


if __name__ == "__main__":
    main()
