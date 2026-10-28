"""Capa 2 de los microdatos: variables armonizadas con el mismo esquema en todos los censos.

Lee la capa 1 (carpeta `estandarizado`), las fichas de metadatos/variables/ y la correspondencia
de comunas (metadatos/territorio/comunas.csv), y escribe en la carpeta `armonizado`:

  viviendas/<censo>.parquet, hogares/<censo>.parquet, personas/<censo>.parquet

Columnas (ver docs/estructura_microdatos.md):
  - claves de la capa 1: censo, id_vivienda, id_hogar, id_persona;
  - territorio: comuna, provincia y region en DPA2018, region_dpa1974, comuna_entrega, area;
  - hogar_particular (hogares y personas): la vivienda es particular (tipo_vivienda_comp 1 a 6);
  - cada variable de las fichas en dos versiones:
      <variable>       común: mismo código y etiqueta en todos los censos, con el detalle de cada
                       censo y su propio universo;
      <variable>_comp  comparable: categorías generales y universo común. Solo existe si difiere
                       de la común (la ficha tiene detalle, universo comparable o censos no comparables).
Faltantes comunes: -1 no aplica, -2 ignorado, -3 suprimido; NULL = el censo no lo preguntó.
Un código original que la ficha no prevé detiene el pipeline.

Escribe además validacion/controles_armonizado.csv, validacion/frecuencias_armonizado.csv y
metadatos/concordancia/variables_armonizadas.csv (variable × censo: origen, clase y estado).

Uso:
  python pipelines/armonizar_microdatos.py [censos...]
"""

from __future__ import annotations

import sys
from collections import defaultdict
from functools import cache
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipelines.comun import (RAIZ, actualizar_csv, conectar, escribir_csv, escribir_parquet, ident,  # noqa: E402
                             leer_config, leer_yaml, mensaje, nombre_estandar, ruta_sql, uno)

CENSOS = ["1992", "2002", "2017", "2024"]
UNIDADES = ["viviendas", "hogares", "personas"]
# Variables armonizadas por unidad (además del territorio y del área, que van en todas).
VARIABLES = {
    "viviendas": ["tipo_vivienda", "condicion_ocupacion", "n_hogares", "n_personas"],
    "hogares": ["n_personas"],
    "personas": ["sexo", "edad", "edad_85", "parentesco", "estado_civil", "alfabetismo", "asistencia_escolar",
                 "hijos_nacidos_vivos", "hijos_sobrevivientes"],
}
CLAVES = {"viviendas": ["censo", "id_vivienda"],
          "hogares": ["censo", "id_vivienda", "id_hogar"],
          "personas": ["censo", "id_vivienda", "id_hogar", "id_persona"]}
# Variables que se cuentan en otra tabla de la capa 1 (ficha con `derivada: conteo`): tabla y filtro.
CONTEOS = {"n_hogares": ("hogares", "n_hogar >= 1"), "n_personas": ("personas", "true")}
EDAD_TOPE = 85
COMUNAS = RAIZ / "metadatos" / "territorio" / "comunas.csv"
CONTROLES = RAIZ / "validacion" / "controles_armonizado.csv"
FRECUENCIAS = RAIZ / "validacion" / "frecuencias_armonizado.csv"
MATRIZ = RAIZ / "metadatos" / "concordancia" / "variables_armonizadas.csv"


# --- Fichas ---------------------------------------------------------------------------------

@cache
def ficha(nombre: str) -> dict:
    return leer_yaml(RAIZ / "metadatos" / "variables" / f"{nombre}.yaml")


def regla(nombre: str, censo: str) -> dict | None:
    return ficha(nombre)["censos"].get(int(censo))


def padres(f: dict) -> dict[int, int]:
    """Código detallado de la versión común -> categoría general de la versión comparable."""
    return {d["codigo"]: c["codigo"] for c in f.get("categorias", []) for d in c.get("detallado", [])}


def tiene_comp(nombre: str) -> bool:
    f = ficha(nombre)
    return (bool(padres(f)) or "universo_comparable" in f
            or any(r.get("clase") == "solo_comun" for r in f["censos"].values()))


# --- SQL ------------------------------------------------------------------------------------

def ramas(col: str, mapa: dict | None) -> list[str]:
    """{original: destino}; la clave nula (`null` en la ficha) corresponde al valor vacío."""
    return [f"WHEN {col} IS NULL THEN {v}" if k is None else f"WHEN {col} = {k} THEN {v}"
            for k, v in (mapa or {}).items()]


def caso(col: str, ramas_: list[str], etiqueta: str) -> str:
    """CASE que detiene la consulta ante un valor no previsto."""
    falla = f"error('{etiqueta}: código no previsto ' || coalesce({col}::VARCHAR, 'NULL'))"
    return f"CAST(CASE {' '.join(ramas_)} ELSE {falla} END AS SMALLINT)"


def condiciones(universo: dict, valor) -> list[tuple[str, str]]:
    """(valor, condición de pertenencia) por variable del universo; `valor(variable)` da su SQL."""
    pares = []
    for variable, cond in universo.items():
        v = valor(variable)
        partes = ([f"{v} >= {cond['min']}"] if "min" in cond else []) + \
                 ([f"{v} <= {cond['max']}"] if "max" in cond else []) + \
                 ([f"{v} IN ({', '.join(map(str, cond['en']))})"] if "en" in cond else [])
        pares.append((v, " AND ".join(partes)))
    return pares


def fuera_universo(universo: dict, valor) -> str:
    """Verdadero si se sabe que el registro está fuera del universo: alguna variable del universo
    no cumple su condición o no aplica (-1). Un ignorado o suprimido (-2, -3) o un nulo no decide:
    el registro conserva su valor."""
    return " OR ".join(f"({v} = -1 OR ({v} >= 0 AND NOT ({c})))" for v, c in condiciones(universo, valor))


def dentro_universo(universo: dict, valor) -> str:
    return " AND ".join(f"({v} >= 0 AND {c})" for v, c in condiciones(universo, valor))


def columna(variable: str) -> str:
    return f"x.{ident(nombre_estandar(variable))}"


@cache
def comun_sql(nombre: str, censo: str) -> str:
    """Versión común de una variable para un censo, calculada desde la capa 1 (alias x)."""
    f, r = ficha(nombre), regla(nombre, censo)
    if r is None:  # el censo no hizo la pregunta
        return "NULL::SMALLINT"
    if f.get("derivada") == "conteo":
        return f"CAST(coalesce({nombre}.n, 0) AS SMALLINT)"
    if f.get("derivada_de") == "edad":
        e = comun_sql("edad", censo)
        return f"CAST(CASE WHEN {e} < 0 THEN {e} ELSE least({e}, {EDAD_TOPE}) END AS SMALLINT)"

    col = columna(r["variables_originales"][0])
    previas = []
    if "universo" in r:  # fuera del universo del censo: no aplica, cualquiera sea el código
        previas.append(f"WHEN {fuera_universo(r['universo'], lambda v: comun_sql(v, censo))} THEN -1")
    if "recodificacion_operativo" in r:
        # tipo_vivienda 2024: primero el operativo (colectiva, situación de calle), luego el tipo particular.
        previas += ramas(col, r["recodificacion_operativo"])
        col = columna(r["recodificacion_variable"])
    if "rango" in r:
        a, b = r["rango"]
        previas.append(f"WHEN {col} BETWEEN {a} AND {b} THEN {col}")
    resto = [*ramas(col, r.get("recodificacion")), *ramas(col, r.get("faltantes"))]
    if "fuera_de_rango" in r:
        resto.append(f"WHEN {col} IS NOT NULL THEN {r['fuera_de_rango']}")
    return caso(col, [*previas, *resto], f"{nombre} {censo}")


def comp_sql(nombre: str, censo: str) -> str:
    """Versión comparable, calculada desde las columnas comunes de la consulta interna (alias c)."""
    f, r = ficha(nombre), regla(nombre, censo)
    if r is None or r.get("clase") == "solo_comun":
        return "NULL::SMALLINT"
    v = f"c.{ident(nombre)}"
    previas = []
    if "universo_comparable" in f:
        previas.append(f"WHEN {fuera_universo(f['universo_comparable'], lambda u: valor_comp(u, censo))} THEN -1")
    grupos = defaultdict(list)
    for detalle, general in padres(f).items():
        grupos[general].append(str(detalle))
    previas += [f"WHEN {v} IN ({', '.join(d)}) THEN {g}" for g, d in grupos.items()]
    return f"CAST(CASE {' '.join(previas)} ELSE {v} END AS SMALLINT)" if previas else v


def valor_comp(variable: str, censo: str) -> str:
    """Variable de un universo comparable: `<var>_comp` o la versión común `<var>`."""
    if variable.endswith("_comp"):
        return comp_sql(variable.removesuffix("_comp"), censo)
    return f"c.{ident(variable)}"


# --- Capa 2 ---------------------------------------------------------------------------------

class Armonizador:
    def __init__(self, con, config: dict, censo: str):
        self.con, self.config, self.censo = con, config, censo
        self.resultados: list[dict] = []

    def capa1(self, unidad: str) -> str:
        return f"read_parquet({ruta_sql(Path(self.config['estandarizado']) / self.censo / f'{unidad}.parquet')})"

    def destino(self, unidad: str) -> Path:
        return Path(self.config["armonizado"]) / unidad / f"{self.censo}.parquet"

    def capa2(self, unidad: str) -> str:
        return f"read_parquet({ruta_sql(self.destino(unidad))})"

    def armonizar(self) -> None:
        area = ficha("area")["censos"][int(self.censo)]
        area_sql = caso("x.area", ramas("x.area", area["recodificacion"]), f"area {self.censo}")
        codigo_entrega = "comuna_1992" if self.censo == "1992" else "comuna"
        for unidad in UNIDADES:
            mensaje(f"[{self.censo}] {unidad}")
            clave = CLAVES[unidad][-1]
            cols = [f"x.{c}" for c in CLAVES[unidad]]
            cols += ["t.comuna::INTEGER AS comuna", "t.provincia::SMALLINT AS provincia",
                     "t.region::SMALLINT AS region", "t.region_dpa1974::SMALLINT AS region_dpa1974",
                     "x.comuna AS comuna_entrega", f"{area_sql} AS area"]
            desde = f"{self.capa1(unidad)} x LEFT JOIN comunas t ON x.comuna = t.{codigo_entrega}"
            if unidad != "viviendas":
                cols.append("(v.tipo_vivienda_comp BETWEEN 1 AND 6) AS hogar_particular")
                desde += f" LEFT JOIN {self.capa2('viviendas')} v ON x.id_vivienda = v.id_vivienda"
            externas = [c.split(" AS ")[-1].removeprefix("x.") for c in cols]
            for variable in VARIABLES[unidad]:
                if ficha(variable).get("derivada") == "conteo":
                    tabla, filtro = CONTEOS[variable]
                    desde += (f" LEFT JOIN (SELECT {clave}, count(*) FILTER (WHERE {filtro}) AS n FROM {self.capa1(tabla)}"
                              f" GROUP BY 1) {variable} ON x.{clave} = {variable}.{clave}")
                cols.append(f"{comun_sql(variable, self.censo)} AS {variable}")
                externas.append(variable)
                if tiene_comp(variable):
                    externas.append(f"{comp_sql(variable, self.censo)} AS {variable}_comp")
            externas = [e if " AS " in e else f"c.{e}" for e in externas]
            escribir_parquet(self.con, f"SELECT {', '.join(externas)} FROM (SELECT {', '.join(cols)} FROM {desde}) c "
                                       f"ORDER BY {clave}", self.destino(unidad))

    # --- Controles ------------------------------------------------------------------------------

    def registrar(self, tabla: str, control: str, ok: bool, detalle: str = "") -> None:
        self.resultados.append({"censo": self.censo, "tabla": tabla, "control": control,
                                "resultado": "ok" if ok else "error", "detalle": detalle})
        if not ok:
            mensaje(f"[{self.censo}] {tabla}: {control} -> ERROR {detalle}")

    def controlar(self) -> list[dict]:
        frecuencias = []
        for unidad in UNIDADES:
            a, c = self.capa2(unidad), self.capa1(unidad)
            clave = CLAVES[unidad][-1]
            n_a, n_c = uno(self.con, f"SELECT count(*) FROM {a}"), uno(self.con, f"SELECT count(*) FROM {c}")
            self.registrar(unidad, "filas = capa 1", n_a == n_c, f"{n_a} / {n_c}")
            nulos = uno(self.con, f"SELECT count(*) FILTER (WHERE comuna IS NULL OR region IS NULL OR area IS NULL) FROM {a}")
            self.registrar(unidad, "territorio y área sin nulos", nulos == 0, f"{nulos} nulos")
            if self.censo in ("2017", "2024"):
                m = uno(self.con, f"""SELECT count(*) FROM {a} a JOIN {c} c USING ({clave})
                                      WHERE a.region <> c.region OR a.provincia <> c.provincia""")
                self.registrar(unidad, "región y provincia = entrega", m == 0, f"{m} distintas")
            if unidad != "viviendas":
                nulos, distintos = self.con.execute(f"""
                    SELECT count(*) FILTER (WHERE a.hogar_particular IS NULL),
                           count(*) FILTER (WHERE a.hogar_particular = c.hogar_ficticio)
                    FROM {a} a JOIN {c} c USING ({clave})""").fetchone()
                self.registrar(unidad, "hogar_particular sin nulos", nulos == 0, f"{nulos} nulos")
                # Donde existe el hogar 0 (1992, 2024), debe coincidir con las viviendas no particulares.
                if self.censo in ("1992", "2024"):
                    self.registrar(unidad, "hogar 0 = vivienda no particular", distintos == 0, f"{distintos} distintos")
            for variable in VARIABLES[unidad]:
                self.controlar_variable(unidad, variable)
            columnas = [r[0] for r in self.con.execute(f"DESCRIBE SELECT * FROM {a}").fetchall()]
            for v in columnas:
                if v in {*CLAVES[unidad], "comuna", "provincia", "comuna_entrega"}:
                    continue
                for valor, n in self.con.execute(f"""SELECT {ident(v)}::VARCHAR AS valor, count(*) FROM {a}
                                                     GROUP BY 1 ORDER BY TRY_CAST(valor AS INTEGER) NULLS LAST, valor""").fetchall():
                    frecuencias.append({"censo": self.censo, "tabla": unidad, "variable": v, "valor": valor, "n": n})
        if self.censo == "2024":
            fuera, total = self.con.execute(f"""
                SELECT count(*) FILTER (WHERE c.comuna_bajo_umbral <> 1), count(*)
                FROM {self.capa2('personas')} a JOIN {self.capa1('personas')} c USING (id_persona)
                WHERE a.edad = -3""").fetchone()
            self.registrar("personas", "edad suprimida solo en comunas bajo umbral", fuera == 0, f"{fuera} de {total} fuera")
        return frecuencias

    def controlar_variable(self, unidad: str, variable: str) -> None:
        r, a = regla(variable, self.censo), self.capa2(unidad)
        if r is None:
            return
        col = lambda v: ident(v)  # noqa: E731
        if "universo" in r:
            # Dentro del universo del censo no debe quedar ningún "no aplica".
            n = uno(self.con, f"SELECT count(*) FROM {a} WHERE {variable} = -1 AND {dentro_universo(r['universo'], col)}")
            self.registrar(unidad, f"{variable}: sin no aplica dentro del universo", n == 0, f"{n} registros")
        for original in (r.get("control") or {}).get(unidad, []):
            # Las variables contadas deben coincidir con la variable original equivalente (dentro del
            # universo comparable, si la ficha lo define).
            filtro = f"AND a.{variable}_comp >= 0" if tiene_comp(variable) else ""
            n, total = self.con.execute(f"""
                SELECT count(*) FILTER (WHERE a.{variable} <> c.{ident(original)}), count(*)
                FROM {a} a JOIN {self.capa1(unidad)} c USING ({CLAVES[unidad][-1]})
                WHERE c.{ident(original)} IS NOT NULL {filtro}""").fetchone()
            self.registrar(unidad, f"{variable} = {original} de la entrega", n == 0, f"{n} distintos de {total}")


def matriz() -> list[dict]:
    """Una fila por variable armonizada y censo: variables originales, clase y estado."""
    filas = []
    for unidad, variables in VARIABLES.items():
        for nombre in variables:
            f = ficha(nombre)
            for censo in CENSOS:
                r = regla(nombre, censo)
                filas.append({
                    "variable": nombre, "unidad": unidad, "censo": censo, "comparable": tiene_comp(nombre),
                    "variables_originales": "" if r is None else " + ".join(r.get("variables_originales") or []),
                    "clase": "no_existe" if r is None else r.get("clase", "comparable"),
                    "estado": "" if r is None else r.get("estado", ""),
                    "etiqueta": f["etiqueta"],
                })
    return filas


def main() -> None:
    censos = sys.argv[1:] or CENSOS
    config = leer_config()
    if "armonizado" not in config:
        sys.exit("Falta la clave `armonizado` en config.yaml.")
    con = conectar(config)
    con.execute(f"CREATE TABLE comunas AS SELECT * FROM read_csv({ruta_sql(COMUNAS)})")
    controles, frecuencias = [], []
    for censo in censos:
        a = Armonizador(con, config, censo)
        a.armonizar()
        frecuencias += a.controlar()
        controles += a.resultados
    actualizar_csv(CONTROLES, controles, set(censos))
    actualizar_csv(FRECUENCIAS, frecuencias, set(censos))
    escribir_csv(MATRIZ, matriz())
    errores = sum(r["resultado"] == "error" for r in controles)
    mensaje(f"{len(controles)} controles, {errores} con error")
    if errores:
        sys.exit(1)


if __name__ == "__main__":
    main()
