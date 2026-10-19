"""Planilla con el estado de avance de la digitalización de cada censo histórico (1813-1982).

Lee el catálogo de cuadros, los cuadros transcritos (digitalizacion/) y las cifras ya
digitalizadas (productos/tabulados/tabulados_publicaciones.csv), y escribe
productos/avance/avance_censos_historicos.xlsx con las hojas:
  - Resumen: una fila por censo; los conteos son fórmulas sobre las demás hojas.
  - Cuadros transcritos: un cuadro por fila, con su cobertura.
  - Cifras: cifras digitalizadas agregadas por censo, cuadro y nivel territorial.
  - Catálogo: copia de metadatos/catalogo_cuadros.csv.
  - Notas: definiciones y fuentes.
El estado y los pasos pendientes de cada censo (columnas en azul) se escriben a mano en ESTADO,
a partir de docs/estado.md y docs/digitalizacion.md.

Uso:
  python herramientas/resumen_avance.py
"""

from __future__ import annotations

import csv
import datetime as dt
from pathlib import Path

import pandas as pd
import pymupdf
import yaml
from openpyxl import Workbook
from openpyxl.formatting.rule import FormulaRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from paginas import cargar_config, ruta_pdf

RAIZ = Path(__file__).resolve().parents[1]
SALIDA = RAIZ / "productos" / "avance" / "avance_censos_historicos.xlsx"

CENSOS = [1813, 1835, 1843, 1854, 1865, 1875, 1885, 1895, 1907, 1920, 1930, 1940, 1952, 1960, 1970, 1982]

# Estado, pendiente y observaciones de cada censo (escritos a mano).
ESTADO = {
    1813: ("Catalogado", "Transcribir los «Censo de provincia» (totales por provincia).",
           "Sin índice. No hay datos de Santiago; Concepción figura con las matrículas de 1812. "
           "Totales de Rancagua y Colchagua cruzados en la edición."),
    1835: ("Catalogado", "Transcribir habitantes por provincia y departamento (cap. IX, págs. 171–222).",
           "Dos páginas impresas por página del PDF."),
    1843: ("Sin publicación", "Buscar un ejemplar digitalizado.", "No hay publicación digitalizada disponible."),
    1854: ("Sin publicación", "Buscar un ejemplar digitalizado.", "No hay publicación digitalizada disponible."),
    1865: ("Serie desde otros censos", "Transcribir el Censo general de la República (págs. 321–392) para tener sexo.",
           "Provincia × área desde 1952 C9; departamento (total) desde 1920 C1. Errata en Atacama (1920 C1) "
           "y en Santiago rural (1952 C9)."),
    1875: ("Serie desde otros censos", "Transcribir los cuadros generales (págs. 601–645) para tener sexo.",
           "Provincia × área desde 1952 C9; departamento (total) desde 1920 C1."),
    1885: ("Serie desde otros censos", "Transcribir los cuadros generales (págs. 839–867) para tener sexo.",
           "El PDF trae solo el tomo I de 2. Provincia × área desde 1952 C9; departamento desde 1920 C1."),
    1895: ("Serie desde otros censos", "Transcribir los cuadros generales del tomo IV (págs. 467–551) para tener sexo.",
           "Departamento × área desde 1920 C3 (con departamentos agrupados); provincia × área desde 1930 C10 y 1952 C9."),
    1907: ("Parcial", "Transcribir los resúmenes por provincia del volumen de 1907 (sexo por provincia y departamento).",
           "Departamento × área desde 1920 C1 y C3; área × sexo solo para el país (1930 C9)."),
    1920: ("Núcleo completo", "Opcional: comunas y subdelegaciones (Cuadro 5, págs. 8–104).",
           "Departamento × área × sexo (Cuadro 4). El Cuadro 3 tiene seis cifras de 1920 que no cuadran: usar el Cuadro 4."),
    1930: ("Núcleo completo", "—", "Comuna × área × sexo (Cuadro 9). Errata en el total de Atacama."),
    1940: ("Núcleo completo", "—",
           "Comuna × área × sexo, con viviendas. Cifras ajustadas (~2,8 %); las revisadas están en 1952 C9 y 1960 C1.1.1."),
    1952: ("Parcial", "Comuna: Tomo I (Cuadro 4) y Tomo II (Cuadro 1 de cada provincia). Buscar otro ejemplar "
                      "con los cuadros nacionales 1 y 2.",
           "Provincia × área (1952 C9, 1960 C1.1.1). Faltan en el escaneo las págs. 85–116 (cuadros nacionales 1 y 2)."),
    1960: ("Núcleo por provincia", "Bajar a departamento o comuna si hay cuadro.", "Provincia × área × sexo (Cuadro 1.2)."),
    1970: ("Catalogado", "Buscar una publicación con población por provincia y área.",
           "El volumen «Total País» no trae cuadros por provincia de población por área."),
    1982: ("Núcleo completo", "Tomos II y III: ocupación, educación, vivienda, hogar y familia.",
           "Región, provincia y comuna × área × sexo (Cuadro 1.01). Todas las sumas cuadran."),
}
COLOR_ESTADO = {
    "Núcleo completo": "C6EFCE", "Núcleo por provincia": "DDEBF7", "Parcial": "FFEB9C",
    "Serie desde otros censos": "FCE4D6", "Catalogado": "EDEDED", "Sin publicación": "D9D9D9",
}
NIVELES = ["comuna", "departamento", "provincia", "region", "pais"]  # de más fino a más grueso
NOMBRE_NIVEL = {"comuna": "Comuna", "departamento": "Departamento", "provincia": "Provincia",
                "region": "Región", "pais": "País"}

ARIAL = "Arial"
F_NORMAL = Font(name=ARIAL, size=10)
F_INPUT = Font(name=ARIAL, size=10, color="0000FF")
F_TITULO = Font(name=ARIAL, size=14, bold=True)
F_HEAD = Font(name=ARIAL, size=10, bold=True, color="FFFFFF")
F_BOLD = Font(name=ARIAL, size=10, bold=True)
F_NOTA = Font(name=ARIAL, size=9, italic=True, color="595959")
FILL_HEAD = PatternFill("solid", fgColor="1F4E78")
FILL_TOTAL = PatternFill("solid", fgColor="F2F2F2")
BORDE = Border(bottom=Side(style="thin", color="BFBFBF"))
MILES = "#,##0;-#,##0;-"


def cabecera(ws, fila, titulos, anchos):
    for j, (t, w) in enumerate(zip(titulos, anchos), 1):
        c = ws.cell(fila, j, t)
        c.font, c.fill = F_HEAD, FILL_HEAD
        c.alignment = Alignment(wrap_text=True, vertical="center", horizontal="center")
        ws.column_dimensions[get_column_letter(j)].width = w
    ws.row_dimensions[fila].height = 42


def paginas_pdf(fuentes, config):
    out = {}
    for f in fuentes:
        n = f.get("paginas_pdf")
        if n is None:
            try:
                n = pymupdf.open(ruta_pdf(f["id"], config)).page_count
            except Exception:
                n = None
        out[f["id"]] = n
    return out


def main() -> None:
    config = cargar_config()
    fuentes = [f for f in yaml.safe_load((RAIZ / "metadatos" / "fuentes.yaml").read_text(encoding="utf-8"))["publicaciones"]]
    paginas = paginas_pdf(fuentes, config)
    pubs = {}
    for f in fuentes:
        pubs.setdefault(f["censo"], []).append(f["id"])

    cat = pd.read_csv(RAIZ / "metadatos" / "catalogo_cuadros.csv", dtype=str).fillna("")
    tab = pd.read_csv(RAIZ / "productos" / "tabulados" / "tabulados_publicaciones.csv", dtype=str).fillna("")
    tab["con_area"] = tab.area != "_T"
    tab["con_sexo"] = tab.sexo != "_T"
    cifras = (tab.groupby(["censo", "fuente_id", "cuadro", "territorio_nivel", "con_area", "con_sexo"])
              .agg(cifras=("valor", "size"), con_valor=("valor", lambda x: (x != "").sum()),
                   inconsistentes=("estado_valor", lambda x: (x == "inconsistente").sum()))
              .reset_index())

    wb = Workbook()

    # --- Cifras ---------------------------------------------------------------------------
    wc = wb.active
    wc.title = "Cifras"
    tit = ["Censo", "Publicación", "Cuadro", "Nivel territorial", "Con área", "Con sexo",
           "Cifras", "Con valor", "Inconsistentes"]
    cabecera(wc, 1, tit, [8, 14, 9, 16, 10, 10, 10, 10, 14])
    for i, r in enumerate(cifras.itertuples(index=False), 2):
        vals = [int(r.censo), r.fuente_id, r.cuadro, r.territorio_nivel, "Sí" if r.con_area else "No",
                "Sí" if r.con_sexo else "No", int(r.cifras), int(r.con_valor), int(r.inconsistentes)]
        for j, v in enumerate(vals, 1):
            c = wc.cell(i, j, v)
            c.font = F_NORMAL
            if j >= 7:
                c.number_format = MILES
    n_cif = len(cifras) + 1
    wc.freeze_panes = "A2"
    wc.auto_filter.ref = f"A1:I{n_cif}"
    rng = lambda col: f"Cifras!${col}$2:${col}${n_cif}"

    # --- Catálogo -------------------------------------------------------------------------
    wk = wb.create_sheet("Catálogo")
    cols = list(cat.columns)
    cabecera(wk, 1, cols, [12, 8, 30, 8, 70, 9, 10, 10, 12, 11, 60])
    for i, r in enumerate(cat.itertuples(index=False), 2):
        for j, v in enumerate(r, 1):
            if cols[j - 1] in ("censo", "pagina_pdf") and v.isdigit():
                v = int(v)
            wk.cell(i, j, v).font = F_NORMAL
    n_cat = len(cat) + 1
    wk.freeze_panes = "A2"
    wk.auto_filter.ref = f"A1:{get_column_letter(len(cols))}{n_cat}"
    crng = lambda nombre: f"'Catálogo'!${get_column_letter(cols.index(nombre) + 1)}$2:${get_column_letter(cols.index(nombre) + 1)}${n_cat}"

    # --- Cuadros transcritos --------------------------------------------------------------
    wt = wb.create_sheet("Cuadros transcritos")
    tit = ["Censo de la publicación", "Publicación", "Cuadro", "Título", "Páginas del PDF", "Censos que cubre",
           "Niveles territoriales", "Área", "Sexo", "Filas", "Cifras", "Inconsistentes anotadas", "Archivo"]
    cabecera(wt, 1, tit, [11, 13, 8, 60, 12, 22, 30, 7, 7, 8, 10, 13, 42])
    fila = 2
    for meta_ruta in sorted((RAIZ / "digitalizacion").rglob("*.yaml")):
        meta = yaml.safe_load(meta_ruta.read_text(encoding="utf-8"))
        sub = tab[(tab.fuente_id == meta["fuente_id"]) & (tab.cuadro == str(meta["cuadro"]))]
        with meta_ruta.with_suffix(".csv").open(encoding="utf-8") as fh:
            n_filas = sum(1 for _ in csv.DictReader(fh))
        pdfs = [p["pdf"] for p in meta["paginas"]]
        censos = sorted(set(sub.censo.astype(int)))
        niveles = [NOMBRE_NIVEL.get(n, n) for n in NIVELES[::-1] if n in set(sub.territorio_nivel)]
        rel = meta_ruta.relative_to(RAIZ).with_suffix(".csv").as_posix()
        vals = [int(meta_ruta.parent.name), meta["fuente_id"], str(meta["cuadro"]), meta["titulo"],
                f"{min(pdfs)}–{max(pdfs)}" if len(pdfs) > 1 else str(pdfs[0]),
                ", ".join(map(str, censos)) if len(censos) <= 3 else f"{censos[0]}–{censos[-1]} ({len(censos)} censos)",
                ", ".join(niveles), "Sí" if sub.con_area.any() else "No", "Sí" if sub.con_sexo.any() else "No",
                n_filas,
                f'=SUMIFS({rng("G")},{rng("B")},B{fila},{rng("C")},C{fila})',
                f'=SUMIFS({rng("I")},{rng("B")},B{fila},{rng("C")},C{fila})',
                rel]
        for j, v in enumerate(vals, 1):
            c = wt.cell(fila, j, v)
            c.font = F_NORMAL
            c.alignment = Alignment(wrap_text=j in (4, 6, 7), vertical="top")
            if j in (10, 11, 12):
                c.number_format = MILES
        fila += 1
    n_tr = fila - 1
    wt.cell(fila, 1, "Total").font = F_BOLD
    for j in (10, 11, 12):
        col = get_column_letter(j)
        c = wt.cell(fila, j, f"=SUM({col}2:{col}{n_tr})")
        c.font, c.number_format, c.fill = F_BOLD, MILES, FILL_TOTAL
    wt.freeze_panes = "A2"
    wt.auto_filter.ref = f"A1:M{n_tr}"

    # --- Resumen --------------------------------------------------------------------------
    ws = wb.create_sheet("Resumen", 0)
    ws["A1"] = "Estado de avance de la digitalización de los censos históricos (1813–1982)"
    ws["A1"].font = F_TITULO
    ws["A2"] = (f"Generado el {dt.date.today():%d-%m-%Y} con herramientas/resumen_avance.py. Conteos y niveles: "
                "fórmulas sobre las hojas Catálogo y Cifras. Columnas en azul: escritas a mano. Ver la hoja Notas.")
    ws["A2"].font = F_NOTA
    tit = ["Censo", "Publicaciones", "Páginas del PDF", "Entradas en el catálogo", "Cuadros", "Bloques", "Textos",
           "Página del PDF verificada", "Página del PDF estimada", "Página sin ubicar o ausente",
           "Cuadros transcritos de la publicación", "Cifras digitalizadas del censo",
           "Nivel más fino: total", "Nivel más fino: área", "Nivel más fino: área × sexo",
           "Cifras inconsistentes anotadas", "Estado", "Pendiente / próximo paso", "Observaciones"]
    cabecera(ws, 4, tit, [8, 16, 10, 11, 9, 9, 8, 11, 11, 11, 12, 12, 14, 14, 14, 12, 24, 48, 60])
    ws.row_dimensions[4].height = 56
    c_censo, c_tipo, c_est_pdf, c_estado = crng("censo"), crng("tipo"), crng("pagina_pdf_estado"), crng("estado")

    def nivel_mas_fino(fila, area=False, sexo=False):
        cond = f'{rng("A")},$A{fila}'
        if area:
            cond += f',{rng("E")},"Sí"'
        if sexo:
            cond += f',{rng("F")},"Sí"'
        f = '"—"'
        for n in NIVELES[::-1]:
            f = f'IF(COUNTIFS({cond},{rng("D")},"{n}")>0,"{NOMBRE_NIVEL[n]}",{f})'
        return "=" + f

    primera = 5
    for i, censo in enumerate(CENSOS):
        r = primera + i
        estado, pendiente, obs = ESTADO[censo]
        ids = pubs.get(censo, [])
        pags = [paginas.get(x) for x in ids]
        vals = [
            censo,
            ", ".join(ids) if ids else "—",
            sum(p for p in pags if p) if ids else None,
            f"=COUNTIFS({c_censo},$A{r})",
            f'=COUNTIFS({c_censo},$A{r},{c_tipo},"cuadro")',
            f'=COUNTIFS({c_censo},$A{r},{c_tipo},"bloque")',
            f'=COUNTIFS({c_censo},$A{r},{c_tipo},"texto")',
            f'=COUNTIFS({c_censo},$A{r},{c_est_pdf},"verificada")',
            f'=COUNTIFS({c_censo},$A{r},{c_est_pdf},"estimada")',
            f'=COUNTIFS({c_censo},$A{r},{c_est_pdf},"desconocida")+COUNTIFS({c_censo},$A{r},{c_est_pdf},"ausente")',
            f'=COUNTIFS({c_censo},$A{r},{c_estado},"transcrito")',
            f'=SUMIFS({rng("G")},{rng("A")},$A{r})',
            nivel_mas_fino(r),
            nivel_mas_fino(r, area=True),
            nivel_mas_fino(r, area=True, sexo=True),
            f'=SUMIFS({rng("I")},{rng("A")},$A{r})',
            estado, pendiente, obs,
        ]
        for j, v in enumerate(vals, 1):
            c = ws.cell(r, j, v)
            c.font = F_INPUT if j >= 17 else F_NORMAL
            c.border = BORDE
            c.alignment = Alignment(wrap_text=j in (2, 18, 19), vertical="top",
                                    horizontal="center" if 3 <= j <= 16 or j == 1 else None)
            if 3 <= j <= 12 or j == 16:
                c.number_format = MILES
        ws.cell(r, 17).fill = PatternFill("solid", fgColor=COLOR_ESTADO[estado])
    ultima = primera + len(CENSOS) - 1
    t = ultima + 1
    ws.cell(t, 1, "Total").font = F_BOLD
    for j in list(range(3, 13)) + [16]:
        col = get_column_letter(j)
        c = ws.cell(t, j, f"=SUM({col}{primera}:{col}{ultima})")
        c.font, c.number_format, c.fill = F_BOLD, MILES, FILL_TOTAL
        c.alignment = Alignment(horizontal="center")
    ws.cell(t + 1, 1, "Las cifras se cuentan por el censo al que se refieren, aunque vengan de la publicación de otro "
                      "censo: p. ej., 1865 tiene cifras de 1920 C1 y 1952 C9 sin tener cuadros transcritos de su "
                      "propia publicación. El catálogo de 1992 (9 entradas) no se incluye.").font = F_NOTA
    # Resaltar los niveles "—" (sin cifras) en gris
    gris = Font(name=ARIAL, size=10, color="A6A6A6")
    ws.conditional_formatting.add(f"M{primera}:O{ultima}",
                                  FormulaRule(formula=[f'M{primera}="—"'], font=gris))
    ws.freeze_panes = ws.cell(primera, 2)

    # Leyenda de estados
    fl = t + 3
    ws.cell(fl, 1, "Estados").font = F_BOLD
    leyenda = {
        "Núcleo completo": "Población por territorio × área × sexo transcrita bajo el nivel de provincia.",
        "Núcleo por provincia": "Población por provincia × área × sexo transcrita.",
        "Parcial": "Hay cifras por territorio y área, pero falta sexo o falta bajar de provincia.",
        "Serie desde otros censos": "Cifras tomadas de cuadros comparativos de censos posteriores; "
                                    "la publicación propia aún no se transcribe.",
        "Catalogado": "Cuadros catalogados; sin cifras transcritas.",
        "Sin publicación": "No hay publicación digitalizada.",
    }
    for k, (e, d) in enumerate(leyenda.items(), 1):
        c = ws.cell(fl + k, 1, e)
        c.font, c.fill = F_NORMAL, PatternFill("solid", fgColor=COLOR_ESTADO[e])
        ws.merge_cells(start_row=fl + k, start_column=1, end_row=fl + k, end_column=3)
        ws.cell(fl + k, 4, d).font = F_NORMAL

    # --- Notas ----------------------------------------------------------------------------
    wn = wb.create_sheet("Notas")
    wn.column_dimensions["A"].width = 30
    wn.column_dimensions["B"].width = 110
    notas = [
        ("Fuentes", ""),
        ("Catálogo", "metadatos/catalogo_cuadros.csv (cuadros, bloques por provincia y textos de cada publicación)."),
        ("Cifras", "productos/tabulados/tabulados_publicaciones.csv, generado por pipelines/tabulados_publicaciones.py "
                   "desde los cuadros transcritos en digitalizacion/."),
        ("Páginas del PDF", "metadatos/fuentes.yaml (paginas_pdf) o, si falta, el conteo del PDF."),
        ("Estado y pendientes", "Escritos a mano desde docs/estado.md y docs/digitalizacion.md (texto en azul)."),
        ("", ""),
        ("Definiciones", ""),
        ("Bloque", "Conjunto de cuadros de una provincia sin índice propio (se catalogó el bloque, no cada cuadro)."),
        ("Página del PDF", "verificada = vista en la imagen; estimada = interpolada desde la página impresa; "
                           "sin ubicar = desconocida; ausente = falta en el escaneo."),
        ("Cifras digitalizadas del censo", "Todas las cifras referidas a ese censo, de cualquier publicación. Incluye "
                                           "las celdas sin dato impresas como «-» o «..»."),
        ("Nivel más fino", "Nivel territorial más desagregado con cifras: total (sin área ni sexo), con área "
                           "urbana/rural, y con área × sexo."),
        ("Cifras inconsistentes", "Cifras transcritas tal como están impresas que no cuadran con sus totales "
                                  "(erratas de la publicación), anotadas en el YAML de cada cuadro."),
        ("", ""),
        ("Fuera de esta planilla", "1992 a 2024 se trabajan desde microdatos (ver docs/estado.md)."),
    ]
    for i, (a, b) in enumerate(notas, 1):
        wn.cell(i, 1, a).font = F_BOLD if not b else F_NORMAL
        c = wn.cell(i, 2, b)
        c.font, c.alignment = F_NORMAL, Alignment(wrap_text=True, vertical="top")
        if a and not b:
            wn.cell(i, 1).font = Font(name=ARIAL, size=11, bold=True)

    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    wb.save(SALIDA)
    print(SALIDA.relative_to(RAIZ).as_posix())


if __name__ == "__main__":
    main()
