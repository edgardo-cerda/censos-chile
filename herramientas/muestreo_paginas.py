"""Lee por OCR el encabezado y el pie de páginas del PDF para ubicar cuadros y medir el desfase.

Sirve para armar el catálogo de cuadros cuando el índice no trae la página del PDF: por cada
página escribe una línea con el número del PDF, los desfases candidatos (PDF - número impreso
leído) y el texto de la franja superior e inferior. La salida se agrega al archivo a medida que
avanza y las páginas ya leídas se saltan, así que puede correrse por tandas cortas.

Uso:
  python herramientas/muestreo_paginas.py pub_1875 1 680 20 -o muestreo_1875.tsv
  python herramientas/muestreo_paginas.py pub_1952 15 260 -o enc_1952.tsv --franja 0.14
  python herramientas/muestreo_paginas.py pub_1952 --lista 1205,1206,1338 -o enc_1952.tsv

El encabezado con el título del cuadro suele caber en el 9 % superior de la página (--franja);
en 1895 y 1952 hace falta 0,14-0,16. Unos 6 s por página: correr una sola instancia a la vez.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import pymupdf

from paginas import cargar_config, ruta_pdf


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("fuente_id")
    ap.add_argument("desde", nargs="?", type=int)
    ap.add_argument("hasta", nargs="?", type=int)
    ap.add_argument("paso", nargs="?", type=int, default=1)
    ap.add_argument("-o", "--salida", help="archivo .tsv (se agrega; las páginas ya presentes se saltan)")
    ap.add_argument("--lista", help="páginas del PDF separadas por coma, en lugar de desde/hasta/paso")
    ap.add_argument("--franja", type=float, default=0.09, help="alto de la franja superior (fracción de la página)")
    args = ap.parse_args()
    if args.lista:
        paginas = [int(x) for x in args.lista.split(",")]
    elif args.desde is not None and args.hasta is not None:
        paginas = list(range(args.desde, args.hasta + 1, args.paso))
    else:
        ap.error("indicar desde y hasta, o --lista")
    salida = args.salida

    from rapidocr_onnxruntime import RapidOCR
    motor = RapidOCR()
    doc = pymupdf.open(ruta_pdf(args.fuente_id, cargar_config()))
    hechas: set[int] = set()
    if salida and Path(salida).exists():
        hechas = {int(l.split("\t")[0]) for l in Path(salida).read_text(encoding="utf-8").splitlines() if l}
    arch = open(salida, "a", encoding="utf-8") if salida else None

    for n in paginas:
        if n in hechas or not 1 <= n <= doc.page_count:
            continue
        pag = doc[n - 1]
        r = pag.rect
        textos = []
        for y0, y1 in ((0.0, args.franja), (0.93, 1.0)):
            clip = pymupdf.Rect(r.x0, r.y0 + r.height * y0, r.x1, r.y0 + r.height * y1)
            pix = pag.get_pixmap(dpi=110, clip=clip, colorspace=pymupdf.csGRAY)
            res, _ = motor(pix.tobytes("png"))
            textos.append(" ".join(t for _, t, _ in sorted(res or [], key=lambda x: x[0][0][0])))
        numeros = [int(x) for x in re.findall(r"(?<![\d.,])(\d{1,4})(?![\d.,])", " ".join(textos)) if 0 < int(x) < 3000]
        linea = f"{n}\t{[n - x for x in numeros][:3]}\t{textos[0][:90]}\t{textos[1][:60]}"
        print(linea, flush=True)
        if arch:
            arch.write(linea + "\n")
            arch.flush()


if __name__ == "__main__":
    main()
