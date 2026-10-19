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
| Digitalización | Cada cuadro se transcribe tal como está impreso (CSV) con un YAML de procedencia y mapeo; las erratas de la publicación se conservan y se anotan como `inconsistente`, no se corrigen. |

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
| Catálogo de cuadros de las publicaciones | ✅ 1813–1992, 638 entradas (ver Fase 4) |

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
| 4. Digitalización histórica 1813–1982 | 🟡 Herramientas y formato listos; catálogo completo 1813–1992 (638 entradas: 423 cuadros, 133 bloques por provincia y 82 textos; página del PDF verificada en 214 y estimada en 399; los cuadros nacionales 1 y 2 de 1952 faltan en el escaneo). Transcritos: 1920 C1 (departamento/provincia 1865–1920), C3 (× área 1895–1920) y C4 (× área × sexo 1920); 1952 C9; 1930 C9 (provincia/departamento/comuna × área × sexo) y C10; 1960 C1.1.1 y C1.2; 1982 C1.01 (región/provincia/comuna × área × sexo, 1.166 filas); 1940 urbano-rural hasta comuna (388 filas, con viviendas). Total 13.689 cifras; erratas de imprenta anotadas; contraste entre cuadros sin diferencias de transcripción. Ver [digitalizacion.md](digitalizacion.md) y la planilla `productos/avance/avance_censos_historicos.xlsx` |
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
6. Fase 4: núcleo = población por territorio × área × sexo × edad. Ningún censo histórico lo
   tiene completo todavía: falta la edad en todos. Territorio × área × sexo: 1952 por comuna desde
   el Tomo I (Cuadro 4) y el Tomo II (Cuadro 1 de cada provincia); sexo por provincia de 1865 a
   1952 en el comparativo 5 de 1952; 1907 por departamento en los resúmenes del volumen de 1907.
   Los cuadros de edad de cada censo están en la planilla de avance (columna «Pendiente»). Los
   cuadros nacionales 1 y 2 de 1952 faltan en el escaneo: buscar otro ejemplar.

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
