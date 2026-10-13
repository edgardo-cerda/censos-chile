"""Contrasta el tabulado de población derivado de microdatos con cifras publicadas.

Uso:
  python validacion/validar_poblacion.py
Solo contrasta los censos presentes en el tabulado (1992 en adelante); las referencias de 1982
quedan como cifras publicadas para el tabulado digitalizado. Sale con código 1 si alguna cifra difiere.
"""

import sys
from pathlib import Path

import duckdb

sys.stdout.reconfigure(encoding="utf-8")

RAIZ = Path(__file__).resolve().parents[1]
TABULADO = (RAIZ / "productos" / "tabulados" / "poblacion_microdatos.csv").as_posix()
REFERENCIAS = (RAIZ / "validacion" / "referencias_poblacion.csv").as_posix()

filas = duckdb.sql(f"""
    WITH t AS (
        SELECT censo, area, sexo, valor FROM read_csv('{TABULADO}')
        WHERE dpa_version = 'DPA2018'
    ),
    r AS (SELECT * FROM read_csv('{REFERENCIAS}', all_varchar = true))
    SELECT r.censo, r.area, r.sexo, r.valor::BIGINT AS publicado,
           (SELECT sum(valor) FROM t
            WHERE t.censo = r.censo::INT
              AND (r.area = '_T' OR t.area = r.area)
              AND (r.sexo = '_T' OR t.sexo = r.sexo))::BIGINT AS microdatos,
           r.fuente_id, r.cuadro
    FROM r WHERE r.censo::INT IN (SELECT DISTINCT censo FROM t)
    ORDER BY 1, 2, 3
""").fetchall()

errores = 0
for censo, area, sexo, pub, mic, fuente, cuadro in filas:
    dif = mic - pub
    errores += dif != 0
    marca = "ok " if dif == 0 else "DIF"
    print(f"{marca} {censo} {area:7} {sexo:7} publicado={pub:>11,} microdatos={mic:>11,} dif={dif:>+9,}  [{fuente}, {cuadro}]")
print(f"\n{len(filas) - errores} de {len(filas)} cifras coinciden.")
sys.exit(1 if errores else 0)
