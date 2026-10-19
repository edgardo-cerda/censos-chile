# Borradores de transcripción

Lecturas sin validar que no entran al pipeline (no tienen YAML). Sirven de punto de partida.

- `pub_1865_p386_parroquias_lectura.csv`: lectura directa de la "Clasificación de los habitantes de
  la República, por parroquias" de 1865 (págs. 386-391, PDF 419-424), 143 parroquias, edad x sexo
  y totales (celdas vacías = ilegibles; la columna de mujeres de 25 a 50 de la pág. 386 queda
  cortada en el escaneo). No validada: el escaneo confunde 4/1, 3/1 y 3/8, y las parroquias no
  suman a los departamentos (son unidades eclesiásticas), así que solo se controla cada fila
  (edades = total del sexo) y el total nacional. Con la reparación de dígitos quedan 71 filas
  ambiguas y los totales nacionales no cuadran. Requiere relectura a más resolución u otro
  ejemplar. El total impreso excluye el Territorio de Magallanes.
- `pub_1813_provincias.csv`: «Censo de provincia» de 1813 (14 partidos, Copiapó a Talca): edades
  del total por sexo (5 tramos), total por sexo y total general, leídos a 160 dpi (escaneo nítido).
  No validado: en 8 partidos los tramos de edad no suman el total del sexo (diferencias de 3 a 100,
  p. ej. Huasco mujeres +100, Curicó hombres +44). Hay que releerlos a 300 dpi y, si persisten,
  anotarlos como inconsistencias de la edición de 1953. Falta además la población por distrito.
