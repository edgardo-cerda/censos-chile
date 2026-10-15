# Digitalización de las publicaciones (Fase 4)

Cómo se transcriben los cuadros de las publicaciones censales escaneadas (1813–1982) y qué se
sabe de cada PDF. Las cifras resultantes van a `productos/tabulados/tabulados_publicaciones.csv`.

## Flujo

1. **Ubicar el cuadro** en [metadatos/catalogo_cuadros.csv](../metadatos/catalogo_cuadros.csv)
   (título, página impresa, página del PDF y si esta última está verificada o es estimada).
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
   impreso: mismas filas, mismas columnas, nombres como aparecen. Guion impreso = `-`; celda en
   blanco = vacío. Las cifras sin separador de miles.
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
  conocidos están en [metadatos/paginacion.csv](../metadatos/paginacion.csv).
- Algunas tablas vienen giradas 90° (p. ej. 1960, cuadros 1.1.1 y 1.2): `--rotar 90`.
- 1970 y 1982 son listados de computador: 1970 sin separador de miles, 1982 con coma (11,329,736).
- OCR (RapidOCR): 12–17 s por página a 130 dpi con un solo proceso; varios procesos en paralelo
  agotan la memoria. Confunde 8/9, 1/l y los separadores de miles y omite celdas: sirve para
  recorrer muchas páginas buscando filas, nunca como transcripción final.
- 1843 y 1854 no están digitalizados.

## Notas por publicación

Hallazgos de la extracción previa (septiembre de 2026), antes de este flujo.

**1930.** Índice en la página 2 del PDF. Cuadro 10 (pág. 56): urbana y rural por provincias,
1895–1930. Urbana = pueblos y ciudades de más de 1.000 habitantes (1907–1930); en 1895 se
incluyeron además algunos caseríos y aldeas. Sus cifras de 1907 y 1920 incluyen el
departamento de Arica, a diferencia del Cuadro 9 de 1952. Las cifras de 1895–1920 del Cuadro 10
están reagrupadas en las provincias de 1930, por lo que no son comparables provincia a provincia
con el Cuadro 9 de 1952 (que usa las provincias de cada censo). Cuadro 9 (PDF 49–53): urbana y
rural × sexo por provincia, departamento y comuna, más los totales del país de 1920 y 1907.
Erratas impresas: Atacama total 61.008 (coherente 61.098; en los cuadros 9 y 10), Penco mujeres
5.441 (5.444) y Cunco rural 16.601 (16.604).

**1940.** Reedición de cuadros publicados en la Revista Estadística Chilena (1941–46). Las cifras
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

**1952.** Sin índice. Cuadro 9 (pág. 44–45, PDF 40–41): provincias × total/urbana/rural de
1865 a 1952. En 1885–1920 excluye el departamento de Arica. Errata: Santiago 1865 rural
impreso 200.118 (coherente: 200.148).

**1960.** Índice en PDF 5–7. Cuadros girados 90° (`--rotar 90`). Cuadro 1.1.1 (PDF 138):
urbana y rural por provincias 1940, 1952 y 1960; la urbana 1940 puede leerse "2.638.311"
(cuadra 2.639.311). Errata: Chiloé 1952 total impreso 100.637 (coherente 100.687, como en 1952).
Cuadro 1.2 (PDF 142–143): provincias × área × sexo, 1960. En la tipografía negrita de los
totales se confunden 0, 6, 8 y 9: se transcriben como suma de las filas urbana y rural.

**1970.** Volumen "Total País": sin cuadros por provincia de población por área. Índice en
PDF 2–3; conceptos y definiciones en PDF 4–9.

**1982.** Tomo I: índice en PDF 5–6. Cuadro 1.01 repetido en secciones TOTAL (PDF 40–61),
URBANO (PDF 62–83) y RURAL (PDF 84–104), por región, provincia y comuna; las secciones urbano y
rural omiten las unidades sin población del área. Las páginas del PDF ya vienen en la orientación
correcta (no usar `--rotar`; el visor puede mostrarlas giradas). El OCR lee mal este listado
(confunde 0/C, 8/6 y separadores): se transcribió leyendo cada página a 170 dpi. Sin erratas:
todas las sumas cuadran. Tomos II y III sin revisar.

**1992** (publicación "Ciudades, pueblos y aldeas"). No trae totales país ni urbano/rural
explícitos: total = suma de las 13 regiones del Cuadro 1; urbana = ciudades + pueblos del
Cuadro 5. Al extraer texto, a veces el nombre y la primera cifra vienen en la misma línea
(p. ej. "San Vicente de Taguatagua (27) 13.843"): contrastar siempre el Cuadro 3 con el 5.
