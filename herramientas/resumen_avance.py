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

# Estado, pendiente y observaciones de cada censo (escritos a mano). El núcleo es la población
# por territorio × área × sexo × edad: la estructura demográfica básica.
ESTADO = {
    1813: ("Parcial",
           "Opcional: edades por distrito desde los «Censo de territorio» (bloques). Santiago no está en la edición; Concepción solo con matrículas de 1812.",
           "Partido × sexo × edad (5 tramos) y × estado civil, y distrito × sexo, de los 14 partidos de Copiapó a Talca (cobertura parcial del país). Totales validados con el estado civil; en 8 partidos las edades no suman el total y en 4 los distritos tampoco (impreso así)."),
    1835: ("Parcial",
           "Nada más en el PDF para el núcleo: no trae edad ni área. Opcional: subdelegaciones de Santiago (PDF 93).",
           "Departamento × sexo × estado (solteros/casados) desde la propia publicación (arts. 34–42), validado con los sinópticos de 1865 y 1875 (salvo Cauquenes, +2). Sin edad en la publicación."),
    1843: ("Sin publicación",
           "Nada más en los PDF disponibles (solo totales por departamento y provincia).",
           "Sin publicación digitalizada. Departamento y provincia (totales) desde los sinópticos de 1865 y 1875, que coinciden entre sí."),
    1854: ("Sin publicación",
           "Opcional: contrastar con el resumen general de 1907 (PDF 1222). Buscar un ejemplar digitalizado.",
           "Sin publicación digitalizada. Departamento y provincia (totales) desde los sinópticos de 1865 y 1875, que coinciden entre sí."),
    1865: ("Serie desde otros censos",
           "Parroquia × sexo × edad (pág. 386, PDF 419) y subdelegación/distrito × sexo × edad desde los bloques provinciales (p. ej. Coquimbo, PDF 302).",
           "Departamento × sexo × edad en 6 tramos (pág. 352) y provincia × sexo × edad (pág. 360) desde la propia publicación; valida 1952 C5 y C6. Departamento (total) desde su sinóptico, validado con el de 1875; provincia × área (1952 C9). Escaneo malo: cifras dudosas fijadas con sumas por fila y por provincia. Errata: Caupolicán 16–25 hombres."),
    1875: ("Serie desde otros censos", "Validar 1952 C5 y C6 contra la clasificación urbana y rural por departamentos y "
                                       "provincias según sexo y edad (pág. 601, PDF ~617), que además cruza área × sexo.",
           "Provincia × área (1952 C9) y provincia × sexo × edad en 6 tramos (1952 C5 y C6); departamento (total) "
           "desde 1920 C1."),
    1885: ("Serie desde otros censos", "Sexo × edad por provincia: clasificación por departamentos y provincias "
                                       "(pág. 839, PDF ~873); validar con ella 1952 C5 y C7.",
           "El PDF trae solo el tomo I de 2. Provincia × área (1952 C9) y × sexo (1952 C5); edad del país en decenios "
           "(1952 C7); departamento desde 1920 C1. Malleco: 3 000 personas sin sexo (1952 C5)."),
    1895: ("Serie desde otros censos", "Sexo × edad por provincia: clasificación por departamentos y provincias, tomo IV "
                                       "(pág. 467, PDF ~2457); validar con ella 1952 C5 y C7.",
           "Departamento × área desde 1920 C3 (con departamentos agrupados); provincia × área (1930 C10, 1952 C9) y "
           "× sexo (1952 C5); edad del país en decenios (1952 C7)."),
    1907: ("Parcial", "Área × sexo y sexo × edad por provincia y departamento: resúmenes por provincia del volumen de "
                      "1907 (bloques).",
           "Departamento × área desde 1920 C1 y C3; provincia × sexo (1952 C5); área × sexo (1930 C9) y edad en "
           "decenios (1952 C7) solo para el país."),
    1920: ("Falta edad", "Edad: estado civil por edad y sexo (págs. 235–275, PDF ~250); revisar su nivel territorial.",
           "Departamento × área × sexo (Cuadro 4); edad del país en decenios (1952 C7). El Cuadro 3 tiene seis "
           "cifras de 1920 que no cuadran: usar el Cuadro 4."),
    1930: ("Falta edad", "Edad: el volumen disponible no trae cuadros por edad; buscar otra publicación de 1930.",
           "Comuna × área × sexo (Cuadro 9); edad del país en decenios (1952 C7). Errata en el total de Atacama."),
    1940: ("Falta edad", "Edad: población por edades individuales, sexo y provincias (pág. 8, PDF ~14) o por grupos "
                         "de edades (pág. 332, PDF ~338).",
           "Comuna × área × sexo, con viviendas; edad del país en decenios (1952 C7). Cifras ajustadas (~2,8 %); las "
           "revisadas están en 1952 C5, C9 y 1960 C1.1.1."),
    1952: ("Parcial", "Comuna: Tomo I (Cuadro 4) y Tomo II (Cuadro 1). Sexo × edad × área: el nacional 1 falta en el "
                      "escaneo; el Cuadro 1 del Tomo II la trae por comuna para el Núcleo Central.",
           "Provincia × área (C9, 1960 C1.1.1) y × sexo (C5); edad del país en decenios con edad ignorada (C7). "
           "Faltan en el escaneo las págs. 85–116 (cuadros nacionales 1 y 2)."),
    1960: ("Falta edad", "Edad: 1.2.1 grupos de edades por provincias (PDF ~144); 1.3 área × sexo × años de edad "
                         "del país (PDF ~156).",
           "Provincia × área × sexo (Cuadro 1.2)."),
    1970: ("Catalogado", "Sexo × edad × área del país: Cuadro 3 (PDF 11). Buscar una publicación por provincia.",
           "El volumen «Total País» no trae cuadros por provincia de población por área."),
    1982: ("Núcleo completo",
           "Nada más para el núcleo en los volúmenes publicados (la edad solo viene para el país). Tomos II y III: ocupación, educación, vivienda, hogar y familia (módulos temáticos).",
           "Región, provincia y comuna × área × sexo (Cuadro 1.01); país × área × sexo × edad simple (Cuadro 1.03, 1.089 cifras, todas las sumas cuadran). Los volúmenes no traen edad bajo el nivel país."),
}
COLOR_ESTADO = {
    "Núcleo completo": "C6EFCE", "Falta edad": "DDEBF7", "Parcial": "FFEB9C",
    "Serie desde otros censos": "FCE4D6", "Catalogado": "EDEDED", "Sin publicación": "D9D9D9",
}
NIVELES = ["distrito", "comuna", "partido", "departamento", "provincia", "region", "pais"]  # de más fino a más grueso
# Niveles del catálogo (metadatos/catalogo_cuadros.csv, columna nivel_territorial), de más fino a más grueso.
NIVELES_PDF = ["entidad", "distrito", "comuna", "parroquia", "partido", "departamento", "provincia", "region", "pais"]
NOMBRE_NIVEL = {"entidad": "Entidad", "distrito": "Distrito", "comuna": "Comuna", "parroquia": "Parroquia", "partido": "Partido",
                "departamento": "Departamento", "provincia": "Provincia", "region": "Región", "pais": "País"}
DESAGREGACIONES = {"Total": [], "Área": ["area"], "Área × sexo": ["area", "sexo"], "Sexo × edad": ["sexo", "edad"]}

ARIAL = "Arial"
F_NORMAL = Font(name=ARIAL, size=10)
F_INPUT = Font(name=ARIAL, size=10, color="0000FF")
F_TITULO = Font(name=ARIAL, size=14, bold=True)
F_HEAD = Font(name=ARIAL, size=10, bold=True, color="FFFFFF")
F_BOLD = Font(name=ARIAL, size=10, bold=True)
F_NOTA = Font(name=ARIAL, size=9, italic=True, color="595959")
FILL_HEAD = PatternFill("solid", fgColor="1F4E78")
FILL_TOTAL = PatternFill("solid", fgColor="F2F2F2")
FILL_HEAD_PDF = PatternFill("solid", fgColor="2E75B6")
FILL_PDF = PatternFill("solid", fgColor="F3F8FC")
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
    tab["con_edad"] = tab.edad_min != ""
    cifras = (tab.groupby(["censo", "fuente_id", "cuadro", "territorio_nivel", "con_area", "con_sexo", "con_edad"])
              .agg(cifras=("valor", "size"), con_valor=("valor", lambda x: (x != "").sum()),
                   inconsistentes=("estado_valor", lambda x: (x == "inconsistente").sum()))
              .reset_index())

    wb = Workbook()

    # --- Cifras ---------------------------------------------------------------------------
    wc = wb.active
    wc.title = "Cifras"
    tit = ["Censo", "Publicación", "Cuadro", "Nivel territorial", "Con área", "Con sexo", "Con edad",
           "Cifras", "Con valor", "Inconsistentes"]
    cabecera(wc, 1, tit, [8, 14, 9, 16, 10, 10, 10, 10, 10, 14])
    for i, r in enumerate(cifras.itertuples(index=False), 2):
        vals = [int(r.censo), r.fuente_id, r.cuadro, r.territorio_nivel, "Sí" if r.con_area else "No",
                "Sí" if r.con_sexo else "No", "Sí" if r.con_edad else "No", int(r.cifras), int(r.con_valor), int(r.inconsistentes)]
        for j, v in enumerate(vals, 1):
            c = wc.cell(i, j, v)
            c.font = F_NORMAL
            if j >= 8:
                c.number_format = MILES
    n_cif = len(cifras) + 1
    wc.freeze_panes = "A2"
    wc.auto_filter.ref = f"A1:J{n_cif}"
    rng = lambda col: f"Cifras!${col}$2:${col}${n_cif}"

    # --- Catálogo -------------------------------------------------------------------------
    wk = wb.create_sheet("Catálogo")
    cols = list(cat.columns)
    for i, r in enumerate(cat.itertuples(index=False), 2):
        for j, v in enumerate(r, 1):
            if cols[j - 1] in ("censo", "pagina_pdf") and v.isdigit():
                v = int(v)
            wk.cell(i, j, v).font = F_NORMAL
    n_cat = len(cat) + 1
    # Hoja auxiliar con el orden de los niveles territoriales (1 = más fino) y la columna nivel_orden
    # del catálogo, para buscar el nivel más fino con MINIFS.
    wv = wb.create_sheet("Niveles")
    cabecera(wv, 1, ["Orden", "Nivel en el catálogo", "Nombre"], [8, 22, 16])
    for k, n in enumerate(NIVELES_PDF, 1):
        for j, v in enumerate((k, n, NOMBRE_NIVEL[n]), 1):
            wv.cell(k + 1, j, v).font = F_NORMAL
    n_niv = len(NIVELES_PDF) + 1
    col_nivel = get_column_letter(cols.index("nivel_territorial") + 1)
    col_orden = len(cols) + 1
    cabecera(wk, 1, cols + ["nivel_orden"], [12, 8, 30, 8, 70, 9, 10, 10, 12, 24, 14, 14, 11, 13, 11, 60, 11])
    for i in range(2, n_cat + 1):
        c = wk.cell(i, col_orden, f'=IFERROR(MATCH({col_nivel}{i},Niveles!$B$2:$B${n_niv},0),"")')
        c.font = F_NORMAL
    cols = cols + ["nivel_orden"]
    wk.freeze_panes = "A2"
    wk.auto_filter.ref = f"A1:{get_column_letter(len(cols))}{n_cat}"
    crng = lambda nombre: f"'Catálogo'!${get_column_letter(cols.index(nombre) + 1)}$2:${get_column_letter(cols.index(nombre) + 1)}${n_cat}"

    # --- Cuadros transcritos --------------------------------------------------------------
    wt = wb.create_sheet("Cuadros transcritos")
    tit = ["Censo de la publicación", "Publicación", "Cuadro", "Título", "Páginas del PDF", "Censos que cubre",
           "Niveles territoriales", "Área", "Sexo", "Edad", "Filas", "Cifras", "Inconsistentes anotadas", "Archivo"]
    cabecera(wt, 1, tit, [11, 13, 8, 60, 12, 22, 30, 7, 7, 7, 8, 10, 13, 42])
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
                "Sí" if sub.con_edad.any() else "No", n_filas,
                f'=SUMIFS({rng("H")},{rng("B")},B{fila},{rng("C")},C{fila})',
                f'=SUMIFS({rng("J")},{rng("B")},B{fila},{rng("C")},C{fila})',
                rel]
        for j, v in enumerate(vals, 1):
            c = wt.cell(fila, j, v)
            c.font = F_NORMAL
            c.alignment = Alignment(wrap_text=j in (4, 6, 7), vertical="top")
            if j in (11, 12, 13):
                c.number_format = MILES
        fila += 1
    n_tr = fila - 1
    wt.cell(fila, 1, "Total").font = F_BOLD
    for j in (11, 12, 13):
        col = get_column_letter(j)
        c = wt.cell(fila, j, f"=SUM({col}2:{col}{n_tr})")
        c.font, c.number_format, c.fill = F_BOLD, MILES, FILL_TOTAL
    wt.freeze_panes = "A2"
    wt.auto_filter.ref = f"A1:N{n_tr}"

    # --- Resumen --------------------------------------------------------------------------
    ws = wb.create_sheet("Resumen", 0)
    ws["A1"] = "Estado de avance de la digitalización de los censos históricos (1813–1982)"
    ws["A1"].font = F_TITULO
    ws["A2"] = (f"Generado el {dt.date.today():%d-%m-%Y} con herramientas/resumen_avance.py. Conteos y niveles: "
                "fórmulas sobre las hojas Catálogo y Cifras. Columnas en azul: escritas a mano. Ver la hoja Notas.")
    ws["A2"].font = F_NOTA
    tit = ["Censo", "Publicaciones", "Páginas del PDF", "Entradas en el catálogo", "Cuadros", "Bloques", "Textos",
           "Página del PDF verificada", "Página del PDF estimada", "Página sin ubicar o ausente",
           "Cuadros transcritos de la publicación", "Cifras digitalizadas del censo"]
    anchos = [8, 16, 10, 11, 9, 9, 8, 11, 11, 11, 12, 12]
    for d in DESAGREGACIONES:
        tit += [f"{d}: transcrito", f"{d}: en los PDF"]
        anchos += [13, 15]
    tit += ["Cifras inconsistentes anotadas", "Estado", "Pendiente / próximo paso", "Observaciones"]
    anchos += [12, 20, 52, 60]
    cabecera(ws, 4, tit, anchos)
    ws.row_dimensions[4].height = 56
    c_niv = 13  # primera columna de niveles
    c_inc = c_niv + 2 * len(DESAGREGACIONES)
    c_est = c_inc + 1
    for k in range(len(DESAGREGACIONES)):
        ws.cell(4, c_niv + 2 * k + 1).fill = FILL_HEAD_PDF
    c_censo, c_tipo, c_est_pdf, c_estado = crng("censo"), crng("tipo"), crng("pagina_pdf_estado"), crng("estado")
    c_censos, c_vars, c_cob, c_orden = crng("censos_datos"), crng("variables"), crng("cobertura"), crng("nivel_orden")

    def nivel_transcrito(fila, variables):
        cond = f'{rng("A")},$A{fila}'
        for v, col in (("area", "E"), ("sexo", "F"), ("edad", "G")):
            if v in variables:
                cond += f',{rng(col)},"Sí"'
        f = '"—"'
        for n in NIVELES[::-1]:
            f = f'IF(COUNTIFS({cond},{rng("D")},"{n}")>0,"{NOMBRE_NIVEL[n]}",{f})'
        return "=" + f

    def nivel_pdf(fila, variables):
        """Nivel más fino con esas variables en algún cuadro del catálogo que cubra el país; si no hay,
        el de algún cuadro que cubra solo parte del país, marcado "(parcial)"."""
        def orden(cobertura):  # orden del nivel más fino (0 = ninguno): primer orden con algún cuadro
            cond = f'{c_censos},"*"&$A{fila}&"*",{c_est_pdf},"<>ausente",{c_cob},"{cobertura}"'
            for v in variables:
                cond += f',{c_vars},"*{v}*"'
            ordenes = "{" + ",".join(str(k) for k in range(1, len(NIVELES_PDF) + 1)) + "}"
            return f"IFERROR(MATCH(TRUE,COUNTIFS({cond},{c_orden},{ordenes})>0,0),0)"
        nombre = lambda o: f"INDEX(Niveles!$C$2:$C${n_niv},{o})"
        c, p = orden("completa"), orden("parcial")
        extra = f'IF(AND({p}>0,{p}<{c}),"; "&LOWER({nombre(p)})&" (parcial)","")'
        return f'=IF({c}>0,{nombre(c)}&{extra},IF({p}>0,{nombre(p)}&" (parcial)","—"))'

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
            f'=SUMIFS({rng("H")},{rng("A")},$A{r})',
        ]
        for variables in DESAGREGACIONES.values():
            vals += [nivel_transcrito(r, variables), nivel_pdf(r, variables)]
        vals += [f'=SUMIFS({rng("J")},{rng("A")},$A{r})', estado, pendiente, obs]
        for j, v in enumerate(vals, 1):
            c = ws.cell(r, j, v)
            c.font = F_INPUT if j >= c_est else F_NORMAL
            c.border = BORDE
            c.alignment = Alignment(wrap_text=j in (2, c_est + 1, c_est + 2) or c_niv <= j < c_inc, vertical="top",
                                    horizontal="center" if j <= c_inc and j != 2 else None)
            if 3 <= j <= 12 or j == c_inc:
                c.number_format = MILES
            if c_niv <= j < c_inc and (j - c_niv) % 2 == 1:
                c.fill = FILL_PDF
        ws.cell(r, c_est).fill = PatternFill("solid", fgColor=COLOR_ESTADO[estado])
    ultima = primera + len(CENSOS) - 1
    t = ultima + 1
    ws.cell(t, 1, "Total").font = F_BOLD
    for j in list(range(3, 13)) + [c_inc]:
        col = get_column_letter(j)
        c = ws.cell(t, j, f"=SUM({col}{primera}:{col}{ultima})")
        c.font, c.number_format, c.fill = F_BOLD, MILES, FILL_TOTAL
        c.alignment = Alignment(horizontal="center")
    ws.cell(t + 1, 1, "Las cifras se cuentan por el censo al que se refieren, aunque vengan de la publicación de otro "
                      "censo: p. ej., 1865 tiene cifras de 1920 C1 y 1952 C9 sin tener cuadros transcritos de su "
                      "propia publicación. El catálogo de 1992 (9 entradas) no se incluye.").font = F_NOTA
    ws.cell(t + 2, 1, "«Transcrito»: nivel más fino ya digitalizado. «En los PDF»: nivel más fino que traen las "
                      "publicaciones según el catálogo (incluidos los cuadros comparativos de censos posteriores); "
                      "«(parcial)» = solo para parte del país; si para parte del país hay un nivel más fino que para el país "
                      "completo, se muestran ambos.").font = F_NOTA
    # Resaltar los niveles "—" (sin cifras) en gris
    gris = Font(name=ARIAL, size=10, color="A6A6A6")
    ini, fin = get_column_letter(c_niv), get_column_letter(c_inc - 1)
    ws.conditional_formatting.add(f"{ini}{primera}:{fin}{ultima}",
                                  FormulaRule(formula=[f'{ini}{primera}="—"'], font=gris))
    ws.freeze_panes = ws.cell(primera, 2)

    # Leyenda de estados
    fl = t + 3
    ws.cell(fl, 1, "Estados").font = F_BOLD
    leyenda = {
        "Núcleo completo": "Población por territorio × área × sexo × edad transcrita al nivel más fino que traen los PDF.",
        "Falta edad": "Población por territorio × área × sexo transcrita; falta la edad.",
        "Parcial": "Hay cifras por territorio y área, pero falta sexo (salvo para el país) o falta bajar de provincia.",
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
        ("Núcleo", "Población por territorio × área × sexo × edad: la estructura demográfica básica de cada censo."),
        ("Nivel más fino: transcrito", "Nivel territorial más desagregado con cifras ya digitalizadas: total (sin "
                                       "área ni sexo), con área urbana/rural, con área × sexo y con sexo × edad."),
        ("Nivel más fino: en los PDF", "Nivel más desagregado que traen las publicaciones, según las columnas "
                                       "censos_datos, nivel_territorial, variables y cobertura del catálogo (solo "
                                       "cuadros de población; no cuenta las páginas ausentes del escaneo). "
                                       "«(parcial)» = solo hay cuadros para parte del país. Orden de los niveles: "
                                       "entidad, distrito, comuna, parroquia, departamento, provincia, región, país."),
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
