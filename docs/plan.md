# Plan del proyecto

> Estado de avance, decisiones y próximos pasos: [estado.md](estado.md).

## Objetivo

Reunir los resultados de todos los censos de población y vivienda de Chile en un formato
común, comparable en el tiempo, con procedencia verificable, y ponerlos a disposición mediante
librerías de Python y R, archivos descargables y un sitio de documentación.

## Principios

1. **Nada se pierde.** Las variables y cifras originales se conservan siempre; la armonización se agrega encima.
2. **Todo es trazable.** Cada cifra transcrita indica documento, cuadro y página; cada archivo
   original tiene URL o vía de acceso y checksum.
3. **La comparabilidad se documenta, no se fuerza.** Cuando cambian definiciones (urbano/rural,
   pueblos originarios, nivel educacional, límites territoriales), se registra en una nota de
   comparabilidad en lugar de "corregir" la cifra.
4. **Solo fuentes públicas.** Publicaciones censales y microdatos entregados por el INE como
   información pública (descarga web o solicitud de acceso a la información).
5. **Reproducible.** Todo dato derivado se genera con código del repositorio a partir de las fuentes.

## Productos

### A. Tabulados armonizados (1813–2024)

Formato largo con el esquema de [metadatos/esquema_tabulados.yaml](../metadatos/esquema_tabulados.yaml).
Hasta 1982 provienen de la digitalización de los libros; desde 1992 se calculan con los
microdatos y se contrastan con las cifras publicadas en su momento.

Decisiones de diseño:
- La edad se guarda como intervalo (`edad_min`, `edad_max`) para poder reagregar agrupaciones distintas.
- Totales y "no aplica" usan los códigos `_T` y `_Z` (convención SDMX).
- El territorio se guarda con su código y nombre originales, la versión de DPA vigente y,
  cuando es posible, su correspondencia con la DPA 2024.

### B. Microdatos armonizados (1992–2024)

Los microdatos de 1982 existen pero se descartaron por problemas de codificación y documentación
(ver [notas_microdatos.md](notas_microdatos.md)); 1982 se trata como un censo con publicaciones.

Tablas de viviendas, hogares y personas por censo con:
- identificadores comunes (`censo`, `id_vivienda`, `id_hogar`, `id_persona`),
- territorio original y en DPA 2024,
- variables originales (con nombres normalizados) y variables armonizadas con un código
  general (comparable entre todos los censos) y uno detallado (específico de cada censo).

### C. Metadatos

- `censos.yaml`: censos levantados y fuentes disponibles.
- `fuentes.yaml`: documentos y archivos originales.
- `variables/`: una ficha por variable armonizada: definición, universo, categorías y,
  por censo, variable original, transformación y nota de comparabilidad.
- `territorio/`: códigos por censo y correspondencias, con ponderadores cuando una unidad se divide.

## Fases

### Fase 0: base del proyecto
- [x] Repositorio, licencias (MIT para el código, CC BY 4.0 para los datos) y estructura.
- [ ] Completar `fuentes.yaml`: URL directas de 2024 y de los PDF históricos; números de solicitud
      de transparencia de 1992 y 2002 (pendiente).
- [x] Reunir las publicaciones digitalizadas: todas salvo 1843 y 1854, que no están digitalizadas.

### Fase 1: inventarios
- [x] Inventario automático de microdatos 1992–2024 (`herramientas/inventario_microdatos.py`).
      Hallazgos en [notas_microdatos.md](notas_microdatos.md).
- [ ] Matriz de concordancia concepto × censo para microdatos (borrador listo; falta verificar
      2002 contra su cuestionario).
- [x] Cuestionarios de 1992 (en la carpeta de 1982), 2002 (escaneado), 2017 y 2024.
      No existe libro de códigos de 2002: las etiquetas se toman del cuestionario.
- [ ] Cuestionario de 1982 (para la digitalización; probablemente en los volúmenes publicados).
- [ ] Catálogo de cuadros de las publicaciones: censo, número, título, variables,
      desagregación, nivel territorial, página impresa y página del PDF.

### Fase 2: núcleo (primera versión pública)
- [ ] **Diccionario consolidado de microdatos 1992–2024** (`productos/diccionario/diccionario_censos.xlsx`),
      antes de armonizar cualquier variable. Permite ver de un vistazo qué existe en cada censo:
  - hoja `variables`: una fila por variable original (censo, tabla, nombre, etiqueta, pregunta
    del cuestionario, universo, tipo, n.º de categorías, % sin respuesta, concepto asignado);
  - hoja `categorias`: una fila por código (censo, tabla, variable, código en la base, etiqueta,
    frecuencia, fuente de la etiqueta);
  - hoja `matriz`: concepto × censo con el nombre de la variable en cada año (vista cruzada de
    la concordancia).
  Etiquetas desde el diccionario oficial (2024), los cuestionarios (1992, 2002, 2017) y las tablas
  auxiliares de la entrega (1992, 2002). Las fuentes de verdad son CSV versionados en
  `metadatos/diccionario/`; el Excel se genera con un script. En esta fase se completa para las
  variables de identificación, territorio y demografía básica.
  Versión 0.1 generada (`herramientas/generar_diccionario.py`): 360 variables y 2.476 códigos;
  2017 y 2024 completos con etiquetas oficiales; quedan sin etiqueta 60 códigos de 1992 y 198 de
  2002 (sobre todo ocupación y rama a 2 dígitos y uso de piezas).
- [ ] Variables núcleo armonizadas: fichas en borrador de región, área, sexo, edad, parentesco y
      tipo de vivienda. `validacion/revisar_fichas.py` comprueba que la recodificación cubra todos
      los códigos observados. Falta revisión del autor y aplicarlas en los pipelines.
- [x] Serie de población por región (DPA1974 y DPA2018) × área × sexo × edad quinquenal,
      1992–2024, desde microdatos (`pipelines/poblacion_nucleo.py`).
- [ ] Serie por comuna (requiere correspondencia de comunas 1992 -> DPA2018).
- [ ] Validación de microdatos contra los libros publicados (`validacion/`): 1992 coincide;
      faltan cifras publicadas regionales y de 2002, 2017 y 2024.
- [ ] Librerías Python y R v0.1: `tabulado()`, `microdatos()`, `diccionario()`, `territorio()`.
- [ ] Sitio de documentación.

### Fase 3: módulos temáticos
Uno a la vez, con el mismo flujo (diccionario consolidado del módulo → ficha → correspondencia
por censo → código → validación → versión). El primer paso de cada módulo completa y verifica en
el diccionario consolidado las variables y categorías del tema en todos los censos:
educación; vivienda y servicios; migración y lugar de nacimiento; trabajo (ocupación y rama);
hogares; fecundidad; pueblos originarios; discapacidad y religión.

### Fase 4: digitalización histórica (1813–1982)
Catálogo de cuadros → render de página → OCR o transcripción asistida → doble verificación →
controles aritméticos → CSV con fuente. Prioridad según demanda y cobertura del núcleo.
Procedimiento y notas por publicación en [digitalizacion.md](digitalizacion.md).
- [x] Herramientas: render y OCR de páginas (`herramientas/paginas.py`), formato de
      transcripción (CSV tal como está impreso + YAML) y pipeline con controles
      (`pipelines/tabulados_publicaciones.py`).
- [ ] Catálogo de cuadros (`metadatos/catalogo_cuadros.csv`): 1930, 1940, 1952 (solo C9), 1960,
      1970, 1982 (Tomo I) y 1992 cargados desde los índices; faltan 1813–1920, 1952 completo
      y 1982 tomos II y III.
- [ ] Núcleo: población por provincia × área (× sexo) de cada censo. Piloto hecho:
      1952 C9 (provincias × urbana/rural, 1865–1952).

### Fase 5: publicación y comunidad
Versiones con DOI (Zenodo), CRAN/PyPI, guía de contribución, registro público de erratas
(incluidas las inconsistencias de las propias publicaciones).

## Flujo para incorporar una variable

0. Variables y categorías originales completas y verificadas en el diccionario consolidado.
1. Ficha en `metadatos/variables/<variable>.yaml` con definición, universo y categorías armonizadas.
2. Por cada censo: variable original, valores observados (desde `metadatos/inventario/`),
   regla de transformación y nota de comparabilidad.
3. Código de transformación en el pipeline del censo. `python validacion/revisar_fichas.py <variable>`
   verifica la recodificación contra las frecuencias del inventario antes de llevarla al pipeline.
4. Validación: totales contra publicaciones, coherencia entre censos, tests automáticos.
5. Revisión y publicación en la siguiente versión.
