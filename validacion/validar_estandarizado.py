"""Controles de la capa 1 de microdatos (pipelines/estandarizar_microdatos.py).

  1. Archivos: existen y su md5 coincide con el manifiesto.
  2. Filas: cada tabla tiene las mismas filas que su archivo original (metadatos/inventario/archivos.csv);
     en los hogares reconstruidos de 2002, la suma de n_personas es el total de personas.
  3. Identificadores: únicos y sin nulos.
  4. Enlaces entre tablas: todo hogar tiene vivienda, toda persona tiene hogar, toda vivienda
     tiene portafolio (salvo las filas sin vivienda declaradas en la ficha) y la jerarquía de los
     identificadores es coherente (id_hogar // 100 = id_vivienda).
  5. Archivo de enlace: mismos identificadores que la tabla (uno a uno), clave original única y
     fila_origen de 1 a n.
  6. Geografía: comuna y área sin nulos en viviendas, hogares y personas.
  7. Contenido: cada variable original reproduce el inventario de metadatos/inventario/
     (frecuencias completas cuando las hay; si no, nulos, valores distintos, mínimo y máximo).

Escribe validacion/controles_estandarizado.csv y termina con error si algún control falla.

Uso:
  python validacion/validar_estandarizado.py [censos...]
"""

from __future__ import annotations

import math
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipelines.comun import (RAIZ, actualizar_csv, conectar, ident, leer_config, leer_csv,  # noqa: E402
                             leer_yaml, mensaje, ruta_sql, uno)
from pipelines.estandarizar_microdatos import CENSOS, MAPA, md5  # noqa: E402

SALIDA = RAIZ / "validacion" / "controles_estandarizado.csv"
INVENTARIO = RAIZ / "metadatos" / "inventario"
CLAVES = {"viviendas": "id_vivienda", "hogares": "id_hogar", "personas": "id_persona", "piezas": "id_pieza",
          "portafolios": "id_portafolio"}
ENLACES = {"hogares": ("id_vivienda", "viviendas"), "personas": ("id_hogar", "hogares"), "piezas": ("id_vivienda", "viviendas"),
           "viviendas": ("id_portafolio", "portafolios")}


class Validador:
    def __init__(self, con, config: dict, censo: str, manifiesto: list[dict], mapa: list[dict], archivos: list[dict]):
        self.con, self.config, self.censo = con, config, censo
        self.est = leer_yaml(RAIZ / "metadatos" / "estructura" / f"{censo}.yaml")
        self.nulos = set(self.est.get("valores_nulos") or []) | {""}
        self.manifiesto = [m for m in manifiesto if m["censo"] == censo]
        self.mapa = [m for m in mapa if m["censo"] == censo]
        self.filas_original = {a["tabla"]: int(a["filas"]) for a in archivos if a["censo"] == censo}
        self.resultados: list[dict] = []

    def pq(self, tabla: str, enlace: bool = False) -> str:
        archivo = f"enlaces/{tabla}.parquet" if enlace else f"{tabla}.parquet"
        return f"read_parquet({ruta_sql(Path(self.config['estandarizado']) / self.censo / archivo)})"

    def registrar(self, tabla: str, control: str, ok: bool, detalle: str = "") -> None:
        self.resultados.append({"censo": self.censo, "tabla": tabla, "control": control,
                                "resultado": "ok" if ok else "error", "detalle": detalle})
        if not ok:
            mensaje(f"[{self.censo}] {tabla}: {control} -> ERROR {detalle}")

    def origen(self, tabla: str) -> str | None:
        geo = self.est.get("geografia")
        if geo and tabla == geo["origen"]:
            return tabla
        return self.est["tablas"].get(tabla, {}).get("origen")

    def validar(self) -> list[dict]:
        for m in self.manifiesto:
            ruta = Path(self.config["estandarizado"]) / m["archivo"]
            self.registrar(m["tabla"], "archivo y md5", ruta.exists() and md5(ruta) == m["md5"], m["archivo"])
        tablas = {m["tabla"] for m in self.manifiesto}
        for m in self.manifiesto:
            if m["contenido"] == "datos":
                mensaje(f"[{self.censo}] {m['tabla']}")
                self.validar_tabla(m["tabla"], tablas)
        return self.resultados

    def validar_tabla(self, tabla: str, tablas: set[str]) -> None:
        pq = self.pq(tabla)
        n = uno(self.con, f"SELECT count(*) FROM {pq}")
        origen = self.origen(tabla)
        huerfanas = self.est["tablas"].get(tabla, {}).get("huerfanas", 0)

        # 2. Filas.
        if origen:
            esperado = self.filas_original[origen]
            self.registrar(tabla, "filas = original", n == esperado, f"{n} / {esperado}")
        else:
            personas = uno(self.con, f"SELECT count(*) FROM {self.pq('personas')}")
            suma = uno(self.con, f"SELECT sum(n_personas) FROM {pq}")
            self.registrar(tabla, "suma de n_personas = personas", suma == personas, f"{suma} / {personas}")

        # 3. Identificador.
        clave = CLAVES[tabla]
        d, v = self.con.execute(f"SELECT count(DISTINCT {clave}), count({clave}) FROM {pq}").fetchone()
        self.registrar(tabla, f"{clave} único y sin nulos", d == n and v == n, f"{d} distintos, {n - v} nulos")

        # 4. Enlaces entre tablas y jerarquía de identificadores.
        if tabla in ENLACES and ENLACES[tabla][1] in tablas:
            col, destino = ENLACES[tabla]
            h = uno(self.con, f"SELECT count(*) FROM {pq} x ANTI JOIN {self.pq(destino)} y ON x.{col} = y.{col}")
            self.registrar(tabla, f"{col} existe en {destino}", h == huerfanas, f"{h} huérfanas (declaradas: {huerfanas})")
        if tabla in ("hogares", "personas"):
            m = uno(self.con, f"""SELECT count(*) FILTER (WHERE id_hogar // 100 <> id_vivienda OR id_hogar % 100 <> n_hogar
                                  OR hogar_ficticio <> (n_hogar = 0)) FROM {pq}""")
            self.registrar(tabla, "id_hogar = id_vivienda * 100 + n_hogar", m == 0, f"{m} incoherentes")
        if tabla == "personas":
            m = uno(self.con, f"""SELECT count(*) FILTER (WHERE id_persona // 10000 <> id_hogar
                                  OR id_persona % 10000 <> n_persona) FROM {pq}""")
            self.registrar(tabla, "id_persona = id_hogar * 10000 + n_persona", m == 0, f"{m} incoherentes")

        # 5. Archivo de enlace.
        self.validar_enlace(tabla, n)

        # 6. Geografía.
        if tabla in ("viviendas", "hogares", "personas"):
            g = uno(self.con, f"SELECT count(*) FILTER (WHERE comuna IS NULL OR area IS NULL) FROM {pq}")
            self.registrar(tabla, "comuna y área sin nulos", g == 0, f"{g} nulos")

        # 7. Contenido de cada variable original contra el inventario.
        if origen:
            self.validar_contenido(tabla, origen)

    def validar_enlace(self, tabla: str, n: int) -> None:
        clave, pq, enl = CLAVES[tabla], self.pq(tabla), self.pq(tabla, enlace=True)
        n_e = uno(self.con, f"SELECT count(*) FROM {enl}")
        sueltas = uno(self.con, f"""SELECT count(*) FROM {pq} x FULL JOIN {enl} e ON x.{clave} = e.{clave}
                                    WHERE x.{clave} IS NULL OR e.{clave} IS NULL""")
        self.registrar(tabla, f"enlace: mismos {clave} que la tabla", n_e == n and sueltas == 0,
                       f"{n_e} / {n} filas, {sueltas} sin pareja")
        archivo = f"{self.censo}/enlaces/{tabla}.parquet"
        claves = ", ".join(ident(m["variable"]) for m in self.mapa if m["archivo"] == archivo and m["rol"] == "enlace")
        d = uno(self.con, f"SELECT count(DISTINCT ({claves})) FROM {enl}")
        self.registrar(tabla, f"enlace: clave original ({claves}) única", d == n_e, f"{d} distintas")
        d, a, b, v = self.con.execute(f"""SELECT count(DISTINCT fila_origen), min(fila_origen), max(fila_origen),
                                                 count(fila_origen) FROM {enl}""").fetchone()
        if v:
            self.registrar(tabla, "enlace: fila_origen de 1 a n", d == n_e and a == 1 and b == n_e,
                           f"{d} distintos, {a} a {b}")

    def validar_contenido(self, tabla: str, origen: str) -> None:
        inv_var = {v["variable"]: v for v in leer_csv(INVENTARIO / f"{self.censo}_{origen}_variables.csv")}
        inv_frec: dict[str, Counter] = {}
        for f in leer_csv(INVENTARIO / f"{self.censo}_{origen}_frecuencias.csv"):
            valor = None if f["valor"] in self.nulos else normalizar(f["valor"])
            inv_frec.setdefault(f["variable"], Counter())[valor] += int(f["n"])
        variables = [m for m in self.mapa if m["tabla"] == tabla and m["tabla_original"] == origen
                     and m["variable_original"] in inv_var]
        malas = []
        for m in variables:
            iv = inv_var[m["variable_original"]]
            c = ident(m["variable"])
            pq = f"read_parquet({ruta_sql(Path(self.config['estandarizado']) / m['archivo'])})"
            nulos, distintos, minimo, maximo = self.con.execute(
                f"""SELECT count(*) FILTER (WHERE {c} IS NULL), count(DISTINCT {c}),
                           min(TRY_CAST({c} AS DOUBLE)), max(TRY_CAST({c} AS DOUBLE)) FROM {pq}""").fetchone()
            nulos_inv = int(iv["n_vacios"]) + int(iv["n_na"])
            ok = nulos == nulos_inv
            if iv["con_frecuencias"] == "True":
                propia = Counter(dict(self.con.execute(f"SELECT {c}::VARCHAR, count(*) FROM {pq} GROUP BY 1").fetchall()))
                ok = ok and propia == inv_frec[m["variable_original"]]
            else:
                # El inventario cuenta el vacío y "NA" como valores distintos; la capa 1, no.
                dif = int(iv["n_distintos"]) - distintos
                ok = ok and 0 <= dif <= 2 and (dif == 0 or nulos_inv > 0)
                if m["tipo"] != "VARCHAR":
                    ok = ok and math.isclose(minimo, float(iv["min"])) and math.isclose(maximo, float(iv["max"]))
            if not ok:
                malas.append(m["variable_original"])
        self.registrar(tabla, f"{len(variables)} variables reproducen el inventario", not malas, " ".join(malas))


def normalizar(valor: str) -> str:
    """Valor del inventario como lo escribe la capa 1 (1e+05 -> 100000)."""
    if "e+" in valor:
        try:
            return str(int(float(valor)))
        except ValueError:
            pass
    return valor


def main() -> None:
    config = leer_config()
    manifiesto = leer_csv(Path(config["estandarizado"]) / "manifiesto.csv")
    censos = sys.argv[1:] or [c for c in CENSOS if any(m["censo"] == c for m in manifiesto)]
    mapa = leer_csv(MAPA)
    archivos = leer_csv(INVENTARIO / "archivos.csv")
    con = conectar(config)
    resultados = []
    for censo in censos:
        resultados += Validador(con, config, censo, manifiesto, mapa, archivos).validar()
    actualizar_csv(SALIDA, resultados, set(censos))
    errores = sum(r["resultado"] == "error" for r in resultados)
    mensaje(f"{len(resultados)} controles, {errores} con error")
    if errores:
        sys.exit(1)


if __name__ == "__main__":
    main()
