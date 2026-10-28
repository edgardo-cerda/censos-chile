# Estructura común de los microdatos (1992–2024)

Cómo se guardan los microdatos para que todos los censos tengan el mismo formato y la misma
estructura. Hallazgos sobre cada base: [notas_microdatos.md](notas_microdatos.md).

## Punto de partida

| | 1992 | 2002 | 2017 | 2024 |
|---|---|---|---|---|
| Formato original | CSV exportado desde R (encabezado latin-1) | CSV exportado desde R | CSV con `;` (de los `.rar`) | Parquet |
| Tablas | portafolios, viviendas, hogares, personas, uso_piezas | portafolios, viviendas, personas (**sin hogares**) | viviendas, hogares, personas | viviendas, hogares, personas |
| Clave de vivienda | `Portafolio` + `Vivienda` | `Portafolio` + `VN` | `ID_ZONA_LOC` + `NVIV` | `id_vivienda` |
| Clave de hogar | + `Hogar` (0–15) | + `HN` (1–92) | + `NHOGAR` (1–36) | + `id_hogar` (0–26) |
| Clave de persona | + `Persona` (≤ 3.327) | + `PN` (≤ 7.473) | + `PERSONAN` (≤ 5.912) | + `id_persona` (≤ 5.806) |
| Geografía | tabla `portafolios` | tabla `portafolios` (ya en DPA2018) | repetida en cada tabla | repetida en cada tabla |
| Nombres | descriptivos (`Agua_cañeria`) | código de pregunta (`P18`) | código de pregunta (`P08`) | descriptivos en minúsculas |

En los cuatro censos las claves compuestas son únicas y no hay registros huérfanos. En 2024,
`id_hogar` e `id_persona` son números dentro de la vivienda, no identificadores únicos.

## Tres capas

```
<datos_originales>/          capa 0: archivos tal como se entregaron (sha256 en metadatos/inventario/archivos.csv)
censos-chile-datos/
  estandarizado/             capa 1: mismo contenido, forma común
    1992/  viviendas.parquet  hogares.parquet  personas.parquet  piezas.parquet  portafolios.parquet
    2002/  viviendas.parquet  hogares.parquet  personas.parquet  portafolios.parquet
    2017/  viviendas.parquet  hogares.parquet  personas.parquet
    2024/  viviendas.parquet  hogares.parquet  personas.parquet
    manifiesto.csv           filas, columnas, md5, archivo original, commit y fecha
  armonizado/                capa 2: variables comparables, mismo esquema en todos los censos
    viviendas/<censo>.parquet  hogares/<censo>.parquet  personas/<censo>.parquet
```

La capa 1 cambia la forma pero no el contenido: cada código queda como venía. La capa 2 cambia el
contenido según las fichas de `metadatos/variables/`. Toda cifra de la capa 2 se puede rastrear
hasta la capa 1 (por los identificadores) y de ahí hasta la fila del archivo original
(`fila_origen`). Las rutas están en `config.yaml` (`estandarizado`, `armonizado`, `temporal`).

Todo el procesamiento es en Python con DuckDB (`herramientas/requirements.txt`); las utilidades
comunes están en `pipelines/comun.py`.

## Capa 1: estandarizado

Generada por `pipelines/estandarizar_microdatos.py` a partir de las fichas de estructura
`metadatos/estructura/<censo>.yaml`, que declaran para cada censo el archivo de origen de cada
tabla, sus claves, la tabla geográfica y los valores nulos.

**Formato.** Parquet con compresión zstd y texto en UTF-8, un archivo por censo y tabla.

**Tablas.** Todos los censos tienen `viviendas`, `hogares` y `personas`.
- 1992 agrega `piezas` (de `uso_piezas`) y 1992 y 2002 conservan `portafolios` completa: incluye
  los portafolios sin viviendas (2 en 1992 y 25.627 en 2002).
- En 1992 y 2002 las columnas de `portafolios` también se copian en `viviendas`, y comuna, área y
  distrito en hogares y personas, para no tener que unir tablas en cada consulta.
- En 2002 `hogares` se reconstruye desde personas: solo claves, geografía y `n_personas` (la entrega
  no trae las preguntas de hogar).

**Columnas comunes**, al inicio y con el mismo nombre y tipo en todos los censos:

| Columna | Tipo | Tablas | Regla |
|---|---|---|---|
| `censo` | SMALLINT | todas | |
| `id_vivienda` | BIGINT | todas menos portafolios | correlativo en el orden de la clave original de la vivienda |
| `id_hogar` | BIGINT | hogares, personas | `id_vivienda * 100 + n_hogar` |
| `id_persona` | BIGINT | personas | `id_hogar * 10000 + n_persona` |
| `n_hogar`, `n_persona`, `n_pieza` | SMALLINT | | número de orden original (columna original renombrada) |
| `hogar_ficticio` | BOOLEAN | hogares, personas | `n_hogar = 0` (ver más abajo) |
| `fila_origen` | BIGINT | todas | fila del archivo original (1 = primera fila de datos); nulo en los hogares reconstruidos de 2002 |
| `region`, `provincia` | SMALLINT | | como vienen (2017, 2024); nulo si la entrega no los trae |
| `comuna` | INTEGER | | código de la entrega (1992: «Origen 3»; resto: DPA2018) |
| `area`, `distrito` | SMALLINT | | como vienen; 2024 no trae distrito |

Así, una persona se une a su hogar o a su vivienda con una sola columna, igual en todos los censos.
Los multiplicadores cubren con holgura los máximos observados (92 hogares en una vivienda y 7.473
personas en un hogar); el pipeline se detiene si algún censo los supera.

**Hogar 0.** En 1992 y 2024 el hogar 0 agrupa a las personas que no forman parte de un hogar
particular (viviendas colectivas y personas en situación de calle o en tránsito). Se mantiene como un
hogar propio marcado con `hogar_ficticio`. En 2002 y 2017 no existe hogar 0 (esas personas tienen
hogar 1); para todos los censos, la capa 2 trae `hogar_particular`.

**Nombres.** Las demás columnas conservan su nombre original en minúsculas, ASCII y con guion bajo
(`Agua_cañeria` → `agua_caneria`, `P18` → `p18`). Si coinciden con una columna común se les agrega
`_orig` (2024: `id_vivienda_orig`). La correspondencia completa entre cada columna de la capa 1 y su
tabla y variable originales está en `metadatos/estructura/variables_estandarizadas.csv`.

**Valores.** Los códigos se conservan tal cual (0, 98, 99, -66, -99…). Solo pasan a NULL el campo
vacío y el `NA` de las exportaciones desde R (1992 y 2002). Esas exportaciones escriben algunos
enteros en notación científica (portafolio 100000 → `1e+05`): se leen como el entero que son, y las
uniones entre tablas comparan valores, no texto. Una columna es entera si todos sus
valores, al volver a texto, quedan iguales (sin ceros a la izquierda ni decimales) o están en esa notación científica, con el tipo más
chico que alcance (TINYINT, SMALLINT, INTEGER o BIGINT); si no, queda como texto. La columna sin
nombre de R con el número de fila se reemplaza por `fila_origen` tras verificar que coinciden.

**Filas sin vivienda.** 112 piezas de 1992 apuntan a viviendas que no existen en la entrega. Se
conservan con `id_vivienda` nulo; la ficha de estructura declara su número (`huerfanas`) y el
pipeline se detiene si cambia.

**Controles** (`validacion/validar_estandarizado.py` → `validacion/controles_estandarizado.csv`):
md5 de los archivos; mismas filas que el original; identificadores únicos y sin nulos; enlaces
vivienda–hogar–persona completos; comuna y área sin nulos; y cada variable original reproduce el
inventario de `metadatos/inventario/` (frecuencias completas o nulos, distintos, mínimo y máximo).

## Capa 2: armonizado

Generada por `pipelines/armonizar_microdatos.py` desde la capa 1, las fichas de variables y
`metadatos/territorio/comunas.csv`. Por ahora incluye las variables del núcleo.

| Columna | Unidades | Contenido |
|---|---|---|
| `censo`, `id_vivienda`, `id_hogar`, `id_persona` | | claves de la capa 1 |
| `comuna`, `provincia`, `region` | todas | DPA2018 |
| `region_dpa1974` | todas | 13 regiones (15 → 1, 14 → 10, 16 → 8) |
| `comuna_entrega` | todas | código de comuna tal como viene en la capa 1 |
| `area` | todas | ficha `area` |
| `hogar_particular` | hogares, personas | la vivienda es particular (`tipo_vivienda` 1 a 6) |
| `tipo_vivienda`, `tipo_vivienda_det` | viviendas | ficha `tipo_vivienda` |
| `sexo` | personas | ficha `sexo` |
| `edad` | personas | edad original, sin tope (ficha `edad`) |
| `edad_85` | personas | edad con tope común de 85 años (ficha `edad_85`) |
| `parentesco`, `parentesco_det` | personas | ficha `parentesco` |

**Códigos general y detallado.** La columna con el nombre de la variable trae el código general,
comparable entre todos los censos. `<variable>_det` trae el detallado; cuando un censo no distingue
el detalle, repite el código general (un código de un dígito en `_det` significa «sin más detalle»).

**Faltantes comunes** en todas las variables armonizadas:

| Código | Significado |
|---|---|
| `-1` | No aplica |
| `-2` | Ignorado o sin respuesta |
| `-3` | Suprimido por anonimización (2024) |
| `NULL` | El censo no hizo la pregunta |

Cada ficha declara, por censo, su `recodificacion` (código original → armonizado), los `faltantes`
(código original → -1, -2 o -3) o, para variables numéricas, el `rango` válido. Un código no previsto
detiene el pipeline.

**Territorio.** `metadatos/territorio/comunas.csv` (`herramientas/correspondencia_comunas.py`)
tiene una fila por comuna de la DPA2018 con su código en cada entrega. 2002, 2017 y 2024 vienen en
DPA2018. 1992 viene en la DPA de 15 regiones de 2007: se pasa a la de 2010 con el puente
`COMUNA_15R` → `COMUNA` de 2017, salvo las cuatro comunas que pasaron a la provincia de Marga Marga
(Quilpué 5106 → 5801, Villa Alemana 5108 → 5804, Limache 5505 → 5802, Olmué 5507 → 5803). La
correspondencia se comprueba por nombre contra las tablas `COMUNAS_1992` y `COMUNAS_2002` de las
entregas; coinciden todas salvo cinco variantes de grafía declaradas en el script (Doñigue, Ciunco,
Coihaique, Aisen, Cabo de Horno).

**Controles** (en el mismo pipeline → `validacion/controles_armonizado.csv`): mismas filas que la
capa 1; territorio y área sin nulos; región y provincia derivadas iguales a las de la entrega (2017,
2024); hogar 0 = vivienda no particular (1992, 2024); edad suprimida solo en las comunas bajo umbral
(2024). Las frecuencias de cada variable armonizada por censo quedan en
`validacion/frecuencias_armonizado.csv` para revisión.

## Orden de ejecución

```
python pipelines/estandarizar_microdatos.py        # capa 1 (todos los censos o los indicados)
python validacion/validar_estandarizado.py
python herramientas/correspondencia_comunas.py     # requiere la capa 1 de 1992 y 2017
python pipelines/armonizar_microdatos.py           # capa 2 y sus controles
python pipelines/poblacion_nucleo.py               # tabulado de población desde la capa 2
```

## Pendiente

- Llevar el resto de las variables a la capa 2 módulo a módulo (fase 3), con el mismo flujo de fichas.
- Integrar `variables_estandarizadas.csv` al diccionario consolidado (nombre estandarizado de cada variable).
- Decidir si las capas 1 y 2 se publican (depende de las condiciones de entrega de 1992 y 2002).
