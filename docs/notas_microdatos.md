# Notas sobre los microdatos originales

Observaciones del inventario automático (`herramientas/inventario_microdatos.py`).
Perfiles completos en [metadatos/inventario/](../metadatos/inventario/) y correspondencias
en [metadatos/concordancia/concordancia_microdatos.csv](../metadatos/concordancia/concordancia_microdatos.csv).

## Control de totales

| Censo | Personas en microdatos | Viviendas | Hogares |
|---|---:|---:|---:|
| 1992 | 13.348.401 | 3.369.928 | 3.303.894 |
| 2002 | 15.116.435 | 4.400.247 | sin tabla |
| 2017 | 17.574.003 | 6.499.574 | 5.664.678 |
| 2024 | 18.480.432 | 7.664.466 | 6.622.597 |

El total de personas de cada censo coincide con la población oficial publicada.
Los totales de viviendas y hogares incluyen todos los registros (particulares, colectivas,
desocupadas, etc.) y aún no se contrastan con las publicaciones.

## 1982 (descartado)

Los microdatos de 1982 existen (entregados por transparencia) pero **no se usan en el proyecto**.
Los resultados de 1982 se tomarán de los volúmenes publicados, como los censos anteriores.
Motivos encontrados en el inventario:

- Códigos de comuna propios (201–674), distintos del CUT y sin tabla de nombres en la entrega.
- Sin libro de códigos ni cuestionario: el archivo `Cuestionario Censal.xls` de la carpeta de 1982
  corresponde al cuestionario de 1992.
- El área urbana/rural no reproduce lo publicado: 239.897 personas más como rurales que en el
  Cuadro 1.01 del volumen I (la diferencia se concentra en localidades de categoría 11 y 12).
- Variables con valores irregulares (`Nacional`) o universos sin documentar (`Sabe_leer`).

El total de personas (11.329.736) y los totales por sexo sí coinciden con lo publicado.

## 1992

- CSV en **latin-1**, exportado desde R (primera columna = número de fila).
- La geografía está en `PORTAFOLIOS` (comuna, área, distrito, zona, localidad, entidad); viviendas,
  hogares y personas se unen por `Portafolio` + `Vivienda` + `Hogar`.
- Las comunas de nacimiento, residencia habitual y residencia en 1987 vienen con sufijo `_Origen3`
  (una de varias codificaciones posibles; ver `Entrega_censo1992.xls`).
- Preguntas de pueblos originarios (`Cultura`) y religión solo para personas de 14 años o más.
  Los conteos coinciden con los publicados (mapuche 928.060; aymara 48.477; rapanui 21.848).
- Incluye variables derivadas ajenas al cuestionario: `Puntaje`, `CSE_categoria`, `CSE_Decil`, `Quintil_por_puntaje`.
- El código 0 corresponde a "no aplica" (verificado contra el universo de cada pregunta).
- Tabla adicional `USO_PIEZAS` (13,8 millones de filas: una por pieza). 112 piezas apuntan a
  viviendas (`Portafolio` + `Vivienda`) que no están en `VIVIENDAS_1992`; en la capa 1 quedan con
  `id_vivienda` nulo.
- R escribió algunos enteros en notación científica: los portafolios 100000 y 200000 aparecen como
  `1e+05` y `2e+05` en todas las tablas. La capa 1 los lee como enteros.
- Hogar 0 agrupa a las personas que no forman parte de un hogar particular (parentesco 12, viviendas
  colectivas, y 99, operativos especiales).

## 2002

- Variables con códigos de pregunta (`V1`… en viviendas; `P17`… en personas).
- **Sin tabla de hogares**: solo viviendas y personas. El cuestionario sí preguntó por el hogar
  (combustible, dormitorios, ducha, artefactos y vehículos: preguntas 12 a 16), pero esas variables
  no vienen en la entrega.
- **Geografía ya recodificada a la DPA de 16 regiones** (comunas hasta 16305; columnas `*_HOMOLOGADA_R16`).
  Para reconstruir la DPA de 2002 se necesita la correspondencia inversa.
- Edad hasta 108 años, sin tope.
- Códigos transcritos del cuestionario escaneado (`C2002.pdf`); no existe libro de códigos. Algunas
  preguntas no imprimen el código (sexo, sí/no, lugar de residencia): se asignaron por el orden de las
  opciones y quedan marcadas como `cuestionario_orden` o `inferido` en el diccionario.
- El código 0 corresponde a "no aplica" (verificado contra el universo de cada pregunta).
- Sin clasificación documentada para ocupación (`P31`) y rama (`P32`) a 2 dígitos.
- Como en 1992, R escribió algunos portafolios en notación científica (`1e+05`…).
- 25.627 portafolios no tienen viviendas; se conservan en la tabla `portafolios` de la capa 1.

## 2017

- Censo abreviado: pocas variables de vivienda (`P01`–`P05`) y sin estado civil, alfabetismo,
  ocupación ni religión.
- Geografía en DPA de 16 regiones, con columnas adicionales `_15R` en la DPA de 15 regiones.
- Rama de actividad (`P18`) en letras (secciones CIIU).
- Las etiquetas oficiales de todas las variables vienen como `etiquetas_*.csv` dentro de los `.rar`
  públicos; códigos 98 = no aplica y 99 = missing.
- No hay hogar 0: las personas de viviendas colectivas y operativos (parentesco 17 a 19) tienen
  `NHOGAR` 1 y `TIPO_HOGAR` 98.

## 2024

- Parquet con nombres descriptivos y diccionario oficial (`diccionario_variables_censo2024.xlsx`).
- **Anonimización**: edad con tope en 85 y valor `-66` = suprimido; `comuna_bajo_umbral` marca
  comunas pequeñas. Esto limita la comparación de edades altas con censos anteriores.
- Personas en situación de calle y viviendas colectivas se identifican con `tipo_operativo`; sus
  personas están en el hogar 0.
- `id_hogar` e `id_persona` son números dentro de la vivienda y del hogar, no identificadores únicos.
