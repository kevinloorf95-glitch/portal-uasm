# -*- coding: utf-8 -*-
"""
Capa de acceso a las bases de datos `.db` del Portal MAPE.

Regla de oro: **el estado del portal se calcula siempre leyendo los `.db`**.
Hay una única caché (el *snapshot* de arranque) que se invalida sola en
cuanto cambia el tamaño o la fecha de modificación de cualquier `.db`, de modo
que editar un fichero `.db` por cualquier medio (sqlite3, DBeaver, el editor
del portal…) se refleja en la siguiente petición sin reiniciar nada.
"""
import contextlib
import json
import os
import sqlite3
import threading
import time

import derived as D
import derived_graficos as G
import schema as S

GEOMA_LBL_DEFAULT = {
    "todas": "Todas las geometrías",
    "vetas angostas": "Vetas angostas (≤ 2–3 m)",
    "mantos y capas": "Mantos y capas",
    "cuerpos masivos": "Cuerpos masivos / masivos",
}

DOC_COLS = ["id", "n", "anio", "titulo", "autores", "fuente", "citas", "doi", "enlace",
            "acceso", "acceso_raw", "perfil_acceso", "eid", "cluster",
            "hallazgos", "limitaciones", "novedad", "texto", "tecnologias_txt"]

DOC_EDITABLES = ["n", "anio", "titulo", "autores", "fuente", "citas", "doi", "enlace",
                 "acceso", "acceso_raw", "perfil_acceso", "eid", "cluster",
                 "hallazgos", "limitaciones", "novedad"]

TEC_EDITABLES = ["nombre", "cat", "trl", "geoma", "capex", "opex", "seg", "amb", "n_docs"]


class DbError(Exception):
    pass


def _meta_publica(meta):
    """La tabla `meta` guarda texto; aquí se reconstruye el tipo original."""
    out = {}
    for k, v in (meta or {}).items():
        if isinstance(v, str) and v[:1] in "[{":
            try:
                out[k] = json.loads(v)
                continue
            except ValueError:
                pass
        if isinstance(v, str) and v.lstrip("-").isdigit():
            out[k] = int(v)
        else:
            out[k] = v
    return out


class Store:
    def __init__(self, db_dir=None):
        self.db_dir = str(db_dir or S.DB_DIR)
        self._lock = threading.RLock()
        self._sig = None
        self._cache = {}
        os.makedirs(self.db_dir, exist_ok=True)

    # ------------------------------------------------------------ conexión / firma
    def firma(self):
        """Huella de los .db **de origen**: (nombre, mtime_ns, tamaño) de cada fichero.

        Las bases derivadas (una por gráfica/tabla) quedan fuera a propósito: las
        regenera el propio servidor y, si contaran, cada escritura invalidaría
        la caché y el navegador se recargaría en bucle.
        """
        out = []
        try:
            nombres = sorted(os.listdir(self.db_dir))
        except OSError:
            return ()
        derived = set(S.DERIVED_DBS)
        for n in nombres:
            if not n.endswith(".db") or n in derived:
                continue
            p = os.path.join(self.db_dir, n)
            try:
                st = os.stat(p)
            except OSError:
                continue
            out.append((n, st.st_mtime_ns, st.st_size))
        return tuple(out)

    @property
    def signature(self):
        """Firma actual; si cambia respecto a la anterior se vacía la caché."""
        sig = self.firma()
        with self._lock:
            if sig != self._sig:
                self._sig = sig
                self._cache.clear()
            return sig

    def version(self):
        """Token corto para ETag / recarga del navegador."""
        h = 0
        for n, mt, sz in self.signature:
            for c in n:
                h = (h * 31 + ord(c)) & 0xFFFFFFFF
            h = (h * 31 + (mt & 0xFFFFFFFF)) & 0xFFFFFFFF
            h = (h * 31 + (sz & 0xFFFFFFFF)) & 0xFFFFFFFF
        return "%08x-%d" % (h, len(self.signature))

    @contextlib.contextmanager
    def con(self, name, write=False):
        p = os.path.join(self.db_dir, name)
        if not os.path.exists(p):
            raise DbError("No existe la base de datos %s (ejecuta server/build_db.py)" % name)
        cn = sqlite3.connect(p, timeout=30)
        cn.row_factory = sqlite3.Row
        try:
            if write:
                with self._lock:
                    cn.execute("PRAGMA foreign_keys=ON")
                    yield cn
                    cn.commit()
            else:
                yield cn
        except sqlite3.Error as e:
            with contextlib.suppress(Exception):
                cn.rollback()
            raise DbError(str(e))
        finally:
            cn.close()

    def existe(self, name):
        return os.path.exists(os.path.join(self.db_dir, name))

    def migrar(self):
        """Añade columnas nuevas a .db existentes sin perder datos."""
        anadidas = []
        for cid in S.CORPUS_ORDER:
            name = self.db(cid)
            if not self.existe(name):
                continue
            with self.con(name, write=True) as cn:
                cols = {r["name"] for r in cn.execute("PRAGMA table_info(docs)")}
                for c, tipo in (("tecnologias_txt", "TEXT"), ("texto", "TEXT"),
                                ("acceso_raw", "TEXT"), ("perfil_acceso", "TEXT")):
                    if c not in cols:
                        cn.execute("ALTER TABLE docs ADD COLUMN %s %s" % (c, tipo))
                        anadidas.append("%s.docs.%s" % (name, c))
                ccols = {r["name"] for r in cn.execute("PRAGMA table_info(clusters)")}
                for c, tipo, dflt in (("kws_all", "TEXT", "'[]'"), ("modo", "TEXT", "'hits'")):
                    if c not in ccols:
                        cn.execute("ALTER TABLE clusters ADD COLUMN %s %s DEFAULT %s"
                                   % (c, tipo, dflt))
                        anadidas.append("%s.clusters.%s" % (name, c))
        return anadidas

    # ------------------------------------------------------------ helpers
    @staticmethod
    def _meta(cn):
        out = {}
        for r in cn.execute("SELECT key,value FROM meta"):
            v = r["value"]
            try:
                out[r["key"]] = json.loads(v)
            except (TypeError, ValueError):
                out[r["key"]] = v
        return out

    @staticmethod
    def _clusters(cn):
        out = {}
        for r in cn.execute("SELECT * FROM clusters ORDER BY id"):
            out[str(r["id"])] = {
                "id": r["id"], "nombre": r["nombre"], "temas": r["temas"],
                "kws": D.jloads(r["kws"]), "kws_all": D.jloads(r["kws_all"]),
                "modo": r["modo"] or "hits",
            }
        return out

    def _cluster_list(self, cn):
        return [self._clusters(cn)[k] for k in sorted(self._clusters(cn), key=int)]

    # ------------------------------------------------------------ documentos
    @staticmethod
    def _doc_row(r, tecs):
        d = {k: r[k] for k in r.keys() if k != "texto"}
        d["tecs"] = tecs.get(r["id"], [])
        d["cluster"] = r["cluster"]
        return d

    def _tecs_map(self, cn):
        out = {}
        for r in cn.execute("SELECT doc_id,tec_id FROM doc_tecs"):
            out.setdefault(r["doc_id"], []).append(r["tec_id"])
        return out

    def doc(self, cid, doc_id):
        name = self.db(cid)
        with self.con(name) as cn:
            r = cn.execute("SELECT * FROM docs WHERE id=?", (doc_id,)).fetchone()
            if not r:
                raise DbError("Documento %s no encontrado en %s" % (doc_id, name))
            return self._doc_row(r, self._tecs_map(cn))

    def docs(self, cid, search="", cluster="", tec="", acceso="", y0=None, y1=None,
             page=1, per=25, orden="citas", con_texto=False):
        """Consulta filtrada + paginada sobre `corpus_*.db`."""
        name = self.db(cid)
        where, args = [], []
        if search:
            q = "%" + search.strip().lower() + "%"
            where.append("(lower(titulo) LIKE ? OR lower(autores) LIKE ? OR lower(fuente) LIKE ?"
                         " OR lower(doi) LIKE ? OR lower(COALESCE(tecnologias_txt,'')) LIKE ?)")
            args += [q, q, q, q, q]
        if cluster != "" and cluster is not None:
            where.append("cluster=?")
            args.append(int(cluster))
        if tec:
            where.append("id IN (SELECT doc_id FROM doc_tecs WHERE tec_id=?)")
            args.append(tec)
        if acceso:
            where.append("acceso=?")
            args.append(acceso)
        if y0 not in (None, ""):
            where.append("anio IS NOT NULL AND anio>=?")
            args.append(int(y0))
        if y1 not in (None, ""):
            where.append("anio IS NOT NULL AND anio<=?")
            args.append(int(y1))
        sql_where = (" WHERE " + " AND ".join(where)) if where else ""
        orden_sql = {"citas": "citas DESC, anio DESC",
                     "anio": "anio DESC, citas DESC",
                     "titulo": "titulo COLLATE NOCASE ASC"}.get(orden, "citas DESC")
        per = max(1, min(int(per or 25), 5000))
        page = max(1, int(page or 1))
        cols = "*" if con_texto else ", ".join(c for c in DOC_COLS if c != "texto")
        with self.con(name) as cn:
            total = cn.execute("SELECT COUNT(*) FROM docs" + sql_where, args).fetchone()[0]
            rows = cn.execute("SELECT " + cols + " FROM docs" + sql_where +
                              " ORDER BY " + orden_sql + " LIMIT ? OFFSET ?",
                              args + [per, (page - 1) * per]).fetchall()
            tecs = self._tecs_map(cn)
            docs = [self._doc_row(r, tecs) for r in rows]
        pages = max(1, -(-total // per))
        return {"total": total, "page": min(page, pages), "per": per, "pages": pages,
                "docs": docs}

    def top_citados(self, cid, n=5):
        r = self.docs(cid, per=n, orden="citas")
        return r["docs"]

    def meta_corpus(self, cid):
        """Metadatos **vivos**: se calculan sobre la tabla `docs` del `.db`."""
        self.signature
        name = self.db(cid)
        with self.con(name) as cn:
            meta = self._meta(cn)
            clusters = self._clusters(cn)
            agg = cn.execute(
                "SELECT COUNT(*) n, MIN(anio) y0, MAX(anio) y1, "
                "       COALESCE(SUM(citas),0) c FROM docs").fetchone()
            acc = {r["acceso"]: r["n"] for r in cn.execute(
                "SELECT acceso, COUNT(*) n FROM docs GROUP BY acceso")}
            cc = {int(r["cluster"]): r["n"] for r in cn.execute(
                "SELECT cluster, COUNT(*) n FROM docs WHERE cluster IS NOT NULL GROUP BY cluster")}
            n_tecs = cn.execute("SELECT COUNT(DISTINCT tec_id) n FROM doc_tecs").fetchone()[0]
            fuente = cn.execute("SELECT valor FROM fuentes WHERE clave='csv'").fetchone()
        n = agg["n"] or 0
        y0 = agg["y0"] if agg["y0"] is not None else (meta.get("rango") or [None, None])[0]
        y1 = agg["y1"] if agg["y1"] is not None else (meta.get("rango") or [None, None])[1]
        libre = int(acc.get(D.ACCESO_LIBRE, 0))
        return {
            "id": cid,
            "nombre": meta.get("nombre", S.CORPUS_LABELS.get(cid, cid)),
            "csv": meta.get("csv", S.CORPUS_CSV.get(cid, cid)),
            "db": name,
            "n_docs": n,
            "rango": [y0, y1],
            "citas_totales": int(agg["c"] or 0),
            "oa": libre,
            "oa_pct": round(100 * libre / n, 1) if n else 0.0,
            "n_tecs": int(n_tecs or 0),
            "n_clusters": len(clusters),
            "cluster_counts": {str(k): v for k, v in sorted(cc.items())},
            "acceso": {"libre": libre,
                       "no_abierto": int(acc.get(D.ACCESO_NO, 0)),
                       "sin_dato": int(acc.get(D.ACCESO_SIN, 0))},
            "corpus": meta.get("corpus", meta.get("csv", "")),
            "gen": meta.get("gen", ""),
            "fuente": fuente["valor"] if fuente else "",
        }

    def clusters(self, cid):
        with self.con(self.db(cid)) as cn:
            return self._clusters(cn)

    def series(self, cid):
        """Serie temporal viva (años presentes en `docs`) + índices sintéticos."""
        self.signature
        name = self.db(cid)
        with self.con(name) as cn:
            meta = self._meta(cn)
            fil = cn.execute("SELECT anio, COUNT(*) n FROM docs WHERE anio IS NOT NULL"
                             " GROUP BY anio ORDER BY anio").fetchall()
        if not fil:
            return {"years": [], "pubs": [], "tech_invest": [], "edu_index": []}
        years = [r["anio"] for r in fil]
        pubs = [r["n"] for r in fil]
        tech, edu = D.serie_sintetica(years, seed=int(meta.get("seed_series", 42)))
        return {"years": years, "pubs": pubs, "tech_invest": tech, "edu_index": edu}

    def citas_promedio(self, cid):
        with self.con(self.db(cid)) as cn:
            return {r["anio"]: round(r["m"], 2) for r in cn.execute(
                "SELECT anio, AVG(citas) m FROM docs WHERE anio IS NOT NULL GROUP BY anio")}

    def corpora(self):
        return [{"id": cid, "meta": self.meta_corpus(cid),
                 "clusters": self.clusters(cid)} for cid in S.CORPUS_ORDER
                if self.existe(self.db(cid))]

    def db(self, cid):
        cid = str(cid)
        if cid not in S.CORPUS_DBS:
            raise DbError("Corpus desconocido: %s" % cid)
        return S.CORPUS_DBS[cid]

    # ------------------------------------------------------------ tecnologías
    def tecnologias(self, search="", cat="", geo="", trl=0, seg=0, amb=0):
        self.signature
        with self.con(S.CATALOGO_DB) as cn:
            meta = self._meta(cn)
            lbl = meta.get("geoma_lbl") or GEOMA_LBL_DEFAULT
            rows = [dict(r) for r in cn.execute("SELECT * FROM tecnologias ORDER BY orden")]
            kws = {}
            for r in cn.execute("SELECT tec_id,kw FROM tec_kws"):
                kws.setdefault(r["tec_id"], []).append(r["kw"])
        out = []
        for r in rows:
            t = dict(r)
            t["geoma"] = D.jloads(r["geoma"])
            t["geoma_lbl"] = [lbl.get(g, g) for g in t["geoma"]]
            t["cat_out"] = t.get("cat")
            t["kws"] = kws.get(t["id"], [])
            if search:
                s = search.strip().lower()
                if not (s in (t["nombre"] or "").lower() or s in (t["cat"] or "").lower()
                        or s in " ".join(t["kws"]).lower()):
                    continue
            if cat and t["cat"] != cat:
                continue
            if geo and geo not in t["geoma_lbl"]:
                continue
            if trl and (t["trl"] or 0) < int(trl):
                continue
            if seg and (t["seg"] or 0) < int(seg):
                continue
            if amb and (t["amb"] or 0) < int(amb):
                continue
            out.append(t)
        out.sort(key=lambda t: (-(t["trl"] or 0), -(t["n_docs"] or 0), t["nombre"]))
        return out

    def tecnologia(self, tid, cid="124", n_docs=12):
        with self.con(S.CATALOGO_DB) as cn:
            row = cn.execute("SELECT * FROM tecnologias WHERE id=?", (tid,)).fetchone()
            if not row:
                raise DbError("Tecnología %s no encontrada" % tid)
            kws = [r["kw"] for r in cn.execute("SELECT kw FROM tec_kws WHERE tec_id=?", (tid,))]
        meta = self._meta_sql(S.CATALOGO_DB)
        lbl = meta.get("geoma_lbl") or GEOMA_LBL_DEFAULT
        t = dict(row)
        t["geoma"] = D.jloads(row["geoma"])
        t["geoma_lbl"] = [lbl.get(g, g) for g in t["geoma"]]
        t["cat_out"] = t.get("cat")
        t["kws"] = kws
        r = self.docs(cid, tec=tid, per=n_docs, orden="citas")
        docs = r["docs"]
        anios = [d["anio"] for d in docs if d["anio"]]
        t["docs"] = docs
        t["n_docs_total"] = r["total"]
        t["citas"] = sum(d["citas"] for d in docs)
        t["anio_medio"] = round(sum(anios) / len(anios)) if anios else None
        return t

    def red(self):
        with self.con(S.CATALOGO_DB) as cn:
            return {"links": [dict(r) for r in cn.execute(
                "SELECT s,t,w FROM red ORDER BY w DESC, s, t")]}

    def _meta_sql(self, name):
        with self.con(name) as cn:
            return self._meta(cn)

    def tec_kws(self):
        with self.con(S.CATALOGO_DB) as cn:
            rows = [dict(r) for r in cn.execute("SELECT tec_id,kw FROM tec_kws")]
        return D.compilar_tecnologias(rows)

    def nombres_tecs(self):
        with self.con(S.CATALOGO_DB) as cn:
            return {r["id"]: r["nombre"] for r in cn.execute("SELECT id,nombre FROM tecnologias")}

    # ------------------------------------------------------------ observatorio
    def observatorio(self):
        self.signature
        with self.con(S.OBSERVATORIO_DB) as cn:
            paises = [dict(r) for r in cn.execute(
                "SELECT * FROM paises_obs ORDER BY tech DESC, pais")]
            pub = [dict(r) for r in cn.execute("SELECT * FROM paises_pub ORDER BY n DESC")]
            labels = [r["label"] for r in cn.execute(
                "SELECT label FROM radar_labels ORDER BY orden")]
            series = [{"id": r["id"], "nombre": r["nombre"], "v": D.jloads(r["v"])}
                      for r in cn.execute("SELECT * FROM radar_series ORDER BY orden")]
            igf = [dict(r) for r in cn.execute("SELECT * FROM igf_funds ORDER BY pct DESC")]
            colores = {r["cont"]: r["hex"] for r in cn.execute("SELECT * FROM colores")}
            cols = [r["col"] for r in cn.execute("SELECT col FROM corr_cols ORDER BY orden")]
            n = len(cols)
            mat = [[0.0] * n for _ in range(n)]
            for r in cn.execute("SELECT * FROM corr_mat"):
                if 0 <= r["fila"] < n and 0 <= r["col"] < n:
                    mat[r["fila"]][r["col"]] = r["r"]
            meta = self._meta(cn)
        return {"paises_obs": paises, "paises_pub": pub,
                "radar": {"labels": labels, "series": series,
                          "orden_serie": [s["id"] for s in series], "colores": colores},
                "cont_col": colores, "igf_funds": igf,
                "corr": {"cols": cols, "mat": mat}, "meta": meta}

    # ------------------------------------------------------------ bootstrap
    def ctx_graficos(self, cid=None):
        """Datos crudos que necesitan los cálculos de `derived_graficos`."""
        cid = str(cid or self.cid_activo())
        obs = self.observatorio()
        tec = self.tecnologias()
        return {
            "cid": cid,
            "meta": self.meta_corpus(cid),
            "clusters": self.clusters(cid),
            "series": self.series(cid),
            "docs": self.docs(cid, per=5000, orden="anio")["docs"],
            "top5": self.top_citados(cid, 5),
            "tecnologias": tec,
            "kws": {t["id"]: t.get("kws") for t in tec},
            "links": (self.red() or {}).get("links") or [],
            "obs": obs,
        }

    def cid_activo(self):
        return "124" if self.existe(self.db("124")) else (S.CORPUS_ORDER[0] if S.CORPUS_ORDER else "124")

    def sync_graficos(self, solo=None, ctx=None, cid=None):
        """Regenera los `.db` derivados (uno por gráfica y por tabla).

        Es idempotente: si el contenido no cambia no se escribe nada, así que el
        estado estacionario no toca los ficheros. `cid` indica de qué corpus
        sacar el cálculo (por defecto, el activo en el servidor).
        """
        self.signature
        ids = [solo] if solo else G.ids_graficos()
        if solo and solo not in G.POR_ID:
            raise DbError("Gráfica o tabla desconocida: %s" % solo)
        ctx = ctx or self.ctx_graficos(cid)
        cambiados = []
        for gid in ids:
            filas = G.calc(gid, ctx)
            extra = {}
            if gid == "chart_bubble" and "_bubble_reg" in ctx:
                extra["regresion"] = ctx["_bubble_reg"]
            if gid == "chart_red":
                extra.update({"nodos": ctx.get("_red_nodos"),
                              "aristas": ctx.get("_red_aristas"),
                              "conectada": True,
                              "niveles": ctx.get("_red_niveles")})
            try:
                if G.sync(self.db_dir, gid, filas, meta_extra=extra):
                    cambiados.append(gid)
            except sqlite3.Error as e:
                raise DbError("No se pudo sincronizar %s.db: %s" % (gid, e))
        return cambiados

    def _meta_grafico(self, gid):
        g = G.POR_ID[gid]
        meta = G.leer_meta(self.db_dir, gid)
        return {"id": gid, "db": gid + ".db", "tipo": g["tipo"], "titulo": g["titulo"],
                "desc": g["desc"], "fuente": g["fuente"], "seccion": g["seccion"],
                "columnas": [{"nombre": c["n"], "titulo": c["t"], "tipo": c["tipo"],
                              "ro": c["ro"]} for c in g["cols"]],
                "meta": _meta_publica(meta)}

    def graficos(self, con_filas=True, solo_ligeros=True):
        """Payload de las bases derivadas para el frontend."""
        ids = G.ids_graficos()
        if con_filas and solo_ligeros:
            ids = [i for i in ids if i not in G.PESADAS]
        out = []
        for gid in ids:
            item = self._meta_grafico(gid)
            if con_filas:
                item["filas"] = G.leer_filas(self.db_dir, gid)
            out.append(item)
        return out

    def grafico(self, gid, sync=True, cid=None):
        if gid not in G.POR_ID:
            raise DbError("Gráfica o tabla desconocida: %s" % gid)
        if sync:
            self.sync_graficos(solo=gid, cid=cid)
        item = self._meta_grafico(gid)
        item["filas"] = G.leer_filas(self.db_dir, gid)
        return item

    def grafico_guardar(self, gid, data):
        """Alta/edición de una fila del `.db` derivado (queda como override)."""
        if gid not in G.POR_ID:
            raise DbError("Gráfica o tabla desconocida: %s" % gid)
        clave = str(data.get("clave") or "").strip()
        if not clave:
            raise DbError("Falta la clave de la fila")
        g = G.POR_ID[gid]
        fila = {"clave": clave}
        if data.get("orden") not in (None, ""):
            fila["orden"] = int(data["orden"])
        if "extra" in data:
            fila["extra"] = data["extra"] or None
        for c in g["cols"]:
            if c["n"] in data:
                fila[c["n"]] = data[c["n"]]
        G.override_set(self.db_dir, gid, fila)
        self.sync_graficos(solo=gid)
        return {"gid": gid, "clave": clave,
                "filas": G.leer_filas(self.db_dir, gid)}

    def grafico_borrar(self, gid, clave):
        if gid not in G.POR_ID:
            raise DbError("Gráfica o tabla desconocida: %s" % gid)
        estaba = G.override_del(self.db_dir, gid, clave)
        self.sync_graficos(solo=gid)
        return {"gid": gid, "clave": clave, "borrado": estaba,
                "filas": G.leer_filas(self.db_dir, gid)}

    def grafico_reset(self, gid):
        if gid not in G.POR_ID:
            raise DbError("Gráfica o tabla desconocida: %s" % gid)
        G.reset(self.db_dir, gid)
        self.sync_graficos(solo=gid)
        return {"gid": gid, "ediciones": 0,
                "filas": G.leer_filas(self.db_dir, gid)}

    def bootstrap(self):
        """Payload inicial (misma forma que el antiguo app_data.json)."""
        self.signature
        cid0 = self.cid_activo()
        ctx = self.ctx_graficos(cid0)
        meta = ctx["meta"]
        doc = {"docs": ctx["docs"]}
        self.sync_graficos(ctx=ctx)
        return {
            "clusters": ctx["clusters"],
            "docs": doc["docs"],
            "tecnologias": ctx["tecnologias"],
            "red": {"links": ctx["links"]},
            "series": ctx["series"],
            **self.observatorio(),
            "meta": meta,
            "cid_activo": cid0,
            "graficos": self.graficos(),
            "graficos_meta": [self._meta_grafico(i) for i in G.PESADAS],
            "corpora": [{"id": c["id"], "nombre": c["meta"]["nombre"],
                         "csv": c["meta"]["csv"], "meta": c["meta"],
                         "clusters": c["clusters"]} for c in self.corpora()],
            "dbs": self.inventario(),
        }

    def inventario(self):
        """Estado de cada fichero .db: tamaño, mtime y nº de filas por tabla."""
        out = []
        for name in S.all_db_names():
            p = os.path.join(self.db_dir, name)
            if not os.path.exists(p):
                out.append({"name": name, "existe": False,
                            "derivada": name in S.DERIVED_DBS})
                continue
            st = os.stat(p)
            tablas, filas = {}, 0
            try:
                with self.con(name) as cn:
                    tabs = [r[0] for r in cn.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                        " AND name NOT LIKE 'sqlite_%'")]
                    for tb in tabs:
                        try:
                            n = cn.execute("SELECT COUNT(*) FROM " + tb).fetchone()[0]
                        except sqlite3.Error:
                            n = 0
                        tablas[tb] = n
                        filas += n
            except DbError as e:
                out.append({"name": name, "existe": True, "error": str(e),
                            "bytes": st.st_size, "mtime": st.st_mtime})
                continue
            gid = name[:-3] if name in S.DERIVED_DBS else None
            out.append({"name": name, "existe": True, "bytes": st.st_size,
                        "mtime": st.st_mtime,
                        "iso": time.strftime("%Y-%m-%d %H:%M:%S",
                                             time.localtime(st.st_mtime)),
                        "tablas": tablas, "filas": filas, "derivada": bool(gid),
                        "gid": gid,
                        "titulo": G.POR_ID[gid]["titulo"] if gid else "",
                        "ediciones": int((G.leer_meta(self.db_dir, gid) or {}).get("ediciones", 0))
                        if gid else 0})
        return out

    def esquema(self, name):
        with self.con(name) as cn:
            return [dict(r) for r in cn.execute(
                "SELECT name, type, sql FROM sqlite_master"
                " WHERE type IN ('table','index','view') AND name NOT LIKE 'sqlite_%'"
                " ORDER BY type, name")]

    def consulta(self, name, sql, params=(), max_rows=500):
        """Consulta SQL libre (solo lectura) — handy para inspeccionar los .db."""
        sql = (sql or "").strip()
        if not sql.lower().startswith(("select", "with", "pragma")):
            raise DbError("Sólo se permiten consultas de lectura (SELECT/WITH/PRAGMA)")
        with self.con(name) as cn:
            cur = cn.execute(sql, params)
            cols = [d[0] for d in (cur.description or [])]
            rows = cur.fetchmany(max_rows)
        return {"cols": cols, "rows": [list(r) for r in rows], "sql": sql}

    # ================================================================ escritura
    def guardar_doc(self, cid, data, doc_id=None):
        """Inserta (doc_id=None) o actualiza un documento del `.db`."""
        name = self.db(cid)
        campos = {k: data[k] for k in DOC_EDITABLES if k in data}
        with self.con(name, write=True) as cn:
            if doc_id is None:
                r = cn.execute("SELECT COALESCE(MAX(id),-1)+1 n FROM docs").fetchone()
                doc_id = r["n"]
                base = {"n": doc_id + 1, "cluster": None, "acceso": D.ACCESO_SIN,
                        "citas": 0, "titulo": "", "autores": "s.d.", "fuente": "",
                        "doi": "", "enlace": "", "acceso_raw": "", "perfil_acceso": "",
                        "eid": "", "hallazgos": "", "limitaciones": "", "novedad": "",
                        "anio": None, "texto": ""}
            else:
                old = cn.execute("SELECT * FROM docs WHERE id=?", (doc_id,)).fetchone()
                if old is None:
                    raise DbError("Documento %s no encontrado en %s" % (doc_id, name))
                base = {k: old[k] for k in DOC_COLS}
            base.update(campos)
            if "anio" in campos and campos["anio"] not in (None, ""):
                base["anio"] = D.to_int(campos["anio"], None)
            if "citas" in campos:
                base["citas"] = D.to_int(campos["citas"], 0)
            base["id"] = doc_id
            base["texto"] = self._texto_actualizado(base)
            tecs = data.get("tecs")
            if tecs is None and doc_id is None and self.existe(S.CATALOGO_DB):
                tecs = D.clasificar_tecs(base["texto"], self.tec_kws())
            if not data.get("sin_tecs"):
                nombres = self.nombres_tecs() if self.existe(S.CATALOGO_DB) else {}
                base["tecnologias_txt"] = " | ".join(nombres.get(t, t) for t in (tecs or []))
            cn.execute(
                "INSERT OR REPLACE INTO docs(" + ",".join(DOC_COLS) + ") VALUES(" +
                ",".join("?" * len(DOC_COLS)) + ")", [base[c] for c in DOC_COLS])
            if not data.get("sin_tecs"):
                cn.execute("DELETE FROM doc_tecs WHERE doc_id=?", (doc_id,))
                for tid in tecs or []:
                    if tid:
                        cn.execute("INSERT OR IGNORE INTO doc_tecs(doc_id,tec_id) VALUES(?,?)",
                                   (doc_id, tid))
        self.signature
        return self.doc(cid, doc_id)

    @staticmethod
    def _texto_actualizado(doc):
        """Mantiene el índice de texto alineado con el título/descripción."""
        partes = [doc.get("titulo") or "", doc.get("hallazgos") or "",
                  doc.get("limitaciones") or "", doc.get("novedad") or ""]
        return D.norm(" ".join(p for p in partes if p)).lower()

    def borrar_doc(self, cid, doc_id):
        name = self.db(cid)
        with self.con(name, write=True) as cn:
            n = cn.execute("DELETE FROM docs WHERE id=?", (doc_id,)).rowcount
            cn.execute("DELETE FROM doc_tecs WHERE doc_id=?", (doc_id,))
        self.signature
        if not n:
            raise DbError("Documento %s no encontrado en %s" % (doc_id, name))
        return {"borrado": doc_id}

    def guardar_tecnologia(self, tid, data):
        campos = {k: data[k] for k in TEC_EDITABLES if k in data}
        with self.con(S.CATALOGO_DB, write=True) as cn:
            old = cn.execute("SELECT * FROM tecnologias WHERE id=?", (tid,)).fetchone()
            if old is None:
                raise DbError("Tecnología %s no encontrada" % tid)
            row = {k: old[k] for k in old.keys()}
            row.update(campos)
            if "geoma" in campos and isinstance(campos["geoma"], (list, tuple)):
                row["geoma"] = json.dumps(list(campos["geoma"]), ensure_ascii=False)
            for k in ("trl", "seg", "amb", "n_docs"):
                if row.get(k) is not None:
                    row[k] = D.to_int(row[k], 0)
            cn.execute(
                "UPDATE tecnologias SET nombre=?,cat=?,trl=?,geoma=?,capex=?,opex=?,"
                "seg=?,amb=?,n_docs=? WHERE id=?",
                [row["nombre"], row["cat"], row["trl"], row["geoma"], row["capex"],
                 row["opex"], row["seg"], row["amb"], row["n_docs"], tid])
            if isinstance(data.get("kws"), list):
                cn.execute("DELETE FROM tec_kws WHERE tec_id=?", (tid,))
                cn.executemany("INSERT INTO tec_kws(tec_id,kw) VALUES(?,?)",
                               [(tid, kw) for kw in data["kws"] if str(kw).strip()])
        self.signature
        return self.tecnologia(tid)

    def guardar_pais(self, data, pais=None):
        cols = ["pais", "cont", "gdp_pc", "tech", "edu", "mining_gdp", "seg", "amb", "n_pubs"]
        vals = {c: data.get(c) for c in cols}
        with self.con(S.OBSERVATORIO_DB, write=True) as cn:
            old = cn.execute("SELECT * FROM paises_obs WHERE pais=?", (pais,)).fetchone() if pais else None
            row = ({c: old[c] for c in cols} if old else {c: None for c in cols})
            row.update(vals)
            if not row.get("pais"):
                raise DbError("Falta el nombre del país")
            cn.execute("INSERT OR REPLACE INTO paises_obs(" + ",".join(cols) + ") VALUES(" +
                       ",".join("?" * len(cols)) + ")", [row[c] for c in cols])
            nuevo = row["pais"]
        self.signature
        return nuevo

    def guardar_igf(self, region, pct):
        with self.con(S.OBSERVATORIO_DB, write=True) as cn:
            cn.execute("INSERT OR REPLACE INTO igf_funds(region,pct) VALUES(?,?)",
                       (region, float(pct)))
        self.signature
        return {"region": region, "pct": float(pct)}

    def guardar_meta(self, dbname, key, value):
        with self.con(dbname, write=True) as cn:
            cn.execute("INSERT OR REPLACE INTO meta(key,value) VALUES(?,?)",
                       (key, json.dumps(value, ensure_ascii=False)))
        self.signature
        return {"db": dbname, "key": key, "value": value}

    # ------------------------------------------------------------ reindexado
    def reindexar(self, cid):
        """Recalcula clústeres y tecnologías desde las palabras clave del `.db`."""
        name = self.db(cid)
        clusters = self.clusters(cid)
        clist = [clusters[k] for k in sorted(clusters, key=int)]
        kws = self.tec_kws()
        nombres = self.nombres_tecs()
        cambios = {"cluster": 0, "tecs": 0}
        with self.con(name, write=True) as cn:
            filas = cn.execute("SELECT id, COALESCE(texto,'') t FROM docs ORDER BY id").fetchall()
            for r in filas:
                texto = r["t"] or ""
                cl = D.clasificar_cluster(texto, clist)
                cur = cn.execute("SELECT cluster FROM docs WHERE id=?", (r["id"],)).fetchone()
                if (cur["cluster"] if cur else None) != cl:
                    cn.execute("UPDATE docs SET cluster=? WHERE id=?", (cl, r["id"]))
                    cambios["cluster"] += 1
                nuevos = D.clasificar_tecs(texto, kws)
                act = {x["tec_id"] for x in cn.execute(
                    "SELECT tec_id FROM doc_tecs WHERE doc_id=?", (r["id"],))}
                for t in set(nuevos) - act:
                    cn.execute("INSERT OR IGNORE INTO doc_tecs(doc_id,tec_id) VALUES(?,?)",
                               (r["id"], t))
                    cambios["tecs"] += 1
                for t in act - set(nuevos):
                    cn.execute("DELETE FROM doc_tecs WHERE doc_id=? AND tec_id=?", (r["id"], t))
                    cambios["tecs"] += 1
                cn.execute("UPDATE docs SET tecnologias_txt=? WHERE id=?",
                           (" | ".join(nombres.get(t, t) for t in nuevos), r["id"]))
        if self.existe(S.CATALOGO_DB):
            self._sincronizar_catalogo(cid)
        self.signature
        return {"db": name, "cambios": cambios}

    def _sincronizar_catalogo(self, cid):
        with self.con(S.CATALOGO_DB, write=True) as cn:
            cn.execute("UPDATE tecnologias SET n_docs=0")
        with self.con(self.db(cid)) as cn:
            cuentas = {r["tec_id"]: r["n"] for r in cn.execute(
                "SELECT tec_id, COUNT(*) n FROM doc_tecs GROUP BY tec_id")}
        with self.con(S.CATALOGO_DB, write=True) as cn:
            cn.executemany("UPDATE tecnologias SET n_docs=? WHERE id=?",
                           [(n, t) for t, n in cuentas.items()])
            if cid == "124":
                cn.execute("DELETE FROM red")
                tec = [r["id"] for r in cn.execute("SELECT id FROM tecnologias ORDER BY orden")]
                idx = {t: i for i, t in enumerate(tec)}
                cooc = {}
                with self.con(self.db(cid)) as c2:
                    for r in c2.execute(
                            "SELECT doc_id, GROUP_CONCAT(tec_id) t FROM doc_tecs GROUP BY doc_id"):
                        ids = [idx[x] for x in (r["t"] or "").split(",") if x in idx]
                        for a in range(len(ids)):
                            for b in range(a + 1, len(ids)):
                                key = tuple(sorted((tec[ids[a]], tec[ids[b]])))
                                cooc[key] = cooc.get(key, 0) + 1
                cn.executemany("INSERT OR REPLACE INTO red(s,t,w) VALUES(?,?,?)",
                               [(k[0], k[1], v)
                                for k, v in sorted(cooc.items(), key=lambda x: -x[1])])

    def recargar(self):
        """Fuerza la invalidación de cachés (por si el mtime no cambió)."""
        with self._lock:
            self._sig = None
            self._cache.clear()
        return self.version()


STORE = Store()