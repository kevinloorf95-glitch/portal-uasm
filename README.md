# Portal MAPE · aplicación web sobre bases `.db`

Portal de Transferencia Tecnológica y Observatorio Operativo de la Minería
Artesanal y de Pequeña Escala (MAPE). Es una **aplicación web real**: todo el
estado vive en bases SQLite (`.db`) y la interfaz es un cliente de la API REST
del servidor. Si edita un `.db` con `sqlite3`, DBeaver o con el editor
integrado, el portal recalcula los agregados y se repinta solo.

Sin dependencias externas: backend con la biblioteca estándar (`http.server` +
`sqlite3`), frontend con `index.html` + `assets/app.js` + Plotly.

## Arranque

En este equipo el único intérprete con las dependencias es el del entorno
virtual del proyecto, así que hay que invocarlo por ruta completa:

```bash
cd resultados/frame
..\..\.venv\Scripts\python.exe server\app.py     # http://127.0.0.1:8000
```

El proceso se queda en primer plano: esa ventana **es** el servidor (Ctrl+C
para detenerlo). Después se abre `http://127.0.0.1:8000/` en el navegador.

Otras opciones:

```bash
..\..\.venv\Scripts\python.exe server\app.py --port 8765         # otro puerto
..\..\.venv\Scripts\python.exe server\app.py --rebuild           # recrea los .db desde los CSV
..\..\.venv\Scripts\python.exe server\app.py --db-dir D:\mis\dbs # usar otras bases
..\..\.venv\Scripts\python.exe server\app.py --verbose           # log de cada petición
```

Al arrancar, si falta algún `.db`, se construye automáticamente importando los
CSV del proyecto (`thirdPass_124.csv`, `scopusRevisionManual.csv`,
`scopusAnalisisLimpio.csv`, `analisis_paises.csv`).

Pruebas (Playwright + pytest, 65 tests):

```bash
..\..\.venv\Scripts\python.exe -m pytest test_portal.py -v
```

Los tests arrancan el servidor real sobre una **copia** de `db/*.db` en un
directorio temporal, de modo que las pruebas de escritura no tocan las bases
del proyecto.

## Estructura

```
frame/
  index.html            shell de la aplicación + sección «Bases .db» (editor)
  assets/app.js         cliente de la API: filtros, gráficos, editor, recarga
  assets/style.css
  assets/plotly.min.js
  db/                   BASES DE DATOS (fuente única de verdad)
    corpus_124.db       n=124  2008–2026  4 clústeres C4  (+cualitativo)
    corpus_360.db       n=360  1973–2026  export original
    corpus_269.db       n=269  1974–2026  corpus depurado
    corpus_258.db       n=258  2006–2026  rango analítico
    corpus_207.db       n=207  2006–2026  clúster mina subterránea × tecnología
    catalogo_tecnologias.db   19 tecnologías (TRL, CAPEX/OPEX, seg/amb, kws)
    observatorio.db     países, radar regional, fondos IGF, correlaciones
    <gráfico>.db        17 bases derivadas: una por gráfica y por tabla
  server/
    app.py              servidor HTTP + API REST + exportaciones + estáticos
    dbstore.py          acceso a datos, caché por firma de archivo, CRUD
    schema.py           esquema SQL de las 7 bases y sus metadatos
    derived.py          normalizaciones compartidas (acceso, clusters, series…)
    derived_graficos.py cálculo de las 17 bases derivadas + red conectada
    build_db.py         importador CSV → .db  (python server/build_db.py --force)
  build_data.py         generador histórico (data/app_data.js); ya no se usa
  data/                 artefactos históricos del generador anterior
  test_portal.py        suite Playwright
```

## Las 17 bases derivadas

Cada gráfica y cada tabla del portal se pinta desde **su propia** base SQLite,
generada por el servidor a partir de las 7 bases fuente:

| Grupo | Bases |
|---|---|
| Series y donuts | `chart_anios` · `chart_donut_cluster` · `chart_donut_acceso` · `chart_top5` · `chart_cat` |
| Distribuciones y comparativas | `chart_radar` · `chart_bubble` · `chart_series` · `chart_corr` · `chart_igf` · `chart_paises_pub` · `chart_tec_bar` || Red | `chart_red` (red conectada: árbol de expansión máxima + puentes por similitud, con posiciones calculadas en Python) |
| Tablas | `tabla_tecnologias` · `tabla_corpus` · `tabla_paises_obs` · `tabla_deliverable` |

Todas comparten el mismo esquema:

```sql
base(clave TEXT PRIMARY KEY, orden INTEGER, extra TEXT, <columnas del cálculo>)
datos(clave TEXT PRIMARY KEY, orden INTEGER, extra TEXT, <mismas columnas>)
overrides(clave TEXT PRIMARY KEY, orden INTEGER, extra TEXT,
          accion TEXT, <mismas columnas>)
columnas(orden INTEGER PRIMARY KEY, nombre TEXT, titulo TEXT, tipo TEXT, ro INTEGER)
meta(key TEXT PRIMARY KEY, value TEXT)
fuentes(clave TEXT PRIMARY KEY, valor TEXT)
```

- `base` es el cálculo del servidor; `datos` es lo que se pinta.
- Editar una fila en `datos` (portal o `sqlite3`/DBeaver) deja la versión
  original en `base` y la nueva en `overrides` (las bajas se marcan con
  `accion='borrar'`), así que sobrevive a las recargas; «Restablecer» en el
  editor borra `overrides` y vuelve al cálculo.
- La escritura es **idempotente**: solo se toca el fichero si cambian
  `hash_fuente` o `hash_datos`, así que en estado estacionario ni el mtime ni
  la «versión» cambian.
- Las derivadas quedan fuera de la firma de la caché (para no realimentar el
  sondeo) pero aparecen en el inventario con su `gid`, título y nº de ediciones.
- Al cambiar de pestaña del corpus se recalculan para ese corpus:
  `GET /api/graficos?cid=360`.

## Cómo se calculan los datos

Nada está precalculado y embebido: los agregados se derivan de las filas.

| Dato en pantalla | Origen |
|---|---|
| n documentos, rango de años, citas totales | `COUNT`/`SUM` sobre `docs` |
| acceso abierto | `acceso` normalizado en el servidor (`derived.clasificar_acceso`) |
| clústeres y sus conteos | tabla `clusters` + `docs.cluster` |
| donut de clústeres | `cluster_counts` + «Sin clúster temático» |
| serie anual, inversión, educación | `serie_sintetica` a partir de los conteos por año |
| correlación | `pearson`/`matriz_corr` sobre series e indicadores |
| red de co-ocurrencia | tabla `red` (`construir_red` sobre `doc_tecs`) |
| radar, países, fondos IGF | tablas `paises_obs`, `paises_pub`, `igf_funds`, `radar_*` |
| n documentos por tecnología | technologies ↔ `doc_tecs` |
| cada gráfica y cada tabla | la tabla `datos` de su `<gid>.db` derivada |

La caché del servidor se invalida sola: la «versión» es la firma
`(nombre, mtime_ns, tamaño)` de los 7 archivos fuente. Si cambia, se recalcula
todo. El navegador consulta `/api/health` cada 8 s y, si la versión cambia, se
recarga y repinta (no hay que pulsar nada).

## Esquema de las bases

### `corpus_<n>.db` (una por vista del corpus)

```sql
docs(
  id INTEGER PRIMARY KEY, n INTEGER, anio INTEGER,
  titulo TEXT, autores TEXT, fuente TEXT, citas INTEGER,
  doi TEXT, enlace TEXT,
  acceso TEXT, acceso_raw TEXT, perfil_acceso TEXT,  -- perfil normalizado
  eid TEXT, cluster INTEGER,                            -- cluster → clusters.id
  hallazgos TEXT, limitaciones TEXT, novedad TEXT,      -- análisis cualitativo
  texto TEXT, tecnologias_txt TEXT)
doc_tecs(doc_id INTEGER, tec_id TEXT, PRIMARY KEY(doc_id, tec_id))
clusters(id INTEGER PRIMARY KEY, nombre TEXT, temas TEXT,
         kws TEXT, kws_all TEXT, modo TEXT)   -- modo: hits | prioridad
fuentes(clave TEXT PRIMARY KEY, valor TEXT)
meta(key TEXT PRIMARY KEY, value TEXT)
```

La asignación de clúster se recalcula con `derived.clasificar_cluster`:
modo `hits` (nº de palabras clave, el usado en el corpus 124 → 4 clústeres) o
modo `prioridad` (`kws_all` con AND, usado en 360/269/258/207, donde el
clúster 0 es «Mina subterránea × tecnología minera» y abarca los 207 docs).

### `catalogo_tecnologias.db`

```sql
tecnologias(id TEXT PRIMARY KEY, nombre TEXT, cat TEXT, trl INTEGER,
           geoma TEXT, capex TEXT, opex TEXT, seg INTEGER, amb INTEGER,
           n_docs INTEGER, orden INTEGER)
tec_kws(tec_id TEXT, kw TEXT, PRIMARY KEY(tec_id, kw))  -- vocabulario de asignación
red(s TEXT, t TEXT, w INTEGER, PRIMARY KEY(s, t))      -- co-ocurrencias
fuentes(clave TEXT PRIMARY KEY, valor TEXT)
meta(key TEXT PRIMARY KEY, value TEXT)
```

### `observatorio.db`

```sql
paises_obs(pais TEXT PRIMARY KEY, cont TEXT, gdp_pc REAL, tech REAL,
           edu REAL, mining_gdp REAL, seg REAL, amb REAL, n_pubs INTEGER)
paises_pub(pais TEXT PRIMARY KEY, n INTEGER, pct REAL)
radar_labels(orden INTEGER PRIMARY KEY, label TEXT)
radar_series(id TEXT PRIMARY KEY, nombre TEXT, orden INTEGER, v0..v5 REAL)
igf_funds(region TEXT PRIMARY KEY, pct REAL)
colores(clave TEXT PRIMARY KEY, hex TEXT)
corr_cols(orden INTEGER PRIMARY KEY, col TEXT)     -- matriz de correlación
corr_mat(fila INTEGER, col INTEGER, r REAL, PRIMARY KEY(fila, col))
fuentes(clave TEXT PRIMARY KEY, valor TEXT)
meta(key TEXT PRIMARY KEY, value TEXT)
```

Los valores del observatorio son **sintéticos calibrados** (UNESCO, Banco
Mundial, IGF) y validados con el panel Delphi-AHP, tal como se advierte en la
sección Inicio del portal.

## API

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/api/health` | estado, versión de las bases e inventario |
| GET | `/api/db` | carpeta de bases + inventario (filas, tamaño, mtime) |
| GET | `/api/db/<nombre>.db/schema` | esquema de una base |
| POST | `/api/db/<nombre>.db/query` | `SELECT` de solo lectura |
| GET | `/api/db/download/<nombre>.db` | descarga del `.db` |
| PATCH | `/api/db/<nombre>.db/meta` | clave/valor de `meta` |
| GET | `/api/bootstrap` | todo lo que necesita el frontend en una llamada |
| GET | `/api/corpora` | las 5 vistas con sus metadatos |
| GET | `/api/corpora/<id>` | vista completa (docs + clústeres + serie) |
| GET | `/api/corpora/<id>/docs` | documentos filtrados y paginados |
| GET | `/api/corpora/<id>/series` · `/stats` · `/top5` | derivados del corpus activo |
| POST | `/api/corpora/<id>/reindex` | reclasificar clústeres y tecnologías |
| GET | `/api/tecnologias` · `/api/tecnologias/<id>` | catálogo (+filtros `search,cat,geo,trl,seg,amb`) |
| PATCH | `/api/tecnologias/<id>` | editar TRL, CAPEX/OPEX, seg/amb, vocabulario |
| GET | `/api/observatorio` | países, radar, IGF, correlaciones |
| POST | `/api/observatorio/paises_obs` · `/igf` | editar observatorio |
| POST | `/api/db/<corpus>.db/docs` | crear documento |
| PATCH/DELETE | `/api/db/<corpus>.db/docs/<id>` | editar / eliminar documento |
| GET | `/api/graficos` · `?cid=` · `?ligero=0` | bases derivadas (ligeras) del corpus pedido |
| POST | `/api/graficos/sync` | regenerar las 17 derivadas (devuelve cuáles cambiaron) |
| GET | `/api/grafico/<gid>` · `?cid=` | ficha + `datos` de una derivada |
| POST | `/api/grafico/<gid>/fila` | alta/edición de fila (queda en `overrides`) |
| DELETE | `/api/grafico/<gid>/fila/<clave>` | baja de fila |
| POST | `/api/grafico/<gid>/reset` | borrar `overrides` y volver al cálculo |
| GET | `/api/grafico/<gid>.db` · `.csv` · `.json` | descarga de la derivada |
| GET | `/api/export/corpus/<id>.csv` · `.json` | exportación (respeta filtros) |
| GET | `/api/export/table/<tabla>.csv` | `tabla_tecnologias`, `tabla_corpus`, `tabla_paises_obs`, `tabla_deliverable` |
| GET | `/api/export/app_data.json` | volcado completo (archivable en Zenodo) |
| POST | `/api/admin/reload` | releer bases del disco |
| POST | `/api/admin/rebuild` | recrear los `.db` desde los CSV |

Los `.db` no se sirven como ficheros estáticos (403): solo se descargan por
`/api/db/download/<nombre>`.

## Editar datos

1. **Desde el portal**: sección «Bases .db» → inventario (7 fuente + 17
   derivadas) y descarga, editor de documentos (alta/edición/baja con
   reclasificación automática), editor de gráficas y tablas (cada `.db`
   derivada: ver filas, editarlas, darlas de alta o de baja, restablecer),
   editor de tecnologías, editor del observatorio (países e IGF) y consola SQL
   de solo lectura.
2. **Desde fuera**: `sqlite3 db/corpus_124.db "UPDATE docs SET citas = citas + 5"`.
   En ≤ 8 s la web detecta el cambio de versión y se repinta. Lo mismo vale
   para `db/chart_anios.db`: edita su tabla `datos` y el servidor memoriza la
   diferencia como `override` para que no se pierda al recalcular.
3. **Desde los CSV**: `python server/build_db.py --force` (o `--rebuild` al
   arrancar el servidor).

## Nota sobre los ficheros heredados

`build_data.py` y `data/app_data.{js,json}` pertenecen a la versión anterior
del portal (HTML estático con los datos embebidos). Ya no se usan en tiempo de
ejecución: el equivalente actual es `GET /api/export/app_data.json`. El
generador anterior se conserva por reproducibilidad histórica.