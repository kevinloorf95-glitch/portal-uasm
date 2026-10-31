# -*- coding: utf-8 -*-
"""
Genera `data/app_data.js` para el Portal de Transferencia Tecnológica
y Observatorio Operativo de la MAPE.

Fuentes:
  - thirdPass_124.csv        (corpus final n=124, tercera pasada revisión sistemática)
  - clústeres temáticos C4   (4 clústeres por co-ocurrencia de términos, revisión sistemática)
  - analisis_paises.csv      (top países por producción real, revisión ampliada)
  - scopusRevisionManual.csv (360 registros: export Scopus original)
  - scopusAnalisisLimpio.csv (269 registros: corpus depurado · 258 en rango 2006–2026 · 207 clúster sub×tec)
  - indicadores sintéticos calibrados (Delphi-AHP)
"""
import json
import re
import os
import numpy as np
import pandas as pd

BASE = r"C:\Users\user20\IdeaProjects\ingenieriaDatos\revision_03092026"
OUT = BASE + r"\resultados\frame\data"
CSV_CORPUS = BASE + r"\resultados\thirdPass_124.csv"


def norm(v):
    if v is None:
        return ""
    s = str(v)
    return " ".join(line.strip().replace("\xad", "") for line in s.splitlines() if line.strip())


def norm_doi(v):
    return "" if pd.isna(v) else str(v).strip().lower()


# ---------------------------------------------------------------- carga del corpus (3ª pasada)
docs = pd.read_csv(CSV_CORPUS, sep=";", encoding="utf-8-sig")
docs = docs[docs["n"].notna()].copy()  # descarta filas vacías del export
docs = docs.reset_index(drop=True)
docs["anio"] = pd.to_numeric(docs["anio"], errors="coerce")

paises = pd.read_csv(BASE + r"\analisis_paises.csv", encoding="utf-8-sig")

# ---------------------------------------------------------------- acceso (perfil ya clasificado)
def perfil_acceso_row(r):
    v = norm(r.get("perfil_acceso")).lower()
    if "libre" in v or "open access" in v:
        return "Acceso libre"
    if "abierto" in v or "open" in v:
        return "No abierto"
    return "Sin dato"

docs["_acceso"] = docs["perfil_acceso"].map(lambda v: perfil_acceso_row({"perfil_acceso": v}) if pd.notna(v) else "Sin dato")


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
for t in TEC:
    t["geoma_lbl"] = [GEOMA_LBL[g] for g in t["geoma"]]

# ---------------------------------------------------------------- matching tecnología → docs
def texto_doc(r):
    return " ".join([
        norm(r.get("titulo", "")),
        norm(r.get("Hallazgos principales", "")),
        norm(r.get("Limitaciones", "")),
        norm(r.get("Novedad", "")),
        norm(r.get("fuente", ""))[:400],
    ]).lower()

docs["_texto"] = docs.apply(texto_doc, axis=1)

# ---------------------------------------------------------------- clúster temáticos C4 (4)
CLS = {
    0: {"nombre": "Geomecánica, simulación y monitoreo", "temas": "fragmentation, geomechanics and stress, ground stability, modeling and simulation, monitoring, ore deposits, underground mining",
        "kws": ["fragment", "geomecan", "stress", "estrés", "stability", "estabilidad", "model", "simul", "monitor", "ore", "underground", "subterr", "excavat"]},
    1: {"nombre": "Minería sostenible, seguridad y ventilación", "temas": "artisanal and small-scale underground, equipment and performance, mine safety, mining technology, sustainable mining, ventilation",
        "kws": ["artisanal", "artesanal", "equipment", "equipo", "maquin", "performance", "rendimiento", "mine safety", "safety", "seguridad", "mining technology", "sustainable", "sosten", "ventil"]},
    2: {"nombre": "Minería del carbón e inteligente", "temas": "coal mining, mining safety, smart mining, trigeneration, virtual and augmented reality",
        "kws": ["coal", "carbón", "carbon", "mining safety", "mine safety", "smart mining", "smart mine", "intelig", "trigeneration", "virtual reality", "augmented reality", "realidad virtual"]},
    3: {"nombre": "Métodos de explotación, backfill y mineralización", "temas": "artisanal and small-scale gold, backfilling, mineralization zones, mining methods, tailings",
        "kws": ["artisanal gold", "small-scale gold", "gold", "oro", "backfill", "relleno", "mineraliz", "mining method", "explotac", "extraction method", "tailings", "relave"]},
}

_cluster_rx = {c: re.compile("|".join(re.escape(k) for k in cls["kws"])) for c, cls in CLS.items()}
doc_clus = {}
for i in range(len(docs)):
    t = docs["_texto"].iloc[i]
    hits = {c: len(_cluster_rx[c].findall(t)) for c in _cluster_rx}
    best, best_n = -1, 0
    for c in sorted(hits):
        if hits[c] > best_n:
            best, best_n = c, hits[c]
    doc_clus[i] = best if best_n > 0 else None

doc_tecs = {i: [] for i in range(len(docs))}
for t in TEC:
    pat = "|".join(re.escape(k) for k in t["kws"])
    rx = re.compile(pat)
    hit = [i for i in range(len(docs)) if rx.search(docs["_texto"].iloc[i])]
    t["n_docs"] = len(hit)
    for i in hit:
        doc_tecs[i].append(t["id"])

# ---------------------------------------------------------------- co-ocurrencia (red)
n_tech = {t["id"]: i for i, t in enumerate(TEC)}
cooc = np.zeros((len(TEC), len(TEC)), dtype=int)
for i in range(len(docs)):
    ids = [n_tech[x] for x in doc_tecs[i]]
    for a in range(len(ids)):
        for b in range(a + 1, len(ids)):
            cooc[ids[a], ids[b]] += 1
links = []
for a in range(len(TEC)):
    for b in range(a + 1, len(TEC)):
        w = int(cooc[a, b])
        if w >= 1:
            links.append({"s": TEC[a]["id"], "t": TEC[b]["id"], "w": w})
links.sort(key=lambda x: -x["w"])

# ---------------------------------------------------------------- serie años (2008–2026)
pubs = docs["anio"].value_counts().sort_index()
y0 = int(docs["anio"].min()); y1 = int(docs["anio"].max())
years = list(range(y0, y1 + 1))
pubs_series = [int(pubs.get(y, 0)) for y in years]

rng = np.random.RandomState(42)
iy = np.arange(y0, y1 + 1)
tech_invest = np.clip(10 + 55 * (1 - np.exp(-0.18 * (iy - y0))) + rng.normal(0, 2, len(iy)), 8, 72)
edu_index = np.clip(0.42 + 0.38 * (1 - np.exp(-0.12 * (iy - y0))) + rng.normal(0, 0.015, len(iy)), 0.40, 0.82)

# ---------------------------------------------------------------- países (observatorio)
countries = [
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

# ---------------------------------------------------------------- colores por continente
CONT_COL = {
    "Africa": "#56B4E9",
    "LatAm": "#009E73",
    "Asia": "#E69F00",
    "AsiaPac": "#E69F00",
    "Europe": "#0072B2",
    "Global": "#888888",
}

# ---------------------------------------------------------------- fondos IGF (sintético)
igf_funds = [
    {"region": "África Sub.", "pct": 38},
    {"region": "Latinoamérica", "pct": 22},
    {"region": "Asia", "pct": 16},
    {"region": "Europa", "pct": 12},
    {"region": "Resto", "pct": 12},
]

radar = {
    "labels": ["Adopción\nTecnológica", "Índice de\nSeguridad", "Cumplimiento\nAmbiental",
               "Producción\nCientífica", "Inversión", "Marco\nNormativo"],
    "series": [
        {"id": "Africa", "nombre": "África", "v": [12, 22, 18, 8, 15, 20]},
        {"id": "LatAm", "nombre": "Latinoamérica", "v": [32, 45, 40, 28, 30, 38]},
        {"id": "AsiaPac", "nombre": "Asia-Pacífico", "v": [26, 38, 30, 22, 25, 32]},
        {"id": "Europe", "nombre": "Europa", "v": [58, 60, 55, 30, 55, 62]},
        {"id": "Global", "nombre": "Global (ref.)", "v": [25, 38, 30, 20, 23, 30]},
    ],
    "orden_serie": ["Africa", "LatAm", "AsiaPac", "Europe", "Global"],
    "colores": CONT_COL,
}

# correlaciones (replica del notebook, seed 42)
cc = np.random.RandomState(42)
n21 = len(years)
corr_data = pd.DataFrame({
    "Publicaciones": pubs_series[:n21],
    "Inversión Tech": tech_invest[:n21],
    "Índice Educativo": edu_index[:n21],
    "Citas Promedio": [float(np.nan)] * n21,
    "Minería PIB%": np.clip(7 + 3 * np.sin(np.linspace(0, 2 * np.pi, n21)) + cc.normal(0, 0.5, n21), 4, 12),
    "Safety Score": np.clip(25 + 15 * (1 - np.exp(-0.15 * np.arange(n21))) + cc.normal(0, 2, n21), 20, 45),
    "Env Score": np.clip(20 + 18 * (1 - np.exp(-0.12 * np.arange(n21))) + cc.normal(0, 2, n21), 18, 42),
})
citas_avg = docs.groupby("anio")["citas"].apply(
    lambda s: pd.to_numeric(s, errors="coerce").mean()).reindex(years).fillna(0)
corr_data["Citas Promedio"] = citas_avg.values
corr = corr_data.corr()
cols = list(corr.columns)
cm = [[round(corr.iloc[i, j], 3) for j in range(len(cols))] for i in range(len(cols))]

# ---------------------------------------------------------------- docs finales
def primeros_autores(a, n=2):
    a = norm(a)
    if not a:
        return "s.d."
    parts = [x.strip() for x in re.split(r"[;]", a) if x.strip()]
    if len(parts) <= n:
        return " · ".join(parts[:n])
    return " · ".join(parts[:n]) + " et al."

def clip_text(v, n=1200):
    s = norm(v)
    return s[:n]

docs_out = []
for i, r in docs.iterrows():
    doi = norm_doi(r.get("doi"))
    tecs = doc_tecs.get(i, [])
    docs_out.append({
        "id": i,
        "titulo": norm(r.get("titulo", ""))[:300],
        "anio": int(r["anio"]) if pd.notna(r["anio"]) else None,
        "citas": int(pd.to_numeric(r["citas"], errors="coerce")) if pd.notna(pd.to_numeric(r["citas"], errors="coerce")) else 0,
        "autores": primeros_autores(r.get("autores")),
        "fuente": norm(r.get("fuente") or r.get("fuenteabrev"))[:140],
        "doi": doi,
        "enlace": norm(r.get("enlace")),
        "acceso": r["_acceso"],
        "cluster": int(doc_clus[i]) if doc_clus.get(i) is not None else None,
        "tecs": tecs,
        "hallazgos": clip_text(r.get("Hallazgos principales")),
        "limitaciones": clip_text(r.get("Limitaciones")),
        "novedad": clip_text(r.get("Novedad")),
        "kws": [TEC[n_tech[x]]["nombre"] for x in tecs][:8],
    })

oa_count = int((docs["_acceso"] == "Acceso libre").sum())
acc_counts = docs["_acceso"].value_counts().to_dict()
acc_counts = {"libre": int(acc_counts.get("Acceso libre", 0)),
              "no_abierto": int(acc_counts.get("No abierto", 0)),
              "sin_dato": int(acc_counts.get("Sin dato", 0))}
cit_total = int(pd.to_numeric(docs["citas"], errors="coerce").fillna(0).sum())

tech_out = []
for t in TEC:
    tt = dict(t)
    tt["cat_out"] = tt.pop("cat")
    tech_out.append({k: v for k, v in tt.items()})
    tech_out[-1]["n_docs"] = int(t["n_docs"])
    del tech_out[-1]["kws"]

tema_docs = {}
for c in doc_clus.values():
    if c is not None:
        tema_docs[int(c)] = tema_docs.get(int(c), 0) + 1

# países reales (producción, revisión ampliada Scopus)
paises_out = paises.sort_values("documentos", ascending=False).head(15).to_dict("records")
paises_out = [{"pais": r["pais"], "n": int(r["documentos"]), "pct": float(r["porcentaje_%"])} for r in paises_out]

# ---------------------------------------------------------------- corpora adicionales (360 / 269 / 258 / 207)
CSV_360 = BASE + r"\scopusRevisionManual.csv"
CSV_269 = BASE + r"\scopusAnalisisLimpio.csv"

C3_SUB = ["underground min", "subterranean min", "underground coal", "underground excavation", "mineria subterranea", "minería subterránea"]
C3_TEC = ["mining technolog", "tecnologia minera", "tecnologías mineras", "mining engineer", "mining science"]
C3_DEP = re.compile("gold deposit|gold ore|auriferous|gold mineralization|yacimientos de oro|gold mining deposit")
C3_EST = re.compile("stabilit|estabilidad")
CLS3 = {
    0: {"nombre": "Mina subterránea × tecnología minera", "temas": "underground mining technology, equipment and engineering, smart/automated underground mining"},
    1: {"nombre": "Depósitos de oro y mineralización", "temas": "gold deposits, ore bodies, gold mineralization, auriferous zones"},
    2: {"nombre": "Estabilidad y geomecánica", "temas": "stability, geomechanics, ground control"},
}


def clasif_acceso(v):
    s = norm(v).lower()
    if not s:
        return "Sin dato"
    if "no open access" in s:
        return "No abierto"
    if "open access" in s:
        return "Acceso libre"
    return "Sin dato"


def corpus_entry(df, cid, nombre, csv_name):
    df = df.reset_index(drop=True)
    df["_texto"] = (df["titulo"].fillna("") + " " + df["resumen"].fillna("") + " " +
                    df["palabras"].fillna("") + " " + df["indices"].fillna("")).str.lower()
    cl = np.full(len(df), -1, dtype=int)
    m_sub = df["_texto"].str.contains("|".join(C3_SUB), na=False)
    m_tec = df["_texto"].str.contains("|".join(C3_TEC), na=False)
    cl[(m_sub & m_tec)] = 0
    cl[df["_texto"].str.contains(C3_DEP, na=False) & (cl < 0)] = 1
    cl[df["_texto"].str.contains(C3_EST, na=False) & (cl < 0)] = 2
    df["_cl"] = cl
    df["_acceso"] = df["acceso"].map(lambda v: clasif_acceso(v) if pd.notna(v) else "Sin dato")
    dtecs = {i: [] for i in range(len(df))}
    for t in TEC:
        rx = re.compile("|".join(re.escape(k) for k in t["kws"]))
        hit = [i for i in range(len(df)) if rx.search(df["_texto"].iloc[i])]
        for i in hit:
            dtecs[i].append(t["id"])
    docs = []
    for i, r in df.iterrows():
        doi = norm_doi(r.get("doi"))
        tecs = dtecs.get(i, [])
        docs.append({
            "id": i,
            "titulo": norm(r.get("titulo", ""))[:300],
            "anio": int(r["anio"]) if pd.notna(r["anio"]) else None,
            "citas": int(pd.to_numeric(r["citas"], errors="coerce")) if pd.notna(pd.to_numeric(r["citas"], errors="coerce")) else 0,
            "autores": primeros_autores(r.get("autores")),
            "fuente": norm(r.get("fuente") or r.get("fuenteabrev"))[:140],
            "doi": doi,
            "enlace": norm(r.get("enlace")),
            "acceso": r["_acceso"],
            "cluster": int(r["_cl"]) if r["_cl"] >= 0 else None,
            "tecs": tecs,
            "hallazgos": "", "limitaciones": "", "novedad": "",
            "kws": [TEC[n_tech[x]]["nombre"] for x in tecs][:8],
        })
    acc = df["_acceso"].value_counts()
    cluster_counts = {int(k): int(v) for k, v in df["_cl"].value_counts().items() if int(k) >= 0}
    n_serie = len(set(x for v in dtecs.values() for x in v))
    anios = pd.to_numeric(df["anio"], errors="coerce").dropna()
    yA, yB = int(anios.min()), int(anios.max())
    pubs_c = df["anio"].value_counts().sort_index()
    years_c = list(range(yA, yB + 1))
    pubs_series_c = [int(pubs_c.get(y, 0)) for y in years_c]
    rng_c = np.random.RandomState(7)
    iy_c = np.arange(yA, yB + 1)
    tech_c = np.clip(10 + 55 * (1 - np.exp(-0.18 * (iy_c - yA))) + rng_c.normal(0, 2, len(iy_c)), 8, 72)
    edu_c = np.clip(0.42 + 0.38 * (1 - np.exp(-0.12 * (iy_c - yA))) + rng_c.normal(0, 0.015, len(iy_c)), 0.40, 0.82)
    libre = int(acc.get("Acceso libre", 0))
    return {
        "id": cid,
        "nombre": nombre,
        "csv": csv_name,
        "meta": {
            "n_docs": len(df),
            "rango": [yA, yB],
            "citas_totales": int(pd.to_numeric(df["citas"], errors="coerce").fillna(0).sum()),
            "oa": libre,
            "oa_pct": round(100 * libre / len(df), 1),
            "n_tecs": n_serie,
            "n_clusters": len(cluster_counts),
            "cluster_counts": cluster_counts,
            "acceso": {"libre": libre,
                       "no_abierto": int(acc.get("No abierto", 0)),
                       "sin_dato": int(acc.get("Sin dato", 0))},
            "corpus": csv_name,
            "gen": "2026-09-18",
        },
        "clusters": CLS3,
        "docs": docs,
        "series": {"years": years_c, "pubs": pubs_series_c,
                   "tech_invest": [round(float(x), 1) for x in tech_c],
                   "edu_index": [round(float(x), 3) for x in edu_c]},
    }


g360 = pd.read_csv(CSV_360, encoding="utf-8-sig")
g269 = pd.read_csv(CSV_269, encoding="utf-8-sig")
for g in (g360, g269):
    g["anio"] = pd.to_numeric(g["anio"], errors="coerce")
enr = g269["anio"].between(2006, 2026)
g258 = g269[enr]
_txt = (g269["titulo"].fillna("") + " " + g269["resumen"].fillna("") + " " +
        g269["palabras"].fillna("") + " " + g269["indices"].fillna("")).str.lower()
_subtec = _txt.str.contains("|".join(C3_SUB), na=False) & _txt.str.contains("|".join(C3_TEC), na=False)
g207 = g269[_subtec & enr]

corpora = [
    corpus_entry(g360, "360", "360 · registros Scopus", "scopusRevisionManual.csv"),
    corpus_entry(g269, "269", "269 · corpus depurado", "scopusAnalisisLimpio.csv"),
    corpus_entry(g258, "258", "258 · rango 2006–2026", "scopusAnalisisLimpio.csv · rango 2006–2026"),
    corpus_entry(g207, "207", "207 · clúster sub×tec", "scopusAnalisisLimpio.csv · Mina subterránea × tecnología minera"),
]

data = {
    "meta": {
        "n_docs": len(docs),
        "rango": [y0, y1],
        "citas_totales": cit_total,
        "oa": oa_count,
        "oa_pct": round(100 * oa_count / len(docs), 1),
        "n_tecs": len(tech_out),
        "n_clusters": len(CLS),
        "cluster_counts": tema_docs,
        "acceso": acc_counts,
        "corpus": "thirdPass_124.csv",
        "gen": "2026-09-15",
    },
    "clusters": CLS,
    "docs": docs_out,
    "tecnologias": tech_out,
    "red": {"links": links},
    "series": {"years": years, "pubs": pubs_series,
               "tech_invest": [round(float(x), 1) for x in tech_invest],
               "edu_index": [round(float(x), 3) for x in edu_index]},
    "paises_pub": paises_out,
    "paises_obs": countries,
    "radar": radar,
    "cont_col": CONT_COL,
    "igf_funds": igf_funds,
    "corr": {"cols": cols, "mat": cm},
    "corpora": corpora,
}

js = "// Generado por build_data.py · Portal MAPE · corpus 124 (thirdPass_124.csv) + vistas 360/269/258/207\n"
js += "window.APP_DATA = " + json.dumps(data, ensure_ascii=False, indent=0) + ";\n"
os.makedirs(OUT, exist_ok=True)
with open(OUT + r"\app_data.js", "w", encoding="utf-8") as f:
    f.write(js)
with open(OUT + r"\app_data.json", "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print("OK · docs:", len(docs_out), "· tecs:", len(tech_out), "· links:", len(links), "· years:", y0, "-", y1)
print("corpora adicionales:")
for c in corpora:
    print("  [%s] %-38s n=%d  citas=%d  (acceso libre=%d)" % (c["id"], c["nombre"], c["meta"]["n_docs"], c["meta"]["citas_totales"], c["meta"]["oa"]))
print("docs por clúster C4:")
for c in sorted(CLS):
    print("  %-45s n=%d" % (CLS[c]["nombre"], tema_docs.get(c, 0)))
sin = sum(1 for v in doc_clus.values() if v is None)
print("  sin clúster: n=%d" % sin)
print("docs por técnica:")
for t in TEC:
    print("  %-42s n=%3d  TRL=%d" % (t["nombre"], t["n_docs"], t["trl"]))