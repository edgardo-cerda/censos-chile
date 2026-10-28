"""Capa 2 de los microdatos: variables armonizadas con el mismo esquema en todos los censos.

Lee la capa 1 (carpeta `estandarizado`), las fichas de metadatos/variables/ y la correspondencia
de comunas (metadatos/territorio/comunas.csv), y escribe en la carpeta `armonizado`:

  viviendas/<censo>.parquet, hogares/<censo>.parquet, personas/<censo>.parquet

Columnas (ver docs/estructura_microdatos.md):
  - claves de la capa 1: censo, id_vivienda, id_hogar, id_persona;
  - territorio: comuna, provincia y region en DPA2018, region_dpa1974, comuna_entrega, area;
  - hogar_particular (hogares y personas): la vivienda es particular (tipo_vivienda 1 a 6);
  - variables de las fichas: código general y, si la ficha tiene detalle, <variable>_det
    (cuando el censo no distingue el detalle, _det repite el código general).
Faltantes comunes: -1 no aplica, -2 ignorado, -3 suprimido; NULL = el censo no lo preguntó.
Un código original que la ficha no prevé detiene el pipeline.

Escribe además validacion/controles_armonizado.csv y validacion/frecuencias_armonizado.csv.

Uso:
  python pipelines/armonizar_microdatos.py [censos...]
"""

from __future__ import annotations

import sys
from functools import cache
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipelines.comun import (RAIZ, actualizar_csv, conectar, escribir_parquet, ident, leer_config,  # noqa: E402
                             leer_yaml, mensaje, nombre_estandar, ruta_sql, uno)

CENSOS = ["1992", "2002", "2017", "2024"]
UNIDADES = ["viviendas", "hogares", "personas"]
# Variables armonizadas por unidad (además del territorio y del área, que van en todas).
VARIABLES = {"viviendas": ["tipo_vivienda"], "hogares": [], "personas": ["sexo", "edad", "edad_85", "parentesco"]}
CLAVES = {"viviendas": ["censo", "id_vivienda"],
          "hogares": ["censo", "id_vivienda", "id_hogar"],
          "personas": ["censo", "id_vivienda", "id_hogar", "id_persona"]}
EDAD_TOPE = 85
COMUNAS = RAIZ / "metadatos" / "territorio" / "comunas.csv"
CONTROLES = RAIZ / "validacion" / "controles_armonizado.csv"
FRECUENCIAS = RAIZ / "validacion" / "frecuencias_armonizado.csv"


@cache
def ficha(nombre: str) -> dict:
    return leer_yaml(RAIZ / "metadatos" / "variables" / f"{nombre}.yaml")


def tiene_detalle(f: dict) -> bool:
    return any("detallado" in c for c in f["categorias"])


def codigo(valor, detalle: bool) -> int:
    """{original: general} o {original: [general, detallado]}; sin detallado, repite el general."""
    if isinstance(valor, list):
        return valor[1] if detalle and len(valor) > 1 and valor[1] is not None else valor[0]
    return valor


def caso(col: str, ramas: list[str], etiqueta: str) -> str:
    """CASE que detiene la consulta ante un valor no previsto."""
    falla = f"error('{etiqueta}: código no previsto ' || coalesce({col}::VARCHAR, 'NULL'))"
    return f"CAST(CASE {' '.join(ramas)} ELSE {falla} END AS SMALLINT)"


def ramas(col: str, recodificacion: dict, detalle: bool = False) -> list[str]:
    return [f"WHEN {col} = {orig} THEN {codigo(v, detalle)}" for orig, v in (recodificacion or {}).items()]


def columna(variable: str) -> str:
    return f"x.{ident(nombre_estandar(variable))}"


def variable_sql(nombre: str, censo: str) -> dict[str, str]:
    """Columnas armonizadas de una variable para un censo: nombre -> SQL."""
    f = ficha(nombre)
    nombres = [nombre, f"{nombre}_det"] if tiene_detalle(f) else [nombre]
    regla = f["censos"].get(int(censo))
    if regla is None:  # el censo no hizo la pregunta
        return {n: "NULL::SMALLINT" for n in nombres}
    etiqueta = f"{nombre} {censo}"
    col = columna(regla["variables_originales"][0])
    faltantes = ramas(col, regla.get("faltantes"))

    if f.get("derivada_de") == "edad":
        e = variable_sql("edad", censo)["edad"]
        return {nombre: f"CAST(CASE WHEN {e} < 0 THEN {e} ELSE least({e}, {EDAD_TOPE}) END AS SMALLINT)"}
    if "rango" in regla:
        a, b = regla["rango"]
        return {nombre: caso(col, [f"WHEN {col} BETWEEN {a} AND {b} THEN {col}", *faltantes], etiqueta)}

    previo = lambda detalle: []  # noqa: E731
    if "recodificacion_operativo" in regla:
        # tipo_vivienda 2024: primero el operativo (colectiva, situación de calle), luego el tipo particular.
        operativo, col = col, columna(regla["recodificacion_variable"])
        previo = lambda detalle: ramas(operativo, regla["recodificacion_operativo"], detalle)  # noqa: E731
    return {n: caso(col, [*previo(det), *ramas(col, regla["recodificacion"], det), *faltantes], etiqueta)
            for n, det in zip(nombres, (False, True))}


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
            cols = [f"x.{c}" for c in CLAVES[unidad]]
            cols += ["t.comuna::INTEGER AS comuna", "t.provincia::SMALLINT AS provincia",
                     "t.region::SMALLINT AS region", "t.region_dpa1974::SMALLINT AS region_dpa1974",
                     "x.comuna AS comuna_entrega", f"{area_sql} AS area"]
            desde = f"{self.capa1(unidad)} x LEFT JOIN comunas t ON x.comuna = t.{codigo_entrega}"
            if unidad != "viviendas":
                cols.append("(v.tipo_vivienda BETWEEN 1 AND 6) AS hogar_particular")
                desde += f" LEFT JOIN {self.capa2('viviendas')} v ON x.id_vivienda = v.id_vivienda"
            for variable in VARIABLES[unidad]:
                cols += [f"{sql} AS {nombre}" for nombre, sql in variable_sql(variable, self.censo).items()]
            escribir_parquet(self.con, f"SELECT {', '.join(cols)} FROM {desde} ORDER BY {CLAVES[unidad][-1]}",
                             self.destino(unidad))

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
    errores = sum(r["resultado"] == "error" for r in controles)
    mensaje(f"{len(controles)} controles, {errores} con error")
    if errores:
        sys.exit(1)


if __name__ == "__main__":
    main()
