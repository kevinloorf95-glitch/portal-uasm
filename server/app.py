# -*- coding: utf-8 -*-
"""
Portal MAPE · aplicación web (servidor + API REST sobre bases `.db`).

Arranque (desde `frame/`):
    python server/app.py                # http://127.0.0.1:8000
    python server/app.py --port 9000 --rebuild

    Equivalente:      python -m server.app

La aplicación **no** lee ningún CSV/JSON en tiempo de ejecución: todo se resuelve
contra los ficheros `.db` de `frame/db/`.  Si editas un `.db` con cualquier
herramienta (sqlite3, DBeaver, el editor del propio portal) el cambio se ve en
la siguiente petición; el navegador además sondea `/api/health` y recarga solo.

Endpoints
---------
  GET    /api/health                     estado + versión de las bases
  GET    /api/db                         inventario de .db (tamaño, filas, tablas)
  GET    /api/db/<nombre>/schema         esquema SQL de un .db
  POST   /api/db/<nombre>/query          SELECT libre (diagnóstico)
  GET    /api/db/download/<nombre>       descarga el fichero .db
  GET    /api/bootstrap                  payload inicial del portal
  GET    /api/corpora                    las 5 vistas del corpus
  GET    /api/corpora/<id>               una vista completa (docs incluidos)
  GET    /api/corpora/<id>/docs          docs filtrados + paginación (SQL)
  GET    /api/corpora/<id>/series        serie temporal viva
  GET    /api/corpora/<id>/stats         agregados (clústeres, acceso, n_docs)
  GET    /api/corpora/<id>/top5          documentos más citados
  POST   /api/corpora/<id>/reindex       reclasifica clústeres y tecnologías
  GET    /api/tecnologias[?filtros]      catálogo filtrado
  GET    /api/tecnologias/<tec>          detalle + documentos del corpus 124
  PATCH  /api/tecnologias/<tec>          edita catalogo_tecnologias.db
  GET    /api/observatorio               países, radar, IGF, correlaciones
  GET    /api/graficos                   bases .db derivadas (1 por gráfica/tabla)
  GET    /api/grafico/<id>                datos de una de ellas (sincroniza)
  POST   /api/grafico/<id>/fila           alta/edición de una fila
  DELETE /api/grafico/<id>/fila/<clave>   baja de una fila
  POST   /api/grafico/<id>/reset          descarta las ediciones de esa base
  POST   /api/graficos/sync              regenera todas las bases derivadas
  GET    /api/grafico/<id>.csv|.json|.db  exportación / descarga
  GET    /api/export/corpus/<id>.csv|json
  GET    /api/export/table/<tabla>.csv
  GET    /api/export/app_data.json
  POST   /api/db/corpus_<id>/docs        crea documento en el .db
  PATCH  /api/db/corpus_<id>/docs/<id>   actualiza documento
  DELETE /api/db/corpus_<id>/docs/<id>   borra documento
  POST   /api/observatorio/paises_obs    alta/actualización de país
  POST   /api/observatorio/igf           alta/actualización de fondo IGF
  POST   /api/admin/reload               fuerza la recarga de cachés
  POST   /api/admin/rebuild              reimporta los CSV a los .db
"""
import argparse
import csv
import functools
import io
import json
import mimetypes
import os
import pathlib
import posixpath
import re
import socketserver
import subprocess
import sys
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import derived as D  # noqa: E402
import derived_graficos as G  # noqa: E402
import dbstore  # noqa: E402
import schema as S  # noqa: E402

STORE = dbstore.STORE
APP_DIR = S.APP_DIR

MIME = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
        ".css": "text/css; charset=utf-8", ".json": "application/json; charset=utf-8",
        ".svg": "image/svg+xml", ".png": "image/png", ".ico": "image/x-icon"}


# ---------------------------------------------------------------- utilidades
def json_bytes(obj):
    return json.dumps(obj, ensure_ascii=False, allow_nan=False).encode("utf-8")


def csv_bytes(header, rows):
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";", lineterminator="\r\n", quoting=csv.QUOTE_MINIMAL)
    w.writerow(header)
    for r in rows:
        w.writerow([("" if v is None else v) for v in r])
    return ("﻿" + buf.getvalue()).encode("utf-8")


def limpio(v):
    return D.norm(v).replace("\r", " ").replace("\n", " ")


# ---------------------------------------------------------------- exportación CSV/JSON
CSV_CORPUS_HEAD = ["anio", "titulo", "autores", "fuente", "citas", "doi", "enlace",
                   "acceso", "cluster", "tecnologias", "keywords"]

CSV_DELIVERABLE_HEAD = ["N", "Año", "Título", "Autores", "Fuente", "Citas", "Acceso",
                        "Clúster", "Hallazgos principales", "Limitaciones", "Novedad"]

CSV_OBS_HEAD = ["País", "Región", "PIB pc (US$)", "Tech", "Seg.", "Amb.", "Minería% PIB"]

CSV_TEC_HEAD = ["Tecnología", "Categoría", "Docs", "TRL", "Geometría", "CAPEX", "OPEX",
                "Seg.", "Amb."]


def _filas_corpus(cid, **filtros):
    nombre_tec = STORE.nombres_tecs()
    clusters = STORE.clusters(cid)
    out = []
    for d in STORE.docs(cid, **filtros)["docs"]:
        out.append([
            d.get("anio") or "", limpio(d.get("titulo")), limpio(d.get("autores")),
            limpio(d.get("fuente")), d.get("citas") or 0, d.get("doi") or "",
            d.get("enlace") or "", d.get("acceso") or "",
            "" if d.get("cluster") is None else d["cluster"],
            " | ".join(nombre_tec.get(t, t) for t in d.get("tecs", [])),
            d.get("tecnologias_txt") or "",
        ])
    return out


def export_corpus_csv(cid, **filtros):
    return CSV_CORPUS_HEAD, _filas_corpus(cid, **filtros)


def export_corpus_json(cid, filtros=None):
    f = dict(filtros or {})
    f["per"] = int(f.get("per") or 5000)
    d = STORE.docs(cid, **f)
    c = STORE.meta_corpus(cid)
    return {"id": cid, "nombre": c["nombre"], "csv": c["csv"], "meta": c,
            "clusters": STORE.clusters(cid), "docs": d["docs"],
            "series": STORE.series(cid)}


def export_deliverable_csv(cid="124"):
    clusters = STORE.clusters(cid)
    docs = STORE.docs(cid, per=5000, orden="anio")["docs"]
    rows = []
    for i, d in enumerate(docs):
        cl = clusters.get(str(d.get("cluster"))) if d.get("cluster") is not None else None
        rows.append([i + 1, d.get("anio") or "—", limpio(d.get("titulo")),
                     limpio(d.get("autores")), limpio(d.get("fuente")),
                     d.get("citas") or 0, d.get("acceso") or "",
                     cl["nombre"] if cl else "—",
                     limpio(d.get("hallazgos")), limpio(d.get("limitaciones")),
                     limpio(d.get("novedad"))])
    return CSV_DELIVERABLE_HEAD, rows


def export_obs_csv():
    reg = {"Africa": "África", "LatAm": "Latinoamérica", "Asia": "Asia",
           "AsiaPac": "Asia-Pacífico", "Europe": "Europa", "Global": "Global"}
    obs = STORE.observatorio()["paises_obs"]
    return CSV_OBS_HEAD, [[p["pais"], reg.get(p["cont"], p["cont"]),
                           p["gdp_pc"], p["tech"], p["seg"], p["amb"],
                           round(p["mining_gdp"], 1)] for p in obs]


def export_tec_csv(**filtros):
    rows = []
    for t in STORE.tecnologias(**filtros):
        rows.append([t["nombre"], t["cat"], t["n_docs"], t["trl"],
                     " | ".join(t["geoma_lbl"]), t["capex"], t["opex"], t["seg"], t["amb"]])
    return CSV_TEC_HEAD, rows


TABLES = {"tabla_paises_obs", "tabla_deliverable", "tabla_tecnologias", "tabla_corpus"}


def export_tabla(nombre, q):
    if nombre == "tabla_paises_obs":
        return export_obs_csv()
    if nombre == "tabla_deliverable":
        return export_deliverable_csv()
    if nombre == "tabla_tecnologias":
        return export_tec_csv(**filtros_tec(q))
    cid = q.get("corpus", ["124"])[0]
    head, rows = export_corpus_csv(cid, **filtros_docs(q))
    return CSV_CORPUS_HEAD, rows


def filtros_docs(q):
    def one(k, d=None):
        v = q.get(k, [d])
        return v[0] if v else d
    return {"search": one("search", "") or "", "cluster": one("cluster", "") or "",
            "tec": one("tec", "") or "", "acceso": one("acceso", "") or "",
            "y0": one("y0", "") or "", "y1": one("y1", "") or "",
            "page": int(one("page", "1") or 1),
            "per": int(one("per", "5000") or 5000),
            "orden": one("orden", "citas")}


def filtros_tec(q):
    def num(k):
        v = q.get(k, ["0"])
        try:
            return int(v[0] or 0)
        except (TypeError, ValueError):
            return 0
    def one(k, d=""):
        v = q.get(k, [d])
        return v[0] if v else d
    return {"search": one("search"), "cat": one("cat"), "geo": one("geo"),
            "trl": num("trl"), "seg": num("seg"), "amb": num("amb")}


# ---------------------------------------------------------------- handler
class PortalHandler(BaseHTTPRequestHandler):
    server_version = "PortalMAPE/1.0"
    protocol_version = "HTTP/1.1"
    verbose = False

    # -------------------------------------------------- utilidades de respuesta
    def _send(self, body, ctype, status=200, extra=None):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-DB-Version", STORE.version())
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def json(self, obj, status=200):
        self._send(json_bytes(obj), MIME[".json"], status)

    def fail(self, msg, status=400):
        self.json({"error": str(msg), "status": status}, status)

    def body_json(self):
        datos = self._leer_cuerpo()
        if not datos:
            return {}
        try:
            return json.loads(datos.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            raise dbstore.DbError("Cuerpo JSON no válido")

    def _leer_cuerpo(self):
        """Lee (una sola vez) el cuerpo de la petición.

        Imprescindible con HTTP/1.1: si el handler no consume el body, los
        bytes sobrantes se interpretan como la siguiente petición y el
        servidor responde 501. Todos los verbos con cuerpo pasan por aquí.
        """
        if getattr(self, "_cuerpo", None) is None:
            n = int(self.headers.get("Content-Length") or 0)
            self._cuerpo = self.rfile.read(n) if n > 0 else b""
        return self._cuerpo

    # -------------------------------------------------- verbos
    def do_GET(self):
        self._route("GET")

    def do_HEAD(self):
        self._route("GET")

    def do_POST(self):
        self._route("POST")

    def do_PATCH(self):
        self._route("PATCH")

    def do_PUT(self):
        self._route("PATCH")

    def do_DELETE(self):
        self._route("DELETE")

    def do_OPTIONS(self):
        self._send(b"", "text/plain", 204, {"Allow": "GET,POST,PATCH,DELETE,OPTIONS"})

    # -------------------------------------------------- router
    def _route(self, method):
        self._cuerpo = None
        try:
            parsed = urllib.parse.urlsplit(self.path)
            path = urllib.parse.unquote(parsed.path)
            q = urllib.parse.parse_qs(parsed.query)
            if not path.startswith("/api/"):
                return self.estatico(path)
            if method in ("POST", "PATCH", "PUT", "DELETE"):
                self._leer_cuerpo()
            for m, rx, fn in ROUTES:
                mt = rx.match(path)
                if mt and m == method:
                    return fn(self, q, *mt.groups())
            if path == "/api" or path == "/api/":
                return self.json({"app": "Portal MAPE", "api": "/api/health"})
            return self.fail("Endpoint no encontrado: %s %s" % (method, path), 404)
        except dbstore.DbError as e:
            self.fail(e, 404)
        except BrokenPipeError:
            pass
        except Exception as e:  # pragma: no cover
            if self.verbose:
                import traceback
                traceback.print_exc()
            self.fail("Error interno: %s" % e, 500)

# -------------------------------------------------- ficheros estáticos
    def estatico(self, path):
        rel = "index.html" if path in ("/", "") else posixpath.normpath(path).lstrip("/")
        destino = (APP_DIR / rel).resolve()
        if os.path.commonpath([str(destino), str(APP_DIR.resolve())]) != str(APP_DIR.resolve()):
            return self.fail("Ruta no permitida", 403)
        if destino.is_dir():
            destino = destino / "index.html"
        if not destino.exists() or not destino.is_file():
            return self.fail("No encontrado: %s" % rel, 404)
        # las bases .db se descargan por /api/db/download/<nombre>
        if destino.suffix == ".db":
            return self.fail("Usa /api/db/download/%s" % destino.name, 403)
        ctype = MIME.get(destino.suffix) or mimetypes.guess_type(str(destino))[0] or \
            "application/octet-stream"
        self._send(destino.read_bytes(), ctype)

    # ================================================================= API
    # -------------------------------------------------- salud / bases
    def api_health(self, q):
        return self.json({"ok": True, "version": STORE.version(),
                          "dbs": STORE.inventario(), "time": time.time()})

    def api_db_list(self, q):
        return self.json({"dir": STORE.db_dir, "dbs": STORE.inventario()})

    def api_db_schema(self, q, name):
        _validar_db(name)
        return self.json({"db": name, "objetos": STORE.esquema(name),
                          "dbs": STORE.inventario()})

    def api_db_query(self, q, name):
        _validar_db(name)
        data = self.body_json()
        return self.json(STORE.consulta(name, data.get("sql", ""), data.get("params") or [],
                                        int(data.get("max_rows") or 200)))

    def api_db_download(self, q, name):
        _validar_db(name)
        p = pathlib.Path(STORE.db_dir) / name
        self._send(p.read_bytes(), "application/x-sqlite3", 200,
                   {"Content-Disposition": 'attachment; filename="%s"' % name})

    # -------------------------------------------------- datos del portal
    def api_bootstrap(self, q):
        return self.json(STORE.bootstrap())

    def api_corpora(self, q):
        return self.json({"corpora": STORE.corpora()})

    def api_corpus(self, q, cid):
        return self.json(export_corpus_json(cid, {}))

    def api_corpus_docs(self, q, cid):
        f = filtros_docs(q)
        return self.json(STORE.docs(cid, **f))

    def api_corpus_series(self, q, cid):
        return self.json(STORE.series(cid))

    def api_corpus_stats(self, q, cid):
        return self.json(STORE.meta_corpus(cid))

    def api_corpus_top5(self, q, cid):
        n = int((q.get("n") or ["5"])[0] or 5)
        return self.json({"docs": STORE.top_citados(cid, n)})

    def api_corpus_reindex(self, q, cid):
        return self.json(STORE.reindexar(cid))

    def api_tecnologias(self, q):
        return self.json({"tecnologias": STORE.tecnologias(**filtros_tec(q))})

    def api_tecnologia(self, q, tid):
        return self.json(STORE.tecnologia(tid, n_docs=int((q.get("n") or ["12"])[0] or 12)))

    def api_tecnologia_patch(self, q, tid):
        return self.json(STORE.guardar_tecnologia(tid, self.body_json()))

    def api_observatorio(self, q):
        return self.json(STORE.observatorio())

    # -------------------------------------------------- bases derivadas (gráficas/tablas)
    @staticmethod
    def _cid(q):
        """Corpus solicitado (`?cid=360`); si no, el que el servidor tiene activo."""
        return (q.get("cid") or [None])[0]

    def api_graficos(self, q):
        # `?ligero=0` incluye además las tablas pesadas (tabla_corpus, entrega)
        completo = (q.get("ligero") or ["1"])[0] in ("0", "false", "no")
        STORE.sync_graficos(cid=self._cid(q))
        return self.json({"dir": STORE.db_dir,
                          "graficos": STORE.graficos(con_filas=True, solo_ligeros=not completo)})

    def api_grafico(self, q, gid):
        return self.json(STORE.grafico(gid, cid=self._cid(q)))

    def api_grafico_fila(self, q, gid):
        data = self.body_json()
        return self.json(STORE.grafico_guardar(gid, data))

    def api_grafico_fila_del(self, q, gid, clave):
        return self.json(STORE.grafico_borrar(gid, clave))

    def api_grafico_reset(self, q, gid):
        return self.json(STORE.grafico_reset(gid))

    def api_graficos_sync(self, q):
        cambiados = STORE.sync_graficos()
        return self.json({"ok": True, "sincronizados": cambiados,
                          "dbs": STORE.inventario()})

    def api_grafico_export(self, q, gid, ext):
        item = STORE.grafico(gid, cid=self._cid(q))
        if ext == "csv":
            self._send(G.csv_filas(gid, item["filas"]), "text/csv; charset=utf-8", 200,
                       {"Content-Disposition": 'attachment; filename="%s.csv"' % gid})
            return None
        if ext == "json":
            self._send(json_bytes(item), MIME[".json"], 200,
                       {"Content-Disposition": 'attachment; filename="%s.json"' % gid})
            return None
        nombre = item["db"]
        _validar_db(nombre)
        p = pathlib.Path(STORE.db_dir) / nombre
        self._send(p.read_bytes(), "application/x-sqlite3", 200,
                   {"Content-Disposition": 'attachment; filename="%s"' % nombre})
        return None

    # -------------------------------------------------- exportaciones
    def api_export_corpus(self, q, cid, ext):
        if ext == "csv":
            head, rows = export_corpus_csv(cid, **filtros_docs(q))
            self._send(csv_bytes(head, rows), "text/csv; charset=utf-8", 200,
                       {"Content-Disposition": 'attachment; filename="corpus_%s.csv"' % cid})
            return None
        self._send(json_bytes(export_corpus_json(cid, filtros_docs(q))),
                   MIME[".json"], 200,
                   {"Content-Disposition": 'attachment; filename="corpus_%s.json"' % cid})
        return None

    def api_export_tabla(self, q, tabla):
        if tabla not in TABLES:
            raise dbstore.DbError("Tabla desconocida: %s" % tabla)
        head, rows = export_tabla(tabla, q)
        self._send(csv_bytes(head, rows), "text/csv; charset=utf-8", 200,
                   {"Content-Disposition": 'attachment; filename="%s.csv"' % tabla})
        return None

    def api_export_app_data(self, q):
        self._send(json_bytes(STORE.bootstrap()), MIME[".json"], 200,
                   {"Content-Disposition": 'attachment; filename="app_data.json"'})
        return None

    # -------------------------------------------------- escritura (.db)
    def api_doc_new(self, q, dbname):
        cid = _cid_de_db(dbname)
        return self.json({"doc": STORE.guardar_doc(cid, self.body_json())}, 201)

    def api_doc_patch(self, q, dbname, doc_id):
        cid = _cid_de_db(dbname)
        return self.json({"doc": STORE.guardar_doc(cid, self.body_json(), int(doc_id))})

    def api_doc_delete(self, q, dbname, doc_id):
        cid = _cid_de_db(dbname)
        return self.json(STORE.borrar_doc(cid, int(doc_id)))

    def api_pais(self, q):
        data = self.body_json()
        return self.json({"pais": STORE.guardar_pais(data, data.get("pais"))})

    def api_igf(self, q):
        data = self.body_json()
        if not data.get("region"):
            raise dbstore.DbError("Falta la región")
        return self.json(STORE.guardar_igf(data["region"], data.get("pct") or 0))

    def api_meta(self, q, dbname):
        _validar_db(dbname)
        data = self.body_json()
        return self.json(STORE.guardar_meta(dbname, data.get("key", ""), data.get("value")))

    # -------------------------------------------------- administración
    def api_reload(self, q):
        return self.json({"ok": True, "version": STORE.recargar(),
                          "dbs": STORE.inventario()})

    def api_rebuild(self, q):
        data = self.body_json()
        buf = io.StringIO()
        old = sys.stdout
        sys.stdout = buf
        try:
            _rebuild(["--force"] if data.get("force", True) else [])
        finally:
            sys.stdout = old
        STORE.recargar()
        return self.json({"ok": True, "log": buf.getvalue().splitlines()[-25:],
                          "dbs": STORE.inventario()})


def _rebuild(argv):
    old_argv = sys.argv
    sys.argv = ["build_db.py"] + argv
    try:
        import build_db
        build_db.main()
    finally:
        sys.argv = old_argv


def _validar_db(name):
    if name not in S.ALL_DBS and not (name.endswith(".db") and
                                       (pathlib.Path(STORE.db_dir) / name).exists()):
        raise dbstore.DbError("Base de datos desconocida: %s" % name)
    if not name.endswith(".db"):
        raise dbstore.DbError("Las bases deben terminar en .db: %s" % name)


def _cid_de_db(dbname):
    _validar_db(dbname)
    base = dbname[:-3]
    cid = base.replace("corpus_", "")
    if cid not in S.CORPUS_DBS:
        raise dbstore.DbError("No es una base de corpus: %s" % dbname)
    return cid


def rx(p):
    return re.compile("^" + p + "$")


ROUTES = [
    ("GET", rx(r"/api/health"), PortalHandler.api_health),
    ("GET", rx(r"/api/db"), PortalHandler.api_db_list),
    ("GET", rx(r"/api/db/([^/]+)/schema"), PortalHandler.api_db_schema),
    ("POST", rx(r"/api/db/([^/]+)/query"), PortalHandler.api_db_query),
    ("GET", rx(r"/api/db/download/([^/]+)"), PortalHandler.api_db_download),
    ("PATCH", rx(r"/api/db/([^/]+)/meta"), PortalHandler.api_meta),

    ("GET", rx(r"/api/bootstrap"), PortalHandler.api_bootstrap),
    ("GET", rx(r"/api/corpora"), PortalHandler.api_corpora),
    ("GET", rx(r"/api/corpora/([^/]+)"), PortalHandler.api_corpus),
    ("GET", rx(r"/api/corpora/([^/]+)/docs"), PortalHandler.api_corpus_docs),
    ("GET", rx(r"/api/corpora/([^/]+)/series"), PortalHandler.api_corpus_series),
    ("GET", rx(r"/api/corpora/([^/]+)/stats"), PortalHandler.api_corpus_stats),
    ("GET", rx(r"/api/corpora/([^/]+)/top5"), PortalHandler.api_corpus_top5),
    ("POST", rx(r"/api/corpora/([^/]+)/reindex"), PortalHandler.api_corpus_reindex),

    ("GET", rx(r"/api/tecnologias"), PortalHandler.api_tecnologias),
    ("GET", rx(r"/api/tecnologias/([^/]+)"), PortalHandler.api_tecnologia),
    ("PATCH", rx(r"/api/tecnologias/([^/]+)"), PortalHandler.api_tecnologia_patch),

    ("GET", rx(r"/api/observatorio"), PortalHandler.api_observatorio),
    ("POST", rx(r"/api/observatorio/paises_obs"), PortalHandler.api_pais),
    ("POST", rx(r"/api/observatorio/igf"), PortalHandler.api_igf),

    ("GET", rx(r"/api/graficos"), PortalHandler.api_graficos),
    ("POST", rx(r"/api/graficos/sync"), PortalHandler.api_graficos_sync),
    ("GET", rx(r"/api/grafico/([^/]+)\.(csv|json|db)"), PortalHandler.api_grafico_export),
    ("GET", rx(r"/api/grafico/([^/]+)"), PortalHandler.api_grafico),
    ("POST", rx(r"/api/grafico/([^/]+)/fila"), PortalHandler.api_grafico_fila),
    ("DELETE", rx(r"/api/grafico/([^/]+)/fila/([^/]+)"), PortalHandler.api_grafico_fila_del),
    ("POST", rx(r"/api/grafico/([^/]+)/reset"), PortalHandler.api_grafico_reset),

    ("GET", rx(r"/api/export/corpus/([^/]+)\.(csv|json)"), PortalHandler.api_export_corpus),
    ("GET", rx(r"/api/export/table/([^/]+)\.csv"), PortalHandler.api_export_tabla),
    ("GET", rx(r"/api/export/app_data\.json"), PortalHandler.api_export_app_data),

    ("POST", rx(r"/api/db/([^/]+)/docs"), PortalHandler.api_doc_new),
    ("PATCH", rx(r"/api/db/([^/]+)/docs/(\d+)"), PortalHandler.api_doc_patch),
    ("DELETE", rx(r"/api/db/([^/]+)/docs/(\d+)"), PortalHandler.api_doc_delete),

    ("POST", rx(r"/api/admin/reload"), PortalHandler.api_reload),
    ("POST", rx(r"/api/admin/rebuild"), PortalHandler.api_rebuild),
]


class PortalServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


# ---------------------------------------------------------------- arranque
STORE = dbstore.STORE


def migrar():
    try:
        add = STORE.migrar()
        for a in add:
            print("[db] columna añadida: %s" % a)
    except Exception as e:  # pragma: no cover
        print("[db] aviso al migrar: %s" % e)
def asegurar_dbs(rebuild=False):
    faltan = [n for n in S.ALL_DBS if not STORE.existe(n)]
    if rebuild or faltan:
        print("[db] construyendo bases .db (%s)" % ("rebuild" if rebuild else
                                                   ", ".join(faltan)))
        import build_db
        old = sys.argv
        sys.argv = ["build_db.py"] + (["--force"] if rebuild else [])
        try:
            build_db.main()
        finally:
            sys.argv = old
        STORE.recargar()


def _say(line=""):
    """Imprime en consola sin abortar el arranque si el terminal no codifica el texto.

    La consola de Windows suele usar cp850/cp1252, donde los caracteres de dibujo
    de cajas (├──, │) no existen. Con _say el banner se degrena a '?' en vez de
    provocar UnicodeEncodeError y matar el servidor.
    """
    try:
        print(line)
        sys.stdout.flush()
    except UnicodeEncodeError:
        enc = getattr(sys.stdout, "encoding", None) or "ascii"
        try:
            print(line.encode(enc, "replace").decode(enc, "replace"))
        except Exception:
            print(repr(line))
        sys.stdout.flush()
def main():
    global STORE
    ap = argparse.ArgumentParser(description="Portal MAPE - aplicación web")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--db-dir", default=None, help="carpeta con los .db")
    ap.add_argument("--rebuild", action="store_true", help="recrea los .db desde los CSV")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()
    if args.db_dir:
        globals()["STORE"] = dbstore.Store(args.db_dir)
    PortalHandler.verbose = args.verbose
    migrar()
    asegurar_dbs(args.rebuild)

    if not args.verbose:
        def log_message(self, fmt, *a):
            try:
                sys.stderr.write("  %s %s\n" % (self.address_string(), fmt % a))
                sys.stderr.flush()
            except UnicodeEncodeError:
                pass
        PortalHandler.log_message = log_message

    srv = PortalServer((args.host, args.port), PortalHandler)
    rule = "  " + "-" * 62
    _say("")
    _say("  Portal MAPE - aplicación web")
    _say(rule)
    _say("  servidor : http://%s:%d/" % (args.host, args.port))
    _say("  bases    : %s" % STORE.db_dir)
    for d in STORE.inventario():
        if d.get("existe"):
            _say("              %-24s %7.1f KB  %6d filas" % (
                d["name"], d["bytes"] / 1024, d.get("filas") or 0))
        else:
            _say("              %-24s [falta]" % d["name"])
    _say("  API      : /api/health  -  /api/db  -  /api/bootstrap")
    _say(rule)
    _say("  Ctrl+C para detener. Navegador: http://%s:%d/" % (args.host, args.port))
    _say("")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        _say("\n[web] servidor detenido")
    finally:
        srv.server_close()


if __name__ == "__main__":
    main()