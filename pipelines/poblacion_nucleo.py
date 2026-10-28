"""Tabulado de población por región, área, sexo y edad quinquenal, 1992–2024 (desde microdatos).

Lee la capa 2 de personas (carpeta `armonizado` de config.yaml, generada por
pipelines/armonizar_microdatos.py) y escribe productos/tabulados/poblacion_microdatos.csv con el
esquema de metadatos/esquema_tabulados.yaml.

Cada fila es una celda disjunta (región × área × sexo × tramo de edad); los totales se obtienen
sumando. La región se entrega en dos versiones de la DPA, ambas exactas porque las regiones
creadas en 2007 y 2018 son uniones de comunas completas:
  - DPA1974: 13 regiones (vigente en 1992 y 2002).
  - DPA2018: 16 regiones (vigente en 2017 y 2024).
La edad usa edad_85 (tope común de 85 años); la edad suprimida de 2024 se informa como ignorada.

Uso:
  python pipelines/poblacion_nucleo.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipelines.comun import RAIZ, conectar, leer_config, ruta_sql  # noqa: E402

SALIDA = RAIZ / "productos" / "tabulados" / "poblacion_microdatos.csv"
EDAD_TOPE = 85


def main() -> None:
    config = leer_config()
    con = conectar(config)
    personas = ruta_sql(Path(config["armonizado"]) / "personas" / "*.parquet")
    con.execute(f"""
        CREATE TEMP TABLE base AS
        SELECT censo, region AS region16, region_dpa1974 AS region13, area, sexo,
               CASE WHEN edad_85 < 0 THEN NULL ELSE edad_85 // 5 * 5 END AS edad_min,
               count(*) AS valor
        FROM read_parquet({personas}) GROUP BY ALL
    """)

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
                   'micro_' || censo AS fuente_id,
                   NULL AS cuadro, NULL AS pagina_impresa, NULL AS pagina_pdf,
                   'microdatos' AS metodo, 'sin_verificar' AS verificacion, NULL AS nota
            FROM base GROUP BY ALL
        """)
    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    con.execute(f"""
        COPY (SELECT * FROM ({' UNION ALL '.join(filas)})
              ORDER BY censo, dpa_version, territorio_cod_orig::INT, area, sexo, edad_min NULLS LAST)
        TO {ruta_sql(SALIDA)} (HEADER, DELIMITER ',')
    """)

    print(con.execute(f"""
        SELECT censo, dpa_version, count(DISTINCT territorio_cod_orig) AS regiones, sum(valor) AS poblacion,
               sum(valor) FILTER (WHERE area = 'urbana') / sum(valor) AS prop_urbana,
               sum(valor) FILTER (WHERE edad_estado = 'ignorada') AS edad_ignorada
        FROM read_csv({ruta_sql(SALIDA)}) GROUP BY ALL ORDER BY 1, 2
    """).fetchall())


if __name__ == "__main__":
    sys.exit(main())
