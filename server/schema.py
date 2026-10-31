# -*- coding: utf-8 -*-
"""
Esquema de las bases de datos `.db` (SQLite) del Portal MAPE.

Todas las bases de datos que usa la aplicación web viven en `frame/db/` y tienen
extensión `.db`.  El frontend NUNCA lee ficheros CSV/JSON: todo se resuelve
contra estos ficheros SQLite, de modo que si se edita un `.db` (a mano con
`sqlite3`, DBeaver, Navicat, o desde el editor integrado del portal) la
aplicación web lo refleja en la siguiente petición.

Ficheros .db
------------
  corpus_124.db          corpus cualitativo de la 3ª pasada (thirdPass_124.csv)
  corpus_360.db          export original de Scopus (scopusRevisionManual.csv)
  corpus_269.db          corpus depurado (scopusAnalisisLimpio.csv)
  corpus_258.db          subconjunto 2006–2026 del corpus depurado
  corpus_207.db          subconjunto "Mina subterránea × tecnología minera"
  catalogo_tecnologias.db  catálogo de tecnologías + red de co-ocurrencia
  observatorio.db          indicadores del observatorio (países, radar, IGF…)

Cada `corpus_*.db` es autónomo: `docs`, `doc_tecs`, `clusters`, `meta`.
"""
import pathlib

import derived_graficos as G

APP_DIR = pathlib.Path(__file__).resolve().parent.parent
DB_DIR = APP_DIR / "db"

# ---------------------------------------------------------------- registro de .db
CORPUS_DBS = {
    "124": "corpus_124.db",
    "360": "corpus_360.db",
    "269": "corpus_269.db",
    "258": "corpus_258.db",
    "207": "corpus_207.db",
}
CORPUS_ORDER = ["124", "360", "269", "258", "207"]
CATALOGO_DB = "catalogo_tecnologias.db"
OBSERVATORIO_DB = "observatorio.db"

ALL_DBS = [CORPUS_DBS[i] for i in CORPUS_ORDER] + [CATALOGO_DB, OBSERVATORIO_DB]

# bases *derivadas*: una por cada gráfica y tabla del portal (server/derived_graficos.py).
# Se crean solas al arrancar el servidor y se regeneran cuando cambia cualquier
# base de origen; por eso NO entran en la firma que invalida la caché (si no,
# el propio servidor se invalidaría a sí mismo en bucle).
DERIVED_DBS = G.nombres_db()
DERIVED_DB_IDS = {n[:-3]: n for n in DERIVED_DBS}


def all_db_names():
    """Todas las bases del portal: las de origen y las derivadas."""
    return ALL_DBS + DERIVED_DBS


def db_path(name):
    return DB_DIR / name


# ---------------------------------------------------------------- SQL
SQL_CORPUS = """
CREATE TABLE IF NOT EXISTS docs (
    id            INTEGER PRIMARY KEY,
    n             INTEGER,          -- número original de la revisión (n=124)
    anio          INTEGER,
    titulo        TEXT,
    autores       TEXT,
    fuente        TEXT,
    citas         INTEGER DEFAULT 0,
    doi           TEXT,
    enlace        TEXT,
    acceso        TEXT,             -- Acceso libre | No abierto | Sin dato
    acceso_raw    TEXT,             -- texto original de Scopus
    perfil_acceso TEXT,             -- sólo en el corpus 124
    eid           TEXT,
    cluster       INTEGER,          -- FK clusters.id
    hallazgos     TEXT,
    limitaciones  TEXT,
    novedad       TEXT,
    texto         TEXT,             -- título+hallazgos+… en minúsculas (reindexado por la app)
    tecnologias_txt TEXT             -- nombres de las tecnologías asignadas (búsqueda)
);
CREATE TABLE IF NOT EXISTS doc_tecs (
    doc_id INTEGER NOT NULL,
    tec_id TEXT    NOT NULL,
    PRIMARY KEY (doc_id, tec_id)
);
CREATE TABLE IF NOT EXISTS clusters (
    id      INTEGER PRIMARY KEY,
    nombre  TEXT,
    temas   TEXT,
    kws     TEXT,                    -- JSON array: basta con 1 coincidencia
    kws_all TEXT,                    -- JSON array de grupos (AND entre grupos)
    modo    TEXT DEFAULT 'hits'      -- 'hits' (más coincidencias) | 'prioridad'
);
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
CREATE INDEX IF NOT EXISTS ix_docs_anio    ON docs(anio);
CREATE INDEX IF NOT EXISTS ix_docs_cluster ON docs(cluster);
CREATE INDEX IF NOT EXISTS ix_docs_citas   ON docs(citas);
CREATE TABLE IF NOT EXISTS fuentes (
    clave TEXT PRIMARY KEY,
    valor TEXT
);
"""

SQL_CATALOGO = """
CREATE TABLE IF NOT EXISTS tecnologias (
    id       TEXT PRIMARY KEY,
    nombre   TEXT,
    cat      TEXT,
    trl      INTEGER,
    geoma    TEXT,                   -- JSON array de geometrías
    capex    TEXT,
    opex     TEXT,
    seg      INTEGER,
    amb      INTEGER,
    n_docs   INTEGER DEFAULT 0,
    orden    INTEGER
);
CREATE TABLE IF NOT EXISTS tec_kws (
    tec_id TEXT,
    kw     TEXT,
    PRIMARY KEY (tec_id, kw)
);
CREATE TABLE IF NOT EXISTS red (
    s TEXT,
    t TEXT,
    w INTEGER,
    PRIMARY KEY (s, t)
);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS fuentes (clave TEXT PRIMARY KEY, valor TEXT);
"""

SQL_OBSERVATORIO = """
CREATE TABLE IF NOT EXISTS paises_obs (
    pais       TEXT PRIMARY KEY,
    cont       TEXT,
    gdp_pc     REAL,
    tech       REAL,
    edu        REAL,
    mining_gdp REAL,
    seg        REAL,
    amb        REAL,
    n_pubs     INTEGER
);
CREATE TABLE IF NOT EXISTS paises_pub (
    pais TEXT PRIMARY KEY,
    n    INTEGER,
    pct  REAL
);
CREATE TABLE IF NOT EXISTS radar_labels (orden INTEGER PRIMARY KEY, label TEXT);
CREATE TABLE IF NOT EXISTS radar_series (
    id     TEXT PRIMARY KEY,
    nombre TEXT,
    orden  INTEGER,
    v      TEXT                      -- JSON array de 6 valores
);
CREATE TABLE IF NOT EXISTS igf_funds (region TEXT PRIMARY KEY, pct REAL);
CREATE TABLE IF NOT EXISTS colores (cont TEXT PRIMARY KEY, hex TEXT);
CREATE TABLE IF NOT EXISTS corr_cols (orden INTEGER PRIMARY KEY, col TEXT);
CREATE TABLE IF NOT EXISTS corr_mat (
    fila INTEGER,
    col  INTEGER,
    r    REAL,
    PRIMARY KEY (fila, col)
);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS fuentes (clave TEXT PRIMARY KEY, valor TEXT);
"""

# ---------------------------------------------------------------- fuentes CSV
FUENTES = {
    "corpus_124": "resultados/thirdPass_124.csv",
    "corpus_360": "scopusRevisionManual.csv",
    "corpus_269": "scopusAnalisisLimpio.csv",
    "corpus_258": "scopusAnalisisLimpio.csv · rango 2006–2026",
    "corpus_207": "scopusAnalisisLimpio.csv · Mina subterránea × tecnología minera",
    "catalogo_tecnologias": "catálogo Delphi-AHP (build_data.py)",
    "observatorio": "analisis_paises.csv + indicadores sintéticos Delphi-AHP",
}

CORPUS_LABELS = {
    "124": "124 · corpus final cualitativo",
    "360": "360 · registros Scopus",
    "269": "269 · corpus depurado",
    "258": "258 · rango 2006–2026",
    "207": "207 · clúster sub×tec",
}

# nombre de fichero CSV que muestra el portal como "fuente" de cada vista
CORPUS_CSV = {
    "124": "thirdPass_124.csv",
    "360": "scopusRevisionManual.csv",
    "269": "scopusAnalisisLimpio.csv",
    "258": "scopusAnalisisLimpio.csv · rango 2006–2026",
    "207": "scopusAnalisisLimpio.csv · Mina subterránea × tecnología minera",
}