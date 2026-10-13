# censos-chile

Resultados de los censos de población y vivienda de Chile (1813–2024) en un formato común,
documentado y reproducible, con librerías para Python y R.

> Proyecto personal, independiente del Instituto Nacional de Estadísticas (INE).
> Usa únicamente información pública. Las cifras originales son del INE y de sus
> organismos predecesores; los errores de procesamiento son responsabilidad de este proyecto.

**Estado:** en construcción (fases 1 y 2: inventario de fuentes y primera serie núcleo). Ver [docs/plan.md](docs/plan.md).

## Qué ofrece

| Producto | Cobertura | Origen |
|---|---|---|
| **Tabulados armonizados**: serie larga en formato largo con un esquema único | 1813–2024 | Libros digitalizados (hasta 1970) y agregación de microdatos (desde 1982) |
| **Microdatos armonizados**: viviendas, hogares y personas con variables comparables | 1982–2024 | Microdatos públicos del INE |
| **Metadatos**: diccionario de variables, correspondencias territoriales, catálogo de fuentes | todos | Este repositorio |

Cada cifra conserva su procedencia (documento, cuadro, página) y cada variable armonizada
documenta, censo por censo, qué variable original usa, cómo se transformó y qué limita su comparabilidad.

## Estructura

```
metadatos/
  censos.yaml               censos levantados en Chile y fuentes disponibles
  fuentes.yaml              documentos y archivos originales (procedencia, acceso, checksum)
  esquema_tabulados.yaml    esquema común de los tabulados
  variables/                fichas de variables armonizadas (una por variable)
  concordancia/             matriz concepto × censo
  inventario/               perfil automático de cada tabla de microdatos
digitalizacion/             cifras transcritas de las publicaciones (CSV por cuadro)
herramientas/               scripts de inventario y extracción
pipelines/                  generación de productos a partir de las fuentes
productos/tabulados/        tabulados armonizados (CSV)
validacion/                 cifras publicadas de referencia y contrastes
docs/                       plan, criterios y notas metodológicas
```

Las librerías (`python/`, `r/`) se agregarán en la fase 2.

## Uso local

Los microdatos no se versionan en este repositorio. Para correr las herramientas:

1. Copiar `config.ejemplo.yaml` como `config.yaml` y ajustar las rutas.
2. `pip install -r herramientas/requirements.txt`
3. `python herramientas/inventario_microdatos.py` (convierte y perfila los microdatos)
4. `python pipelines/poblacion_nucleo.py` (genera el tabulado de población)
5. `python validacion/validar_poblacion.py` (contrasta con cifras publicadas)

## Licencias

- Código: [MIT](LICENSE).
- Datos y metadatos producidos por el proyecto: [CC BY 4.0](LICENSE-DATOS.md).
