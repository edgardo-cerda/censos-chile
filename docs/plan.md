# Plan del proyecto

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
Hasta 1970 provienen de la digitalización de los libros; desde 1982 se calculan con los
microdatos y se contrastan con las cifras publicadas en su momento.

Decisiones de diseño:
- La edad se guarda como intervalo (`edad_min`, `edad_max`) para poder reagregar agrupaciones distintas.
- Totales y "no aplica" usan los códigos `_T` y `_Z` (convención SDMX).
- El territorio se guarda con su código y nombre originales, la versión de DPA vigente y,
  cuando es posible, su correspondencia con la DPA 2024.

### B. Microdatos armonizados (1982–2024)

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
- [ ] Completar `fuentes.yaml`: URL pública o número de solicitud de transparencia de cada archivo.
- [ ] Ubicar los censos sin publicación digital local (1843, 1854, 1875, 1885, 1895).

### Fase 1: inventarios
- [x] Inventario automático de microdatos 1982–2024 (`herramientas/inventario_microdatos.py`).
      Hallazgos en [notas_microdatos.md](notas_microdatos.md).
- [ ] Matriz de concordancia concepto × censo para microdatos (borrador listo; falta verificar
      1982 y 2002 contra sus cuestionarios).
- [ ] Obtener cuestionarios y libros de códigos de 1982 y 2002.
- [ ] Catálogo de cuadros de las publicaciones: censo, número, título, variables,
      desagregación, nivel territorial, página impresa y página del PDF.

### Fase 2: núcleo (primera versión pública)
- [ ] Variables núcleo armonizadas: territorio, área urbana/rural, sexo, edad, parentesco,
      tipo de vivienda.
- [ ] Serie de población por sexo × edad quinquenal × área: país y división mayor para todos
      los censos; comuna desde 1982.
- [ ] Validación de microdatos 1982–2002 contra los libros publicados.
- [ ] Librerías Python y R v0.1: `tabulado()`, `microdatos()`, `diccionario()`, `territorio()`.
- [ ] Sitio de documentación.

### Fase 3: módulos temáticos
Uno a la vez, con el mismo flujo (ficha → correspondencia por censo → código → validación → versión):
educación; vivienda y servicios; migración y lugar de nacimiento; trabajo (ocupación y rama);
hogares; fecundidad; pueblos originarios; discapacidad y religión.

### Fase 4: digitalización histórica (1813–1970)
Catálogo de cuadros → render de página → OCR o transcripción asistida → doble verificación →
controles aritméticos → CSV con fuente. Prioridad según demanda y cobertura del núcleo.

### Fase 5: publicación y comunidad
Versiones con DOI (Zenodo), CRAN/PyPI, guía de contribución, registro público de erratas
(incluidas las inconsistencias de las propias publicaciones).

## Flujo para incorporar una variable

1. Ficha en `metadatos/variables/<variable>.yaml` con definición, universo y categorías armonizadas.
2. Por cada censo: variable original, valores observados (desde `metadatos/inventario/`),
   regla de transformación y nota de comparabilidad.
3. Código de transformación en el pipeline del censo.
4. Validación: totales contra publicaciones, coherencia entre censos, tests automáticos.
5. Revisión y publicación en la siguiente versión.
