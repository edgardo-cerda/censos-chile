# Digitalización de las publicaciones (Fase 4)

Cómo se transcriben los cuadros de las publicaciones censales escaneadas (1813–1982) y qué se
sabe de cada PDF. Las cifras resultantes van a `productos/tabulados/tabulados_publicaciones.csv`.

## Flujo

1. **Ubicar el cuadro** en [metadatos/catalogo_cuadros.csv](../metadatos/catalogo_cuadros.csv)
   (título, página impresa, página del PDF y su estado: `verificada` si se vio en la página,
   `estimada` si se interpoló entre páginas de referencia y puede errar en unas pocas,
   `desconocida` si no se ubicó y `ausente` si la página falta en el escaneo). En 1813, en las
   publicaciones del siglo XIX, en 1907 y en la división territorial de 1952, cada provincia es
   una entrada de tipo `bloque`:
   la nota trae sus páginas y la lista de cuadros que contiene, que se repite en cada provincia.
   Los cuadros de población (los del núcleo) traen además su desagregación: `censos_datos` (censos
   cuyas cifras trae, separados por «;»; los comparativos traen varios), `nivel_territorial` (el más
   fino: entidad, distrito, comuna, parroquia, departamento, provincia, región o país), `variables`
   (cruces de `area`, `sexo` y `edad`, unidos por «+»), `cobertura` (`completa` o `parcial`, si solo
   cubre parte del país) y `desagregacion_fuente` (`verificada` si se vio en la página, `nota` si
   sale de la descripción del bloque, `título` si solo del título). Con ellas la planilla de avance
   calcula el nivel más fino disponible en los PDF para cada censo.
2. **Renderizar** la página con `herramientas/paginas.py`:
   ```
   python herramientas/paginas.py pub_1952 --pdf 40                 # página completa, 120 dpi
   python herramientas/paginas.py pub_1952 --impresa 44 --dpi 200 --recorte 0.35,0.60
   python herramientas/paginas.py pub_1940 --pdf 82-121 --ocr       # borrador OCR por filas
   ```
   Para cuadros largos, `herramientas/ocr_cuadro.py` genera un borrador celda por celda (OCR de
   cada columna entre las líneas del cuadro). En 1930 funcionó en páginas nítidas pero desalineó
   filas en otras: conviene probarlo en una página y, si falla, leer franjas a 200 dpi.
   La página completa a 110–130 dpi sirve para ubicarse; para leer cifras, recortes horizontales
   a 200 dpi, y a 400 dpi para dígitos dudosos (`--recorte y0,y1,x0,x1`, fracciones de la página).
3. **Transcribir** en `digitalizacion/<censo>/<fuente>_c<cuadro>.csv` el cuadro tal como está
   impreso: mismas filas, mismas columnas, nombres como aparecen. Guion impreso = `-`; dos puntos
   impresos (sin dato) = `..`; celda en blanco = vacío. Las cifras sin separador de miles. Los
   controles no suman las partes sin dato. Los tramos de edad van como columnas (`edad_min`,
   `edad_max` en el YAML) o, si son filas, con columnas auxiliares `edad_min`, `edad_max` y
   `edad_estado`; el control de edad puede combinar dimensiones
   (`dimension: [edad_min, edad_estado]`) para separar el total de la edad ignorada. Las notas de
   celda pueden nombrar cualquier columna del CSV (p. ej. `sexo` o `grupo`) para ubicar la fila.
4. **Describir** en el `.yaml` del mismo nombre: fuente, cuadro, páginas (con la primera fila
   de cada página), cómo se mapean filas y columnas a las dimensiones del esquema, notas del
   cuadro, notas de celdas y controles. Ejemplo: [digitalizacion/1952/pub_1952_c09.yaml](../digitalizacion/1952/pub_1952_c09.yaml).
5. **Controlar** con `python pipelines/tabulados_publicaciones.py`: aplica los controles del
   YAML (partes = total por dimensión, por territorio y por jerarquía provincia → departamento →
   comuna) y lista las diferencias en `validacion/controles_digitalizacion.csv`. Además compara
   las cifras que publican varios cuadros (mismo censo, división y unidad) en
   `validacion/contraste_fuentes.csv`. Una diferencia se resuelve de dos formas:
   - error de transcripción: se relee el recorte y se corrige el CSV;
   - error de la propia publicación: la cifra se deja **tal como está impresa** y se anota la
     celda con `estado_valor: inconsistente` y una nota que explique el valor coherente.
   El script sale con error mientras quede alguna diferencia sin anotar.
6. **Registrar** el avance en el catálogo (`estado`: pendiente → transcrito → verificado).
   "Verificado" requiere una segunda lectura independiente (doble captura) o el contraste
   con otra publicación que traiga la misma cifra.

Criterios:
- Un dígito cortado o ambiguo se resuelve con la aritmética del cuadro solo si una única
  lectura cuadra, y se deja nota de la celda.
- Una cifra que aparece en varias publicaciones (p. ej. 1940 en su propio censo, revisada en 1952
  y 1960) se transcribe de cada una por separado: comparten `censo` y difieren en `fuente_id`.
- `dpa_version` indica la división vigente en el cuadro (`provincias_<censo>` para las
  provincias de cada censo). Las correspondencias con la DPA actual son un trabajo aparte.

## Características de los PDF

- Todos son escaneos sin capa de texto, salvo `censo1992.pdf` (texto extraíble con pymupdf).
- No traen marcadores útiles y la paginación impresa no coincide con la del PDF: los desfases
  conocidos están en [metadatos/paginacion.csv](../metadatos/paginacion.csv). En 1865, 1875,
  1885, 1907, 1952 (Tomo I) y 1982 (Tomo III) el desfase cambia a lo largo del volumen (láminas
  intercaladas o páginas que faltan en el escaneo): van en tramos con estado `muestreo`, entre
  páginas de referencia leídas cada 15–25 páginas, y dentro de un tramo pueden errar en unas
  pocas. 1895 y 1952 juntan varios tomos con numeración propia en un solo PDF: para ellos se usa
  `--pdf` con la página del catálogo.
- Las páginas de referencia se leen con `herramientas/muestreo_paginas.py` (OCR del encabezado y
  del pie; guarda cada página apenas la lee, así que se corre por tandas cortas).
- Algunas tablas vienen giradas 90° (p. ej. 1960, cuadros 1.1.1 y 1.2): `--rotar 90`.
- 1970 y 1982 son listados de computador: 1970 sin separador de miles, 1982 con coma (11,329,736).
- OCR (RapidOCR): 12–17 s por página a 130 dpi con un solo proceso; varios procesos en paralelo
  agotan la memoria. Confunde 8/9, 1/l y los separadores de miles y omite celdas: sirve para
  recorrer muchas páginas buscando filas, nunca como transcripción final.
- 1843 y 1854 no están digitalizados.

## Notas por publicación

Las de 1930–1992 vienen en parte de la extracción previa (septiembre de 2026); las de 1813–1920 y
los tomos completos de 1952 y 1982 se agregaron al armar el catálogo (octubre de 2026).

**Censos sin publicación propia (1843 y 1854).** Sus cifras están en otras publicaciones: por
departamento en los cuadros sinópticos de 1865 (pág. 392, PDF 425: 1835, 1843, 1854 y 1865) y de
1875 (págs. 645–646, PDF 661–662: 1835 a 1875), y en el resumen general de 1907 (pág. 1263, PDF
1222: 1854 a 1907, por provincia y departamento); por provincia en el Cuadro 4 de 1952 (1835 a
1952). Los dos sinópticos están transcritos (departamentos y, aparte, los totales por provincia
de cada censo con sus propias provincias) y coinciden cifra por cifra; el de 1865 está mal
escaneado y sus cifras dudosas se resolvieron con el de 1875, que es nítido. Errata del de 1875:
Talca 1865 = 84.660 (es 84.630). El de 1875 pone el departamento de Curicó de 1865 solo en la
columna de provincias.

**1813** (edición del Archivo Nacional, 1953). Sin índice. Por provincia, de Copiapó a Talca:
cuadros "Censo de territorio" por distrito y un "Censo de provincia" con el total (estado civil
por sexo, edades y clases). No hay datos de Santiago. Concepción figura con las matrículas de
1812 por curatos (PDF 261–263). Los totales de Rancagua y Colchagua están cruzados: tras los
distritos de Rancagua viene un total rotulado Colchagua (PDF 217) y el de Rancagua aparece
después de los distritos de Colchagua (PDF 231).
Transcritas las 14 hojas de totales (`pub_1813_provincias`: edad × sexo, estado civil, totales) y
sus distritos × sexo (`pub_1813_distritos`). Los totales cuadran con el estado civil; las edades
no suman el total en 8 partidos y los distritos tampoco en 4 (impreso así, releído a 300 dpi): se
registran como `excepciones` del control en el YAML, porque no hay una cifra culpable identificable.

**1835** ("Repertorio Chileno"). Dos páginas impresas por página del PDF. Índice en PDF 114–116.
Habitantes en el art. 3 (pág. 3) y en el capítulo IX, por provincia y departamento (págs. 171–222).
Cada departamento trae hombres y mujeres solteros y casados (sin edad ni parroquias); transcrito en
`pub_1835_departamentos`, con los habitantes de cada provincia según el texto. Coincide con los
sinópticos de 1865 y 1875 salvo Cauquenes (34.633, sinópticos 34.631) y el total de Concepción
(118.364 en el texto; sus departamentos suman 118.362).

**1865.** Índice en PDF 2–4. Un bloque por provincia y el Censo general de la República
(págs. 321–392). Desfase +31 al comienzo y +33 desde la pág. 77. Clasificación de los habitantes
por provincias (págs. 360–361, PDF 393–394): transcrita la edad por sexo y los totales; coincide
cifra por cifra con el Cuadro 6 de 1952. El escaneo es malo: los números de estilo antiguo pierden
los trazos bajo la línea (4 y 3 se leen como 1; 3 como 8). Diez cifras se fijaron con los totales
impresos de la provincia y de la República. Los tramos impresos repiten los límites ("de 7 a 15",
"de 15 a 25"…); se registran como 8–15, 16–25…, igual que 1952.
Clasificación por departamentos (págs. 352–353, PDF 385–386): transcrita igual; 62 cifras ilegibles
se fijaron con la suma de cada fila y la de su provincia (= pág. 360). Errata: Caupolicán 16–25
hombres impreso 7.760 (coherente 6.760). La provincia de Coquimbo trae además, en su bloque, la
clasificación por subdelegaciones (PDF 302), que respalda las cifras adoptadas.

**1875.** Índice en PDF 3–5. Provincias, cuadros generales (págs. 601–645) y comparativos
(pág. 647). El desfase baja de +56 al comienzo a +16 al final.

**1885.** Solo el tomo I de 2. Índice en PDF 9–11; cuadros generales en págs. 839–867. El PDF no
trae profesiones ni extranjeros.

**1895.** Cuatro tomos en un PDF, cada uno con su índice (PDF 2–4, 609–612, 1326–1329 y
1995–1998). Cuadros generales en el tomo IV, págs. 467–551 (PDF 2455–2539). El número de página
cae más abajo que en otros volúmenes (franja de 0,16 en el muestreo). Desde la PDF 2086 (Cautín a
Magallanes y los cuadros generales) el escaneo es bitonal a ~72 dpi y no se lee con seguridad; el
tomo IV completo está en Memoria Chilena (MC0055464, en grises; impresa = PDF + 4 en los cuadros
generales), registrado como copia de lectura en `metadatos/fuentes.yaml`.
Cada provincia trae, al pie del cuadro por subdelegaciones (sexo × edad, en cinco páginas), un
«Resumen por departamentos i total de la provincia»; en Tarapacá y Antofagasta coincide cifra por
cifra con el cuadro general. El área (urbana y rural) solo viene para el total, no por sexo.
Transcrito el cuadro general «Clasificación de los habitantes por departamentos i provincias, según
el sexo i edad» (págs. 467–486, cuatro bloques de cinco páginas): sexo × 26 grupos de edad
(`pub_1895_cg_edad`, con meses bajo 1 año) y total, urbana y rural (`pub_1895_cg_area`), por
departamento, provincia y país. El original tiene muchas erratas: 26 celdas con culpable
identificable (la fila y la columna fallan por lo mismo) van como `inconsistente` con el valor
implicado, y las demás como `excepciones` de los controles. En Colchagua las cifras de menores de 2
años repiten las de 2 a 25 años; las correctas están en el resumen del tomo II, pág. 511
(`pub_1895_colchagua_menores2`). Validación: provincias por sexo = 1952 C5 (salvo Valparaíso, +1
hombre, y Bío-Bío, anotada), decenios del país = 1952 C7 (±1), urbana y rural = 1920 C3 (que trae
corregidas las erratas del cuadro).

**1907.** Índice al final (PDF 1274–1277), por provincia y departamento. Cada departamento trae 11
cuadros numerados (urbana y rural por subdelegación y distrito, entidades pobladas,
nacionalidad, religión, instrucción, edades, profesiones, estado civil, propietarios, defectos
físicos), y cada provincia un resumen. Resumen general de la República en págs. 1261–1308;
indios araucanos en pág. 1309. Memoria, anexos y láminas en PDF 2–67. El desfase va de +65 a −41
(faltan páginas en el escaneo).
- Cuadro 7 de cada departamento (grado de instrucción por edad y sexo; PDF 78–1215): transcritas las
  columnas de total (`pub_1907_c7`, 18 grupos de edad, 79 unidades). Todo cuadra; las provincias
  coinciden por sexo con 1952 C5 y el país sin Tacna, por decenios, con 1952 C7. Los departamentos son
  los de 1907: Tacna incluye Tarata, y Petorca/La Ligua, Melipilla/Cachapoal y Valdivia/La Unión tienen
  otros límites que en el Cuadro 1 de 1920. El impreso usa «...» para celda sin casos (se transcribe «-»).
- Cuadro 1 del resumen de cada provincia (urbana y rural por sexo y departamento; PDF 91–1211;
  Magallanes solo trae el resumen por comarcas, se toma su total): `pub_1907_c1`. Coincide con el
  cuadro 7 y con el Cuadro 3 de 1920, salvo Quillota: su fila cuenta como urbanos 1 450 hombres y
  1 244 mujeres que el total de Valparaíso (y 1920 C3) pone como rurales.

**1920.** Sin índice en el PDF: los capítulos I a IX se ubicaron por sus portadas. Desfase +15
constante. El capítulo I trae los cuadros más útiles para la serie: Cuadro 1 (pág. 1),
población por departamento y provincia de 1865 a 1920; Cuadro 3 (pág. 4), urbana y rural por
departamento en 1895, 1907 y 1920; Cuadro 4 (pág. 6), urbana y rural por sexo en 1920.
Los tres están transcritos (PDF 16–17, 19–20 y 21–22), por departamento y provincia de la
división de 1920, con Tacna (Tarata, Tacna y Arica) desde 1885. La diferencia con el Cuadro 9 de
1952 en el total del país de 1885–1920 es exactamente la provincia de Tacna. ".." = sin dato.
- Cuadro 1: errata en Atacama 1865 (77.456 impreso; los departamentos y el total del país dan
  77.453). En el ejemplar escaneado, Constitución 1895 (26.199) está tachado a mano.
- Cuadro 3: en 1895 y 1907 varios departamentos no traen la división urbana/rural y su
  población va incluida en otros (p. ej., San Antonio en Melipilla, Villarrica en Valdivia,
  Santa Cruz repartido entre Vichuquén y Curicó en 1895); la lista está en el YAML. En 1895 el
  total del país excluye Tacna. En 1920 difiere del Cuadro 4 en Curepto, Talca, Concepción y
  Ancud: el Cuadro 4 cuadra con el Cuadro 1 y con el Cuadro 9 de 1952, así que para 1920 se
  prefiere el Cuadro 4.
- Cuadro 4: todas las sumas cuadran. Un doblez de la hoja tapa las últimas cifras del total de
  Magallanes y de la República, que se reconstruyen como hombres + mujeres (estado `ilegible`).
- Capítulo II, cuadro 4 (págs. 234–275, PDF 249–290): estado civil por edad y sexo de cada
  departamento; transcritas las columnas de total (`pub_1920_ec_edad`, 28 grupos de edad). Valida con
  el Cuadro 4 y, sin Tacna, con el comparativo 7 de 1952 por decenios. Talca imprime como total la cifra
  errada del Cuadro 3 y tiene dos filas erradas (45–49 hombres, 60–64 mujeres y total), resueltas con las
  columnas por estado civil; también hay erratas en La Ligua (2 años) y Llanquihue (40–44, 85–89).

**1930.** Índice en la página 2 del PDF. Cuadro 10 (pág. 56): urbana y rural por provincias,
1895–1930. Urbana = pueblos y ciudades de más de 1.000 habitantes (1907–1930); en 1895 se
incluyeron además algunos caseríos y aldeas. Sus cifras de 1907 y 1920 incluyen el
departamento de Arica, a diferencia del Cuadro 9 de 1952. Las cifras de 1895–1920 del Cuadro 10
están reagrupadas en las provincias de 1930, por lo que no son comparables provincia a provincia
con el Cuadro 9 de 1952 (que usa las provincias de cada censo). Cuadro 9 (PDF 49–53): urbana y
rural × sexo por provincia, departamento y comuna, más los totales del país de 1920 y 1907.
Erratas impresas: Atacama total 61.008 (coherente 61.098; en los cuadros 9 y 10), Penco mujeres
5.441 (5.444) y Cunco rural 16.601 (16.604).
El PDF trae después de la pág. 297 un tomo de edades (numeración propia, desfase ~+307): Cuadro 4,
edad simple × estado civil × sexo por provincia (PDF 315–336; transcritas las columnas de total en
`pub_1930_edad4`), y luego el mismo cuadro por comunas (PDF ~337–480), nacionalidad, religión e
instrucción por comunas y actividades. Erratas del Cuadro 4: Valdivia 30 años (total 5.844, coherente
5.847), 31 años (1.772 → 1.742) y 40 años (hombres 1.213 y total 4.678 → 2.223 y 4.688), coherentes con
1952 C7; en Cautín hombres y mujeres se compensan en ±10 y en Magallanes faltan 1 mujer en las edades.

**1940.** Reedición de cuadros publicados en la Revista Estadística Chilena (1941–46). Las
primeras páginas (PDF 7 en adelante) traen la población por provincia, departamento y comuna de
1875 a 1940, reordenada según la división de 1940. Las cifras
fueron **ajustadas** (~2,8 %) por la Dirección de Estadística, sin publicar la población
efectivamente empadronada (introducción, PDF 4–6). El cuadro urbano-rural por provincias,
departamentos, comunas y distritos (págs. 76–115) no trae total país y tiene inconsistencias
propias: la suma provincial (5.021.474) queda 2.065 bajo el total oficial (5.023.539);
Valparaíso urbana + rural = 423.001 frente a 425.065 impreso (la diferencia son las 2.064
personas de la Bahía, sin clasificar por área); Llanquihue 117.225 frente a 115.425 (errata en
Calbuco: 14.605 por 16.405); Maule, diferencia de 1. Las cifras revisadas aparecen en 1952
(Cuadro 9) y 1960 (Cuadro 1.1.1): urbana 2.639.311, rural 2.384.228; la revisión traspasa 6.788
personas de Colchagua a Santiago. Transcrito hasta comuna (PDF 82–121, 388 filas); los totales van
después de sus unidades (`totales_al_final` en el YAML). Otras erratas: Antofagasta total
115.147 (145.147), viviendas rurales de Atacama y Yungay, mujeres rurales de Ñuble (77.709 por
77.679). La provincia de Osorno figura separada de Llanquihue.
Población por grupos quinquenales de edad, sexo y provincias (págs. 332–335, PDF 338–341,
mecanografiado): cifras revisadas; cada provincia cuadra, y la fila del país difiere de la suma de
las provincias en seis celdas (±1 a ±3, compensadas dentro de cada sexo).

**1952.** El PDF (2.431 págs.) junta varias piezas:
- Tomo I, Resumen del País (PDF 1–239; índice en PDF 232–234): reseña histórica, cuadros
  comparativos 1–10 (págs. 30–45) y cuadros nacionales 1–31 por provincia (págs. 103–269).
  **Faltan en el escaneo las págs. 85–116**, con los gráficos 1–10 y los cuadros nacionales 1
  (edades × sexo × área) y 2 (provincias × sexo × área). El Cuadro 4 (pág. 123) trae la población,
  superficie y densidad por provincia, departamento y comuna. Desfase −3/−4 hasta la pág. 84 y −39
  desde la 131.
- Tomo II, Núcleo Central (PDF 1056–1950; índice en PDF 1947–1949): Aconcagua, Valparaíso,
  Santiago, O'Higgins y Colchagua, con 14 cuadros cada una. Los cuadros 1–8 traen el resumen de la
  provincia y luego cada comuna. Los preliminares (PDF 1069–1074) traen la población por comuna
  de 1875 a 1940. Desfase de +1082 a +1078 según la provincia.
- División territorial y población por entidades (mecanografiado, sin índice ni paginación
  continua): Concepción, Ñuble, Linares, Maule, Arauco, Bío-Bío, Malleco y Cautín en PDF 240–1055;
  Tarapacá, Antofagasta, Atacama, Coquimbo, Aconcagua y Valparaíso (con Isla de Pascua) en
  PDF 1951–2373. Por comuna-subdelegación: decreto de límites, mapa y población por distrito y
  entidad (categoría, viviendas, hombres, mujeres). Cada provincia cierra con una hoja de
  abreviaturas de las categorías.
- Censo de vivienda (PDF 2374–2431).
Talca, Curicó y las provincias de Valdivia a Magallanes solo aparecen en los cuadros por
provincia del Tomo I.
Cuadros comparativos 5 a 7 (págs. 39–43, PDF 35–39), sacados de las publicaciones de cada censo
(validación pendiente contra ellas):
- C5: provincias × sexo, 1865–1952; mismos totales que el C9. Malleco 1885: hombres + mujeres
  quedan 3.000 bajo el total (Mariluán sin sexo); hombres y mujeres del país 1895 difieren en 1 de
  la suma de las provincias. Santiago 1952: una mancha tapa una cifra del total (1.754.954).
- C6: provincias × sexo × edad (seis tramos: hasta 7, 8–15, 16–25, 26–50, 51–80, 81 y más) en 1865
  y 1875. Dos partes con las mismas filas (PDF 36–37 y 38); en el CSV van juntas y el YAML indica
  la página de las columnas de la segunda (`columnas` en `paginas`). Todas las sumas cuadran.
- C7: país por decenios de edad, 1885–1952 (edad ignorada solo en 1952). Los grupos de 1885 suman
  2.497.796 frente al total impreso de 2.497.797.
Cuadro Nacional 4 (PDF 86–89): población por provincia, departamento y comuna (271 comunas),
transcrita sin superficie ni densidad. Erratas: Depto. Petorca impreso 34.314 (comunas y densidad:
34.413); Imperial 75.477 (75.467); las comunas de Rancagua suman 2.000 más que el departamento,
las de Valdivia 2 menos y las de Castro 5 menos. Cuadro Nacional 7 (PDF 102): la columna «Total
general» da país × sexo × edad quinquenal y reemplaza al Cuadro Nacional 1, ausente.
Cuadro comparativo 9 (págs. 44–45, PDF 40–41): provincias × total/urbana/rural de 1865 a 1952.
En 1885–1920 excluye el departamento de Arica. Errata: Santiago 1865 rural impreso 200.118
(coherente: 200.148).

**1960.** Índice en PDF 5–7. Cuadros girados 90° (`--rotar 90`). Cuadro 1.1.1 (PDF 138):
urbana y rural por provincias 1940, 1952 y 1960; la urbana 1940 puede leerse "2.638.311"
(cuadra 2.639.311). Errata: Chiloé 1952 total impreso 100.637 (coherente 100.687, como en 1952).
Cuadro 1.2 (PDF 142–143): provincias × área × sexo, 1960. En la tipografía negrita de los
totales se confunden 0, 6, 8 y 9: se transcriben como suma de las filas urbana y rural.
Cuadro 1.2.1 (PDF 144–145): provincias × 17 grupos de edad, sin sexo. Cuadro 1.3 (PDF 156–160):
país × área × sexo por años simples; los menores de 1 año vienen por meses (dimensión `meses`)
y la última fila, «100 años», se toma como 100 y más. Todas las sumas cuadran.

**1970.** Volumen "Total País": sin cuadros por provincia de población por área. Índice en
PDF 2–3; conceptos y definiciones en PDF 4–9.
Transcritos el Cuadro 3 (país × área × sexo × edad simple, PDF 11–14; todas las sumas cuadran) y
la columna TOTAL del Cuadro 5 (población por provincia, PDF 21). Los demás cuadros por provincia
son de subpoblaciones (10, 5 o 12 años y más). Los volúmenes por provincia de 1970 no están en los
PDF disponibles.

**1982.** Tomo I: índice en PDF 5–6. Cuadro 1.01 repetido en secciones TOTAL (PDF 40–61),
URBANO (PDF 62–83) y RURAL (PDF 84–104), por región, provincia y comuna; las secciones urbano y
rural omiten las unidades sin población del área. Las páginas del PDF ya vienen en la orientación
correcta (no usar `--rotar`; el visor puede mostrarlas giradas). El OCR lee mal este listado
(confunde 0/C, 8/6 y separadores): se transcribió leyendo cada página a 170 dpi. Sin erratas:
todas las sumas cuadran. Tomo II (índice en PDF 5; desfase +15): características ocupacionales
(cuadros 4.06–4.18) y educacionales (5.01–5.04). Tomo III (índice en PDF 5–7; desfase ~+56):
vivienda (1.01–1.06), hogar (2.01–2.11) y familia (3.01–3.23), varios repetidos en cifras
relativas.

**1992** (publicación "Ciudades, pueblos y aldeas"). No trae totales país ni urbano/rural
explícitos: total = suma de las 13 regiones del Cuadro 1; urbana = ciudades + pueblos del
Cuadro 5. Al extraer texto, a veces el nombre y la primera cifra vienen en la misma línea
(p. ej. "San Vicente de Taguatagua (27) 13.843"): contrastar siempre el Cuadro 3 con el 5.
