# -*- coding: utf-8 -*-
"""
Bases `.db` **derivadas**: una por cada gráfica y cada tabla del portal.

Cada figura o tabla que se pinta en pantalla tiene su propio fichero SQLite
(`frame/db/<id>.db`) con los datos exactos que se dibujan.  Propiedades:

* **Materializada y viva**: se regenera sola en cuanto cambia cualquier `.db`
  fuente (alta/baja/edición de documentos, tecnologías o indicadores), de modo
  que el `.db` derivado y la gráfica siempre coinciden.
* **Editable**: las filas se pueden modificar desde el portal (API de escritura)
  o directamente con `sqlite3` / DBeaver sobre `datos`.  Las ediciones se
  memorizan en la tabla `overrides`, así que sobreviven a las regeneraciones.
* **Autodescriptiva**: la tabla `columnas` declara el nombre, el título, el tipo
  y si cada campo es editable; `meta` guarda la huella de la fuente y la
  fecha de la última sincronización.

Esquema de cada `.db` derivado
-----------------------------
    base       filas regeneradas desde los .db fuente        (no editar)
    datos      vista efectiva = base + overrides             (editable)
    overrides  ediciones del usuario (accion = set | del)
    columnas   catálogo de campos (orden, nombre, titulo, tipo, ro)
    meta       huella de la fuente, generación, descripción
    fuentes    procedencia de los datos

Las bases de origen (`corpus_*.db`, `catalogo_tecnologias.db`,
`observatorio.db`) **no se tocan**: las derivadas sólo las leen.
"""
import hashlib
import json
import math
import os
import random
import re
import sqlite3
import threading

# ---------------------------------------------------------------- paleta
CAT_COLORES = {
    "Sensórica y monitoreo": "#56B4E9",
    "Modelado y simulación": "#0072B2",
    "Inteligencia artificial": "#E69F00",
    "Geomática": "#009E73",
    "Automatización y robótica": "#D55E00",
    "Comunicaciones y datos": "#CC79A7",
    "Operación y ambiente": "#E69F00",
    "Gobernanza": "#999999",
}
NIVEL_COLORES = {"fuerte": "#0b4f6c", "media": "#7ba7bb", "debil": "#c4d6de"}
ACCESO_COLORES = {"Acceso libre": "#2e7d42", "No abierto": "#5d7280", "Sin dato": "#b07a1a"}
CONT_COLORES = {"Africa": "#56B4E9", "LatAm": "#009E73", "Asia": "#E69F00",
                "AsiaPac": "#E69F00", "Europe": "#0072B2", "Global": "#888888"}
CLUSTER_COLORES = ["#D55E00", "#0072B2", "#009E73", "#56B4E9", "#CC79A7",
                   "#E69F00", "#999999", "#0b4f6c"]

SIM_FUERTE = 0.34          # similitud a partir de la cual un enlace sintético es "medio"
W_FUERTE = 2               # co-ocurrencias a partir de las cuales el enlace es "fuerte"
MAX_PUENTES = 18           # topes de enlaces sintéticos para no saturar el grafo

_LOCK = threading.RLock()
_RESERVED = ("clave", "orden", "extra")


def _c(n, t, tipo="text", ro=False):
    """Declara un campo de una tabla derivada."""
    assert n not in _RESERVED, "campo reservado: %s" % n
    return {"n": n, "t": t, "tipo": tipo, "ro": bool(ro)}


# ---------------------------------------------------------------- registro
GRAFIOS = [
    dict(id="chart_anios", tipo="grafica", seccion="Inicio",
         titulo="Producciones científicas por año",
         desc="Barras: número de documentos del corpus activo por año de publicación.",
         fuente="docs.anio del corpus activo",
         cols=[_c("anio", "Año", "int"), _c("etiqueta", "Etiqueta"),
               _c("publicaciones", "Publicaciones", "num")]),
    dict(id="chart_donut_cluster", tipo="grafica", seccion="Inicio",
         titulo="Clústeres temáticos del corpus",
         desc="Dona: reparto de documentos por clúster temático.",
         fuente="docs.cluster + clusters.nombre",
         cols=[_c("cluster", "Clúster"), _c("etiqueta", "Categoría"),
               _c("docs", "Documentos", "num"), _c("color", "Color")]),
    dict(id="chart_donut_acceso", tipo="grafica", seccion="Inicio",
         titulo="Perfil de acceso abierto",
         desc="Dona: reparto de documentos por perfil de acceso.",
         fuente="docs.acceso",
         cols=[_c("acceso", "Acceso"), _c("etiqueta", "Categoría"),
               _c("docs", "Documentos", "num"), _c("color", "Color")]),
    dict(id="chart_top5", tipo="grafica", seccion="Inicio",
         titulo="Documentos más citados",
         desc="Barras horizontales: los documentos con más citas del corpus activo.",
         fuente="docs.citas (orden descendente)",
         cols=[_c("doc_id", "ID", "int"), _c("etiqueta", "Título"),
               _c("anio", "Año", "int"), _c("citas", "Citas", "num")]),
    dict(id="chart_radar", tipo="grafica", seccion="Observatorio",
         titulo="Perfil regional multidimensional",
         desc="Radar: seis indicadores por región, escala 0–100.",
         fuente="radar_labels + radar_series",
         cols=[_c("serie", "Serie"), _c("etiqueta", "Región"),
               _c("eje", "Indicador"), _c("orden_eje", "Orden del eje", "int"),
               _c("valor", "Valor (0–100)", "num"), _c("color", "Color")]),
    dict(id="chart_bubble", tipo="grafica", seccion="Observatorio",
         titulo="Adopción tecnológica vs. PIB per cápita",
         desc="Burbujas por país: eje X = PIB per cápita (log), eje Y = adopción (0–100), "
              "tamaño = publicaciones, color = región. La recta punteada es la regresión "
              "log-PIB → adopción (r y ecuación en la ficha del .db).",
         fuente="paises_obs",
         cols=[_c("pais", "País"), _c("etiqueta", "País"),
               _c("gdp_pc", "PIB per cápita (US$)", "num"),
               _c("adopcion", "Adopción (0–100)", "num"),
               _c("region", "Región"), _c("seg", "Seguridad", "num"),
               _c("amb", "Ambiente", "num"), _c("n_pubs", "Publicaciones", "num"),
               _c("color", "Color")]),
    dict(id="chart_series", tipo="grafica", seccion="Observatorio",
         titulo="Convergencia temporal: publicaciones · inversión · educación",
         desc="Barras de publicaciones + índices de inversión tecnológica y educación (×100).",
         fuente="docs.anio + serie_sintetica",
         cols=[_c("anio", "Año", "int"), _c("etiqueta", "Etiqueta"),
               _c("publicaciones", "Publicaciones", "num"),
               _c("inversion", "Inversión tecnológica (0–100)", "num"),
               _c("educacion", "Índice educativo (×100)", "num")]),
    dict(id="chart_corr", tipo="grafica", seccion="Observatorio",
         titulo="Matriz de correlaciones",
         desc="Mapa de calor: coeficientes r entre los siete indicadores del corpus.",
         fuente="corr_cols + corr_mat",
         cols=[_c("fila", "Indicador"), _c("col", "Indicador 2"),
               _c("r", "r", "num")]),
    dict(id="chart_igf", tipo="grafica", seccion="Observatorio",
         titulo="Asignación de fondos IGF por región",
         desc="Barras: porcentaje de los fondos IGF por región beneficiaria.",
         fuente="igf_funds",
         cols=[_c("region", "Región"), _c("etiqueta", "Categoría"),
               _c("pct", "% de fondos", "num"), _c("color", "Color")]),
    dict(id="chart_paises_pub", tipo="grafica", seccion="Observatorio",
         titulo="Producción científica real por país",
         desc="Barras horizontales: documentos de la revisión ampliada por país y su peso.",
         fuente="paises_pub",
         cols=[_c("pais", "País"), _c("etiqueta", "País"),
               _c("n", "Documentos", "num"), _c("pct", "% del total", "num")]),
    dict(id="chart_red", tipo="grafica", seccion="Red",
         titulo="Red de convergencia tecnológica",
         desc="Grafo co-ocurrencia de las tecnologías del catálogo. **Todos los nodos quedan "
              "unidos**: enlaces fuertes (co-ocurrencia ≥ 2), medios (co-ocurrencia 1 o "
              "similitud alta) y débiles (puentes de similitud que cierran la red). "
              "Las coordenadas x/y del layout también viven aquí y son editables.",
         fuente="tecnologias + red + tec_kws",
         cols=[_c("tipo", "Tipo"), _c("id", "ID"), _c("etiqueta", "Etiqueta"),
               _c("categoria", "Categoría"),
               _c("valor", "Valor", "num"), _c("valor2", "Grado", "num"),
               _c("nivel", "Nivel del enlace"), _c("similitud", "Similitud", "num"),
               _c("x", "x", "num"), _c("y", "y", "num"), _c("color", "Color")]),
    dict(id="chart_cat", tipo="grafica", seccion="Red",
         titulo="Categorías representadas",
         desc="Dona: documentos del corpus por categoría de tecnología.",
         fuente="tecnologias.n_docs por categoría",
         cols=[_c("cat", "Categoría"), _c("etiqueta", "Categoría"),
               _c("docs", "Documentos", "num"), _c("color", "Color")]),
    dict(id="chart_tec_bar", tipo="grafica", seccion="Red",
         titulo="Frecuencia por tecnología",
         desc="Barras horizontales: documentos del corpus por tecnología.",
         fuente="tecnologias.n_docs",
         cols=[_c("tec", "Tecnología"), _c("etiqueta", "Tecnología"),
               _c("docs", "Documentos", "num"), _c("categoria", "Categoría"),
               _c("color", "Color")]),
    dict(id="tabla_tecnologias", tipo="tabla", seccion="Matriz",
         titulo="Matriz de tecnologías",
         desc="Tabla de la matriz de transferencia tecnológica (una fila por tecnología).",
         fuente="catalogo_tecnologias.tecnologias",
         cols=[_c("tec", "ID"), _c("nombre", "Tecnología"), _c("cat", "Categoría"),
               _c("docs", "Docs", "num"), _c("trl", "TRL", "num"),
               _c("geoma", "Geometría"), _c("capex", "CAPEX"), _c("opex", "OPEX"),
               _c("seg", "Seg.", "num"), _c("amb", "Amb.", "num")]),
    dict(id="tabla_paises_obs", tipo="tabla", seccion="Observatorio",
         titulo="Países modelo del observatorio",
         desc="Tabla de indicadores por país del observatorio operativo.",
         fuente="observatorio.paises_obs",
         cols=[_c("pais", "País"), _c("cont", "Región"),
               _c("gdp_pc", "PIB pc (US$)", "num"), _c("tech", "Tech", "num"),
               _c("seg", "Seg.", "num"), _c("amb", "Amb.", "num"),
               _c("mining_gdp", "Minería% PIB", "num")]),
    dict(id="tabla_corpus", tipo="tabla", seccion="Corpus",
         titulo="Corpus (vista de la tabla)",
         desc="Filas de la tabla del explorador del corpus activo (número, año, título…).",
         fuente="docs del corpus activo",
         cols=[_c("n", "N", "num"), _c("anio", "Año", "num"),
               _c("titulo", "Título"), _c("autores", "Autores"),
               _c("fuente", "Fuente"), _c("citas", "Citas", "num"),
               _c("doi", "DOI"), _c("enlace", "Enlace"), _c("acceso", "Acceso"),
               _c("cluster", "Clúster"), _c("tecnologias", "Tecnologías"),
               _c("keywords", "Keywords")]),
    dict(id="tabla_deliverable", tipo="tabla", seccion="Corpus",
         titulo="Entrega científica (n=124)",
         desc="Análisis cualitativo por documento: hallazgos, limitaciones y novedad.",
         fuente="docs.hallazgos / limitaciones / novedad",
         cols=[_c("n", "N", "num"), _c("anio", "Año", "num"),
               _c("titulo", "Título"), _c("autores", "Autores"),
               _c("fuente", "Fuente"), _c("citas", "Citas", "num"),
               _c("acceso", "Acceso"), _c("cluster", "Clúster"),
               _c("hallazgos", "Hallazgos principales"),
               _c("limitaciones", "Limitaciones"), _c("novedad", "Novedad")]),
]

POR_ID = {g["id"]: g for g in GRAFIOS}

# tablas que el navegador carga siempre (el resto se piden bajo demanda)
PESADAS = {"tabla_deliverable", "tabla_corpus"}


def nombres_db():
    return [g["id"] + ".db" for g in GRAFIOS]


def es_derivada(nombre):
    return nombre in nombres_db()


def ids_graficos():
    return [g["id"] for g in GRAFIOS]


# ---------------------------------------------------------------- helpers
def _t(color):
    return str(color or "#0b4f6c")


def _f(v, default=0.0):
    try:
        f = float(v)
        return default if f != f else f
    except (TypeError, ValueError):
        return default


def _i(v, default=0):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return default


def _texto(v):
    return "" if v is None else str(v)


def _cont_id(nombre):
    n = _texto(nombre)
    if "frica" in n or n == "Africa":
        return "Africa"
    if "Latinoam" in n or n == "LatAm":
        return "LatAm"
    if n in ("Asia", "Asia-Pacífico", "AsiaPac"):
        return "AsiaPac"
    if "Europa" in n or n == "Europe":
        return "Europe"
    return "Global"


def _tokens(palabras):
    out = set()
    for k in (palabras or []):
        for t in re.split(r"[^0-9a-záéíóúüñ]+", _texto(k).lower()):
            if len(t) > 2:
                out.add(t)
    return out


def _jaccard(a, b):
    if not a or not b:
        return 0.0
    inter = len(a & b)
    return inter / float(len(a | b))


# ================================================================ cálculos
def calc(gid, ctx):
    """Filas de la gráfica/tabla `gid` a partir del contexto del portal."""
    fn = CALC.get(gid)
    return fn(ctx) if fn else []


# --- Inicio ---------------------------------------------------------------
def _anios(ctx):
    s = ctx.get("series") or {}
    return [{"clave": str(a), "orden": i, "anio": int(a), "etiqueta": str(a),
             "publicaciones": _f(p)}
            for i, (a, p) in enumerate(zip(s.get("years") or [], s.get("pubs") or []))]


def _donut_cluster(ctx):
    meta = ctx.get("meta") or {}
    clusters = ctx.get("clusters") or {}
    cc = meta.get("cluster_counts") or {}
    filas = []
    for k in sorted(cc, key=lambda x: int(x)):
        c = clusters.get(str(k)) or {}
        filas.append({"clave": str(k), "orden": int(k), "cluster": str(k),
                      "etiqueta": c.get("nombre") or ("Clúster " + str(k)),
                      "docs": _f(cc[k]),
                      "color": CLUSTER_COLORES[int(k) % len(CLUSTER_COLORES)]})
    asignados = sum(_f(v) for v in cc.values())
    sin = _f(meta.get("n_docs")) - asignados
    if sin > 0:
        filas.append({"clave": "sin", "orden": 900, "cluster": "",
                      "etiqueta": "Sin clúster temático", "docs": sin, "color": "#8fa3ad"})
    return filas


def _donut_acceso(ctx):
    ac = (ctx.get("meta") or {}).get("acceso") or {}
    return [{"clave": "libre", "orden": 0, "acceso": "Acceso libre",
             "etiqueta": "Acceso libre", "docs": _f(ac.get("libre")),
             "color": ACCESO_COLORES["Acceso libre"]},
            {"clave": "no", "orden": 1, "acceso": "No abierto",
             "etiqueta": "No abierto", "docs": _f(ac.get("no_abierto")),
             "color": ACCESO_COLORES["No abierto"]},
            {"clave": "sd", "orden": 2, "acceso": "Sin dato",
             "etiqueta": "Sin dato", "docs": _f(ac.get("sin_dato")),
             "color": ACCESO_COLORES["Sin dato"]}]


def _top5(ctx):
    return [{"clave": str(d.get("id")), "orden": i, "doc_id": _i(d.get("id")),
             "etiqueta": _texto(d.get("titulo")), "anio": _i(d.get("anio")),
             "citas": _f(d.get("citas"))}
            for i, d in enumerate(ctx.get("top5") or [])]


# --- Observatorio ---------------------------------------------------------
def _radar(ctx):
    rd = (ctx.get("obs") or {}).get("radar") or {}
    colores = rd.get("colores") or {}
    filas = []
    for s in rd.get("series") or []:
        for j, v in enumerate(s.get("v") or []):
            eje = (rd.get("labels") or [])
            filas.append({"clave": "%s|%d" % (s.get("id"), j), "orden": j,
                          "serie": _texto(s.get("id")), "etiqueta": _texto(s.get("nombre")),
                          "eje": _texto(eje[j] if j < len(eje) else ""),
                          "orden_eje": j, "valor": _f(v),
                          "color": _t(colores.get(s.get("id")))})
    return filas


def _bubble(ctx):
    obs = ctx.get("obs") or {}
    puntos = []
    for p in obs.get("paises_obs") or []:
        cid = _cont_id(p.get("cont"))
        puntos.append({"clave": _texto(p.get("pais")), "orden": len(puntos),
                       "pais": _texto(p.get("pais")), "etiqueta": _texto(p.get("pais")),
                       "gdp_pc": _f(p.get("gdp_pc")), "adopcion": _f(p.get("tech")),
                       "region": _texto(p.get("cont")),
                       "seg": _f(p.get("seg")), "amb": _f(p.get("amb")),
                       "n_pubs": _f(p.get("n_pubs")),
                       "color": _t(CONT_COLORES.get(p.get("cont"),
                                                    CONT_COLORES.get(cid)))})
    r = pearson_log(puntos)
    for p in puntos:
        p["x"] = p["gdp_pc"]
        p["y"] = p["adopcion"]
    ctx.setdefault("_bubble_reg", r)
    return puntos


def pearson_log(puntos):
    """Regresión lineal log10(PIB pc) → adopción; devuelve r, pendiente, intercepto."""
    xs = [(p["gdp_pc"], p["adopcion"]) for p in puntos if p["gdp_pc"] > 0]
    if len(xs) < 3:
        return {"r": 0.0, "slope": 0.0, "intercept": 0.0, "n": len(xs)}
    lx = [math.log10(x) for x, _ in xs]
    ly = [y for _, y in xs]
    n = len(xs)
    mx, my = sum(lx) / n, sum(ly) / n
    den = sum((v - mx) ** 2 for v in lx) or 1e-9
    slope = sum((lx[i] - mx) * (ly[i] - my) for i in range(n)) / den
    ic = my - slope * mx
    cov = sum((lx[i] - mx) * (ly[i] - my) for i in range(n))
    den2 = math.sqrt(sum((v - mx) ** 2 for v in lx) * sum((v - my) ** 2 for v in ly)) or 1e-9
    return {"r": round(cov / den2, 3), "slope": round(slope, 3),
            "intercept": round(ic, 3), "n": n}


def _series(ctx):
    s = ctx.get("series") or {}
    filas = []
    years = s.get("years") or []
    pubs = s.get("pubs") or []
    inv = s.get("tech_invest") or []
    edu = s.get("edu_index") or []
    for i, a in enumerate(years):
        filas.append({"clave": str(a), "orden": i, "anio": int(a), "etiqueta": str(a),
                      "publicaciones": _f(pubs[i]) if i < len(pubs) else 0.0,
                      "inversion": _f(inv[i]) if i < len(inv) else 0.0,
                      "educacion": round(_f(edu[i]) * 100, 2) if i < len(edu) else 0.0})
    return filas


def _corr(ctx):
    corr = (ctx.get("obs") or {}).get("corr") or {}
    cols = corr.get("cols") or []
    mat = corr.get("mat") or []
    filas = []
    for i, f in enumerate(cols):
        for j, c in enumerate(cols):
            if i < len(mat) and j < len(mat[i]):
                filas.append({"clave": "%d|%d" % (i, j), "orden": i * len(cols) + j,
                              "fila": _texto(f), "col": _texto(c), "r": _f(mat[i][j])})
    return filas


def _igf(ctx):
    fondos = ((ctx.get("obs") or {}).get("igf_funds")) or []
    return [{"clave": _texto(f.get("region")), "orden": i,
             "region": _texto(f.get("region")), "etiqueta": _texto(f.get("region")),
             "pct": _f(f.get("pct")),
             "color": _t(CONT_COLORES.get(_cont_id(f.get("region"))))}
            for i, f in enumerate(fondos)]


def _paises_pub(ctx):
    return [{"clave": _texto(p.get("pais")), "orden": i, "pais": _texto(p.get("pais")),
             "etiqueta": _texto(p.get("pais")), "n": _f(p.get("n")),
             "pct": _f(p.get("pct"))}
            for i, p in enumerate((ctx.get("obs") or {}).get("paises_pub") or [])]


# --- Red ------------------------------------------------------------------
def _cat(ctx):
    agg = {}
    for t in ctx.get("tecnologias") or []:
        c = t.get("cat_out") or t.get("cat") or "—"
        agg[c] = agg.get(c, 0) + _f(t.get("n_docs"))
    filas = [{"clave": k, "orden": i, "cat": k, "etiqueta": k, "docs": float(v),
              "color": _t(CAT_COLORES.get(k))}
             for i, (k, v) in enumerate(sorted(agg.items(), key=lambda x: -x[1]))]
    return filas


def _tec_bar(ctx):
    ts = sorted(ctx.get("tecnologias") or [],
                key=lambda t: (_f(t.get("n_docs")), t.get("nombre") or ""))
    return [{"clave": _texto(t.get("id")), "orden": i, "tec": _texto(t.get("id")),
             "etiqueta": _texto(t.get("nombre")), "docs": _f(t.get("n_docs")),
             "categoria": _texto(t.get("cat_out") or t.get("cat")),
             "color": _t(CAT_COLORES.get(t.get("cat_out") or t.get("cat")))}
            for i, t in enumerate(ts)]


def red_conectada(tecs, links, kws, W=760.0, H=460.0):
    """Red de co-ocurrencia **con todos los nodos unidos**.

    1. las co-ocurrencias reales (`w >= 1`) son la parte «medida» de la red;
    2. un árbol de expansión máxima (Kruskal) garantiza que los componentes
       reales queden unidos entre sí por sus enlaces más fuertes;
    3. las tecnologías sin ningún enlace se cuelgan de la tecnología más afín
       (similitud Jaccard de su vocabulario, y a igualdad la misma categoría);
    4. se añaden algunos puentes extra de similitud alta, para que la red
       tenga también enlaces débiles intermedios.

    Cada enlace queda etiquetado como `fuerte` (w >= 2), `media` (w == 1 o
    similitud >= SIM_FUERTE) o `debil` (puente de similitud baja).
    """
    nodos = [{"id": t["id"], "nombre": t.get("nombre") or t["id"],
              "cat": t.get("cat_out") or t.get("cat") or "—",
              "n": _f(t.get("n_docs")),
              "r": 9.0 + math.sqrt(max(0.0, _f(t.get("n_docs")))) * 2.6}
             for t in (tecs or [])]
    ids = [nd["id"] for nd in nodos]
    byid = {nd["id"]: nd for nd in nodos}
    toks = {i: _tokens((kws or {}).get(i)) for i in ids}

    def sim(a, b):
        return _jaccard(toks.get(a), toks.get(b))

    real, pares = {}, set()
    for l in (links or []):
        s, t = l.get("s"), l.get("t")
        if s not in byid or t not in byid or s == t:
            continue
        k = tuple(sorted((s, t)))
        pares.add(k)
        real[k] = real.get(k, 0) + _i(l.get("w"))

    # --- 1/2: árbol de expansión máxima sobre las co-ocurrencias reales
    padre = {i: i for i in ids}

    def find(a):
        while padre[a] != a:
            padre[a] = padre[padre[a]]
            a = padre[a]
        return a

    aristas = []
    for (s, t), w in sorted(real.items(), key=lambda kv: (-kv[1], kv[0])):
        ra, rb = find(s), find(t)
        if ra != rb:
            padre[ra] = rb
            aristas.append({"s": s, "t": t, "w": w, "real": True, "sim": sim(s, t)})
    conectadas = {a["s"] for a in aristas} | {a["t"] for a in aristas}
    sueltas = [i for i in ids if i not in conectadas]

    # --- 3: las sueltas se cuelgan del nodo más afín
    if ids:
        hub = max(ids, key=lambda i: (_f(byid[i]["n"]), i))
        for i in sueltas:
            cands = [j for j in ids if j != i and j in conectadas] or [hub]
            mejor = max(cands, key=lambda j: (round(sim(i, j), 3),
                                              1 if byid[j]["cat"] == byid[i]["cat"] else 0,
                                              byid[j]["n"], j))
            k = tuple(sorted((i, mejor)))
            if k not in pares:
                pares.add(k)
                aristas.append({"s": k[0], "t": k[1], "w": 0, "real": False,
                                "sim": round(sim(i, mejor), 3)})
            conectadas.add(i)

    # --- 4: puentes adicionales con alta similitud (enlaces débiles utiles)
    extra = []
    for i in ids:
        for j in ids:
            if i == j:
                continue
            k = tuple(sorted((i, j)))
            if k in pares:
                continue
            sm = sim(i, j)
            if sm >= SIM_FUERTE:
                extra.append((sm, k))
    extra.sort(key=lambda x: (-x[0], x[1]))
    for sm, k in extra[:MAX_PUENTES]:
        aristas.append({"s": k[0], "t": k[1], "w": 0, "real": False, "sim": round(sm, 3)})

    grado = {i: 0 for i in ids}
    for a in aristas:
        grado[a["s"]] += 1
        grado[a["t"]] += 1
    for nd in nodos:
        nd["grado"] = grado.get(nd["id"], 0)

    pos = _layout(nodos, aristas, W, H)
    for nd in nodos:
        nd["x"], nd["y"] = pos[nd["id"]]

    for a in aristas:
        if a["real"]:
            a["nivel"] = "fuerte" if a["w"] >= W_FUERTE else "media"
        else:
            a["nivel"] = "media" if a["sim"] >= SIM_FUERTE else "debil"
    return nodos, aristas


def _layout(nodos, aristas, W, H, seed=42, iters=520):
    """Fruchterman–Reingold determinista (sin dependencias) + des-solapamiento."""
    n = len(nodos)
    if n == 0:
        return {}
    if n == 1:
        return {nodos[0]["id"]: (W / 2.0, H / 2.0)}
    rng = random.Random(seed)
    pos = {}
    area = W * H
    k = 0.72 * math.sqrt(area / n)
    for i, nd in enumerate(nodos):
        ang = i * 2.399963229728653          # ángulo áureo: reparto uniforme
        rad = 0.60 * min(W, H) * math.sqrt((i + 0.5) / n)
        pos[nd["id"]] = [W / 2.0 + rad * math.cos(ang) * 1.28,
                         H / 2.0 + rad * math.sin(ang)]
    idx = {nd["id"]: i for i, nd in enumerate(nodos)}
    pesos = {}
    for a in aristas:
        i, j = idx[a["s"]], idx[a["t"]]
        key = (min(i, j), max(i, j))
        pesos[key] = max(pesos.get(key, 0.0), 3.0 if a["real"] else 1.0)
    temp = 0.28 * min(W, H)
    for it in range(iters):
        disp = [[0.0, 0.0] for _ in range(n)]
        for i in range(n):
            xi, yi = pos[nodos[i]["id"]]
            for j in range(i + 1, n):
                xj, yj = pos[nodos[j]["id"]]
                dx, dy = xi - xj, yi - yj
                d2 = dx * dx + dy * dy
                if d2 < 1e-6:
                    dx, dy, d2 = (rng.random() - 0.5) * 0.1, (rng.random() - 0.5) * 0.1, 1e-6
                d = math.sqrt(d2)
                f = (k * k) / d2
                ux, uy = dx / d, dy / d
                disp[i][0] += ux * f
                disp[i][1] += uy * f
                disp[j][0] -= ux * f
                disp[j][1] -= uy * f
        for (i, j), peso in pesos.items():
            xi, yi = pos[nodos[i]["id"]]
            xj, yj = pos[nodos[j]["id"]]
            dx, dy = xj - xi, yj - yi
            d = math.sqrt(dx * dx + dy * dy) or 0.01
            largo = k * (0.75 + 0.55 / peso)
            f = (d - largo) / d * 0.55
            disp[i][0] += dx * f
            disp[i][1] += dy * f
            disp[j][0] -= dx * f
            disp[j][1] -= dy * f
        for i in range(n):
            ni = nodos[i]
            x, y = pos[ni["id"]]
            dx, dy = disp[i]
            m = math.sqrt(dx * dx + dy * dy) or 1e-9
            paso = min(m, temp)
            x += dx / m * paso
            y += dy / m * paso
            # gravedad suave al centro: mantiene la red compacta y centrada
            x += (W / 2.0 - x) * 0.012
            y += (H / 2.0 - y) * 0.016
            pos[ni["id"]] = [x, y]
        temp = max(1.2, temp * 0.985)

    # des-solapamiento final: separación mínima según el radio de cada nodo
    pad = 26.0
    for _ in range(220):
        movi = False
        for i in range(n):
            for j in range(i + 1, n):
                a, b = nodos[i], nodos[j]
                ax, ay = pos[a["id"]]
                bx, by = pos[b["id"]]
                dx, dy = ax - bx, ay - by
                d = math.sqrt(dx * dx + dy * dy) or 0.01
                minimo = a["r"] + b["r"] + 9.0
                if d < minimo:
                    push = (minimo - d) / 2.0 + 0.6
                    ux, uy = dx / d, dy / d
                    pos[a["id"]] = [ax + ux * push, ay + uy * push]
                    pos[b["id"]] = [bx - ux * push, by - uy * push]
                    movi = True
        if not movi:
            break
    salida = {}
    for nd in nodos:
        x, y = pos[nd["id"]]
        x = min(max(x, pad + nd["r"] * 0.4), W - pad - nd["r"] * 0.4)
        y = min(max(y, pad + nd["r"] * 0.4), H - pad - nd["r"] * 0.4)
        salida[nd["id"]] = (round(x, 1), round(y, 1))
    return salida


def _red(ctx):
    nodos, aristas = red_conectada(ctx.get("tecnologias"), ctx.get("links"),
                                   ctx.get("kws"))
    filas = []
    for nd in sorted(nodos, key=lambda x: (-x["n"], x["nombre"])):
        filas.append({"clave": "n:" + str(nd["id"]), "orden": 1, "tipo": "nodo",
                      "id": str(nd["id"]), "etiqueta": nd["nombre"], "categoria": nd["cat"],
                      "valor": round(nd["n"], 2), "valor2": nd["grado"],
                      "nivel": "", "similitud": None,
                      "x": nd["x"], "y": nd["y"],
                      "color": _t(CAT_COLORES.get(nd["cat"]))})
    orden = {"fuerte": 0, "media": 1, "debil": 2}
    for a in sorted(aristas, key=lambda a: (orden.get(a["nivel"], 3), -a.get("w", 0),
                                            a["s"], a["t"])):
        filas.append({"clave": "l:%s|%s" % (a["s"], a["t"]), "orden": 0, "tipo": "enlace",
                      "id": "%s|%s" % (a["s"], a["t"]),
                      "etiqueta": "%s — %s" % (
                          nombre_tec(ctx, a["s"]), nombre_tec(ctx, a["t"])),
                      "categoria": "", "valor": float(a.get("w") or 0),
                      "valor2": None, "nivel": a["nivel"],
                      "similitud": round(_f(a.get("sim")), 3), "x": None, "y": None,
                      "color": _t(NIVEL_COLORES.get(a["nivel"]))})
    ctx["_red_nodos"] = len(nodos)
    ctx["_red_aristas"] = len(aristas)
    ctx["_red_niveles"] = {n: sum(1 for a in aristas if a["nivel"] == n)
                          for n in ("fuerte", "media", "debil")}
    return filas


def nombre_tec(ctx, tid):
    for t in ctx.get("tecnologias") or []:
        if t.get("id") == tid:
            return t.get("nombre") or tid
    return tid


# --- Tablas ---------------------------------------------------------------
def _tabla_tecnologias(ctx):
    filas = []
    for t in sorted(ctx.get("tecnologias") or [],
                    key=lambda t: (-_i(t.get("trl")), -_f(t.get("n_docs")))):
        filas.append({"clave": _texto(t.get("id")), "orden": len(filas),
                      "tec": _texto(t.get("id")), "nombre": _texto(t.get("nombre")),
                      "cat": _texto(t.get("cat_out") or t.get("cat")),
                      "docs": _f(t.get("n_docs")), "trl": _i(t.get("trl")),
                      "geoma": " | ".join(t.get("geoma_lbl") or []),
                      "capex": _texto(t.get("capex")), "opex": _texto(t.get("opex")),
                      "seg": _i(t.get("seg")), "amb": _i(t.get("amb"))})
    return filas


def _tabla_paises(ctx):
    return [{"clave": _texto(p.get("pais")), "orden": i,
             "pais": _texto(p.get("pais")), "cont": _texto(p.get("cont")),
             "gdp_pc": _f(p.get("gdp_pc")), "tech": _f(p.get("tech")),
             "seg": _f(p.get("seg")), "amb": _f(p.get("amb")),
             "mining_gdp": round(_f(p.get("mining_gdp")), 1)}
            for i, p in enumerate((ctx.get("obs") or {}).get("paises_obs") or [])]


def _tabla_corpus(ctx):
    clusters = ctx.get("clusters") or {}
    filas = []
    for i, d in enumerate(ctx.get("docs") or []):
        filas.append({"clave": "%s:%s" % (ctx.get("cid"), d.get("id")), "orden": i,
                      "n": _i(d.get("n"), i + 1), "anio": _i(d.get("anio")),
                      "titulo": _texto(d.get("titulo")),
                      "autores": _texto(d.get("autores")),
                      "fuente": _texto(d.get("fuente")), "citas": _f(d.get("citas")),
                      "doi": _texto(d.get("doi")), "enlace": _texto(d.get("enlace")),
                      "acceso": _texto(d.get("acceso")),
                      "cluster": _texto((clusters.get(str(d.get("cluster"))) or {}).get("nombre")
                                        or d.get("cluster")),
                      "tecnologias": _texto(d.get("tecnologias_txt")),
                      "keywords": _texto(d.get("tecnologias_txt"))})
    return filas


def _tabla_deliverable(ctx):
    clusters = ctx.get("clusters") or {}
    filas = []
    for i, d in enumerate(ctx.get("docs") or []):
        filas.append({"clave": "%s:%s" % (ctx.get("cid"), d.get("id")), "orden": i,
                      "n": _i(d.get("n"), i + 1), "anio": _i(d.get("anio")),
                      "titulo": _texto(d.get("titulo")),
                      "autores": _texto(d.get("autores")),
                      "fuente": _texto(d.get("fuente")), "citas": _f(d.get("citas")),
                      "acceso": _texto(d.get("acceso")),
                      "cluster": _texto((clusters.get(str(d.get("cluster"))) or {}).get("nombre")
                                        or d.get("cluster")),
                      "hallazgos": _texto(d.get("hallazgos")),
                      "limitaciones": _texto(d.get("limitaciones")),
                      "novedad": _texto(d.get("novedad"))})
    return filas


CALC = {
    "chart_anios": _anios,
    "chart_donut_cluster": _donut_cluster,
    "chart_donut_acceso": _donut_acceso,
    "chart_top5": _top5,
    "chart_radar": _radar,
    "chart_bubble": _bubble,
    "chart_series": _series,
    "chart_corr": _corr,
    "chart_igf": _igf,
    "chart_paises_pub": _paises_pub,
    "chart_red": _red,
    "chart_cat": _cat,
    "chart_tec_bar": _tec_bar,
    "tabla_tecnologias": _tabla_tecnologias,
    "tabla_paises_obs": _tabla_paises,
    "tabla_corpus": _tabla_corpus,
    "tabla_deliverable": _tabla_deliverable,
}


# ================================================================ persistencia
_TIPOS_SQL = {"int": "INTEGER", "num": "REAL", "text": "TEXT"}
TABLAS = ("base", "datos", "overrides")


def ruta(db_dir, gid):
    return os.path.join(db_dir, gid + ".db")


def _ddl_tabla(nombre, g):
    cols = ["clave TEXT PRIMARY KEY", "orden INTEGER", "extra TEXT"]
    if nombre == "overrides":
        cols.append("accion TEXT NOT NULL DEFAULT 'set'")
    for c in g["cols"]:
        cols.append('"%s" %s' % (c["n"], _TIPOS_SQL[c["tipo"]]))
    return "CREATE TABLE IF NOT EXISTS %s (\n  %s\n)" % (nombre, ",\n  ".join(cols))


def ddl(g):
    partes = [_ddl_tabla(t, g) + ";" for t in TABLAS]
    partes.append(
        "CREATE TABLE IF NOT EXISTS columnas (\n  orden INTEGER PRIMARY KEY,\n"
        "  nombre TEXT, titulo TEXT, tipo TEXT, ro INTEGER\n);")
    partes.append("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);")
    partes.append("CREATE TABLE IF NOT EXISTS fuentes "
                 "(clave TEXT PRIMARY KEY, valor TEXT);")
    return "\n".join(partes)


def existe(db_dir, gid):
    return os.path.exists(ruta(db_dir, gid))


def abrir(db_dir, gid, crear=False):
    path = ruta(db_dir, gid)
    if not crear and not os.path.exists(path):
        return None
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    cn = sqlite3.connect(path, timeout=30)
    cn.row_factory = sqlite3.Row
    cn.execute("PRAGMA journal_mode=DELETE")
    if crear:
        cn.executescript(ddl(POR_ID[gid]))
    return cn


def _coerce(v, tipo):
    if v is None:
        return None
    try:
        if tipo == "int":
            return int(float(v))
        if tipo == "num":
            f = float(v)
            return None if f != f else f
    except (TypeError, ValueError):
        return None
    return str(v)


def normaliza(g, filas):
    """Completa y tipa las filas para que la tabla tenga siempre la misma forma."""
    salida = []
    for i, f in enumerate(filas or []):
        r = {"clave": _texto(f.get("clave") or i), "orden": _i(f.get("orden"), i),
             "extra": f.get("extra") if isinstance(f.get("extra"), str)
             else (json.dumps(f["extra"], ensure_ascii=False)
                   if isinstance(f.get("extra"), (dict, list)) else None)}
        for c in g["cols"]:
            r[c["n"]] = _coerce(f.get(c["n"]), c["tipo"])
        salida.append(r)
    salida.sort(key=lambda r: (r["orden"], r["clave"]))
    return salida


def _huella(filas, cols):
    datos = [{k: r.get(k) for k in ["clave", "orden", "extra"] + [c["n"] for c in cols]}
             for r in filas]
    return hashlib.sha1(json.dumps(datos, sort_keys=True, default=str,
                                   ensure_ascii=False).encode("utf-8")).hexdigest()


def _cols_esperadas(g):
    return [(i, c["n"], c["t"], c["tipo"], 1 if c["ro"] else 0)
            for i, c in enumerate(g["cols"])]


def _columnas(cn, g):
    try:
        return [tuple(r) for r in cn.execute(
            "SELECT orden,nombre,titulo,tipo,ro FROM columnas ORDER BY orden")]
    except sqlite3.Error:
        return []


def _huella_meta(d):
    """Huella canónica de la tabla `meta` (los valores se guardan como texto)."""
    def enc(v):
        return v if isinstance(v, str) else json.dumps(v, ensure_ascii=False, default=str)
    return json.dumps({k: enc(v) for k, v in sorted((d or {}).items())},
                      sort_keys=True, ensure_ascii=False)


def _leer(cn, tabla, g):
    cols = ", ".join('"%s"' % c["n"] for c in g["cols"])
    try:
        rows = cn.execute("SELECT clave, orden, extra, %s FROM %s" % (cols, tabla)).fetchall()
    except sqlite3.Error:
        return []
    out = []
    for r in rows:
        d = {"clave": r["clave"], "orden": r["orden"], "extra": r["extra"]}
        for c in g["cols"]:
            d[c["n"]] = r[c["n"]]
        out.append(d)
    return out


def _meta(cn):
    try:
        return {r["key"]: r["value"] for r in cn.execute("SELECT key,value FROM meta")}
    except sqlite3.Error:
        return {}


def _set_meta(cn, d):
    cn.execute("DELETE FROM meta")
    cn.executemany("INSERT INTO meta(key,value) VALUES(?,?)",
                   [(k, json.dumps(v, ensure_ascii=False) if not isinstance(v, str) else v)
                    for k, v in d.items()])


def _escribir(cn, tabla, g, filas):
    cols = ["clave", "orden", "extra"] + [c["n"] for c in g["cols"]]
    cn.execute("DELETE FROM " + tabla)
    cn.executemany(
        "INSERT INTO %s(%s) VALUES(%s)" % (tabla, ",".join('"%s"' % c for c in cols),
                                           ",".join("?" * len(cols))),
        [[r.get(c) for c in cols] for r in filas])


def _aplica(filas, overrides):
    """Aplica las ediciones del usuario sobre las filas regeneradas."""
    out = {r["clave"]: dict(r) for r in filas}
    for clave, accion, fila in overrides:
        if accion == "del":
            out.pop(clave, None)
        else:
            out[clave] = dict(fila)
    return sorted(out.values(), key=lambda r: (r["orden"] if r["orden"] is not None else 0,
                                               r["clave"]))


def sync(db_dir, gid, filas, meta_extra=None, fuentes=None):
    """Sincroniza el `.db` derivado con las filas calculadas.

    Devuelve ``True`` si el fichero ha cambiado (para no tocar mtime en el
    estado estacionario) y ``False`` si ya estaba al día.
    """
    g = POR_ID[gid]
    filas = normaliza(g, filas)
    with _LOCK:
        cn = abrir(db_dir, gid, crear=True)
        try:
            base = _leer(cn, "base", g)
            datos = _leer(cn, "datos", g)
            meta = _meta(cn)
            h_actual = _huella(datos, g["cols"])
            h_base = _huella(base, g["cols"])
            override_manual = bool(meta.get("hash_datos")) and h_actual != meta["hash_datos"]

            if override_manual:
                # alguien editó `datos` a mano (sqlite3/DBeaver): se memoriza
                prev = {r["clave"]: r for r in base}
                cur = {r["clave"]: r for r in datos}
                cambios = []
                for k, r in cur.items():
                    if k not in prev or prev[k] != r:
                        cambios.append((k, "set", r))
                for k in prev:
                    if k not in cur:
                        cambios.append((k, "del", None))
                if cambios:
                    cn.executemany(
                        "INSERT OR REPLACE INTO overrides(clave,accion,orden,extra,%s) "
                        "VALUES(?,?,?,?,%s)" % (",".join('"%s"' % c["n"] for c in g["cols"]),
                                                ",".join("?" * len(g["cols"]))),
                        [[k, a, (r or {}).get("orden"), (r or {}).get("extra")] +
                         [(r or {}).get(c["n"]) for c in g["cols"]] for k, a, r in cambios])

            ov = []
            try:
                for r in cn.execute(
                        "SELECT clave, accion, orden, extra, %s FROM overrides"
                        % ", ".join('"%s"' % c["n"] for c in g["cols"])):
                    fila = {"clave": r["clave"], "orden": r["orden"], "extra": r["extra"]}
                    for c in g["cols"]:
                        fila[c["n"]] = r[c["n"]]
                    ov.append((r["clave"], r["accion"] or "set", fila))
            except sqlite3.Error:
                ov = []

            final = _aplica(filas, ov)
            h_final = _huella(final, g["cols"])
            h_fuente = _huella(filas, g["cols"])
            cambio = (h_final != h_actual or h_base != h_fuente)
            if cambio:
                _escribir(cn, "base", g, filas)
                _escribir(cn, "datos", g, final)
            if _columnas(cn, g) != _cols_esperadas(g):
                cn.execute("DELETE FROM columnas")
                cn.executemany(
                    "INSERT INTO columnas(orden,nombre,titulo,tipo,ro) VALUES(?,?,?,?,?)",
                    [(i, c["n"], c["t"], c["tipo"], 1 if c["ro"] else 0)
                     for i, c in enumerate(g["cols"])])
            meta_nuevo = {"grafico": gid, "titulo": g["titulo"], "tipo": g["tipo"],
                          "desc": g["desc"], "fuente": g["fuente"],
                          "seccion": g["seccion"],
                          "hash_fuente": h_fuente,
                          "hash_datos": h_final,
                          "filas": len(final), "filas_base": len(filas),
                          "ediciones": len(ov)}
            meta_nuevo.update(meta_extra or {})
            if _huella_meta(meta_nuevo) != _huella_meta(meta):
                _set_meta(cn, meta_nuevo)
                cambio = True
            cn.commit()
            return cambio
        finally:
            cn.close()


def leer_filas(db_dir, gid):
    g = POR_ID[gid]
    cn = abrir(db_dir, gid)
    if cn is None:
        return []
    try:
        return _leer(cn, "datos", g)
    finally:
        cn.close()


def leer_meta(db_dir, gid):
    cn = abrir(db_dir, gid)
    if cn is None:
        return {}
    try:
        return _meta(cn)
    finally:
        cn.close()


def override_set(db_dir, gid, fila):
    g = POR_ID[gid]
    fila = normaliza(g, [fila])[0]
    with _LOCK:
        cn = abrir(db_dir, gid, crear=True)
        try:
            cols = [c["n"] for c in g["cols"]]
            cn.execute("DELETE FROM overrides WHERE clave=?", (fila["clave"],))
            cn.execute(
                "INSERT INTO overrides(clave,accion,orden,extra,%s) VALUES(?,?,?,?,%s)"
                % (",".join('"%s"' % c for c in cols), ",".join("?" * len(cols))),
                [fila["clave"], "set", fila["orden"], fila["extra"]] +
                [fila[c] for c in cols])
            cn.commit()
        finally:
            cn.close()
    return fila


def override_del(db_dir, gid, clave):
    with _LOCK:
        cn = abrir(db_dir, gid, crear=True)
        try:
            cur = cn.execute("SELECT 1 FROM datos WHERE clave=?", (clave,))
            cn.execute("INSERT OR REPLACE INTO overrides(clave,accion) VALUES(?,?)",
                       (clave, "del"))
            cn.commit()
            return cur.fetchone() is not None
        finally:
            cn.close()


def reset(db_dir, gid):
    with _LOCK:
        cn = abrir(db_dir, gid, crear=True)
        try:
            cn.execute("DELETE FROM overrides")
            cn.commit()
        finally:
            cn.close()


def csv_filas(gid, filas):
    """Serializa las filas como CSV (BOM UTF-8, separador ';')."""
    import csv
    import io
    g = POR_ID[gid]
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";", lineterminator="\r\n")
    w.writerow(["clave"] + [c["t"] for c in g["cols"]] + ["extra"])
    for r in filas:
        w.writerow([r.get("clave")] + ["" if r.get(c["n"]) is None else r.get(c["n"])
                                      for c in g["cols"]] + [r.get("extra") or ""])
    return ("﻿" + buf.getvalue()).encode("utf-8")