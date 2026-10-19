# Estado del proyecto

Punto de retorno para retomar el trabajo. El plan completo y su lista de tareas están en
[plan.md](plan.md); este archivo resume dónde quedó cada punto, las decisiones tomadas y lo
que sigue. Actualizarlo al cerrar cada sesión de trabajo.

**Última actualización:** 2026-10-16 (solo commits locales; nada subido a GitHub todavía).

## Decisiones tomadas

| Decisión | Detalle |
|---|---|
| Proyecto personal | Repositorio `github.com/edgardo-cerda/censos-chile`, independiente del INE. |
| Solo datos públicos | Publicaciones censales y microdatos entregados por transparencia. No usar nada interno (p. ej. el diccionario 2024 sin anonimizar de la carpeta `otros`). |
| Sin IPUMS | Se descartó por completo cualquier uso de IPUMS. |
| Librerías | Python y R. |
| Microdatos 1992–2024 | Los de 1982 se descartaron (comunas con códigos propios sin nombres, sin libro de códigos, área urbana/rural que no reproduce lo publicado). 1982 se trata desde sus volúmenes publicados, como los censos anteriores. |
| 2012 excluido | Resultados no validados como estadística oficial. |
| Edad | Tope común de 85 años (2024 trunca en 85); edad suprimida de 2024 se informa como "ignorada". |
| Región | Dos versiones exactas: DPA1974 (13 regiones) y DPA2018 (16). |
| Diccionario consolidado | Antes de armonizar, consolidar variables y categorías de 1992–2024 en un Excel generado desde CSV versionados. |
| Publicación | No subir a GitHub hasta que el autor lo indique. |
| Seguimiento | Después de cada avance se actualizan este archivo y la planilla `productos/avance/avance_censos_historicos.xlsx` (`herramientas/resumen_avance.py`, abrir y guardar en Excel para calcular las fórmulas). |
| Digitalización | Cada cuadro se transcribe tal como está impreso (CSV) con un YAML de procedencia y mapeo; las erratas de la publicación se conservan y se anotan como `inconsistente`, no se corrigen. |
| Cuadros comparativos | Para ganar eficiencia, los censos anteriores se rescatan primero desde los cuadros comparativos de publicaciones posteriores (p. ej., 1952 C5–C9, 1920 C1–C3), pero cada cifra rescatada debe validarse contra la publicación original del censo (contraste entre cuadros). |
| Núcleo | Población por territorio × área × sexo × edad (estructura demográfica básica). Primero territorio × área × sexo; luego la edad. |

## Estado por fase

### Fase 0: base del proyecto
| Punto | Estado |
|---|---|
| Repositorio, licencias, estructura | ✅ Hecho (commits locales) |
| URL de 2017 | ✅ Registradas en `fuentes.yaml` |
| URL directas de 2024 y de los PDF históricos | ⏳ Pendiente: las páginas del INE cargan los enlaces dinámicamente |
| Números de solicitudes de transparencia (1992, 2002) | ⏳ Pendiente (autor) |
| Publicaciones digitalizadas | ✅ Todas salvo 1843 y 1854 (no digitalizadas) |

### Fase 1: inventarios
| Punto | Estado |
|---|---|
| Inventario automático de microdatos 1992–2024 | ✅ Totales de personas coinciden con los oficiales |
| Matriz de concordancia (`metadatos/concordancia/`) | 🟡 Borrador, 56 conceptos; 2002 corregido con su cuestionario |
| Cuestionarios 1992, 2002, 2017, 2024 | ✅ Disponibles (2002 escaneado, sin capa de texto; no hay libro de códigos 2002) |
| Cuestionario de 1982 | ⏳ Buscar en los volúmenes publicados |
| Catálogo de cuadros de las publicaciones | ✅ 1813–1992, 640 entradas (ver Fase 4); desagregación registrada en los cuadros de población |

### Fase 2: núcleo
| Punto | Estado |
|---|---|
| Diccionario consolidado (`productos/diccionario/diccionario_censos.xlsx`) | 🟡 v0.1: 360 variables, 2.476 códigos; 2017 y 2024 completos; faltan 60 códigos de 1992 y 198 de 2002 |
| Fichas región, área, sexo, edad | 🟡 Borrador |
| Fichas parentesco, tipo de vivienda | 🟡 Borrador; recodificación verificada contra el inventario (`validacion/revisar_fichas.py`) |
| Serie de población región × área × sexo × edad, 1992–2024 | ✅ `productos/tabulados/poblacion_microdatos.csv` (8.448 filas) |
| Serie por comuna | ⏳ Falta correspondencia de comunas 1992 → DPA2018 (por nombre, tablas `COMUNAS_1992`/`COMUNAS_2002`) |
| Validación contra publicaciones | 🟡 1992 coincide (total y urbano); faltan cifras regionales y de 2002, 2017, 2024 |
| Librerías Python y R v0.1 | ⏳ No iniciado |
| Sitio de documentación | ⏳ No iniciado |

### Fases 3 a 5
| Punto | Estado |
|---|---|
| 3. Módulos temáticos | ⏳ No iniciado (solo borrador en la concordancia) |
| 4. Digitalización histórica 1813–1982 | 🟡 Herramientas y formato listos; catálogo completo 1813–1992 (640 entradas; los cuadros nacionales 1 y 2 de 1952 faltan en el escaneo). Los 205 cuadros de población traen censos con datos, nivel territorial, variables (área, sexo, edad) y cobertura; la planilla compara lo transcrito con lo disponible en los PDF. 1843 y 1854 tienen cifras por departamento en los sinópticos de 1865 y 1875 y en el resumen de 1907. Transcritos: 1952 cuadros nacionales 4 (comunas) y 7 (país × sexo × edad); 1960 C1.2.1 (provincia × edad) y C1.3 (país × área × sexo × edad simple); 1970 C3 (país × área × sexo × edad simple) y C5 (total por provincia); 1982 C1.03 (país × área × sexo × edad simple); 1835 departamentos × sexo × estado (arts. 34–42); 1813 censos de provincia (14 partidos × sexo × edad y estado civil; distritos × sexo); 1865 clasificación por departamentos (edad × sexo, 52 departamentos; cuadra con la de provincias); cuadros sinópticos de 1865 y 1875 (departamentos y provincias de 1835, 1843, 1854, 1865 y 1875; validados entre sí); 1865 clasificación por provincias (edad × sexo; valida 1952 C6); 1952 comparativos C5 (provincia × sexo 1865–1952), C6 (provincia × sexo × edad 1865 y 1875) y C7 (edad del país 1885–1952); 1920 C1 (departamento/provincia 1865–1920), C3 (× área 1895–1920) y C4 (× área × sexo 1920); 1952 C9; 1930 C9 (provincia/departamento/comuna × área × sexo) y C10; 1960 C1.1.1 y C1.2; 1982 C1.01 (región/provincia/comuna × área × sexo, 1.166 filas); 1940 urbano-rural hasta comuna (388 filas, con viviendas). Total 21.935 cifras; erratas de imprenta anotadas; contraste entre cuadros sin diferencias de transcripción. Ver [digitalizacion.md](digitalizacion.md) y la planilla `productos/avance/avance_censos_historicos.xlsx` |
| 5. Publicación (Zenodo, CRAN/PyPI) | ⏳ No iniciado |

## Pendientes del autor

- Números de las solicitudes de transparencia de 1992 y 2002.
- Indicar cuándo subir el repositorio a GitHub.

## Próximos pasos (en orden)

1. Revisión del diccionario consolidado por el autor; completar los códigos sin etiqueta de
   1992 y 2002 (99/9 probablemente "ignorado"; ocupación y rama 2002; uso de piezas 2002).
2. Revisión de las fichas de parentesco y tipo de vivienda por el autor (operativos especiales de
   1992 y 2002; efecto del censo de derecho de 2024 en viviendas colectivas).
3. Correspondencia de comunas 1992 → DPA2018 y serie de población por comuna.
4. Cifras publicadas de referencia para 2002, 2017 y 2024, y regionales.
5. Esqueleto de las librerías (`tabulado()`, `diccionario()`). Los microdatos de 2017 vienen en
   `.rar`: en R usar el paquete `archive`; en Python requiere una dependencia adicional.
6. Fase 4: núcleo = población por territorio × área × sexo × edad, al nivel más fino que traigan
   los PDF. Orden de trabajo: del censo más reciente hacia atrás (1982, 1970, 1960, 1952, 1940,
   1930, 1920, 1907, 1895, 1885, 1875, 1865). El estado de cada censo y el cuadro que falta están en
   la planilla de avance (columnas «Estado» y «Pendiente»). Resumen:
   - 1982, 1970 y 1960: completos según los PDF (la edad solo viene para el país; de 1970 solo hay
     el volumen «Total País»).
   - 1952: comuna (total), provincia × área y × sexo, país × sexo × edad. Falta área × sexo por
     provincia (Cuadro Nacional 2, ausente en el escaneo: buscar otro ejemplar) y el detalle por
     comuna del Tomo II (Núcleo Central).
   - Siguen 1940, 1930, 1920, 1907, 1895, 1885 y 1875.
   - Ya hechos de los censos antiguos: 1865 provincia y departamento × sexo × edad; 1835
     departamento × sexo; 1843 y 1854 departamento (sinópticos); 1813 partido × sexo × edad y
     distrito × sexo. Borrador sin validar: parroquias de 1865 (`digitalizacion/borradores/`).

## Cómo retomar

- Repositorio local: `C:\Users\escerdae\proyectos\censos-chile`.
- Datos originales (no versionados): carpeta `datos_originales` de `config.yaml`.
- Caché Parquet: `C:/Users/escerdae/proyectos/censos-chile-datos/cache`.
- Regenerar productos:
  ```
  python herramientas/inventario_microdatos.py   # solo si cambian los microdatos
  python herramientas/importar_etiquetas_oficiales.py
  python herramientas/generar_diccionario.py
  python pipelines/poblacion_nucleo.py
  python validacion/validar_poblacion.py
  python pipelines/tabulados_publicaciones.py   # cuadros digitalizados
  python herramientas/resumen_avance.py        # planilla de avance de los censos históricos
  ```
- Hallazgos sobre cada base: [notas_microdatos.md](notas_microdatos.md).
- Procedimiento de digitalización y notas de cada publicación: [digitalizacion.md](digitalizacion.md).
- PDF de las publicaciones: `<datos_originales>/censos previos`. Ahí quedan también los archivos
  de la extracción previa (`notas_extraccion_censos_previos.txt`, `indices_censos_1930_1992.xlsx`,
  `poblacion_urbana_rural_censos_1930_1992.xlsx`), ya incorporados al repositorio.
