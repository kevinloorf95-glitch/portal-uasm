# -*- coding: utf-8 -*-
"""
Lógica de derivación compartida entre el importador (`build_db.py`) y el
servidor (`dbstore.py`): clasificación por clústeres y tecnologías, series
temporales sintéticas y matriz de correlaciones.

Todo se calcula **a partir de las tablas de los `.db`** (nada de ficheros CSV
en tiempo de ejecución), de modo que editar `clusters.kws` o `tec_kws` y
reindexar cambia los agregados del portal.
"""
import json
import math
import random
import re

ACCESO_LIBRE = "Acceso libre"
ACCESO_NO = "No abierto"
ACCESO_SIN = "Sin dato"
ACCESOS = [ACCESO_LIBRE, ACCESO_NO, ACCESO_SIN]

CORR_COLS = ["Publicaciones", "Inversión Tech", "Índice Educativo",
             "Citas Promedio", "Minería PIB%", "Safety Score", "Env Score"]


# ---------------------------------------------------------------- utilidades
def norm(v):
    if v is None:
        return ""
    s = str(v)
    return " ".join(line.strip().replace("\xad", "") for line in s.splitlines() if line.strip())


def norm_doi(v):
    if v is None:
        return ""
    s = str(v).strip().lower()
    return "" if s.lower() in ("nan", "none") else s


def to_int(v, default=0):
    try:
        f = float(str(v).strip())
    except (TypeError, ValueError):
        return default
    return int(f) if f == f else default


def to_float(v, default=None):
    try:
        f = float(str(v).strip().replace(",", "."))
    except (TypeError, ValueError, AttributeError):
        return default
    if f != f:  # NaN
        return default
    return f


def clamp(x, a, b):
    return max(a, min(b, x))


def meta_bool(v):
    return str(v).strip().lower() in ("1", "true", "yes", "si", "sí")


# ---------------------------------------------------------------- acceso
def clasificar_acceso_124(v):
    """Clasificación del corpus cualitativo (columna `perfil_acceso`)."""
    s = norm(v).lower()
    if not s:
        return ACCESO_SIN
    if "libre" in s or "open access" in s:
        return ACCESO_LIBRE
    if "abierto" in s or "open" in s:
        return ACCESO_NO
    return ACCESO_SIN


def clasificar_acceso_scopus(v):
    """Clasificación del export Scopus (columna `acceso`)."""
    s = norm(v).lower()
    if not s:
        return ACCESO_SIN
    if "no open access" in s:
        return ACCESO_NO
    if "open access" in s:
        return ACCESO_LIBRE
    return ACCESO_SIN


def perfil_acceso_row(v):
    return clasificar_acceso_124(v)


# ---------------------------------------------------------------- texto de matching
def texto_124(titulo, hallazgos, limitaciones, novedad, fuente):
    return " ".join([norm(titulo), norm(hallazgos), norm(limitaciones),
                     norm(novedad), norm(fuente)[:400]]).lower()


def texto_scopus(titulo, resumen, palabras, indices):
    return " ".join([norm(titulo), norm(resumen), norm(palabras),
                     norm(indices)]).lower()


# ---------------------------------------------------------------- clasificación
def _cumple(texto, cluster):
    grupos = cluster.get("kws_all") or []
    if grupos:
        return all(any(k in texto for k in g) for g in grupos if g)
    kws = cluster.get("kws") or []
    return bool(kws) and any(k in texto for k in kws)


def _n_hits(texto, cluster):
    total = 0
    for g in (cluster.get("kws_all") or []):
        kws = g if isinstance(g, list) else [g]
        if kws:
            total += len(re.compile("|".join(re.escape(k) for k in kws)).findall(texto))
    for k in (cluster.get("kws") or []):
        if k in texto:
            total += 1
    return total


def clasificar_cluster(texto, clusters):
    """clusters: lista de dicts {id, kws:[...], kws_all:[[...]], modo}.

    modo 'hits'      -> gana el clúster con más coincidencias (empate: id menor)
    modo 'prioridad' -> gana el primer clúster (id ascendente) que cumple la
                        condición; con `kws_all` cada grupo debe tener ≥1
                        coincidencia (conjunción).
    Devuelve el id o None.
    """
    clusters = sorted(clusters, key=lambda c: c.get("id", 0))
    mejor_id, mejor_n = None, 0
    for c in clusters:
        modo = c.get("modo") or "hits"
        if modo == "prioridad":
            if _cumple(texto, c):
                return c.get("id")
            continue
        if not _cumple(texto, c):
            continue
        n = _n_hits(texto, c)
        if n > mejor_n:
            mejor_id, mejor_n = c.get("id"), n
    return mejor_id


def clasificar_tecs(texto,tec_kws):
    """tec_kws: {tec_id: [kw, ...]}  ->  lista ordenada de tec_id."""
    hits = []
    for tec_id, kws in tec_kws.items():
        if not kws:
            continue
        rx = re.compile("|".join(re.escape(k) for k in kws))
        if rx.search(texto):
            hits.append(tec_id)
    return hits


def compilar_tecnologias(tec_kws_rows):
    """[{tec_id, kw}] -> {tec_id: [kw]} conservando el orden del catálogo."""
    out = {}
    for r in tec_kws_rows:
        out.setdefault(r["tec_id"], []).append(r["kw"])
    return out


# ---------------------------------------------------------------- series sintéticas
def serie_sintetica(years, seed=42):
    """Inversión tecnológica e índice educativo sintéticos (misma fórmula que
    el notebook de la 3ª/4ª pasada, sin dependencias de numpy)."""
    if not years:
        return [], []
    y0 = years[0]
    rng = random.Random(seed)
    tech, edu = [], []
    for y in years:
        d = y - y0
        tech.append(round(clamp(10 + 55 * (1 - math.exp(-0.18 * d)) + rng.gauss(0, 2), 8, 72), 1))
        edu.append(round(clamp(0.42 + 0.38 * (1 - math.exp(-0.12 * d)) + rng.gauss(0, 0.015),
                               0.40, 0.82), 3))
    return tech, edu


def componentes_sinteticos(n, seed=42):
    rng = random.Random(seed)
    mineria = [clamp(7 + 3 * math.sin(i * (2 * math.pi / n)) + rng.gauss(0, 0.5), 4, 12)
               for i in range(n)] if n else []
    safety = [clamp(25 + 15 * (1 - math.exp(-0.15 * i)) + rng.gauss(0, 2), 20, 45)
              for i in range(n)] if n else []
    env = [clamp(20 + 18 * (1 - math.exp(-0.12 * i)) + rng.gauss(0, 2), 18, 42)
           for i in range(n)] if n else []
    return mineria, safety, env


def pearson(a, b):
    n = min(len(a), len(b))
    if n < 2:
        return 0.0
    ma = sum(a[:n]) / n
    mb = sum(b[:n]) / n
    va = sum((x - ma) ** 2 for x in a[:n])
    vb = sum((x - mb) ** 2 for x in b[:n])
    if va <= 0 or vb <= 0:
        return 0.0
    cov = sum((a[i] - ma) * (b[i] - mb) for i in range(n))
    return cov / math.sqrt(va * vb)


def matriz_corr(series, seed=42):
    """series: dict con las listas de CORR_COLS (misma longitud)."""
    ref = series.get("Publicaciones") or []
    n_ref = len(ref)
    mineria, safety, env = componentes_sinteticos(n_ref, seed)
    sinteticas = {"Minería PIB%": mineria, "Safety Score": safety, "Env Score": env}
    cols = []
    for name in CORR_COLS:
        v = series.get(name) or sinteticas.get(name) or []
        cols.append([float(x) for x in v])
    n = len(CORR_COLS)
    return [[round(pearson(cols[i], cols[j]), 3) for j in range(n)] for i in range(n)]


def jloads(v, default=None):
    try:
        return json.loads(v)
    except (TypeError, ValueError):
        return default if default is not None else []