# -*- coding: utf-8 -*-
"""
Genera las `.db` derivadas de las NUEVAS figuras del portal (z2..z8).

Reutiliza el esquema y la sincronización de `derived_graficos.py`, de modo que
cada figura queda con exactamente el mismo formato (`base`, `datos`,
`overrides`, `columnas`, `meta`, `fuentes`) que las gráficas ya existentes.

Figuras
-------
* chart_periodos        -> z2  Evolución anual por periodos + impacto acumulado
* chart_casos_pais      -> z3  Países: casos de estudio vs. colaboración
* chart_red_vos         -> z4  Red de co-ocurrencia (VOSviewer / CiteSpace)
* chart_panel_integrado -> z5  Panel integrado: anual+cumulado y Pareto
* chart_ronda1          -> z6  Ronda 1: etapas operativas -> tecnologías (sunburst)
* chart_ronda2          -> z7  Ronda 2: alluvial de 5 ejes (viabilidad, impacto…)
* chart_ronda3          -> z8  Ronda 3: mapa de calor 7 tecnologías × 7 criterios

Uso (desde `resultados/frame/server` o con la carpeta en el PYTHONPATH):

    python derived_nuevos.py

Escribe en `resultados/frame/db/`.
"""
import csv
import math
import os
import re
import sys
import unicodedata
from collections import Counter, defaultdict

import pandas as pd

AQUI = os.path.dirname(os.path.abspath(__file__))
FRAME = os.path.dirname(AQUI)                # .../resultados/frame
RESULT = os.path.dirname(FRAME)              # .../resultados
RAIZ = os.path.dirname(RESULT)               # .../revision_03092026
DB_DIR = os.path.join(FRAME, "db")

sys.path.insert(0, AQUI)
import derived_graficos as dg  # noqa: E402

C = dg._c

# ------------------------------------------------------------------ paleta
OI = {
    "azul": "#0072B2", "naranja": "#E69F00", "verde": "#009E73", "rojo": "#D55E00",
    "morado": "#CC79A7", "celeste": "#56B4E9", "amarillo": "#F0E442",
    "negro": "#1A1A1A", "gris": "#7F7F7F", "grisclaro": "#BFBFBF",
}
PERIODO_COLOR = {"Pre-corte": OI["grisclaro"], "2006-11": OI["celeste"],
                 "2012-19": OI["verde"], "2020-26": OI["rojo"]}
VOS_COLOR = {"0": "#70b4f6", "1": "#ff6f6e", "2": "#68d55e", "3": "#dedd47"}
VOS_NOMBRE = {
    "0": "MAPE, relleno y sostenibilidad",
    "1": "Fragmentación, geomecánica y estabilidad",
    "2": "Mina inteligente, carbón y trigeneración",
    "3": "Equipos, seguridad y ventilación",
}

# ---------------------------------------------------------------- nuevas specs
NUEVAS = [
    dict(id="chart_periodos", tipo="grafica", seccion="Inicio",
         titulo="Producción anual por periodos e impacto acumulado",
         desc="Barras por año coloreadas por periodo (pre-corte y P1–P3) más la curva "
              "de citas acumuladas (%). Corresponde a la Figura 2 del artículo.",
         fuente="scopusAnalisisLimpio.csv (n=269)",
         cols=[C("anio", "Año", "int"), C("periodo", "Periodo"),
               C("publicaciones", "Documentos", "num"), C("citas", "Citas", "num"),
               C("citas_acum", "Citas acumuladas", "num"),
               C("pct_acum", "% impacto acumulado", "num"), C("color", "Color")]),
    dict(id="chart_casos_pais", tipo="grafica", seccion="Observatorio",
         titulo="Casos de estudio vs. índice de colaboración por país",
         desc="Burbujas (Figura 12): eje X = volumen de artículos que son casos de "
              "estudio; eje Y = índice de colaboración (países por artículo); tamaño = "
              "producción total del país.",
         fuente="scopusAnalisisLimpio.csv (n=269)",
         cols=[C("pais", "País"), C("etiqueta", "País"),
               C("produccion", "Producción", "num"),
               C("casos_estudio", "Casos de estudio", "num"),
               C("idx_colaboracion", "Índice de colaboración", "num"),
               C("pct_casos", "% de su producción", "num"), C("color", "Color")]),
    dict(id="chart_red_vos", tipo="grafica", seccion="Red",
         titulo="Red de co-ocurrencia de términos (VOSviewer)",
         desc="Grafo de co-ocurrencia de palabras clave: nodos dimensionados por "
              "frecuencia y coloreados por comunidad temática; enlaces ponderados.",
         fuente="resultados_moduloq/{nodos,aristas}_test2_svg.csv",
         cols=[C("tipo", "Tipo"), C("id", "ID"), C("etiqueta", "Etiqueta"),
               C("cluster", "Comunidad"), C("cluster_nombre", "Tema"),
               C("frecuencia", "Frecuencia", "num"), C("grado", "Grado", "num"),
               C("origen", "Origen"), C("destino", "Destino"),
               C("peso", "Peso", "num"), C("x", "x", "num"), C("y", "y", "num"),
               C("color", "Color")]),
    dict(id="chart_panel_integrado", tipo="grafica", seccion="Inicio",
         titulo="Panel integrado: evolución anual y concentración de fuentes",
         desc="Panel doble (Figura 10): arriba producción anual con citas acumuladas "
              "(n=124, 2008–2026); abajo Pareto de las principales fuentes.",
         fuente="thirdPass_124.csv (n=124)",
         cols=[C("bloque", "Bloque"), C("x", "Posición", "int"),
               C("etiqueta", "Etiqueta"), C("valor", "Valor", "num"),
               C("acum", "Acumulado", "num"), C("pct_acum", "% acumulado", "num"),
               C("color", "Color")]),
    dict(id="chart_ronda1", tipo="grafica", seccion="Matriz",
         titulo="Ronda 1 · Etapas operativas y tecnologías identificadas",
         desc="Sunburst: 5 etapas del proceso minero y las tecnologías de integración "
              "asociadas (Figura de la ronda 1).",
         fuente="ronda1.csv",
         cols=[C("id", "ID"), C("etiqueta", "Etiqueta"), C("padre", "Padre"),
               C("valor", "Valor", "num"), C("nivel", "Nivel", "int"),
               C("color", "Color")]),
    dict(id="chart_ronda2", tipo="grafica", seccion="Matriz",
         titulo="Ronda 2 · Alluvial de viabilidad, impacto, KPI y riesgo",
         desc="Diagrama de flujo de 5 ejes (tecnología → barreras → viabilidad → "
              "impacto financiero → KPI → riesgo) para las 7 tecnologías evaluadas.",
         fuente="ronda2.csv",
         cols=[C("tecnologia", "Tecnología"), C("barreras", "Barreras técnico-económicas"),
               C("viabilidad", "Viabilidad"), C("impacto", "Impacto financiero"),
               C("kpi", "KPI"), C("riesgo", "Riesgos"), C("color", "Color")]),
    dict(id="chart_ronda3", tipo="grafica", seccion="Matriz",
         titulo="Ronda 3 · Priorización multicriterio de tecnologías",
         desc="Mapa de calor 7 tecnologías × 7 criterios (promedio, VT, SSO, IP, SA, "
              "AE, FI) en escala 1–5.",
         fuente="ronda3.csv",
         cols=[C("tecnologia", "Tecnología"), C("criterio", "Criterio"),
               C("valor", "Valor (1–5)", "num"),
               C("orden_tec", "Orden tecnología", "int"),
               C("orden_crit", "Orden criterio", "int"), C("color", "Color")]),
]


# ------------------------------------------------------------------ utilidades
def _norm(s):
    s = unicodedata.normalize("NFKD", str(s or ""))
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", s).strip().lower()


BASES = (RESULT, RAIZ)


def _leer_csv(nombre, sep=";", encoding="utf-8-sig"):
    for base in BASES:
        for enc in (encoding, "latin-1"):
            try:
                return pd.read_csv(os.path.join(base, nombre), sep=sep, encoding=enc)
            except (UnicodeDecodeError, FileNotFoundError):
                continue
    raise FileNotFoundError(nombre)


# ================================================================ z2 · periodos
PERIODOS = [(2006, 2011, "2006-11"), (2012, 2019, "2012-19"), (2020, 2026, "2020-26")]
ANIO_CORTE = 2006


def datos_periodos():
    df = _leer_csv("scopusAnalisisLimpio.csv", sep=",")
    df["anio"] = df["anio"].astype(int)
    df["citas"] = pd.to_numeric(df["citas"], errors="coerce").fillna(0)

    anios = list(range(int(df["anio"].min()), int(df["anio"].max()) + 1))
    conteo = df.groupby("anio").size().reindex(anios, fill_value=0)
    citas = df.groupby("anio")["citas"].sum().reindex(anios, fill_value=0)
    total_citas = float(citas.sum()) or 1.0
    acum = citas.cumsum() / total_citas * 100.0

    filas = []
    for i, a in enumerate(anios):
        if a < ANIO_CORTE:
            per = "Pre-corte"
        elif a <= 2011:
            per = "2006-11"
        elif a <= 2019:
            per = "2012-19"
        else:
            per = "2020-26"
        filas.append({"clave": str(a), "orden": i, "anio": int(a), "periodo": per,
                      "publicaciones": float(conteo.loc[a]), "citas": float(citas.loc[a]),
                      "citas_acum": float(acum.loc[a]), "pct_acum": round(float(acum.loc[a]), 2),
                      "color": PERIODO_COLOR[per]})
    pico = max(filas, key=lambda r: r["publicaciones"])
    i80 = next((r for r in filas if r["pct_acum"] >= 80), None)
    dentro = [r for r in filas if r["anio"] >= ANIO_CORTE]
    n_fuera = int(conteo[[a for a in anios if a < ANIO_CORTE]].sum())
    meta = {"n_docs": int(len(df)), "n_fuera": n_fuera, "citas_totales": int(total_citas),
            "pico_anio": pico["anio"], "pico_n": int(pico["publicaciones"]),
            "anio80": i80["anio"] if i80 else None,
            "media_anual": round(sum(r["publicaciones"] for r in dentro) / max(1, len(dentro)), 2),
            "periodos": ["2006-11", "2012-19", "2020-26"]}
    return filas, meta


# ============================================================ z3 · casos/país
CUES_SITIO = (r"(?i:mine|mina|mines|minas|deposit|deposito|deposits|depositos|"
              r"basin|cuenca|basins|cuencas|quarry|cantera|quarries|pit|pits|"
              r"combine|combines|coalfield|ore\s*body|lode|concession|"
              r"mine\s*site|open[- ]?pit|underground\s+mine)")
RX_SITIO_1 = re.compile(r"\b([A-Z][A-Za-z\u2019'\-]*(?:[\s\-][A-Z][A-Za-z\u2019'\-]*){0,3})\s+"
                        r"(?:[\w\u2019'\-]+\s+){0,3}?" + CUES_SITIO + r"\b")
RX_SITIO_2 = re.compile(CUES_SITIO + r"\s+(?i:of|at|in|from|de|del)\s+"
                        r"([A-Z][A-Za-z\u2019'\-]*(?:[\s\-][A-Z][A-Za-z\u2019'\-]*){0,2})\b")
RX_PALABRA = re.compile(r"[A-Za-z\u2019']+")
NO_SITIO = set(("the a an in on of for to at application applications development "
                "developments virtual study analysis current new improvement improving "
                "method methods review case field underground open coal iron gold copper "
                "lead zinc deep surface bottom top sub super primary preliminary "
                "experimental industrial small complex structure russian russia chinese "
                "china indian india australian australia vietnam vietnamese kazakh "
                "kazakhstan ukrainian ukraine polish poland south north east west korean "
                "brazilian brazil chilean chile swedish sweden spanish spain mongolian "
                "iranian canada canadian africa america mexico mexican colombia peru "
                "peruvian mongolia turkey turkish japan japanese indonesia egyptian egypt "
                "norway finland morocco malaysia thailand ghana guinea suriname armenia "
                "armenian georgia kyrgyz azerbaijan serbia mongol yakutia komi data model "
                "modeling machine intelligence intelligent internet wireless wired "
                "multimedia video real time energy green eco environment "
                "environmental").split())
NO_COLA = set(("signals signal faces method process theory structure safety development "
               "protection analysis approach framework system technique techniques "
               "worker mining coal mine mines deposits ore technologies technology").split())
PAIS_COLOR = [OI["rojo"], OI["naranja"], "#1f77b4", "#2ca02c", "#9467bd", "#8c564b",
              "#e377c2", "#17becf", "#7f7f7f", "#bcbd22", "#aec7e8", "#ffbb78",
              "#98df8a", "#ff9896", "#c5b0d5"]


def datos_casos_pais():
    df = _leer_csv("scopusAnalisisLimpio.csv", sep=",")
    for col in ("titulo", "resumen", "fuente", "autores", "afiliaciones", "paises"):
        df[col] = df[col].fillna("").astype(str)
    tit, res, fue, aut, afi = df["titulo"], df["resumen"], df["fuente"], df["autores"], df["afiliaciones"]

    pais_docs = df["paises"].str.split("; ").explode().str.strip()
    pais_docs = pais_docs[pais_docs.notna() & (pais_docs != "No especificado")]
    freq = pais_docs.value_counts().head(15)

    df_min = Counter()
    for doc in (tit + " " + res).str.lower():
        df_min.update(set(RX_PALABRA.findall(doc)))

    def nombres_sitio(titulo):
        cand = set(RX_SITIO_1.findall(titulo)) | set(RX_SITIO_2.findall(titulo))
        validos = set()
        for nombre in cand:
            toks = RX_PALABRA.findall(nombre)
            if not toks or len(nombre) <= 3 or nombre.isupper():
                continue
            if toks[0].lower() in NO_SITIO or toks[-1].lower() in NO_COLA:
                continue
            if df_min[toks[0].lower()] > 2:
                continue
            validos.add(nombre)
        return validos

    caso_titulo = tit.map(lambda t: bool(nombres_sitio(t)))
    caso_abs = res.str.contains(r"implement\w*", case=False, regex=True)
    caso_fuente = fue.str.contains(r"case\s+stud|caso[s]?\s+de\s+estudio|estudio[s]?\s+de\s+caso",
                                   case=False, regex=True)
    es_caso = (caso_titulo | caso_abs | caso_fuente)
    npaises = df["paises"].apply(
        lambda s: len({p.strip() for p in str(s).split(";")
                       if p.strip() and p.strip() != "No especificado"}))

    filas = []
    for i, p in enumerate(freq.index):
        docs_p = df[df["paises"].apply(
            lambda s, p=p: p in {x.strip() for x in str(s).split(";") if x.strip()})]
        n_prod = len(docs_p)
        n_casos = int(es_caso.loc[docs_p.index].sum())
        ic = round(float(npaises.loc[docs_p.index].mean()), 3) if n_prod else 0.0
        filas.append({"clave": p, "orden": i, "pais": p, "etiqueta": p,
                      "produccion": float(n_prod), "casos_estudio": float(n_casos),
                      "idx_colaboracion": ic,
                      "pct_casos": round(n_casos / n_prod * 100, 1) if n_prod else 0.0,
                      "color": PAIS_COLOR[i % len(PAIS_COLOR)]})
    x = [r["casos_estudio"] for r in filas]
    meta = {"n_docs": int(len(df)), "n_casos": int(es_caso.sum()),
            "pct_casos": round(float(es_caso.mean()) * 100, 1),
            "ic_medio": round(float(npaises.mean()), 3),
            "mediana_casos": float(pd.Series(x).median()),
            "n_paises_total": int(pais_docs.nunique())}
    return filas, meta


# ================================================================ z4 · red VOS
def datos_red_vos():
    nodos = []
    with open(os.path.join(RAIZ, "resultados_moduloq", "nodos_test2_svg.csv"),
              encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh):
            attrs = {k.strip(): v.strip()
                     for k, v in (p.split("=", 1) for p in r["atributos"].split(";") if "=" in p)}
            cl = attrs.get("cluster_citespace", "").strip()
            nodos.append({
                "id": r["nodo"].strip(),
                "grado": float(r["grado"]),
                "x": float(attrs.get("x", 0)), "y": float(attrs.get("y", 0)),
                "frecuencia": float(attrs.get("frecuencia", 0)),
                "cluster": cl,
                "cluster_nombre": VOS_NOMBRE.get(cl, "Comunidad " + cl),
                "color": attrs.get("color", VOS_COLOR.get(cl, "#888888")).strip(),
            })
    index = {n["id"]: i for i, n in enumerate(nodos)}
    filas = []
    for i, n in enumerate(nodos):
        filas.append({"clave": "n:" + n["id"], "orden": i, "tipo": "nodo",
                      "id": n["id"], "etiqueta": n["id"], "cluster": n["cluster"],
                      "cluster_nombre": n["cluster_nombre"], "frecuencia": n["frecuencia"],
                      "grado": n["grado"], "origen": "", "destino": "", "peso": 0.0,
                      "x": n["x"], "y": -n["y"], "color": n["color"]})
    n_aristas = 0
    with open(os.path.join(RAIZ, "resultados_moduloq", "aristas_test2_svg.csv"),
              encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh):
            o, d = r["origen"].strip(), r["destino"].strip()
            if o not in index or d not in index:
                continue
            n_aristas += 1
            pasos = 12
            a, b = nodos[index[o]], nodos[index[d]]
            for k in range(pasos):
                t = k / (pasos - 1.0)
                filas.append({"clave": "e:%s-%s:%d" % (o, d, k), "orden": 1000 + n_aristas * pasos + k,
                              "tipo": "enlace", "id": "%s-%s" % (o, d), "etiqueta": "",
                              "cluster": "", "cluster_nombre": "", "frecuencia": 0.0,
                              "grado": 0.0, "origen": o, "destino": d,
                              "peso": float(r["peso"]),
                              "x": a["x"] + (b["x"] - a["x"]) * t,
                              "y": -(a["y"] + (b["y"] - a["y"]) * t),
                              "color": "#c9d3da"})
    metas = {"n_nodos": len(nodos), "n_enlaces": n_aristas,
             "clusters": [{"id": c, "nombre": VOS_NOMBRE.get(c, c), "color": VOS_COLOR.get(c, "#888"),
                           "n": sum(1 for n in nodos if n["cluster"] == c)}
                          for c in sorted({n["cluster"] for n in nodos})]}
    return filas, metas


# ======================================================== z5 · panel integrado
FUENTES_TOP = 12


def datos_panel():
    df = _leer_csv("thirdPass_124.csv", sep=";")
    df["anio"] = pd.to_numeric(df["anio"], errors="coerce").astype("Int64")
    df["citas"] = pd.to_numeric(df["citas"], errors="coerce").fillna(0)
    df = df[df["anio"].notna()]
    df = df[df["anio"] >= ANIO_CORTE]

    anios = list(range(int(df["anio"].min()), int(df["anio"].max()) + 1))
    conteo = df.groupby("anio").size().reindex(anios, fill_value=0)
    citas = df.groupby("anio")["citas"].sum().reindex(anios, fill_value=0)
    acum = citas.cumsum()
    total_citas = float(citas.sum()) or 1.0

    filas = []
    for i, a in enumerate(anios):
        filas.append({"clave": "a:%d" % a, "orden": i, "bloque": "anual", "x": int(a),
                      "etiqueta": str(a), "valor": float(conteo.loc[a]),
                      "acum": float(acum.loc[a]), "pct_acum": round(float(acum.loc[a]) / total_citas * 100, 2),
                      "color": OI["azul"]})
    top = df["fuente"].fillna("").astype(str).value_counts().head(FUENTES_TOP)
    total_f = float(top.sum()) or 1.0
    running = 0.0
    k80 = None
    for i, (f, v) in enumerate(top.items()):
        running += float(v)
        pct = running / total_f * 100
        if k80 is None and pct >= 80:
            k80 = i
        filas.append({"clave": "f:%d" % i, "orden": 100 + i, "bloque": "pareto", "x": i,
                      "etiqueta": f, "valor": float(v), "acum": running,
                      "pct_acum": round(pct, 2),
                      "color": OI["naranja"] if i == 0 else OI["azul"]})
    meta = {"n_docs": int(len(df)), "anio_min": int(min(anios)), "anio_max": int(max(anios)),
            "citas_totales": int(total_citas), "n_fuentes_mostradas": int(len(top)),
            "fuente_lider": top.index[0] if len(top) else "",
            "k80": k80, "top_fuentes": [str(f) for f in top.index]}
    return filas, meta


# ============================================================ z6 · ronda 1
def datos_ronda1():
    etapas, filas = [], []
    orden = 0
    with open(os.path.join(RESULT, "ronda1.csv"), encoding="utf-8-sig") as fh:
        reader = csv.reader(fh, delimiter=";")
        next(reader, None)
        etapa_actual = None
        for row in reader:
            if len(row) < 2:
                continue
            e, tec = row[0].strip(), row[1].strip()
            if e:
                etapa_actual = e
                etapas.append(e)
            if tec and etapa_actual is not None:
                filas.append(("tec", tec, etapa_actual))
    total_etapas = len(etapas)
    total_tec = len(filas)
    out = []
    for i, e in enumerate(etapas):
        out.append({"clave": "e:%d" % i, "orden": i, "id": "e:%d" % i, "etiqueta": e,
                    "padre": "", "valor": 0.0, "nivel": 0,
                    "color": dg.CLUSTER_COLORES[i % len(dg.CLUSTER_COLORES)]})
    for i, (_, tec, etapa) in enumerate(filas):
        idx = etapas.index(etapa)
        out.append({"clave": "t:%d" % i, "orden": 100 + i, "id": "t:%d" % i, "etiqueta": tec,
                    "padre": "e:%d" % idx, "valor": 1.0, "nivel": 1,
                    "color": dg.CLUSTER_COLORES[idx % len(dg.CLUSTER_COLORES)]})
    meta = {"n_etapas": total_etapas, "n_tec": total_tec}
    return out, meta


# ============================================================ z7 · ronda 2
R2_MAP = {
    "sensor networks": ("Viable", "Mejor balance", "Gases y accidentes", "Resistencia al cambio"),
    "teleoperation": ("Viable", "Favorable", "Avance y costo", "Latencia e inercia"),
    "gas catalysts": ("Viable", "Buen balance", "Gases y accidentes", "Mantenimiento"),
    "pre-concentration": ("Viable", "Mejor balance", "Dilución y energía", "Complejidad"),
    "paste backfill": ("Alta prioridad", "Inversión inicial", "Estabilidad y relaves", "Mezclas"),
    "thermal spalling": ("No viable", "Inversión alta", "Costo y energía", "Falta de escala"),
    "hydrofracturing": ("No viable", "Inversión alta", "Costo y sobrefractura", "Inestabilidad"),
}


def datos_ronda2():
    filas = []
    with open(os.path.join(RESULT, "ronda2.csv"), encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh, delimiter=";")
        for i, r in enumerate(reader):
            tec = (r["Technologies"] or "").strip()
            clave_norm = _norm(tec)
            tag = next((k for k in R2_MAP if k in clave_norm), None)
            viab, imp, kpi, ries = R2_MAP.get(tag, ("Viable", "Favorable", "—", "—"))
            filas.append({"clave": "r2:%d" % i, "orden": i, "tecnologia": tec,
                          "barreras": (r["Technical and economic barriers"] or "").strip(),
                          "viabilidad": viab, "impacto": imp, "kpi": kpi, "riesgo": ries,
                          "color": dg.CLUSTER_COLORES[i % len(dg.CLUSTER_COLORES)]})
    meta = {"n_tec": len(filas), "n_ejes": 5,
            "ejes": ["Tecnología", "Viabilidad", "Impacto", "KPI", "Riesgo"]}
    return filas, meta


# ============================================================ z8 · ronda 3
CRIT_COLOR = ["#0b4f6c", "#1b7a92", "#3fa5b5", "#79c7c6", "#b7e0cf", "#e3eec3", "#f6f1b0"]


def datos_ronda3():
    criterios = []
    filas = []
    with open(os.path.join(RESULT, "ronda3.csv"), encoding="utf-8-sig") as fh:
        reader = csv.reader(fh, delimiter=";")
        header = next(reader)
        criterios = [h.strip() for h in header[1:]]
        for i, row in enumerate(reader):
            if not row:
                continue
            tec = row[0].strip()
            for j, raw in enumerate(row[1:]):
                val = float(raw.replace(",", ".")) if raw.strip() else 0.0
                filas.append({"clave": "r3:%d:%d" % (i, j), "orden": i * len(criterios) + j,
                              "tecnologia": tec, "criterio": criterios[j], "valor": val,
                              "orden_tec": i, "orden_crit": j,
                              "color": CRIT_COLOR[min(j, len(CRIT_COLOR) - 1)]})
    meta = {"n_tec": len({r["tecnologia"] for r in filas}), "n_crit": len(criterios),
            "criterios": criterios, "escala": [1, 5],
            "media": round(sum(r["valor"] for r in filas) / max(1, len(filas)), 3)}
    return filas, meta


CALCS = {
    "chart_periodos": datos_periodos,
    "chart_casos_pais": datos_casos_pais,
    "chart_red_vos": datos_red_vos,
    "chart_panel_integrado": datos_panel,
    "chart_ronda1": datos_ronda1,
    "chart_ronda2": datos_ronda2,
    "chart_ronda3": datos_ronda3,
}


def main():
    dg.GRAFIOS.extend(NUEVAS)
    dg.POR_ID = {g["id"]: g for g in dg.GRAFIOS}
    os.makedirs(DB_DIR, exist_ok=True)
    for spec in NUEVAS:
        gid = spec["id"]
        filas, meta = CALCS[gid]()
        fuente = spec["fuente"]
        dg.sync(DB_DIR, gid, filas, meta_extra=meta,
                fuentes=[("origen", fuente), ("figura", gid)])
        print("OK  %-22s %5d filas  ->  %s.db" % (gid, len(filas), gid))


if __name__ == "__main__":
    main()
