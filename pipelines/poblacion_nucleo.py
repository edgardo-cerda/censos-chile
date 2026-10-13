"""Tabulado de población por región, área, sexo y edad quinquenal, 1992–2024 (desde microdatos).

Lee las tablas en Parquet generadas por herramientas/inventario_microdatos.py (carpeta `cache`
de config.yaml) y escribe productos/tabulados/poblacion_microdatos.csv con el esquema de
metadatos/esquema_tabulados.yaml.

Cada fila es una celda disjunta (región × área × sexo × tramo de edad); los totales se obtienen
sumando. La región se entrega en dos versiones de la DPA, ambas exactas porque las regiones
creadas en 2007 y 2018 son uniones de comunas completas:
  - DPA1974: 13 regiones (vigente en 1992 y 2002).
  - DPA2018: 16 regiones (vigente en 2017 y 2024).

Uso:
  python pipelines/poblacion_nucleo.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import duckdb
import yaml

RAIZ = Path(__file__).resolve().parents[1]
SALIDA = RAIZ / "productos" / "tabulados" / "poblacion_microdatos.csv"

# Tramo máximo común: 2024 trunca la edad en 85 años.
EDAD_TOPE = 85

# Expresiones SQL por censo. Cada consulta entrega una fila por persona con:
#   region16 (DPA2018), area (1 urbano / 2 rural), sexo (1 hombre / 2 mujer), edad (NULL = ignorada).
CONSULTAS = {
    # 1992: comunas en DPA de 15 regiones (códigos "Origen 3"); Ñuble = provincia 84.
    1992: """
        SELECT CASE WHEN g.Comuna::INT // 100 = 84 THEN 16 ELSE g.Comuna::INT // 1000 END AS region16,
               g.Area::INT AS area, p.Sexo::INT AS sexo, p.Edad::INT AS edad
        FROM '{cache}/1992_personas.parquet' p
        JOIN '{cache}/1992_portafolios.parquet' g ON p.Portafolio = g.Portafolios
    """,
    # 2002: geografía ya recodificada a DPA2018.
    2002: """
        SELECT g.Comuna::INT // 1000 AS region16, g.Area::INT AS area,
               p.P18::INT AS sexo, p.P19::INT AS edad
        FROM '{cache}/2002_personas.parquet' p
        JOIN '{cache}/2002_portafolios.parquet' g ON p.Portafolio = g.Portafolio
    """,
    2017: """
        SELECT REGION::INT AS region16, AREA::INT AS area, P08::INT AS sexo, P09::INT AS edad
        FROM '{cache}/2017_personas.parquet'
    """,
    # 2024: edad -66 = suprimida por anonimización.
    2024: """
        SELECT region::INT AS region16, area::INT AS area, sexo::INT AS sexo,
               CASE WHEN edad::INT < 0 THEN NULL ELSE edad::INT END AS edad
        FROM '{cache}/2024_personas.parquet'
    """,
}

FUENTES = {1992: "micro_1992", 2002: "micro_2002", 2017: "micro_2017", 2024: "micro_2024"}


def main() -> None:
    config = yaml.safe_load((RAIZ / "config.yaml").read_text(encoding="utf-8"))
    cache = Path(config["cache"]).as_posix()
    con = duckdb.connect()
    con.execute(f"SET memory_limit = '{config.get('memoria_duckdb', '4GB')}'")

    partes = []
    for censo, sql in CONSULTAS.items():
        print(f"[{censo}]", flush=True)
        con.execute(f"CREATE OR REPLACE TEMP VIEW personas AS {sql.format(cache=cache)}")
        con.execute(f"""
            CREATE OR REPLACE TEMP TABLE t{censo} AS
            SELECT {censo} AS censo, region16,
                   CASE region16 WHEN 15 THEN 1 WHEN 14 THEN 10 WHEN 16 THEN 8 ELSE region16 END AS region13,
                   area, sexo,
                   CASE WHEN edad IS NULL THEN NULL ELSE least(edad, {EDAD_TOPE}) // 5 * 5 END AS edad_min,
                   count(*) AS valor
            FROM personas GROUP BY ALL
        """)
        partes.append(f"t{censo}")

    con.execute("CREATE OR REPLACE TEMP TABLE base AS " + " UNION ALL ".join(f"SELECT * FROM {p}" for p in partes))
    fuentes = " ".join(f"WHEN {c} THEN '{f}'" for c, f in FUENTES.items())
    filas = []
    for dpa, col in (("DPA1974", "region13"), ("DPA2018", "region16")):
        filas.append(f"""
            SELECT censo, 'poblacion' AS indicador, 'personas' AS unidad,
                   'region' AS territorio_nivel, {col}::VARCHAR AS territorio_cod_orig,
                   NULL AS territorio_nombre_orig, '{dpa}' AS dpa_version,
                   CASE WHEN '{dpa}' = 'DPA2018' THEN {col}::VARCHAR END AS territorio_cod_dpa2024,
                   CASE area WHEN 1 THEN 'urbana' WHEN 2 THEN 'rural' END AS area,
                   CASE sexo WHEN 1 THEN 'hombre' WHEN 2 THEN 'mujer' END AS sexo,
                   edad_min,
                   CASE WHEN edad_min IS NULL OR edad_min >= {EDAD_TOPE} THEN NULL ELSE edad_min + 4 END AS edad_max,
                   CASE WHEN edad_min IS NULL THEN 'ignorada' END AS edad_estado,
                   NULL AS dimensiones,
                   sum(valor) AS valor, 'ok' AS estado_valor,
                   CASE censo {fuentes} END AS fuente_id,
                   NULL AS cuadro, NULL AS pagina_impresa, NULL AS pagina_pdf,
                   'microdatos' AS metodo, 'sin_verificar' AS verificacion, NULL AS nota
            FROM base GROUP BY ALL
        """)
    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    con.execute(f"""
        COPY (SELECT * FROM ({' UNION ALL '.join(filas)})
              ORDER BY censo, dpa_version, territorio_cod_orig::INT, area, sexo, edad_min NULLS LAST)
        TO '{SALIDA.as_posix()}' (HEADER, DELIMITER ',')
    """)

    print(con.execute(f"""
        SELECT censo, dpa_version, count(DISTINCT territorio_cod_orig) AS regiones, sum(valor) AS poblacion,
               sum(valor) FILTER (WHERE area = 'urbana') / sum(valor) AS prop_urbana,
               sum(valor) FILTER (WHERE edad_estado = 'ignorada') AS edad_ignorada
        FROM read_csv('{SALIDA.as_posix()}') GROUP BY ALL ORDER BY 1, 2
    """).fetchall())


if __name__ == "__main__":
    sys.exit(main())
