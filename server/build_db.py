# -*- coding: utf-8 -*-
"""
Importador: CSV  ->  bases de datos `.db` (SQLite) del Portal MAPE.

Uso (desde `frame/`):
    python server/build_db.py            # reconstruye los .db desde los CSV
    python server/build_db.py --force    # borra y reconstruye
    python server/build_db.py --db corpus_124.db   # sólo una base

Los CSV son **fuentes de importación**: después de este paso la aplicación web
sólo lee/escribe ficheros `.db`.  Editar un `.db` (o usar el editor del portal)
modifica la aplicación sin volver a ejecutar nada.

Esquema: server/schema.py · Clasificación: server/derived.py
"""
import argparse
import csv
import json
import os
import pathlib
import sqlite3
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import derived as D  # noqa: E402
import schema as S  # noqa: E402

ROOT = S.APP_DIR.parent.parent  # revision_03092026/

# ---------------------------------------------------------------- catálogo de tecnologías
TEC = [
    {"id": "iot", "nombre": "Sensórica IoT subterránea", "cat": "Sensórica y monitoreo",
     "kws": ["iot", "internet of things", "wireless sensor", "telemetry", "sensor nod"],
     "trl": 8, "geoma": ["todas"], "capex": "Bajo", "opex": "Medio", "seg": 4, "amb": 3},
    {"id": "rtsys", "nombre": "Monitoreo en tiempo real", "cat": "Sensórica y monitoreo",
     "kws": ["real-time", "real time", "monitoring system", "on-line monitoring", "online monitoring", "real-time monitoring"],
     "trl": 9, "geoma": ["todas"], "capex": "Medio", "opex": "Medio", "seg": 5, "amb": 4},
    {"id": "mseed", "nombre": "Monitoreo microsísmico y rockburst", "cat": "Sensórica y monitoreo",
     "kws": ["microseismic", "acoustic emission", "rockburst", "seismic"],
     "trl": 8, "geoma": ["cuerpos masivos"], "capex": "Alto", "opex": "Medio", "seg": 5, "amb": 2},
    {"id": "twin", "nombre": "Gemelo digital", "cat": "Modelado y simulación",
     "kws": ["digital twin", "twin model", "virtual mine", "digital shadow"],
     "trl": 5, "geoma": ["todas"], "capex": "Alto", "opex": "Medio", "seg": 4, "amb": 4},
    {"id": "fem", "nombre": "Simulación numérica / FEM", "cat": "Modelado y simulación",
     "kws": ["numerical model", "numerical simulation", "finite element", "mathematical model", "geomechanical model", "numerical modeling"],
     "trl": 9, "geoma": ["todas"], "capex": "Bajo", "opex": "Bajo", "seg": 4, "amb": 3},
    {"id": "ai", "nombre": "Inteligencia artificial / ML", "cat": "Inteligencia artificial",
     "kws": ["machine learning", "deep learning", "neural network", "artificial intelligence", "predictive model", "classification algorithm"],
     "trl": 6, "geoma": ["todas"], "capex": "Medio", "opex": "Bajo", "seg": 4, "amb": 3},
    {"id": "cvision", "nombre": "Visión computarizada", "cat": "Inteligencia artificial",
     "kws": ["computer vision", "image recognition", "image analysis", "automated detection", "object detection"],
     "trl": 6, "geoma": ["todas"], "capex": "Medio", "opex": "Bajo", "seg": 4, "amb": 2},
    {"id": "gis", "nombre": "GIS y geomática", "cat": "Geomática",
     "kws": ["gis", "geographic information system", "geospatial", "georeferenc", "spatial analysis"],
     "trl": 9, "geoma": ["todas"], "capex": "Bajo", "opex": "Bajo", "seg": 4, "amb": 4},
    {"id": "scan", "nombre": "Láser, lidar y fotogrametría", "cat": "Geomática",
     "kws": ["lidar", "laser scanning", "laser scanner", "point cloud", "photogrammetry", "3d scan", "terrestrial laser"],
     "trl": 9, "geoma": ["vetas angostas", "cuerpos masivos"], "capex": "Medio", "opex": "Bajo", "seg": 3, "amb": 2},
    {"id": "uav", "nombre": "Drones / UAV", "cat": "Geomática",
     "kws": ["uav", "drone", "unmanned aerial", "aerial survey", "remote sensing"],
     "trl": 8, "geoma": ["todas"], "capex": "Medio", "opex": "Bajo", "seg": 4, "amb": 3},
    {"id": "aut", "nombre": "Automatización y equipos autónomos", "cat": "Automatización y robótica",
     "kws": ["automation", "automated", "autonomous", "robot", "robotics", "unmanned equipment", "self-driving", "remote control", "remote operation"],
     "trl": 7, "geoma": ["todas"], "capex": "Alto", "opex": "Medio", "seg": 5, "amb": 3},
    {"id": "com5g", "nombre": "Redes 5G / Wi-Fi subterráneas", "cat": "Comunicaciones y datos",
     "kws": ["5g", "wifi", "wi-fi", "wireless communication", "communication system", "information transmission", "smart phone", "mobile terminal"],
     "trl": 8, "geoma": ["todas"], "capex": "Alto", "opex": "Medio", "seg": 3, "amb": 2},
    {"id": "fleet", "nombre": "Gestión de flota / dispatch", "cat": "Comunicaciones y datos",
     "kws": ["fleet management", "dispatch", "truck dispatch", "mine dispatch", "orepass"],
     "trl": 8, "geoma": ["todas"], "capex": "Medio", "opex": "Bajo", "seg": 3, "amb": 2},
    {"id": "bi", "nombre": "Analítica, BI y plataformas de datos", "cat": "Comunicaciones y datos",
     "kws": ["big data", "cloud computing", "database", "data platform", "data processing", "erp", "business intelligence", "dashboard", "analytics", "decision support", "management system", "information system"],
     "trl": 7, "geoma": ["todas"], "capex": "Medio", "opex": "Bajo", "seg": 4, "amb": 3},
    {"id": "backfill", "nombre": "Relleno y backfill", "cat": "Operación y ambiente",
     "kws": ["backfill", "paste fill", "cemented fill", "filling technology", "solid waste backfilling", "grouting"],
     "trl": 9, "geoma": ["vetas angostas", "cuerpos masivos"], "capex": "Alto", "opex": "Alto", "seg": 4, "amb": 5},
    {"id": "vent", "nombre": "Ventilación y control de atmósfera", "cat": "Operación y ambiente",
     "kws": ["ventilation", "mine gas", "gas monitoring", "exhaust", "air flow", "dust control", "substance diffusion"],
     "trl": 9, "geoma": ["todas"], "capex": "Alto", "opex": "Alto", "seg": 5, "amb": 4},
    {"id": "safety", "nombre": "Seguridad ocupacional y gestión de riesgo", "cat": "Operación y ambiente",
     "kws": ["occupational safety", "safety management", "risk assessment", "risk map", "emergency", "escape route", "occupational risk", "worker safety", "safety system"],
     "trl": 9, "geoma": ["todas"], "capex": "Bajo", "opex": "Medio", "seg": 5, "amb": 3},
    {"id": "methane", "nombre": "Aprovechamiento de metano y energía", "cat": "Operación y ambiente",
     "kws": ["methane", "coal mine methane", "geothermal", "energy recovery", "cogeneration", "green energy"],
     "trl": 7, "geoma": ["mantos y capas"], "capex": "Alto", "opex": "Medio", "seg": 3, "amb": 5},
    {"id": "trace", "nombre": "Trazabilidad y blockchain", "cat": "Gobernanza",
     "kws": ["blockchain", "traceab", "supply chain", "carbon footprint", "certified gold", "responsible min"],
     "trl": 5, "geoma": ["todas"], "capex": "Bajo", "opex": "Bajo", "seg": 2, "amb": 4},
]

GEOMA_LBL = {
    "todas": "Todas las geometrías",
    "vetas angostas": "Vetas angostas (≤ 2–3 m)",
    "mantos y capas": "Mantos y capas",
    "cuerpos masivos": "Cuerpos masivos / masivos",
}

# ---------------------------------------------------------------- clústeres temáticos C4 (corpus 124)
CLS = {
    0: {"nombre": "Geomecánica, simulación y monitoreo",
        "temas": "fragmentation, geomechanics and stress, ground stability, modeling and simulation, monitoring, ore deposits, underground mining",
        "kws": ["fragment", "geomecan", "stress", "estrés", "stability", "estabilidad",
                "model", "simul", "monitor", "ore", "underground", "subterr", "excavat"],
        "modo": "hits"},
    1: {"nombre": "Minería sostenible, seguridad y ventilación",
        "temas": "artisanal and small-scale underground, equipment and performance, mine safety, mining technology, sustainable mining, ventilation",
        "kws": ["artisanal", "artesanal", "equipment", "equipo", "maquin", "performance",
                "rendimiento", "mine safety", "safety", "seguridad", "mining technology",
                "sustainable", "sosten", "ventil"],
        "modo": "hits"},
    2: {"nombre": "Minería del carbón e inteligente",
        "temas": "coal mining, mining safety, smart mining, trigeneration, virtual and augmented reality",
        "kws": ["coal", "carbón", "carbon", "mining safety", "mine safety", "smart mining",
                "smart mine", "intelig", "trigeneration", "virtual reality",
                "augmented reality", "realidad virtual"],
        "modo": "hits"},
    3: {"nombre": "Métodos de explotación, backfill y mineralización",
        "temas": "artisanal and small-scale gold, backfilling, mineralization zones, mining methods, tailings",
        "kws": ["artisanal gold", "small-scale gold", "gold", "oro", "backfill", "relleno",
                "mineraliz", "mining method", "explotac", "extraction method", "tailings", "relave"],
        "modo": "hits"},
}

# ---------------------------------------------------------------- clústeres C3 (corpora 360/269/258/207)
C3_SUB = ["underground min", "subterranean min", "underground coal",
          "underground excavation", "mineria subterranea", "minería subterránea"]
C3_TEC = ["mining technolog", "tecnologia minera", "tecnologías mineras",
          "mining engineer", "mining science"]
C3_DEP = ["gold deposit", "gold ore", "auriferous", "gold mineralization",
          "yacimientos de oro", "gold mining deposit"]
C3_EST = ["stabilit", "estabilidad"]

CLS3 = {
    0: {"nombre": "Mina subterránea × tecnología minera",
        "temas": "underground mining technology, equipment and engineering, smart/automated underground mining",
        "kws": [], "kws_all": [C3_SUB, C3_TEC], "modo": "prioridad"},
    1: {"nombre": "Depósitos de oro y mineralización",
        "temas": "gold deposits, ore bodies, gold mineralization, auriferous zones",
        "kws": C3_DEP, "kws_all": [], "modo": "prioridad"},
    2: {"nombre": "Estabilidad y geomecánica",
        "temas": "stability, geomechanics, ground control",
        "kws": C3_EST, "kws_all": [], "modo": "prioridad"},
}

# ---------------------------------------------------------------- observatorio
COUNTRIES = [
    {"pais": "DRC", "cont": "Africa", "gdp_pc": 580, "tech": 8, "edu": 0.48, "mining_gdp": 25, "seg": 15, "amb": 12, "n_pubs": 3},
    {"pais": "Ghana", "cont": "Africa", "gdp_pc": 2363, "tech": 14, "edu": 0.60, "mining_gdp": 7, "seg": 35, "amb": 28, "n_pubs": 5},
    {"pais": "Perú", "cont": "LatAm", "gdp_pc": 6692, "tech": 38, "edu": 0.73, "mining_gdp": 10, "seg": 52, "amb": 48, "n_pubs": 12},
    {"pais": "Ecuador", "cont": "LatAm", "gdp_pc": 6300, "tech": 25, "edu": 0.70, "mining_gdp": 2, "seg": 35, "amb": 30, "n_pubs": 3},
    {"pais": "Colombia", "cont": "LatAm", "gdp_pc": 5333, "tech": 32, "edu": 0.72, "mining_gdp": 5, "seg": 48, "amb": 45, "n_pubs": 10},
    {"pais": "Bolivia", "cont": "LatAm", "gdp_pc": 3143, "tech": 18, "edu": 0.63, "mining_gdp": 12, "seg": 32, "amb": 25, "n_pubs": 4},
    {"pais": "Indonesia", "cont": "Asia", "gdp_pc": 3870, "tech": 28, "edu": 0.71, "mining_gdp": 6, "seg": 40, "amb": 32, "n_pubs": 8},
    {"pais": "Filipinas", "cont": "Asia", "gdp_pc": 3299, "tech": 22, "edu": 0.69, "mining_gdp": 2, "seg": 35, "amb": 30, "n_pubs": 5},
    {"pais": "Mongolia", "cont": "Asia", "gdp_pc": 4007, "tech": 26, "edu": 0.74, "mining_gdp": 15, "seg": 42, "amb": 35, "n_pubs": 6},
    {"pais": "Tanzania", "cont": "Africa", "gdp_pc": 1077, "tech": 11, "edu": 0.53, "mining_gdp": 8, "seg": 25, "amb": 20, "n_pubs": 4},
    {"pais": "Mozambique", "cont": "Africa", "gdp_pc": 448, "tech": 6, "edu": 0.44, "mining_gdp": 13, "seg": 18, "amb": 14, "n_pubs": 2},
    {"pais": "Sudáfrica", "cont": "Africa", "gdp_pc": 6001, "tech": 45, "edu": 0.68, "mining_gdp": 6, "seg": 55, "amb": 50, "n_pubs": 14},
    {"pais": "México", "cont": "LatAm", "gdp_pc": 8347, "tech": 35, "edu": 0.76, "mining_gdp": 4, "seg": 45, "amb": 40, "n_pubs": 9},
    {"pais": "Brasil", "cont": "LatAm", "gdp_pc": 7507, "tech": 30, "edu": 0.76, "mining_gdp": 5, "seg": 42, "amb": 38, "n_pubs": 11},
    {"pais": "Chile", "cont": "LatAm", "gdp_pc": 13232, "tech": 42, "edu": 0.82, "mining_gdp": 10, "seg": 60, "amb": 55, "n_pubs": 8},
    {"pais": "India", "cont": "Asia", "gdp_pc": 2257, "tech": 15, "edu": 0.57, "mining_gdp": 2, "seg": 30, "amb": 25, "n_pubs": 7},
    {"pais": "España", "cont": "Europe", "gdp_pc": 30100, "tech": 58, "edu": 0.80, "mining_gdp": 2, "seg": 60, "amb": 55, "n_pubs": 8},
]

CONT_COL = {"Africa": "#56B4E9", "LatAm": "#009E73", "Asia": "#E69F00",
            "AsiaPac": "#E69F00", "Europe": "#0072B2", "Global": "#888888"}

IGF_FUNDS = [
    {"region": "África Sub.", "pct": 38},
    {"region": "Latinoamérica", "pct": 22},
    {"region": "Asia", "pct": 16},
    {"region": "Europa", "pct": 12},
    {"region": "Resto", "pct": 12},
]

RADAR = {
    "labels": ["Adopción\nTecnológica", "Índice de\nSeguridad", "Cumplimiento\nAmbiental",
               "Producción\nCientífica", "Inversión", "Marco\nNormativo"],
    "series": [
        {"id": "Africa", "nombre": "África", "v": [12, 22, 18, 8, 15, 20]},
        {"id": "LatAm", "nombre": "Latinoamérica", "v": [32, 45, 40, 28, 30, 38]},
        {"id": "AsiaPac", "nombre": "Asia-Pacífico", "v": [26, 38, 30, 22, 25, 32]},
        {"id": "Europe", "nombre": "Europa", "v": [58, 60, 55, 30, 55, 62]},
        {"id": "Global", "nombre": "Global (ref.)", "v": [25, 38, 30, 20, 23, 30]},
    ],
}

# ---------------------------------------------------------------- helpers de sqlite
def abrir(path, sql, reset=False):
    if reset and os.path.exists(path):
        os.remove(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(path))
    con.row_factory = sqlite3.Row
    con.executescript(sql)
    con.execute("PRAGMA journal_mode=DELETE")
    con.commit()
    return con


def set_meta(con, d):
    con.executemany("INSERT OR REPLACE INTO meta(key,value) VALUES(?,?)",
                    [(k, json.dumps(v, ensure_ascii=False) if not isinstance(v, str) else v)
                     for k, v in d.items()])


def leer_csv(path, delim):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f, delimiter=delim))


def primeros_autores(a, n=2):
    a = D.norm(a)
    if not a:
        return "s.d."
    parts = [x.strip() for x in a.split(";") if x.strip()]
    if len(parts) <= n:
        return " · ".join(parts[:n])
    return " · ".join(parts[:n]) + " et al."


# ---------------------------------------------------------------- escritura de un corpus .db
def escribir_corpus(cid, docs, clusters, meta_extra, tec_kws, nombres_tec=None, reset=True):
    """docs: lista de dicts ya normalizados (id, anio, titulo, ..., cluster, tecs)."""
    path = S.db_path(S.CORPUS_DBS[cid])
    con = abrir(path, S.SQL_CORPUS, reset=reset)
    con.execute("DELETE FROM docs"); con.execute("DELETE FROM doc_tecs")
    con.execute("DELETE FROM clusters"); con.execute("DELETE FROM meta")
    con.execute("DELETE FROM fuentes")

    nombres_tec = nombres_tec or {t["id"]: t["nombre"] for t in TEC}
    con.executemany(
        "INSERT INTO docs(id,n,anio,titulo,autores,fuente,citas,doi,enlace,acceso,"
        "acceso_raw,perfil_acceso,eid,cluster,hallazgos,limitaciones,novedad,texto,"
        "tecnologias_txt) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [(d["id"], d.get("n"), d["anio"], d["titulo"], d["autores"], d["fuente"], d["citas"],
          d["doi"], d["enlace"], d["acceso"], d.get("acceso_raw", ""), d.get("perfil_acceso", ""),
          d.get("eid", ""), d.get("cluster"), d.get("hallazgos", ""), d.get("limitaciones", ""),
          d.get("novedad", ""), d.get("texto", ""),
          " | ".join(nombres_tec.get(t, t) for t in d.get("tecs", []))) for d in docs])

    con.executemany("INSERT OR IGNORE INTO doc_tecs(doc_id,tec_id) VALUES(?,?)",
                    [(d["id"], t) for d in docs for t in d.get("tecs", [])])

    con.executemany(
        "INSERT INTO clusters(id,nombre,temas,kws,kws_all,modo) VALUES(?,?,?,?,?,?)",
        [(c["id"], c["nombre"], c.get("temas", ""), json.dumps(c.get("kws", []), ensure_ascii=False),
          json.dumps(c.get("kws_all", []), ensure_ascii=False), c.get("modo", "hits"))
         for c in clusters])

    meta = {
        "id": cid,
        "nombre": S.CORPUS_LABELS.get(cid, cid),
        "csv": S.CORPUS_CSV.get(cid, cid),
        "db": S.CORPUS_DBS[cid],
        "gen": time.strftime("%Y-%m-%d"),
        "seed_series": 42 if cid == "124" else 7,
        "n_tecs": len(tec_kws),
    }
    meta.update(meta_extra or {})
    set_meta(con, meta)
    con.execute("INSERT OR REPLACE INTO fuentes(clave,valor) VALUES(?,?)",
                ("csv", S.FUENTES.get("corpus_" + cid, "")))
    con.commit()
    con.close()
    return path


def construir_124(tec_kws):
    filas = leer_csv(ROOT / "resultados" / "thirdPass_124.csv", ";")
    filas = [r for r in filas if (r.get("n") or "").strip()]
    clusters = [{"id": i, **{k: v for k, v in c.items()}} for i, c in CLS.items()]

    docs = []
    for i, r in enumerate(filas):
        texto = D.texto_124(r.get("titulo"), r.get("Hallazgos principales"),
                             r.get("Limitaciones"), r.get("Novedad"), r.get("fuente"))
        docs.append({
            "id": i,
            "n": D.to_int(r.get("n"), i + 1),
            "anio": D.to_int(r.get("anio"), None) if D.to_int(r.get("anio"), None) is not None else None,
            "titulo": D.norm(r.get("titulo"))[:300],
            "autores": primeros_autores(r.get("autores")),
            "fuente": D.norm(r.get("fuente"))[:140],
            "citas": D.to_int(r.get("citas"), 0),
            "doi": D.norm_doi(r.get("doi")),
            "enlace": D.norm(r.get("enlace")),
            "acceso": D.clasificar_acceso_124(r.get("perfil_acceso")),
            "acceso_raw": D.norm(r.get("acceso")),
            "perfil_acceso": D.norm(r.get("perfil_acceso")),
            "eid": D.norm(r.get("eid")),
            "cluster": D.clasificar_cluster(texto, clusters),
            "hallazgos": D.norm(r.get("Hallazgos principales"))[:1200],
            "limitaciones": D.norm(r.get("Limitaciones"))[:1200],
            "novedad": D.norm(r.get("Novedad"))[:1200],
            "texto": texto,
            "tecs": D.clasificar_tecs(texto, tec_kws),
        })
    meta = {
        "n_docs": len(docs),
        "corpus": "thirdPass_124.csv",
        "n_clusters": len(clusters),
        "citas_totales": sum(d["citas"] for d in docs),
        "oa": sum(1 for d in docs if d["acceso"] == D.ACCESO_LIBRE),
    }
    return escribir_corpus("124", docs, clusters, meta, tec_kws)


def construir_scopus(cid, filas, clusters, tec_kws, con_rango=None):
    clusters_l = [{"id": i, **c} for i, c in clusters.items()]
    docs = []
    for i, r in enumerate(filas):
        texto = D.texto_scopus(r.get("titulo"), r.get("resumen"),
                               r.get("palabras"), r.get("indices"))
        anio = D.to_int(r.get("anio"), None)
        if anio is None:
            anio = None
        docs.append({
            "id": i,
            "n": i + 1,
            "anio": anio,
            "titulo": D.norm(r.get("titulo"))[:300],
            "autores": primeros_autores(r.get("autores")),
            "fuente": D.norm(r.get("fuente") or r.get("fuenteabrev"))[:140],
            "citas": D.to_int(r.get("citas"), 0),
            "doi": D.norm_doi(r.get("doi")),
            "enlace": D.norm(r.get("enlace")),
            "acceso": D.clasificar_acceso_scopus(r.get("acceso")),
            "acceso_raw": D.norm(r.get("acceso"))[:200],
            "perfil_acceso": "",
            "eid": D.norm(r.get("eid")),
            "cluster": D.clasificar_cluster(texto, clusters_l),
            "hallazgos": "", "limitaciones": "", "novedad": "",
            "texto": texto,
            "tecs": D.clasificar_tecs(texto, tec_kws),
        })
    meta = {
        "n_docs": len(docs),
        "n_clusters": len(clusters_l),
        "citas_totales": sum(d["citas"] for d in docs),
        "oa": sum(1 for d in docs if d["acceso"] == D.ACCESO_LIBRE),
        "rango_filtro": list(con_rango) if con_rango else None,
    }
    return escribir_corpus(cid, docs, clusters_l, meta, tec_kws)


def construir_catalogo(tec_kws, docs_tecs=None):
    """docs_tecs: {tec_id: n_docs} y links: [{s,t,w}] calculados del corpus 124."""
    path = S.db_path(S.CATALOGO_DB)
    con = abrir(path, S.SQL_CATALOGO, reset=True)
    con.execute("DELETE FROM tecnologias"); con.execute("DELETE FROM tec_kws")
    con.execute("DELETE FROM red"); con.execute("DELETE FROM meta")

    con.executemany(
        "INSERT INTO tecnologias(id,nombre,cat,trl,geoma,capex,opex,seg,amb,n_docs,orden) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
        [(t["id"], t["nombre"], t["cat"], t["trl"], json.dumps(t["geoma"], ensure_ascii=False),
          t["capex"], t["opex"], t["seg"], t["amb"],
          int((docs_tecs or {}).get(t["id"], 0)), i + 1) for i, t in enumerate(TEC)])
    con.executemany("INSERT INTO tec_kws(tec_id,kw) VALUES(?,?)",
                    [(t["id"], kw) for t in TEC for kw in t["kws"]])
    set_meta(con, {"n_tecs": len(TEC), "geoma_lbl": GEOMA_LBL,
                   "gen": time.strftime("%Y-%m-%d"), "db": S.CATALOGO_DB})
    con.execute("INSERT OR REPLACE INTO fuentes(clave,valor) VALUES(?,?)",
                ("catalogo", S.FUENTES["catalogo_tecnologias"]))
    con.commit()
    con.close()
    return path


def construir_red(docs):
    """Co-ocurrencia de tecnologías en el corpus 124 -> tabla `red`."""
    idx = {t["id"]: i for i, t in enumerate(TEC)}
    n = len(TEC)
    cooc = [[0] * n for _ in range(n)]
    for d in docs:
        ids = [idx[t] for t in d["tecs"] if t in idx]
        for a in range(len(ids)):
            for b in range(a + 1, len(ids)):
                cooc[ids[a]][ids[b]] += 1
    links = []
    for a in range(n):
        for b in range(a + 1, n):
            w = cooc[a][b]
            if w >= 1:
                links.append((TEC[a]["id"], TEC[b]["id"], w))
    links.sort(key=lambda x: -x[2])
    con = sqlite3.connect(str(S.db_path(S.CATALOGO_DB)))
    con.execute("DELETE FROM red")
    con.executemany("INSERT INTO red(s,t,w) VALUES(?,?,?)", links)
    con.commit()
    con.close()
    return links


def construir_observatorio(paises_pub):
    path = S.db_path(S.OBSERVATORIO_DB)
    con = abrir(path, S.SQL_OBSERVATORIO, reset=True)
    for t in ("paises_obs", "paises_pub", "radar_labels", "radar_series", "igf_funds",
              "colores", "corr_cols", "corr_mat", "meta", "fuentes"):
        con.execute("DELETE FROM " + t)

    con.executemany("INSERT INTO paises_obs(pais,cont,gdp_pc,tech,edu,mining_gdp,seg,amb,n_pubs)"
                    " VALUES(?,?,?,?,?,?,?,?,?)",
                    [(c["pais"], c["cont"], c["gdp_pc"], c["tech"], c["edu"], c["mining_gdp"],
                      c["seg"], c["amb"], c["n_pubs"]) for c in COUNTRIES])
    con.executemany("INSERT INTO paises_pub(pais,n,pct) VALUES(?,?,?)",
                    [(p["pais"], p["n"], p["pct"]) for p in paises_pub])
    con.executemany("INSERT INTO radar_labels(orden,label) VALUES(?,?)",
                    list(enumerate(RADAR["labels"])))
    con.executemany("INSERT INTO radar_series(id,nombre,orden,v) VALUES(?,?,?,?)",
                    [(s["id"], s["nombre"], i, json.dumps(s["v"])) for i, s in enumerate(RADAR["series"])])
    con.executemany("INSERT INTO igf_funds(region,pct) VALUES(?,?)",
                    [(f["region"], f["pct"]) for f in IGF_FUNDS])
    con.executemany("INSERT INTO colores(cont,hex) VALUES(?,?)", list(CONT_COL.items()))
    con.executemany("INSERT INTO corr_cols(orden,col) VALUES(?,?)",
                    list(enumerate(D.CORR_COLS)))
    set_meta(con, {"gen": time.strftime("%Y-%m-%d"), "db": S.OBSERVATORIO_DB,
                   "sintetico": True})
    con.execute("INSERT OR REPLACE INTO fuentes(clave,valor) VALUES(?,?)",
                ("csv", S.FUENTES["observatorio"]))
    con.commit()
    con.close()
    return path


def guardar_corr(mat):
    con = sqlite3.connect(str(S.db_path(S.OBSERVATORIO_DB)))
    con.execute("DELETE FROM corr_mat")
    con.executemany("INSERT INTO corr_mat(fila,col,r) VALUES(?,?,?)",
                    [(i, j, mat[i][j]) for i in range(len(mat)) for j in range(len(mat[i]))])
    con.commit()
    con.close()


def sincronizar_catalogo():
    """Recalcula tecnologias.n_docs del catálogo a partir de corpus_124.db."""
    p = S.db_path("corpus_124.db")
    if not p.exists():
        return
    con = sqlite3.connect(str(S.db_path(S.CATALOGO_DB)))
    con.execute("ATTACH DATABASE ? AS corpus124", (str(p),))
    con.execute("""UPDATE tecnologias SET n_docs =
                   (SELECT COUNT(*) FROM corpus124.docs d
                     JOIN corpus124.doc_tecs dt ON dt.doc_id = d.id
                    WHERE dt.tec_id = tecnologias.id)""")
    con.commit()
    con.close()


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description="Construye las bases .db del Portal MAPE")
    ap.add_argument("--force", action="store_true", help="borra las bases antes de crearlas")
    ap.add_argument("--db", help="reconstruye sólo una base (corpus_124.db, observatorio.db…)")
    args = ap.parse_args()

    todo = args.db is None
    t = args.db
    S.DB_DIR.mkdir(parents=True, exist_ok=True)
    tec_kws = {x["id"]: list(x["kws"]) for x in TEC}

    if todo or t in (S.CATALOGO_DB, "corpus_124.db"):
        construir_catalogo(tec_kws)

    docs124 = None
    if todo or t == "corpus_124.db":
        construir_124(tec_kws)
        docs124 = _docs_124_en_memoria(tec_kws)
    if todo or t == S.CATALOGO_DB:
        construir_red(docs124 or _docs_124_en_memoria(tec_kws))

    if todo or t in ("corpus_360.db", "corpus_269.db", "corpus_258.db", "corpus_207.db"):
        filas360 = leer_csv(ROOT / "scopusRevisionManual.csv", ",")
        filas269 = leer_csv(ROOT / "scopusAnalisisLimpio.csv", ",")
        if todo or t == "corpus_360.db":
            construir_scopus("360", filas360, CLS3, tec_kws)
        if todo or t in ("corpus_269.db", "corpus_258.db", "corpus_207.db"):
            construir_scopus("269", filas269, CLS3, tec_kws)

        def en_rango(r):
            a = D.to_int(r.get("anio"), None)
            return a is not None and 2006 <= a <= 2026
        if todo or t == "corpus_258.db":
            construir_scopus("258", [r for r in filas269 if en_rango(r)], CLS3, tec_kws, (2006, 2026))
        if todo or t == "corpus_207.db":
            sub = [r for r in filas269 if en_rango(r) and _es_subtec(r)]
            construir_scopus("207", sub, CLS3, tec_kws, (2006, 2026))

    if todo or t == S.OBSERVATORIO_DB:
        paises = leer_csv(ROOT / "analisis_paises.csv", ",")
        paises = sorted(({"pais": D.norm(p["pais"]),
                          "n": D.to_int(p["documentos"]),
                          "pct": D.to_float(p["porcentaje_%"], 0.0)} for p in paises),
                        key=lambda x: -x["n"])[:15]
        construir_observatorio(paises)
        guardar_corr(D.matriz_corr(_series_de_docs(docs124 or _docs_124_en_memoria(tec_kws)), seed=42))

    sincronizar_catalogo()

    print("Bases de datos en %s:" % S.DB_DIR)
    for name in S.ALL_DBS:
        p = S.db_path(name)
        if not p.exists():
            print("  [falta] %s" % name)
            continue
        con = sqlite3.connect(str(p))
        tabs = [r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
        n = ""
        if "docs" in tabs:
            n = "  docs=%d" % con.execute("SELECT COUNT(*) FROM docs").fetchone()[0]
        elif "tecnologias" in tabs:
            n = "  tec=%d" % con.execute("SELECT COUNT(*) FROM tecnologias").fetchone()[0]
        elif "paises_obs" in tabs:
            n = "  paises=%d" % con.execute("SELECT COUNT(*) FROM paises_obs").fetchone()[0]
        con.close()
        print("  %-24s %8.1f KB%s" % (name, p.stat().st_size / 1024, n))
    print("OK")


def _es_subtec(r):
    t = D.texto_scopus(r.get("titulo"), r.get("resumen"), r.get("palabras"), r.get("indices"))
    return any(k in t for k in C3_SUB) and any(k in t for k in C3_TEC)


def _docs_124_en_memoria(tec_kws):
    """Lee el .db del corpus 124 ya construido (o el CSV si aún no existe)."""
    p = S.db_path("corpus_124.db")
    if p.exists():
        con = sqlite3.connect(str(p))
        con.row_factory = sqlite3.Row
        docs = [dict(r) for r in con.execute("SELECT * FROM docs ORDER BY id")]
        tecs = {}
        for r in con.execute("SELECT doc_id, tec_id FROM doc_tecs"):
            tecs.setdefault(r["doc_id"], []).append(r["tec_id"])
        con.close()
        for d in docs:
            d["tecs"] = tecs.get(d["id"], [])
        return docs
    filas = [r for r in leer_csv(ROOT / "resultados" / "thirdPass_124.csv", ";")
             if (r.get("n") or "").strip()]
    clusters = [{"id": i, **c} for i, c in CLS.items()]
    docs = []
    for i, r in enumerate(filas):
        texto = D.texto_124(r.get("titulo"), r.get("Hallazgos principales"),
                             r.get("Limitaciones"), r.get("Novedad"), r.get("fuente"))
        docs.append({"id": i, "titulo": D.norm(r.get("titulo")), "citas": D.to_int(r.get("citas"), 0),
                     "anio": D.to_int(r.get("anio"), None), "cluster": D.clasificar_cluster(texto, clusters),
                     "tecs": D.clasificar_tecs(texto, tec_kws)})
    return docs


def _series_de_docs(docs):
    """Series del corpus 124 (formato de `derived.matriz_corr`)."""
    anios = [d["anio"] for d in docs if d.get("anio")]
    if not anios:
        return {}
    y0, y1 = min(anios), max(anios)
    years = list(range(y0, y1 + 1))
    pubs = [sum(1 for d in docs if d.get("anio") == y) for y in years]
    tech, edu = D.serie_sintetica(years, seed=42)
    citas = []
    for y in years:
        vals = [d["citas"] for d in docs if d.get("anio") == y]
        citas.append(round(sum(vals) / len(vals), 2) if vals else 0.0)
    return {"Publicaciones": pubs, "Inversión Tech": tech, "Índice Educativo": edu,
            "Citas Promedio": citas, "Minería PIB%": [], "Safety Score": [], "Env Score": []}


if __name__ == "__main__":
    main()