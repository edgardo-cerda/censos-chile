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
      enlaces/               en cada censo: un archivo por tabla con el vínculo al archivo original
    manifiesto.csv           filas, columnas, md5, archivo original, commit y fecha
  armonizado/                capa 2: variables comparables, mismo esquema en todos los censos
    viviendas/<censo>.parquet  hogares/<censo>.parquet  personas/<censo>.parquet
```

La capa 1 cambia la forma pero no el contenido: cada código queda como venía. La capa 2 cambia el
contenido según las fichas de `metadatos/variables/`. Toda cifra de la capa 2 se puede rastrear
hasta la capa 1 (por los identificadores) y de ahí, con los archivos de enlace, hasta la fila del
archivo original (`fila_origen`) o su clave original. Las rutas están en `config.yaml` (`estandarizado`, `armonizado`, `temporal`).

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
- En 1992 y 2002 las columnas de `portafolios` también se copian en `viviendas` (con
  `id_portafolio`, salvo el número de portafolio, que va al enlace), y comuna, área y
  distrito en hogares y personas, para no tener que unir tablas en cada consulta.
- En 2002 `hogares` se reconstruye desde personas: solo claves, geografía y `n_personas` (la entrega
  no trae las preguntas de hogar).

**Columnas comunes**, al inicio y con el mismo nombre y tipo en todos los censos:

| Columna | Tipo | Tablas | Regla |
|---|---|---|---|
| `censo` | SMALLINT | todas | |
| `id_vivienda` | BIGINT | todas menos portafolios | correlativo en el orden de la clave original de la vivienda |
| `id_portafolio` | BIGINT | portafolios, viviendas (1992, 2002) | correlativo en el orden del número de portafolio |
| `id_hogar` | BIGINT | hogares, personas | `id_vivienda * 100 + n_hogar` |
| `id_persona` | BIGINT | personas | `id_hogar * 10000 + n_persona` |
| `id_pieza` | BIGINT | piezas (1992) | correlativo en el orden de `Portafolio` + `Vivienda` + `Pieza` |
| `n_hogar`, `n_persona`, `n_pieza` | SMALLINT | | número de orden original (columna original renombrada) |
| `hogar_ficticio` | BOOLEAN | hogares, personas | `n_hogar = 0` (ver más abajo) |
| `region`, `provincia` | SMALLINT | | como vienen (2017, 2024); nulo si la entrega no los trae |
| `comuna` | INTEGER | | código de la entrega (1992: «Origen 3»; resto: DPA2018) |
| `area`, `distrito` | SMALLINT | | como vienen; 2024 no trae distrito |

Así, una persona se une a su hogar o a su vivienda con una sola columna, igual en todos los censos.
Los multiplicadores cubren con holgura los máximos observados (92 hogares en una vivienda y 7.473
personas en un hogar); el pipeline se detiene si algún censo los supera.

**Enlace con los originales.** Lo que solo sirve para volver al archivo original no está en las
tablas, sino en `<censo>/enlaces/<tabla>.parquet`: una fila por cada fila de la tabla, en el mismo
orden, con el identificador de la tabla, `fila_origen` (fila del archivo original, 1 = primera fila
de datos) y la clave original completa, con su tipo y su nombre estandarizado:

| Censo | Clave original en el enlace |
|---|---|
| 1992 | `portafolio`, `vivienda` + `hogar`, `persona` o `pieza`; portafolios: `portafolios` |
| 2002 | `portafolio`, `vn` + `hn`, `pn`; portafolios: `portafolio` |
| 2017 | `id_zona_loc`, `nviv` + `nhogar`, `personan` |
| 2024 | `id_vivienda_orig` + `id_hogar_orig`, `id_persona_orig` |

Los números de hogar, persona y pieza se repiten en el enlace para que la clave original quede
completa, pero también siguen en las tablas (`n_hogar`, `n_persona`, `n_pieza`) porque tienen
significado propio. En los hogares reconstruidos de 2002, `fila_origen` es nulo.

**Hogar 0.** En 1992 y 2024 el hogar 0 agrupa a las personas que no forman parte de un hogar
particular (viviendas colectivas y personas en situación de calle o en tránsito). Se mantiene como un
hogar propio marcado con `hogar_ficticio`. En 2002 y 2017 no existe hogar 0 (esas personas tienen
hogar 1); para todos los censos, la capa 2 trae `hogar_particular`.

**Nombres.** Las demás columnas conservan su nombre original en minúsculas, ASCII y con guion bajo
(`Agua_cañeria` → `agua_caneria`, `P18` → `p18`). Si coinciden con una columna común se les agrega
`_orig` (2024: `id_vivienda_orig`). La correspondencia completa entre cada columna de la capa 1
(tabla y archivo, de datos o de enlace) y su tabla y variable originales está en
`metadatos/estructura/variables_estandarizadas.csv`.

**Valores.** Los códigos se conservan tal cual (0, 98, 99, -66, -99…). Solo pasan a NULL el campo
vacío y el `NA` de las exportaciones desde R (1992 y 2002). Esas exportaciones escriben algunos
enteros en notación científica (portafolio 100000 → `1e+05`): se leen como el entero que son, y las
uniones entre tablas comparan valores, no texto. Una columna es entera si todos sus
valores, al volver a texto, quedan iguales (sin ceros a la izquierda ni decimales) o están en esa notación científica, con el tipo más
chico que alcance (TINYINT, SMALLINT, INTEGER o BIGINT); si no, queda como texto. La columna sin
nombre de R con el número de fila se reemplaza por `fila_origen` tras verificar que coinciden.

**Filas sin vivienda.** 112 piezas de 1992 apuntan a viviendas que no existen en la entrega. Se
conservan con `id_vivienda` nulo (pero con su `id_pieza`); la ficha de estructura declara su número
(`huerfanas`) y el pipeline se detiene si cambia.

**Controles** (`validacion/validar_estandarizado.py` → `validacion/controles_estandarizado.csv`):
md5 de los archivos; mismas filas que el original; identificadores únicos y sin nulos; enlaces
portafolio–vivienda–hogar–persona completos; cada enlace con los mismos identificadores que su
tabla (uno a uno), clave original única y `fila_origen` de 1 a n; comuna y área sin nulos; y cada
variable original (incluidas las claves del enlace) reproduce el inventario de
`metadatos/inventario/` (frecuencias completas o nulos, distintos, mínimo y máximo).

## Capa 2: armonizado

Generada por `pipelines/armonizar_microdatos.py` desde la capa 1, las fichas de variables y
`metadatos/territorio/comunas.csv`. Incluye el núcleo y la etapa 1 de la armonización
(ver [Etapas](#etapas-de-la-armonizacion)).

**Dos versiones de cada variable.**

| Columna | Versión | Qué garantiza |
|---|---|---|
| `<variable>` | común | Mismo nombre, código y etiqueta para la misma categoría en todos los censos. Conserva el detalle de cada censo (el catálogo es la unión de las categorías de todos) y el universo propio de cada censo. |
| `<variable>_comp` | comparable | Categorías generales que significan lo mismo en todos los censos donde existe y universo común (el más restrictivo): fuera de él, -1. Es NULL en los censos que la ficha marca como `solo_comun`. |

`<variable>_comp` solo existe cuando difiere de la versión común: la ficha tiene categorías
detalladas, un `universo_comparable` o censos no comparables. Si no existe, la versión común ya es
comparable (sexo, área, edad, alfabetismo, número de personas). La edad comparable conserva su
nombre propio, `edad_85`.

En la versión común, las categorías generales tienen códigos de un dígito y las detalladas, de dos
(parentesco: 2 = cónyuge o conviviente; 21 = esposo/a, 22 = conviviente). Un código de un dígito
en la versión común significa que el censo no distingue el detalle. La versión comparable es la
categoría general de cada código.

| Columna | Unidades | Contenido |
|---|---|---|
| `censo`, `id_vivienda`, `id_hogar`, `id_persona` | | claves de la capa 1 |
| `comuna`, `provincia`, `region` | todas | DPA2018 |
| `region_dpa1974` | todas | 13 regiones (15 → 1, 14 → 10, 16 → 8) |
| `comuna_entrega` | todas | código de comuna tal como viene en la capa 1 |
| `area` | todas | ficha `area` |
| `hogar_particular` | hogares, personas | la vivienda es particular (`tipo_vivienda_comp` 1 a 6) |
| `tipo_vivienda`, `tipo_vivienda_comp` | viviendas | ficha `tipo_vivienda` |
| `condicion_ocupacion`, `condicion_ocupacion_comp` | viviendas | ficha `condicion_ocupacion` |
| `n_hogares`, `n_hogares_comp` | viviendas | hogares de la vivienda, sin el hogar 0 (ficha `n_hogares`) |
| `n_personas` | viviendas, hogares | personas de la vivienda o del hogar (ficha `n_personas`) |
| `sexo` | personas | ficha `sexo` |
| `edad` | personas | edad original, sin tope (ficha `edad`) |
| `edad_85` | personas | edad con tope común de 85 años (ficha `edad_85`) |
| `parentesco`, `parentesco_comp` | personas | ficha `parentesco` |
| `estado_civil`, `estado_civil_comp` | personas | ficha `estado_civil` (comparable: 15 años o más) |
| `alfabetismo` | personas | ficha `alfabetismo` |
| `asistencia_escolar`, `asistencia_escolar_comp` | personas | ficha `asistencia_escolar` (2017, 2024) |
| `hijos_nacidos_vivos`, `hijos_nacidos_vivos_comp` | personas | ficha `hijos_nacidos_vivos` (comparable: mujeres de 15 años o más) |
| `hijos_sobrevivientes`, `hijos_sobrevivientes_comp` | personas | ficha `hijos_sobrevivientes` (comparable: mujeres de 15 años o más con hijos) |

**Faltantes comunes** en todas las variables armonizadas:

| Código | Significado |
|---|---|
| `-1` | No aplica |
| `-2` | Ignorado o sin respuesta |
| `-3` | Suprimido por anonimización (2024) |
| `NULL` | El censo no hizo la pregunta |

**Fichas** (`metadatos/variables/<variable>.yaml`, ver `_plantilla.yaml`). Declaran el catálogo
común (`categorias`, con `detallado`), el `universo_comparable` y, por censo:
- `recodificacion` (código original → código común) o, para variables numéricas, `rango` (y
  `fuera_de_rango`, el código para los demás valores);
- `faltantes` (código original → -1, -2 o -3; `null` es el valor vacío);
- `universo` del censo: fuera de él la versión común es -1, cualquiera sea el código (en 2002 el 0
  de hijos nacidos vivos es a la vez "no aplica" y "ningún hijo");
- `clase`: `comparable` (por omisión), `con_reservas` (la reserva va en `comparabilidad`) o
  `solo_comun`.

Los universos se escriben como condiciones sobre variables armonizadas (`edad: {min: 15}`,
`sexo: {en: [2]}`, `tipo_vivienda_comp: {min: 1, max: 6}`). Un registro está fuera si alguna
condición no se cumple o su variable no aplica (-1); si la variable es ignorada o suprimida (-2,
-3), el registro conserva su valor. Un código original no previsto detiene el pipeline. Las
variables contadas (`derivada: conteo`) se calculan desde otra tabla de la capa 1 y se contrastan
con la variable original equivalente (`control`).

La matriz variable × censo (variables originales, clase y estado de la ficha) se genera en
`metadatos/concordancia/variables_armonizadas.csv`.

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
(2024); ningún "no aplica" dentro del universo de cada censo; y los conteos (hogares y personas)
iguales a las variables originales equivalentes. Las frecuencias de cada variable armonizada por censo quedan en
`validacion/frecuencias_armonizado.csv` para revisión.

## Etapas de la armonización

| Etapa | Variables | Estado |
|---|---|---|
| 0. Núcleo | territorio, área, sexo, edad, `edad_85`, parentesco, tipo de vivienda | fichas en borrador |
| 1. Directas | condición de ocupación, número de hogares y de personas, estado civil, alfabetismo, asistencia escolar, hijos nacidos vivos y sobrevivientes | fichas en borrador |
| 2. Categorías gruesas comunes | materiales de la vivienda, agua, servicio higiénico, alumbrado, tenencia, religión, condición de actividad, categoría ocupacional, pueblo originario, migración (comunas en DPA2018, país, período de llegada) | pendiente |
| 3. Construidas | nivel educacional (CINE 2011), años de estudio, ocupación y rama agregadas, tipo de hogar, jefatura, hacinamiento, allegamiento, índices de vivienda | pendiente |
| 4. Solo nivel común | variables de un solo censo o no comparables (afrodescendencia, lengua indígena, nacionalidad, TIC, vehículos, discapacidad…) | pendiente |

## Orden de ejecución

```
python pipelines/estandarizar_microdatos.py        # capa 1 (todos los censos o los indicados)
python validacion/validar_estandarizado.py
python herramientas/correspondencia_comunas.py     # requiere la capa 1 de 1992 y 2017
python pipelines/armonizar_microdatos.py           # capa 2 y sus controles
python pipelines/poblacion_nucleo.py               # tabulado de población desde la capa 2
```

## Pendiente

- Etapas 2 a 4 de la armonización, con el mismo flujo de fichas.
- Integrar `variables_estandarizadas.csv` al diccionario consolidado (nombre estandarizado de cada variable).
- Decidir si las capas 1 y 2 se publican (depende de las condiciones de entrega de 1992 y 2002).
