"""Capa 1 de los microdatos: mismo contenido que los archivos originales, en una forma común.

Lee los archivos originales (carpeta `datos_originales` de config.yaml) según las fichas de
metadatos/estructura/<censo>.yaml y escribe, en la carpeta `estandarizado`:

  <censo>/viviendas.parquet, hogares.parquet, personas.parquet   (todos los censos)
  <censo>/piezas.parquet                                        (1992)
  <censo>/portafolios.parquet                                   (1992 y 2002: tabla geográfica)
  <censo>/enlaces/<tabla>.parquet                               (vínculo con el archivo original)
  manifiesto.csv                                                (filas, columnas, md5, origen)

y en el repositorio metadatos/estructura/variables_estandarizadas.csv (cada columna de la capa 1
con su tabla y variable originales). Reglas en docs/estructura_microdatos.md:
  - columnas comunes al inicio: censo, id_vivienda, id_hogar, id_persona, n_hogar, n_persona,
    hogar_ficticio y el bloque geográfico region, provincia, comuna, area, distrito;
  - id_hogar = id_vivienda * 100 + n_hogar; id_persona = id_hogar * 10000 + n_persona;
    id_pieza e id_portafolio, correlativos en el orden de la clave original;
  - lo que vincula con el original (fila_origen y la clave original) va solo al archivo de
    enlace de cada tabla, con una fila por fila de la tabla y su mismo identificador;
  - nombres originales en minúsculas ASCII; los códigos se conservan tal cual (solo el vacío
    y el NA de las exportaciones de R pasan a NULL); enteros con el tipo más chico que alcance.

Uso:
  python pipelines/estandarizar_microdatos.py            # todos los censos
  python pipelines/estandarizar_microdatos.py 1992 2017  # solo algunos
"""

from __future__ import annotations

import csv
import hashlib
import sys
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipelines.comun import (RAIZ, actualizar_csv, commit_actual, conectar, ident, leer_config,  # noqa: E402
                             leer_yaml, literal, mensaje, nombre_estandar, ruta_sql, uno, escribir_parquet)

CENSOS = ["1992", "2002", "2017", "2024"]
GEOGRAFIA = {"region": "SMALLINT", "provincia": "SMALLINT", "comuna": "INTEGER",
             "area": "SMALLINT", "distrito": "SMALLINT"}
RESERVADOS = {"censo", "id_vivienda", "id_hogar", "id_persona", "id_pieza", "id_portafolio", "n_hogar",
              "n_persona", "n_pieza", "hogar_ficticio", "fila_origen", "n_personas", *GEOGRAFIA}
MULT_HOGAR = 100        # n_hogar máximo observado: 92 (2002)
MULT_PERSONA = 10_000   # n_persona máximo observado: 7.473 (2002)
# Las exportaciones desde R escriben algunos enteros en notación científica (100000 -> "1e+05").
PATRON_CIENTIFICO = r"[0-9](\.[0-9]+)?e\+[0-9]+"
MAPA = RAIZ / "metadatos" / "estructura" / "variables_estandarizadas.csv"


@dataclass
class Origen:
    """Archivo original cargado como tabla de texto. `fila` = expresión con la fila del archivo
    (1 = primera fila de datos)."""
    nombre: str
    tabla: str
    columnas: list[str]
    fila: str = "rowid + 1"
    tipos: dict[str, str] = field(default_factory=dict)


@dataclass
class Columna:
    """Columna de salida: expresión SQL y su registro en variables_estandarizadas.csv."""
    expr: str
    variable: str
    tipo: str
    rol: str
    tabla_original: str = ""
    variable_original: str = ""


def nombre_columna(col: str) -> str:
    """Nombre estandarizado de una columna original; `_orig` si choca con una columna común."""
    nombre = nombre_estandar(col)
    return nombre + "_orig" if nombre in RESERVADOS else nombre


def claves_tabla(t: dict) -> list[str]:
    """Columnas de la clave original de una tabla de la ficha de estructura."""
    return [*t["vivienda"], *(t[r] for r in ("hogar", "persona", "pieza") if r in t)]


# --- Lectura de los CSV originales ----------------------------------------------------------

def leer_encabezado(ruta: Path) -> tuple[str, list[str]]:
    """Separador y nombres de columna de la primera línea (UTF-8 o latin-1)."""
    with ruta.open("rb") as f:
        crudo = f.readline()
    try:
        texto = crudo.decode("utf-8")
    except UnicodeDecodeError:
        texto = crudo.decode("latin-1")
    texto = texto.lstrip("﻿").rstrip("\r\n")
    sep = ";" if texto.count(";") > texto.count(",") else ","
    nombres = next(csv.reader([texto], delimiter=sep))
    # Las exportaciones desde R traen una primera columna sin nombre con el número de fila.
    return sep, [n or "_fila" for n in nombres]


def lineas_extremas(ruta: Path, sep: str) -> tuple[list[str], list[str]]:
    """Primera y última fila de datos, separadas en campos."""
    with ruta.open("rb") as f:
        f.readline()
        primera = f.readline()
        f.seek(max(0, ruta.stat().st_size - 65536))
        ultima = [l for l in f.read().splitlines() if l.strip()][-1]
    partir = lambda b: next(csv.reader([b.decode("latin-1")], delimiter=sep))  # noqa: E731
    return partir(primera.rstrip(b"\r\n")), partir(ultima)


class Estandarizador:
    def __init__(self, censo: str, config: dict):
        self.censo = censo
        self.config = config
        self.est = leer_yaml(RAIZ / "metadatos" / "estructura" / f"{censo}.yaml")
        self.rutas = {k: Path(config["datos_originales"]) / v for k, v in config["microdatos"][int(censo)].items()}
        self.nulos = self.est.get("valores_nulos") or []
        self.excluir = self.est.get("excluir") or []
        self.cientifica = bool(self.est.get("notacion_cientifica"))
        self.geo = self.est.get("geografia")
        self.salida = Path(config["estandarizado"]) / censo
        self.origenes: dict[str, Origen] = {}
        self.mapa: list[dict] = []
        self.manifiesto: list[dict] = []

    # --- SQL de valores ---------------------------------------------------------------------

    def es_nulo(self, c: str) -> str:
        if not self.nulos:
            return f"({c} IS NULL)"
        return f"({c} IS NULL OR {c} IN ({', '.join(literal(n) for n in self.nulos)}))"

    def a_entero(self, c: str) -> str:
        if not self.cientifica:
            return f"TRY_CAST({c} AS BIGINT)"
        return (f"CASE WHEN contains({c}, 'e+') THEN TRY_CAST(TRY_CAST({c} AS DOUBLE) AS BIGINT) "
                f"ELSE TRY_CAST({c} AS BIGINT) END")

    def valor(self, alias: str, origen: Origen, col: str) -> str:
        """Valor tipado de una columna original (NULL para los valores nulos de la ficha)."""
        c = f"{alias}.{ident(col)}"
        v = f"CASE WHEN {self.es_nulo(c)} THEN NULL ELSE {c} END"
        tipo = origen.tipos[col]
        if tipo == "VARCHAR":
            return v
        if self.cientifica:
            v = f"CASE WHEN contains({c}, 'e+') THEN CAST(CAST({c} AS DOUBLE) AS BIGINT)::VARCHAR ELSE {v} END"
        return f"CAST({v} AS {tipo})"

    # --- Carga y tipos ------------------------------------------------------------------------

    def cargar(self, nombre: str) -> Origen:
        ruta = self.rutas[nombre]
        tabla = f"src_{nombre}"
        mensaje(f"[{self.censo}] cargando {ruta.name}")
        if ruta.suffix.lower() == ".parquet":
            cols = [r[0] for r in self.con.execute(f"DESCRIBE SELECT * FROM read_parquet({ruta_sql(ruta)})").fetchall()]
            lista = ", ".join(f"{ident(c)}::VARCHAR AS {ident(c)}" for c in cols)
            self.con.execute(f"""CREATE TABLE {tabla} AS SELECT file_row_number + 1 AS _fila_parquet, {lista}
                                 FROM read_parquet({ruta_sql(ruta)}, file_row_number = true)""")
            origen = Origen(nombre, tabla, cols, fila="_fila_parquet")
        else:
            sep, cols = leer_encabezado(ruta)
            tipos = ", ".join(f"{literal(c)}: 'VARCHAR'" for c in cols)
            self.con.execute(f"""CREATE TABLE {tabla} AS SELECT * FROM read_csv({ruta_sql(ruta)},
                                 delim = {literal(sep)}, quote = '"', escape = '"', header = false, skip = 1,
                                 auto_detect = false, columns = {{{tipos}}})""")
            origen = Origen(nombre, tabla, cols)
            self.comprobar_orden(origen, ruta, sep)
        self.inferir_tipos(origen)
        return origen

    def comprobar_orden(self, origen: Origen, ruta: Path, sep: str) -> None:
        """El orden de inserción debe ser el del archivo: contrasta la primera y la última fila."""
        n = uno(self.con, f"SELECT count(*) FROM {origen.tabla}")
        extremos = self.con.execute(f"SELECT * FROM {origen.tabla} WHERE rowid IN (0, {n - 1}) ORDER BY rowid").fetchall()
        for fila, linea, num in zip(extremos, lineas_extremas(ruta, sep), (1, n)):
            if ["" if v is None else v for v in fila] != linea:
                sys.exit(f"{origen.nombre}: la fila {num} de la tabla no coincide con el archivo.")
        if "_fila" in origen.columnas:
            malas = uno(self.con, f'SELECT count(*) FROM {origen.tabla} WHERE "_fila"::BIGINT <> rowid + 1')
            if malas:
                sys.exit(f"{origen.nombre}: {malas} filas con _fila distinto del número de fila.")

    def inferir_tipos(self, origen: Origen) -> None:
        """Entero con el tipo más chico que alcance si todos los valores son enteros escritos sin
        ceros a la izquierda (o en notación científica de R); si no, texto. Así el valor del
        original se recupera exactamente."""
        partes = []
        for i, col in enumerate(origen.columnas):
            c = ident(col)
            nulo = self.es_nulo(c)
            entero = f"coalesce(TRY_CAST({c} AS BIGINT)::VARCHAR = {c}, false)"
            if self.cientifica:
                doble = f"TRY_CAST({c} AS DOUBLE)"
                entero = f"({entero} OR coalesce(regexp_full_match({c}, '{PATRON_CIENTIFICO}') AND {doble} = round({doble}), false))"
            partes += [f"bool_and({nulo} OR {entero})",
                       f"count(*) FILTER (WHERE NOT {nulo})",
                       f"min(CASE WHEN NOT {nulo} THEN {self.a_entero(c)} END)",
                       f"max(CASE WHEN NOT {nulo} THEN {self.a_entero(c)} END)"]
        r = self.con.execute(f"SELECT {', '.join(partes)} FROM {origen.tabla}").fetchone()
        for i, col in enumerate(origen.columnas):
            es_entero, validos, minimo, maximo = r[4 * i: 4 * i + 4]
            if not es_entero or not validos or minimo is None or maximo is None:
                tipo = "VARCHAR"
            elif -128 <= minimo and maximo <= 127:
                tipo = "TINYINT"
            elif -32768 <= minimo and maximo <= 32767:
                tipo = "SMALLINT"
            elif -2**31 <= minimo and maximo < 2**31:
                tipo = "INTEGER"
            else:
                tipo = "BIGINT"
            origen.tipos[col] = tipo

    # --- Columnas -----------------------------------------------------------------------------

    def originales(self, origen: Origen, alias: str, omitir, rol: str = "original") -> list[Columna]:
        cols = []
        for col in origen.columnas:
            if col in omitir:
                continue
            cols.append(Columna(self.valor(alias, origen, col), nombre_columna(col), origen.tipos[col], rol,
                                origen.nombre, col))
        return cols

    def bloque_geografico(self, mapa: dict, alias: str, origen: Origen) -> list[Columna]:
        cols = []
        for nombre, tipo in GEOGRAFIA.items():
            col = mapa.get(nombre)
            if col is None:
                cols.append(Columna(f"NULL::{tipo}", nombre, tipo, "geografia"))
            else:
                cols.append(Columna(f"CAST({self.valor(alias, origen, col)} AS {tipo})", nombre, tipo,
                                    "geografia", origen.nombre, col))
        return cols

    def clave_original(self, t: dict, origen: Origen) -> list[Columna]:
        """Clave original de cada fila (vivienda y, si corresponde, hogar, persona o pieza): va al enlace."""
        return [Columna(self.valor("x", origen, k), nombre_columna(k), origen.tipos[k], "enlace", origen.nombre, k)
                for k in claves_tabla(t)]

    def fila_origen(self, origen: Origen) -> Columna:
        return Columna(f"x.{origen.fila}", "fila_origen", "BIGINT", "procedencia", origen.nombre, "(número de fila)")

    def id_portafolio(self, alias: str) -> Columna:
        return Columna(f"{alias}._id_geo", "id_portafolio", "BIGINT", "identificador", self.geo["origen"],
                       f"{self.geo['clave']} (correlativo)")

    def geo_comun(self, origen: Origen) -> list[Columna]:
        if self.geo is None:
            return self.bloque_geografico(self.est["comunes"], "x", origen)
        return self.bloque_geografico(self.geo["comunes"], "g", self.origenes[self.geo["origen"]])

    # --- Uniones ------------------------------------------------------------------------------

    def claves(self, t: dict, origen: Origen) -> list[str]:
        return [self.valor("x", origen, k) for k in t["vivienda"]]

    def condicion_ids(self, t: dict, origen: Origen) -> str:
        return " AND ".join(f"{v} = i.k{j}" for j, v in enumerate(self.claves(t, origen), start=1))

    def condicion_geo(self, origen: Origen) -> str:
        g = self.origenes[self.geo["origen"]]
        return f"{self.valor('x', origen, self.geo['enlace'])} = {self.valor('g', g, self.geo['clave'])}"

    def union_geo(self, origen: Origen) -> str:
        if self.geo is None:
            return ""
        return f"LEFT JOIN {self.origenes[self.geo['origen']].tabla} g ON {self.condicion_geo(origen)}"

    def union_ids(self, t: dict, origen: Origen) -> str:
        tipo = "LEFT JOIN" if t.get("huerfanas") else "JOIN"
        return f"{tipo} ids_viv i ON {self.condicion_ids(t, origen)}"

    def comprobar_enlaces(self, t: dict, origen: Origen) -> None:
        """La clave original es única y las filas sin vivienda son exactamente las declaradas en la
        ficha (`huerfanas`)."""
        if "derivada_de" not in t:
            claves = ", ".join(self.valor("x", origen, k) for k in claves_tabla(t))
            repetidas = uno(self.con, f"SELECT count(*) - count(DISTINCT ({claves})) FROM {origen.tabla} x")
            if repetidas:
                sys.exit(f"[{self.censo}] {origen.nombre}: {repetidas} claves originales repetidas.")
        huerfanas = uno(self.con, f"SELECT count(*) FROM {origen.tabla} x ANTI JOIN ids_viv i ON {self.condicion_ids(t, origen)}")
        if huerfanas != t.get("huerfanas", 0):
            sys.exit(f"[{self.censo}] {origen.nombre}: {huerfanas} filas sin vivienda (declaradas: {t.get('huerfanas', 0)}).")
        if self.geo is not None:
            g = self.origenes[self.geo["origen"]]
            sin_geo = uno(self.con, f"SELECT count(*) FROM {origen.tabla} x ANTI JOIN {g.tabla} g ON {self.condicion_geo(origen)}")
            if sin_geo:
                sys.exit(f"[{self.censo}] {sin_geo} filas sin geografía en {origen.nombre}.")

    def numero(self, t: dict, rol: str, origen: Origen) -> str:
        """Número de hogar, persona o pieza; se detiene si no cabe en el identificador."""
        v = self.valor("x", origen, t[rol])
        tope = {"hogar": MULT_HOGAR, "persona": MULT_PERSONA}.get(rol)
        maximo = uno(self.con, f"SELECT max({v}) FROM {origen.tabla} x")
        if tope and maximo >= tope:
            sys.exit(f"[{self.censo}] {t[rol]} llega a {maximo}: no cabe en el identificador.")
        return v

    # --- Escritura ----------------------------------------------------------------------------

    def escribir(self, nombre: str, cols: list[Columna], enlace: list[Columna], desde: str, desde_enlace: str,
                 orden: str, archivos: list[str]) -> None:
        """Escribe la tabla y su enlace, ambos ordenados por el identificador de la tabla."""
        origen = " + ".join(self.config["microdatos"][int(self.censo)][a] for a in archivos if a)
        self.copiar(nombre, f"{nombre}.parquet", "datos", cols, desde, orden, origen)
        self.copiar(nombre, f"enlaces/{nombre}.parquet", "enlace", enlace, desde_enlace, orden, origen)

    def copiar(self, tabla: str, archivo: str, contenido: str, cols: list[Columna], desde: str, orden: str,
               origen: str) -> None:
        variables = [c.variable for c in cols]
        repetidas = {v for v in variables if variables.count(v) > 1}
        if repetidas:
            sys.exit(f"[{self.censo}] {archivo}: columnas repetidas: {', '.join(sorted(repetidas))}")
        destino = self.salida / archivo
        lista = ",\n  ".join(f"{c.expr} AS {ident(c.variable)}" for c in cols)
        mensaje(f"[{self.censo}] escribiendo {archivo}")
        escribir_parquet(self.con, f"SELECT {lista} FROM {desde} ORDER BY {orden}", destino)
        filas = uno(self.con, f"SELECT count(*) FROM read_parquet({ruta_sql(destino)})")
        for orden_col, c in enumerate(cols, start=1):
            d = asdict(c)
            del d["expr"]
            self.mapa.append({"censo": self.censo, "tabla": tabla, "archivo": f"{self.censo}/{archivo}",
                              "orden": orden_col, **d})
        self.manifiesto.append({
            "censo": self.censo, "tabla": tabla, "contenido": contenido, "archivo": f"{self.censo}/{archivo}",
            "filas": filas, "columnas": len(cols), "md5": md5(destino), "origen": origen,
        })
        mensaje(f"[{self.censo}] {archivo}: {filas:_} filas, {len(cols)} columnas".replace("_", "."))

    # --- Proceso ------------------------------------------------------------------------------

    def procesar(self) -> None:
        base = Path(self.config["temporal"]) / f"estandarizar_{self.censo}.duckdb"
        base.unlink(missing_ok=True)
        self.con = conectar(self.config, base)
        try:
            self._procesar()
        finally:
            self.con.close()
            base.unlink(missing_ok=True)
            Path(str(base) + ".wal").unlink(missing_ok=True)

    def _procesar(self) -> None:
        est, geo = self.est, self.geo
        tablas = est["tablas"]

        # 1. Originales a tablas de texto.
        necesarios = ([geo["origen"]] if geo else []) + [t.get("origen") or t["derivada_de"] for t in tablas.values()]
        for nombre in dict.fromkeys(necesarios):
            self.origenes[nombre] = self.cargar(nombre)

        # 2. Identificador de vivienda: correlativo en el orden de la clave original. Las claves se
        #    guardan con su tipo (k1, k2…) y las uniones comparan valores, no texto.
        viv = tablas["viviendas"]
        src_viv = self.origenes[viv["origen"]]
        k = [f"k{j}" for j in range(1, len(viv["vivienda"]) + 1)]
        lista = ", ".join(f"{v} AS {kj}" for v, kj in zip(self.claves(viv, src_viv), k))
        self.con.execute(f"""CREATE TABLE ids_viv AS
                             SELECT {lista}, row_number() OVER (ORDER BY {', '.join(k)}) AS _id_viv
                             FROM {src_viv.tabla} x""")
        repetidas = uno(self.con, f"SELECT count(*) - count(DISTINCT ({', '.join(k)})) FROM ids_viv")
        if repetidas:
            sys.exit(f"[{self.censo}] {repetidas} claves de vivienda repetidas.")

        # 3. Identificador de portafolio (1992 y 2002): correlativo en el orden del número de portafolio.
        if geo:
            g = self.origenes[geo["origen"]]
            clave_geo = self.valor("x", g, geo["clave"])
            if uno(self.con, f"SELECT count(*) - count(DISTINCT {clave_geo}) FROM {g.tabla} x"):
                sys.exit(f"[{self.censo}] {geo['clave']} repetido en {g.nombre}.")
            self.con.execute(f"""CREATE TABLE geo AS SELECT row_number() OVER (ORDER BY {clave_geo}) AS _id_geo,
                                 x.{g.fila} AS _fila_geo, * FROM {g.tabla} x""")
            g.tabla, g.fila = "geo", "_fila_geo"

        omitidas_geo = list(est["comunes"].values()) if geo is None else [geo["enlace"]]
        censo_col = Columna(f"{self.censo}::SMALLINT", "censo", "SMALLINT", "identificador")
        id_viv = Columna("i._id_viv", "id_vivienda", "BIGINT", "identificador", viv["origen"], " + ".join(viv["vivienda"]))
        archivo_geo = geo["origen"] if geo else ""

        # 4. Viviendas.
        self.comprobar_enlaces(viv, src_viv)
        cols = [censo_col, id_viv, *([self.id_portafolio("g")] if geo else []), *self.geo_comun(src_viv)]
        if geo:
            cols += self.originales(g, "g", {*self.excluir, geo["clave"], *geo["comunes"].values()}, rol="geografia")
        cols += self.originales(src_viv, "x", {*self.excluir, *omitidas_geo, *viv["vivienda"]})
        enlace = [censo_col, id_viv, self.fila_origen(src_viv), *self.clave_original(viv, src_viv)]
        desde = f"{src_viv.tabla} x {self.union_ids(viv, src_viv)}"
        self.escribir("viviendas", cols, enlace, f"{desde} {self.union_geo(src_viv)}", desde, "id_vivienda",
                      [viv["origen"], archivo_geo])

        # 5. Hogares y personas (y piezas en 1992).
        for nombre, t in tablas.items():
            if nombre == "viviendas":
                continue
            src = self.origenes[t.get("origen") or t["derivada_de"]]
            self.comprobar_enlaces(t, src)
            cols = [censo_col, id_viv]
            omitir = {*self.excluir, *omitidas_geo, *t["vivienda"]}
            if "hogar" in t:
                h = self.numero(t, "hogar", src)
                id_tabla = Columna(f"i._id_viv * {MULT_HOGAR} + {h}", "id_hogar", "BIGINT", "identificador",
                                   src.nombre, f"id_vivienda * {MULT_HOGAR} + {t['hogar']}")
                cols.append(id_tabla)
                if "persona" in t:
                    p = self.numero(t, "persona", src)
                    id_tabla = Columna(f"(i._id_viv * {MULT_HOGAR} + {h}) * {MULT_PERSONA} + {p}", "id_persona",
                                       "BIGINT", "identificador", src.nombre, f"id_hogar * {MULT_PERSONA} + {t['persona']}")
                    cols.append(id_tabla)
                cols.append(Columna(f"CAST({h} AS SMALLINT)", "n_hogar", "SMALLINT", "identificador", src.nombre, t["hogar"]))
                if "persona" in t:
                    cols.append(Columna(f"CAST({p} AS SMALLINT)", "n_persona", "SMALLINT", "identificador",
                                        src.nombre, t["persona"]))
                cols.append(Columna(f"({h} = 0)", "hogar_ficticio", "BOOLEAN", "derivada", src.nombre, f"{t['hogar']} = 0"))
                omitir |= {t["hogar"], t.get("persona")}
            if "pieza" in t:
                # Las piezas sin vivienda no tienen id_vivienda: su identificador es un correlativo propio.
                n = self.numero(t, "pieza", src)
                id_tabla = Columna(f"row_number() OVER (ORDER BY {', '.join([*self.claves(t, src), n])})", "id_pieza",
                                   "BIGINT", "identificador", src.nombre, " + ".join(claves_tabla(t)))
                cols += [id_tabla, Columna(f"CAST({n} AS SMALLINT)", "n_pieza", "SMALLINT", "identificador",
                                           src.nombre, t["pieza"])]
                omitir.add(t["pieza"])
            desde_enlace = f"{src.tabla} x {self.union_ids(t, src)}"
            desde = f"{desde_enlace} {self.union_geo(src)}"

            if "derivada_de" in t:
                # Tabla reconstruida (hogares de 2002): una fila por hogar distinto, sin variables propias.
                fila = Columna("NULL::BIGINT", "fila_origen", "BIGINT", "procedencia")
                cols += [*self.geo_comun(src),
                         Columna("CAST(count(*) AS SMALLINT)", "n_personas", "SMALLINT", "derivada", src.nombre,
                                 "(personas del hogar)")]
                desde += " GROUP BY ALL"
                desde_enlace += " GROUP BY ALL"
            else:
                fila = self.fila_origen(src)
                cols += [*self.geo_comun(src), *self.originales(src, "x", omitir)]
            enlace = [censo_col, id_tabla, fila, *self.clave_original(t, src)]
            self.escribir(nombre, cols, enlace, desde, desde_enlace, id_tabla.variable, [src.nombre, archivo_geo])

        # 6. Tabla geográfica completa (incluye portafolios sin viviendas).
        if geo:
            cols = [censo_col, self.id_portafolio("x"),
                    *self.bloque_geografico(geo["comunes"], "x", g),
                    *self.originales(g, "x", {*self.excluir, geo["clave"], *geo["comunes"].values()})]
            enlace = [censo_col, self.id_portafolio("x"), self.fila_origen(g),
                      *self.clave_original({"vivienda": [geo["clave"]]}, g)]
            self.escribir(g.nombre, cols, enlace, f"{g.tabla} x", f"{g.tabla} x", "id_portafolio", [g.nombre])


def md5(ruta: Path) -> str:
    h = hashlib.md5()
    with ruta.open("rb") as f:
        for bloque in iter(lambda: f.read(1 << 24), b""):
            h.update(bloque)
    return h.hexdigest()


def main() -> None:
    censos = sys.argv[1:] or CENSOS
    config = leer_config()
    if "estandarizado" not in config:
        sys.exit("Falta la clave `estandarizado` en config.yaml.")
    commit = commit_actual()
    for censo in censos:
        e = Estandarizador(censo, config)
        e.procesar()
        for fila in e.manifiesto:
            fila.update(commit=commit, fecha=date.today().isoformat())
        actualizar_csv(MAPA, e.mapa, {censo})
        actualizar_csv(Path(config["estandarizado"]) / "manifiesto.csv", e.manifiesto, {censo})
    mensaje("listo")


if __name__ == "__main__":
    main()
