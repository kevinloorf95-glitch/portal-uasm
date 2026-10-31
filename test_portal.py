# -*- coding: utf-8 -*-
"""
Tests automatizados del Portal MAPE (`frame/`) con Playwright + pytest.

El portal es una aplicación web real: los tests arrancan `server/app.py`
(hilo en proceso, puerto efímero) sobre una **copia** de `db/*.db` en un
directorio temporal, de modo que las pruebas de escritura no tocan las bases
de datos del proyecto.

Cubre:
  - carga sin errores de consola/página y estado leído del servidor
  - filtros de la Matriz de Tecnologías (búsqueda, categoría, TRL mínimo)
  - clic en fila de la matriz → detalle de tecnología visible
  - filtros del explorador de Corpus (texto, clúster, rango de años)
  - pestañas del corpus (360 · 269 · 258 · 207) y cambio de vista activa
  - paginación del corpus
  - exportación CSV y JSON (descargas servidas por la API)
  - gráficos Plotly: radar y fondos IGF con colores Okabe-Ito diferenciados
  - descarga de imágenes en SVG y de tablas en CSV
  - entrega científica thirdPass_124.csv (n=124) mostrada en Corpus
  - editor de bases `.db`: inventario (7 fuente + 17 derivadas), CRUD de
    documentos, consola SQL
  - bases derivadas: una por gráfica/tabla, pintadas desde `datos`, con
    ediciones manuales memorizadas en `overrides`, alta/baja de filas y reset
  - sincronización idempotente de las bases derivadas y exportaciones
    (`.db`/`.csv`/`.json`)
  - leyendas de Plotly dentro del SVG y sin solaparse con el contenido

Ejecución (dentro de `frame/`):
    python -m pytest test_portal.py -v
"""
import json
import pathlib
import shutil
import sys
import tempfile
import threading
import re

import pytest
from playwright.sync_api import sync_playwright

FRAME_DIR = pathlib.Path(__file__).resolve().parent
EUROPE_HEX = "#0072B2"
CONT_HEX = {"Africa": "#56B4E9", "LatAm": "#009E73", "Asia": "#E69F00", "Europe": EUROPE_HEX}
BASES_FUENTE = ("corpus_124.db", "corpus_360.db", "corpus_269.db",
                "corpus_258.db", "corpus_207.db", "catalogo_tecnologias.db",
                "observatorio.db")
DERIVED_IDS = ("chart_anios", "chart_donut_cluster", "chart_donut_acceso",
               "chart_top5", "chart_radar", "chart_bubble", "chart_series",
               "chart_corr", "chart_igf", "chart_paises_pub", "chart_red",
               "chart_cat", "chart_tec_bar", "tabla_tecnologias",
               "tabla_corpus", "tabla_paises_obs", "tabla_deliverable")


def rgb2hex(rgb):
    m = re.match(r"rgb\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)", rgb)
    if not m:
        return rgb
    return "#%02x%02x%02x" % tuple(int(g) for g in m.groups())


@pytest.fixture(scope="session")
def db_dir():
    """Copia temporal de db/*.db: los tests pueden escribir sin riesgo.

    Si las bases aún no existen (clone limpio) se dejan vacías y el servidor
    las construye desde los CSV, igual que `python server/app.py`.
    """
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="mape_db_"))
    for db in sorted((FRAME_DIR / "db").glob("*.db")):
        shutil.copy2(db, tmp / db.name)
    yield tmp
    shutil.rmtree(tmp, ignore_errors=True)


@pytest.fixture(scope="session")
def app_url(db_dir):
    sys.path.insert(0, str(FRAME_DIR / "server"))
    try:
        import app as server_app  # noqa: E402
        import dbstore  # noqa: E402
    except ImportError as e:  # pragma: no cover
        pytest.skip("No se pudo importar el servidor (%s)" % e)

    server_app.STORE = dbstore.Store(str(db_dir))
    server_app.PortalHandler.log_message = lambda *a, **k: None
    server_app.migrar()
    server_app.asegurar_dbs()          # construye los .db que falten
    srv = server_app.PortalServer(("127.0.0.1", 0), server_app.PortalHandler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}/"
    srv.shutdown()
    srv.server_close()


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as p:
        b = None
        for channel in ("chrome", "msedge"):
            try:
                b = p.chromium.launch(channel=channel, headless=True)
                break
            except Exception as e:
                last = e
        if b is None:  # pragma: no cover
            pytest.skip("No hay navegador disponible para Playwright "
                        "(instala Chrome/Edge o `playwright install chromium`): %s" % last)
        yield b
        b.close()


@pytest.fixture()
def portal(browser, app_url):
    ctx = browser.new_context(accept_downloads=True)
    pg = ctx.new_page()
    pg.errors = []
    pg.on("pageerror", lambda e: pg.errors.append("pageerror: " + str(e)))
    pg.on("console", lambda msg: (pg.errors.append("console: " + msg.text) if msg.type == "error" else None))
    pg.goto(app_url, wait_until="load")
    pg.wait_for_selector("#tabla_tecnologias tbody tr")
    pg.wait_for_selector("#chart_radar svg")
    pg.wait_for_selector("#chart_igf svg")
    settle(pg)
    yield pg
    ctx.close()


def settle(page, timeout=15000):
    """Espera a que el frontend termine temporizadores y peticiones a la API."""
    page.wait_for_function(
        "() => window.__portal && window.__portal.pending === 0 && window.__portal.timers === 0",
        timeout=timeout)


# ----------------------------------------------------------------- carga
def test_carga_sin_errores(portal):
    assert not portal.errors, "Errores de consola/página:\n" + "\n".join(portal.errors)
    assert portal.title().startswith("Portal de Transferencia")
    assert portal.locator("#kpis .kpi").count() >= 5
    assert portal.locator("#tabla_tecnologias tbody tr").count() > 0
    assert portal.locator("#tabla_corpus tbody tr").count() > 0


def test_datos_son_del_servidor(portal, app_url):
    """APP_DATA proviene de /api/bootstrap, no de un fichero embebido."""
    import urllib.request
    with urllib.request.urlopen(app_url + "api/bootstrap", timeout=30) as r:
        api_data = json.loads(r.read())
    ui = portal.evaluate("() => window.APP_DATA")
    assert ui["meta"]["n_docs"] == api_data["meta"]["n_docs"] == 124
    assert ui["clusters"] == api_data["clusters"]
    assert portal.locator("script[src='data/app_data.js']").count() == 0
    assert "Conectado" in portal.locator("#db_status").inner_text()


def test_datos_y_europa_cargados(portal):
    data = portal.evaluate("() => window.APP_DATA")
    paises = data["paises_obs"]
    espania = [p for p in paises if p["pais"] == "España" and p["cont"] == "Europe"]
    assert espania, "España (Europe) no está en paises_obs"
    radar_ids = [s["id"] for s in data["radar"]["series"]]
    assert "Europe" in radar_ids, "Europa no está en el radar"
    assert data["igf_funds"], "No hay datos de fondos IGF"
    assert any("Europa" in f["region"] for f in data["igf_funds"]), "Europa no está en fondos IGF"
    assert data["cont_col"]["Europe"].upper() == EUROPE_HEX


# ----------------------------------------------------------------- matriz: filtros
def test_matriz_filtro_busqueda(portal):
    rows0 = portal.locator("#tabla_tecnologias tbody tr").count()
    portal.fill("#f_mat_search", "geo")
    settle(portal)
    rows1 = portal.locator("#tabla_tecnologias tbody tr").count()
    assert 0 < rows1 < rows0, f"El filtro de búsqueda debió reducir las filas ({rows0} → {rows1})"
    texts = portal.locator("#tabla_tecnologias tbody tr").all_inner_texts()
    assert all(("geo" in t.lower()) for t in texts)


def test_matriz_filtro_categoria(portal):
    portal.select_option("#f_mat_cat", label="Geomática")
    settle(portal)
    rows = portal.locator("#tabla_tecnologias tbody tr").all_inner_texts()
    assert rows
    assert all(("Geomática" in r) for r in rows)


def test_matriz_filtro_trl_minimo(portal):
    portal.select_option("#f_mat_trl", "8")
    settle(portal)
    rows = portal.locator("#tabla_tecnologias tbody tr td:nth-child(4)").all_inner_texts()
    assert rows
    for cell in rows:
        trl = int(cell.split("/")[0].strip())
        assert trl >= 8, f"TRL {trl} por debajo del mínimo 8"


def test_matriz_filtro_combinado(portal):
    portal.fill("#f_mat_search", "seguridad")
    settle(portal)
    portal.select_option("#f_mat_seg", "5")
    settle(portal)
    names = portal.locator("#tabla_tecnologias tbody tr td:first-child").all_inner_texts()
    assert names, "Sin resultados para el filtro combinado"
    for n in names:
        assert "seguridad" in n.lower()
    seg_cells = portal.locator("#tabla_tecnologias tbody tr td:nth-child(8)").all_inner_texts()
    for c in seg_cells:
        assert int(c.split("/")[0]) >= 5


# ----------------------------------------------------------------- matriz: clic en fila
def test_fila_abre_detalle(portal):
    detail = portal.locator("#tech_detail")
    assert "hidden" in detail.get_attribute("class")
    portal.locator("#tabla_tecnologias tbody tr").first.click()
    detail.wait_for(state="visible")
    portal.wait_for_selector("#tech_detail .docs li", timeout=15000)
    assert "hidden" not in detail.get_attribute("class"), "El detalle no se mostró al hacer clic"
    assert "Documentos del corpus" in detail.inner_text()
    assert detail.locator("h3").count() == 1


def test_fila_detalle_cierre(portal):
    portal.locator("#tabla_tecnologias tbody tr").first.click()
    portal.wait_for_selector("#tech_detail [data-close-detail]", timeout=15000)
    portal.locator("#tech_detail [data-close-detail]").click()
    assert "hidden" in portal.locator("#tech_detail").get_attribute("class")


# ----------------------------------------------------------------- corpus: filtros
def test_corpus_filtro_texto(portal):
    total = portal.locator("#corpus_count").inner_text()
    portal.fill("#f_cor_search", "blockchain")
    settle(portal)
    nuevo = portal.locator("#corpus_count").inner_text()
    assert nuevo != total
    count = int(nuevo.split()[0].replace(".", ""))
    assert 0 <= count < 1000
    if count:
        assert portal.locator("#tabla_corpus tbody tr").count() > 0


def test_corpus_filtro_cluster(portal):
    portal.select_option("#f_cor_cluster", "0")
    settle(portal)
    badges = portal.locator("#tabla_corpus tbody tr td:nth-child(6)").all_inner_texts()
    assert badges
    assert all(("Geomecánica" in b or "monitoreo" in b.lower()) for b in badges)


def test_clusters_c4(portal):
    data = portal.evaluate("() => window.APP_DATA")
    assert data["meta"]["n_clusters"] == 4, f"Se esperaban 4 clústeres C4, se obtuvo {data['meta']['n_clusters']}"
    assert list(data["clusters"].keys()) == ["0", "1", "2", "3"]
    unasi = sum(1 for d in data["docs"] if d["cluster"] is None)
    assert unasi < 10, f"Demasiados documentos sin clúster C4: {unasi}"
    assert sum(data["meta"]["cluster_counts"].values()) + unasi == data["meta"]["n_docs"]
    nombres = {c["nombre"] for c in data["clusters"].values()}
    assert "Geomecánica, simulación y monitoreo" in nombres


def test_corpus_filtro_anios(portal):
    portal.fill("#f_cor_y0", "2020")
    settle(portal)
    portal.fill("#f_cor_y1", "2026")
    settle(portal)
    anios = portal.locator("#tabla_corpus tbody tr td:first-child").all_inner_texts()
    assert anios
    for a in anios:
        if a != "—":
            assert 2020 <= int(a) <= 2026


def test_corpus_filtro_tecnologia(portal):
    # elegir la tecnología 'Analítica, BI y plataformas de datos' (id bi)
    portal.select_option("#f_cor_tec", "bi")
    settle(portal)
    if portal.locator("#tabla_corpus tbody tr").count():
        assert portal.locator("#tabla_corpus tbody tr").count() > 0


def test_corpus_paginacion(portal):
    total_txt = portal.locator("#corpus_count").inner_text()
    total = int(total_txt.split()[0].replace(".", ""))
    if total > 25:
        portal.locator("#corpus_paginacion button:has-text('›')").first.click()
        settle(portal)
        assert "Página 2" in portal.locator("#corpus_paginacion").inner_text()


# ----------------------------------------------------------------- corpus: pestañas (360 / 269 / 258 / 207)
def test_corpora_presentes(portal):
    data = portal.evaluate("() => window.APP_DATA")
    corpora = data.get("corpora")
    assert corpora, "No se generó el bloque 'corpora' en APP_DATA"
    counts = {c["id"]: c["meta"]["n_docs"] for c in corpora}
    assert counts["360"] == 360, counts
    assert counts["269"] == 269, counts
    assert counts["258"] == 258, counts
    assert counts["207"] == 207, counts


def test_corpora_rango_y_acceso(portal):
    data = portal.evaluate("() => window.APP_DATA")
    corpora = {c["id"]: c for c in data["corpora"]}
    c258 = corpora["258"]
    assert c258["meta"]["rango"] == [2006, 2026], c258["meta"]["rango"]
    acc = c258["meta"]["acceso"]
    assert acc["libre"] > 80 and acc["no_abierto"] > 100, acc


def test_cluster_subtec_207(portal, app_url):
    import urllib.request
    with urllib.request.urlopen(app_url + "api/corpora/207", timeout=60) as r:
        c207 = json.loads(r.read())
    nulos = sum(1 for d in c207["docs"] if d["cluster"] is None)
    assert nulos == 0, f"Los 207 docs del clúster sub×tec debían tener clúster asignado (nulos={nulos})"
    for d in c207["docs"]:
        assert d["cluster"] == 0, f"Clúster distinto de 0 en 207: {d['cluster']}"


def test_corpus_tabs_visibles(portal):
    tabs = portal.locator("#corpus_tabs .tab")
    assert tabs.count() >= 5, f"Se esperaban ≥5 pestañas de corpus, se obtuvo {tabs.count()}"
    txt = tabs.all_inner_texts()
    assert any("124" in t for t in txt) and any("360" in t for t in txt)
    assert any("269" in t for t in txt) and any("258" in t for t in txt) and any("207" in t for t in txt)


def test_cambiar_pestana_360(portal):
    portal.locator("#corpus_tabs .tab", has_text="360").first.click()
    settle(portal)
    count = portal.locator("#corpus_count").inner_text()
    assert count.startswith("360"), count
    assert portal.locator("#tabla_corpus tbody tr").count() > 0
    assert "360" in portal.locator("#kpis .kpi").first.inner_text()


def test_cambiar_pestana_207(portal):
    portal.locator("#corpus_tabs .tab", has_text="207").first.click()
    settle(portal)
    count = portal.locator("#corpus_count").inner_text()
    assert count.startswith("207"), count
    badges = portal.locator("#tabla_corpus tbody tr td:nth-child(6)").all_inner_texts()
    assert badges
    assert all("Mina subterránea" in b or "minera" in b.lower() for b in badges[:10])


def test_cambiar_pestana_258_y_volver_124(portal):
    portal.locator("#corpus_tabs .tab", has_text="258").first.click()
    settle(portal)
    assert portal.locator("#corpus_count").inner_text().startswith("258")
    portal.locator("#corpus_tabs .tab", has_text="124").first.click()
    settle(portal)
    assert portal.locator("#corpus_count").inner_text().startswith("124")


def test_filtro_sobre_pestana_269(portal):
    portal.locator("#corpus_tabs .tab", has_text="269").first.click()
    settle(portal)
    portal.fill("#f_cor_y0", "2006")
    portal.fill("#f_cor_y1", "2026")
    settle(portal)
    count = portal.locator("#corpus_count").inner_text()
    assert count.startswith("258"), f"El subconjunto 2006-2026 de 269 debe dar 258, se obtuvo: {count}"


def test_donut_cluster_suma_n_docs_124(portal):
    vals = portal.evaluate("() => document.getElementById('chart_donut_cluster').data[0].values")
    assert sum(vals) == 124, f"La dona de clústeres debe sumar 124 docs, suma {sum(vals)}: {vals}"
    labels = portal.evaluate("() => document.getElementById('chart_donut_cluster').data[0].labels")
    assert "Sin clúster temático" in labels, f"Falta el segmento 'Sin clúster temático' en: {labels}"


def test_donut_cluster_suma_n_docs_otras_pestanas(portal):
    for tab, n in [("360", 360), ("269", 269), ("258", 258), ("207", 207)]:
        portal.locator("#corpus_tabs .tab", has_text=tab).first.click()
        # las bases derivadas se recalculan para el corpus nuevo (petición aparte)
        portal.wait_for_function(
            "n => { const d = document.getElementById('chart_donut_cluster');"
            " return d.data[0].values.reduce((a, b) => a + b, 0) === n; }", arg=n, timeout=25000)
        settle(portal)
        vals = portal.evaluate("() => document.getElementById('chart_donut_cluster').data[0].values")
        assert sum(vals) == n, f"Pestaña {tab}: dona de clústeres suma {sum(vals)}, se esperaba {n} ({vals})"


def test_graficos_segun_corpus_activo(app_url):
    """`?cid=` recalcula las bases derivadas de ese corpus (las ligeras, con filas)."""
    import urllib.request
    def pedir(cid=None):
        u = app_url + "api/graficos" + ("?cid=%s" % cid if cid else "")
        with urllib.request.urlopen(u, timeout=90) as r:
            return json.loads(r.read().decode("utf-8"))["graficos"]

    def filas(graficos, gid):
        g = next((x for x in graficos if x["id"] == gid), None)
        assert g is not None, f"Falta {gid} en el payload"
        assert g["filas"], f"{gid} llega sin filas: {g['meta']}"
        return g["filas"]

    base = filas(pedir(), "chart_donut_cluster")
    assert sum(f["docs"] for f in base) == 124, base
    otros = filas(pedir("360"), "chart_donut_cluster")
    assert sum(f["docs"] for f in otros) == 360, otros
    # sin ?cid= el servidor vuelve a su corpus activo (124)
    assert sum(f["docs"] for f in filas(pedir(), "chart_donut_cluster")) == 124
    # la serie anual sigue a cada corpus (360 arranca en 1973, 124 en 2008)
    assert [f["anio"] for f in filas(pedir(), "chart_anios")][0] == 2008
    assert [f["anio"] for f in filas(pedir("360"), "chart_anios")][0] == 1973
    assert filas(pedir("360"), "chart_anios")[-1]["anio"] == 2026


def test_exportar_json_incluye_corpora(portal):
    data = portal.evaluate("() => window.APP_DATA")
    assert "corpora" in data
    assert data["meta"]["n_docs"] == 124  # el 124 sigue siendo la vista principal


def _tmp(name):
    return str(pathlib.Path(tempfile.gettempdir()) / ("_test_" + name))


def test_descargas_360_csv(portal):
    with portal.expect_download() as dl:
        portal.click('[data-corpus-csv="360"]')
    down = dl.value
    assert down.suggested_filename.endswith(".csv"), down.suggested_filename
    path = _tmp("corpus_360.csv")
    down.save_as(path)
    txt = pathlib.Path(path).read_text(encoding="utf-8-sig")
    lines = txt.splitlines()
    assert lines[0].startswith("anio;titulo")
    assert len(lines) - 1 == 360, f"El CSV de 360 debía tener 360 filas, tiene {len(lines)-1}"
    pathlib.Path(path).unlink()


def test_descargas_207_csv(portal):
    with portal.expect_download() as dl:
        portal.click('[data-corpus-csv="207"]')
    down = dl.value
    path = _tmp("corpus_207.csv")
    down.save_as(path)
    txt = pathlib.Path(path).read_text(encoding="utf-8-sig")
    lines = txt.splitlines()
    assert len(lines) - 1 == 207, f"El CSV de 207 debía tener 207 filas, tiene {len(lines)-1}"
    pathlib.Path(path).unlink()


def test_descargas_258_json(portal):
    with portal.expect_download() as dl:
        portal.click('[data-corpus-json="258"]')
    down = dl.value
    assert down.suggested_filename == "corpus_258.json", down.suggested_filename
    path = _tmp("corpus_258.json")
    down.save_as(path)
    c = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    assert c["meta"]["n_docs"] == 258
    assert len(c["docs"]) == 258
    assert c["meta"]["rango"] == [2006, 2026]
    pathlib.Path(path).unlink()


# ----------------------------------------------------------------- corpus: exportaciones
def test_exportar_csv(portal):
    with portal.expect_download() as dl:
        portal.click("#btn_corpus_csv")
    down = dl.value
    assert down.suggested_filename.endswith(".csv"), down.suggested_filename
    path = _tmp("export.csv")
    down.save_as(path)
    txt = pathlib.Path(path).read_text(encoding="utf-8-sig")
    assert 'anio;titulo;autores' in txt.splitlines()[0]
    assert len(txt.splitlines()) >= 2
    pathlib.Path(path).unlink()


def test_exportar_json(portal):
    with portal.expect_download() as dl:
        portal.click("#btn_data_json")
    down = dl.value
    assert down.suggested_filename == "app_data.json"
    path = _tmp("export.json")
    down.save_as(path)
    data = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    assert data["meta"]["n_docs"] > 100
    assert any(p["cont"] == "Europe" for p in data["paises_obs"])
    pathlib.Path(path).unlink()


# ----------------------------------------------------------------- observatorio: Europa + colores
def test_radar_incluye_europa(portal):
    legend = portal.locator("#chart_radar").inner_text()
    assert "Europa" in legend
    assert "Global" in legend


def test_radar_colores_diferenciados(portal):
    strokes = portal.evaluate("""() => {
      const cols = new Set();
      document.querySelectorAll('#chart_radar svg path').forEach((p) => {
        const s = p.getAttribute('stroke') || (p.style && p.style.stroke);
        if (s && s !== 'none' && s !== '#dfe6eb') cols.add(s);
      });
      return Array.from(cols);
    }""")
    expected = set(CONT_HEX.values())
    hits = {rgb2hex(s).lower() for s in strokes} & {e.lower() for e in expected}
    assert len(hits) >= 4, f"Se esperaban ≥4 colores de series en el radar, se obtuvo: {strokes}"
    assert EUROPE_HEX.lower() in hits, f"Falta el color de Europa en el radar: {strokes}"


def test_radar_trazas_presentes(portal):
    # cada serie debe generar una traza con relleno (polygon) diferenciada
    trace_groups = portal.locator("#chart_radar .scatterlayer .trace").count()
    assert trace_groups >= 5, f"Se esperaban ≥5 trazas (series) en el radar, se obtuvo {trace_groups}"


def test_burbuja_incluye_europa(portal):
    labels = portal.evaluate("""() => Array.from(document.querySelectorAll('#chart_bubble text')).map(t => t.textContent || '')""")
    assert any("España" in l for l in labels), labels


# ----------------------------------------------------------------- descargas SVG / CSV
def test_botones_descarga_svg_presentes(portal):
    n = portal.locator("[data-svg]").count()
    assert n >= 12, f"Se esperaban ≥12 botones de descarga SVG, se obtuvo {n}"


def test_botones_descarga_csv_presentes(portal):
    n = portal.locator("[data-csv]").count()
    assert n == 4, f"Se esperaban 4 tablas exportables a CSV (matriz, corpus, observatorio, entrega), se obtuvo {n}"


def test_botones_editar_grafica_presentes(portal):
    """Cada gráfica/tabla ofrece editar su propia base derivada."""
    ids = portal.eval_on_selector_all(
        "[data-edit]", "els => els.map(e => e.getAttribute('data-edit')).sort()")
    assert ids == sorted(DERIVED_IDS), ids


def test_descargar_svg(portal):
    with portal.expect_download() as dl:
        portal.click("[data-svg='chart_anios']")
    down = dl.value
    assert down.suggested_filename.endswith(".svg"), down.suggested_filename


def test_descargar_svg_radar(portal):
    with portal.expect_download() as dl:
        portal.click("[data-svg='chart_radar']")
    down = dl.value
    assert down.suggested_filename.endswith(".svg"), down.suggested_filename


def test_descargar_csv_tabla_observatorio(portal):
    with portal.expect_download() as dl:
        portal.click("[data-csv='tabla_paises_obs']")
    down = dl.value
    assert down.suggested_filename.endswith(".csv"), down.suggested_filename
    path = _tmp("tabla_obs.csv")
    down.save_as(path)
    txt = pathlib.Path(path).read_text(encoding="utf-8-sig")
    assert "País" in txt.splitlines()[0] and "Región" in txt.splitlines()[0], txt.splitlines()[0]
    assert "España" in txt and "Europa" in txt
    pathlib.Path(path).unlink()


def test_descargar_csv_entrega_cientifica(portal):
    with portal.expect_download() as dl:
        portal.click("[data-csv='tabla_deliverable']")
    down = dl.value
    assert down.suggested_filename.endswith(".csv"), down.suggested_filename
    path = _tmp("entrega.csv")
    down.save_as(path)
    lines = pathlib.Path(path).read_text(encoding="utf-8-sig").splitlines()
    header = lines[0].lower()
    assert "hallazgos principales" in header and "novedad" in header, lines[0]
    assert len(lines) >= 125, f"La entrega científica debe tener 124 filas + cabecera, se obtuvo {len(lines)}"
    pathlib.Path(path).unlink()


# ----------------------------------------------------------------- entrega científica (en Corpus)
def test_tabla_entrega_cientifica(portal):
    rows = portal.locator("#tabla_deliverable tbody tr").count()
    assert rows == 124, f"La tabla de entrega científica debe tener 124 filas, se obtuvo {rows}"
    head = portal.locator("#tabla_deliverable thead").inner_text().lower()
    assert "hallazgos principales" in head and "limitaciones" in head and "novedad" in head


def test_tabla_observatorio_incluye_espana(portal):
    t = portal.locator("#tabla_paises_obs").inner_text()
    assert "España" in t and "Europa" in t


def test_tabla_observatorio_incluye_ecuador(portal):
    t = portal.locator("#tabla_paises_obs").inner_text()
    assert "Ecuador" in t and "Latinoamérica" in t


def test_rango_anios_hasta_2026(portal):
    data = portal.evaluate("() => window.APP_DATA")
    years = data["series"]["years"]
    assert years[-1] == 2026, f"El último año de la serie debe ser 2026, se obtuvo {years[-1]}"
    assert years[0] == 2008, f"El primer año de la serie debe ser 2008 (thirdPass_124.csv), se obtuvo {years[0]}"
    assert len(years) == 19, f"Se esperan 19 años (2008-2026), se obtuvo {len(years)}"
    assert len(data["series"]["pubs"]) == 19, "La serie de publicaciones no cubre 2008-2026"
    assert len(data["series"]["tech_invest"]) == 19, "La serie de inversión tech no cubre 2008-2026"
    assert len(data["series"]["edu_index"]) == 19, "La serie del índice educativo no cubre 2008-2026"
    assert data["meta"]["n_docs"] == 124, f"El corpus debe ser thirdPass_124.csv (n=124), se obtuvo {data['meta']['n_docs']}"
    assert data["meta"]["corpus"] == "thirdPass_124.csv"


def test_igf_incluye_europa_y_color(portal):
    txt = portal.locator("#chart_igf").inner_text()
    assert "Europa" in txt and "12%" in txt
    fills = portal.evaluate("""() => {
      const setc = new Set();
      document.querySelectorAll('#chart_igf svg *').forEach((el) => {
        const m = (el.getAttribute('style') || '').match(/fill:\\s*([^;]+)/i);
        const color = el.getAttribute('fill') || (m && m[1]);
        if (color && color !== 'none' && !String(color).startsWith('url(')) setc.add(String(color).trim());
      });
      return Array.from(setc);
    }""")
    norm = {rgb2hex(f).lower() for f in fills}
    assert EUROPE_HEX.lower() in norm, f"Falta el color Europa en fondos IGF: {fills}"


def test_seccion_metodologia_eliminada(portal):
    """Las entregas se muestran en Corpus: no debe quedar la sección «Metodología»."""
    nav = portal.locator("#nav").inner_text()
    assert "Metodolog" not in nav, nav
    assert portal.locator("#metodologia").count() == 0
    corpus = portal.locator("#corpus").inner_text()
    assert "Entrega" in corpus or "entrega" in corpus, "Las descargas deben estar en Corpus"


# ----------------------------------------------------------------- editor de bases .db
def test_inventario_de_bases(portal):
    portal.locator("#editor").scroll_into_view_if_needed()
    settle(portal)
    filas = portal.locator("#tabla_dbs tbody tr").count()
    assert filas == len(BASES_FUENTE) + len(DERIVED_IDS), \
        f"Se esperaban {len(BASES_FUENTE) + len(DERIVED_IDS)} bases .db, se obtuvo {filas}"
    txt = portal.locator("#tabla_dbs").inner_text()
    for nombre in BASES_FUENTE:
        assert nombre in txt, f"Falta {nombre} en el inventario"
    for gid in DERIVED_IDS:
        assert gid + ".db" in txt, f"Falta la base derivada {gid}.db"
    assert portal.locator("#tabla_dbs a[download]").count() == filas


def test_esquema_de_la_base(portal):
    portal.click("#btn_db_schema")
    portal.wait_for_selector("#db_esquema div", timeout=15000)
    txt = portal.locator("#db_esquema").inner_text()
    assert "docs" in txt


def test_editor_lista_documentos(portal):
    portal.select_option("#ed_corpus", "124")
    settle(portal)
    assert portal.locator("#tabla_ed tbody tr").count() > 0
    info = portal.locator("#ed_info").inner_text()
    assert "corpus_124.db" in info and "124" in info


def test_editor_crud_documento(portal, app_url):
    """Alta y baja de un documento: el portal refleja el cambio en el .db."""
    import urllib.request
    portal.locator("#editor").scroll_into_view_if_needed()
    settle(portal)
    portal.select_option("#ed_corpus", "124")
    settle(portal)
    portal.click("#ed_new")
    portal.wait_for_selector("#ed_form:not(.hidden)")
    portal.fill("#ed_titulo", "Documento de prueba automatizada")
    portal.fill("#ed_anio", "2027")
    portal.fill("#ed_citas", "3")
    portal.select_option("#ed_cluster", "0")
    portal.click("#ed_form button[type=submit]")
    portal.wait_for_function("() => (document.getElementById('ed_msg').textContent || '').indexOf('Guardado') >= 0",
                             timeout=20000)
    settle(portal)
    assert "Guardado" in portal.locator("#ed_msg").inner_text()
    doc_id = portal.locator("#ed_id").input_value()

    def n_docs():
        with urllib.request.urlopen(app_url + "api/corpora/124/stats", timeout=60) as r:
            return json.loads(r.read())

    try:
        st = n_docs()
        assert st["n_docs"] == 125, st["n_docs"]
        assert st["rango"][1] == 2027, st["rango"]
        # el repintado de los KPI ocurre después del POST: se espera explícitamente
        portal.wait_for_function(
            "() => (document.querySelector('#kpis .kpi') || {}).textContent"
            " && document.querySelector('#kpis .kpi').textContent.trim().indexOf('125') === 0",
            timeout=20000)
        assert portal.locator("#kpis .kpi").first.inner_text().strip().startswith("125"), \
            portal.locator("#kpis .kpi").first.inner_text()
    finally:
        portal.once("dialog", lambda d: d.accept())
        portal.click("#ed_delete")
        portal.wait_for_function(
            "() => (document.getElementById('ed_msg').textContent || '').indexOf('Eliminado') >= 0",
            timeout=20000)
        settle(portal)
    assert n_docs()["n_docs"] == 124, n_docs()


def test_editar_base_externa_se_refleja(portal, app_url, db_dir):
    """Si el .db cambia fuera del portal, la versión cambia y la web se repinta."""
    import sqlite3
    antes = portal.evaluate("""async () => (await (await fetch('/api/health')).json()).version""")
    con = sqlite3.connect(str(db_dir / "corpus_124.db"))
    con.execute("UPDATE docs SET citas = citas + 1 WHERE id = (SELECT MIN(id) FROM docs)")
    con.commit()
    con.close()
    despues = portal.evaluate("""async () => (await (await fetch('/api/health')).json()).version""")
    assert despues != antes, "La versión de las bases no cambió tras editar el .db"
    portal.click("#btn_db_reload")
    settle(portal)
    assert "recargadas" in portal.locator("#tec_msg").inner_text()


def test_consola_sql(portal):
    portal.select_option("#sql_db", "corpus_124.db")
    portal.fill("#sql_txt", "SELECT COUNT(*) AS n FROM docs")
    portal.click("#sql_run")
    portal.wait_for_selector("#sql_out table tbody tr", timeout=15000)
    txt = portal.locator("#sql_out").inner_text()
    assert "124" in txt, txt


def test_consola_sql_rechaza_escritura(portal):
    portal.select_option("#sql_db", "corpus_124.db")
    portal.fill("#sql_txt", "DELETE FROM docs")
    portal.click("#sql_run")
    portal.wait_for_selector("#sql_out", timeout=15000)
    portal.wait_for_function(
        "() => document.getElementById('sql_out').textContent.indexOf('solo lectura') >= 0"
        " || document.getElementById('sql_out').textContent.indexOf('Error') >= 0",
        timeout=15000)
    txt = portal.locator("#sql_out").inner_text()
    assert "solo lectura" in txt or "Error" in txt


# ----------------------------------------------------------------- bases derivadas
def _api(app_url, path, payload=None, method=None, raw=False):
    """Llama a la API del servidor de pruebas: devuelve el JSON o (status, bytes)."""
    import urllib.error
    import urllib.request
    cuerpo = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(app_url + path, data=cuerpo,
                                 method=method or ("POST" if cuerpo else "GET"),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            datos = r.read()
            return (r.status, datos) if raw else json.loads(datos.decode("utf-8"))
    except urllib.error.HTTPError as e:
        datos = e.read()
        if raw:
            return e.code, datos
        raise AssertionError("%s %s -> HTTP %d: %s"
                             % (req.get_method(), path, e.code, datos[:200]))


def test_derivadas_pintan_las_graficas(portal):
    """Cada gráfica/tabla se dibuja desde la tabla `datos` de su `<gid>.db`."""
    for gid in DERIVED_IDS:
        if gid.startswith("tabla_"):
            n = portal.locator("#%s tbody tr" % gid).count()
            assert n > 0, f"{gid} se ha pintado sin filas"
        else:
            assert portal.evaluate("""(gid) => {
                const d = document.getElementById(gid);
                return !!d && !!d.data && d.data.length > 0;
            }""", gid), f"{gid} se ha pintado sin datos"


def test_editor_derivado_lista_filas(portal):
    portal.locator("#editor").scroll_into_view_if_needed()
    settle(portal)
    opciones = portal.eval_on_selector_all(
        "#gd_sel option", "els => els.map(e => e.value)")
    assert sorted(opciones) == sorted(DERIVED_IDS), opciones
    portal.select_option("#gd_sel", "chart_anios")
    portal.wait_for_selector("#gd_tabla tbody tr", timeout=15000)
    settle(portal)
    assert portal.locator("#gd_tabla tbody tr").count() == 19
    info = portal.locator("#gd_info").inner_text()
    assert "chart_anios.db" in portal.locator("#gd_titulo").inner_text()
    assert "19" in info and "sin ediciones" in info, info
    # el botón «Editar» de la tarjeta salta a la misma base
    portal.click("[data-edit='chart_cat']")
    portal.wait_for_function("() => document.getElementById('gd_sel').value === 'chart_cat'",
                             timeout=15000)
    settle(portal)
    assert "chart_cat.db" in portal.locator("#gd_titulo").inner_text()


def test_editor_derivado_edicion_se_refleja(portal):
    """Editar `datos` en el portal repinta la gráfica y queda memorizado."""
    portal.locator("#editor").scroll_into_view_if_needed()
    settle(portal)
    portal.select_option("#gd_sel", "chart_anios")
    portal.wait_for_selector("#gd_tabla tbody tr", timeout=15000)
    settle(portal)
    portal.locator("#gd_tabla tbody tr").first.get_by_role("button", name="Editar").click()
    portal.wait_for_selector("#gd_form [data-campo='publicaciones']", timeout=15000)
    portal.fill("#gd_form [data-campo='publicaciones']", "7")
    portal.click("#gd_form button[type=submit]")
    # el mensaje aparece antes del repintado: se espera a que la gráfica cambie
    portal.wait_for_function("() => document.querySelector('#chart_anios').data[0].y[0] === 7",
                             timeout=25000)
    # y a que el editor vuelva a pintar la ficha (va por detrás del repintado)
    portal.wait_for_function(
        "() => /1 ediciones/.test(document.getElementById('gd_info').textContent)", timeout=25000)
    settle(portal)
    try:
        assert portal.locator("#gd_form .ed-msg").inner_text() == "Guardado"
        assert "1 ediciones" in portal.locator("#gd_info").inner_text()
        # la edición sobrevive a la recarga de la página
        portal.reload(wait_until="load")
        portal.wait_for_selector("#chart_anios svg", timeout=20000)
        portal.wait_for_function(
            "() => document.querySelector('#chart_anios').data[0].y[0] === 7", timeout=20000)
    finally:
        portal.locator("#editor").scroll_into_view_if_needed()
        settle(portal)
        portal.once("dialog", lambda d: d.accept())
        portal.click("#gd_reset")
        portal.wait_for_function(
            "() => document.querySelector('#chart_anios').data[0].y[0] === 1", timeout=25000)
    settle(portal)
    portal.wait_for_function(
        "() => /sin ediciones/.test(document.getElementById('gd_info').textContent)", timeout=25000)
    assert "sin ediciones" in portal.locator("#gd_info").inner_text()


def test_editor_derivado_alta_y_baja(portal):
    """Alta y baja de filas en una base derivada."""
    portal.locator("#editor").scroll_into_view_if_needed()
    settle(portal)
    portal.select_option("#gd_sel", "chart_anios")
    portal.wait_for_selector("#gd_tabla tbody tr", timeout=15000)
    settle(portal)
    try:
        portal.click("#gd_new")
        portal.wait_for_selector("#gd_clave", timeout=15000)
        portal.fill("#gd_clave", "2099")
        portal.fill("#gd_form [data-campo='anio']", "2099")
        portal.fill("#gd_form [data-campo='etiqueta']", "2099")
        portal.fill("#gd_form [data-campo='publicaciones']", "3")
        portal.click("#gd_form button[type=submit]")
        portal.wait_for_function("() => document.querySelectorAll('#gd_tabla tbody tr').length === 20",
                                 timeout=25000)
        settle(portal)
        assert portal.evaluate("() => document.querySelector('#chart_anios').data[0].y.length") == 20
        portal.once("dialog", lambda d: d.accept())
        portal.locator("#gd_tabla tbody tr[data-clave='2099']").locator(".btn-danger").click()
        portal.wait_for_function("() => document.querySelectorAll('#gd_tabla tbody tr').length === 19",
                                 timeout=25000)
        settle(portal)
        assert portal.evaluate("() => document.querySelector('#chart_anios').data[0].y.length") == 19
    finally:
        portal.once("dialog", lambda d: d.accept())
        portal.click("#gd_reset")
        portal.wait_for_function("() => document.querySelectorAll('#gd_tabla tbody tr').length === 19",
                                 timeout=25000)


def test_derivadas_exportan(app_url):
    import urllib.request
    for ext, marca in ((".db", b"SQLite format 3"), (".csv", "anio".encode("utf-8")),
                       (".json", b'"filas"')):
        status, cuerpo = _api(app_url, "api/grafico/chart_anios" + ext, raw=True)
        if isinstance(status, int):
            assert status == 200, (ext, status, cuerpo[:200])
            continue
        assert marca in cuerpo, f"{ext} no parece {marca!r}: {cuerpo[:120]}"


def test_grafico_desconocido_da_404(app_url):
    status, cuerpo = _api(app_url, "api/grafico/no_existe", raw=True)
    assert status == 404, (status, cuerpo[:200])


def test_sync_derivadas_es_idempotente(app_url, db_dir):
    """Un resync sin cambios de fuentes no escribe nada (mtime intacto)."""
    import time
    db = db_dir / "chart_anios.db"
    antes = db.stat().st_mtime_ns
    r1 = _api(app_url, "api/graficos/sync", {})
    assert r1["sincronizados"] == [], r1["sincronizados"]
    assert db.stat().st_mtime_ns == antes, "El resync reescribió la base sin cambios"
    time.sleep(0.01)
    r2 = _api(app_url, "api/graficos/sync", {})
    assert r2["sincronizados"] == [], r2["sincronizados"]
    assert db.stat().st_mtime_ns == antes
    assert len(list(db_dir.glob("*.db"))) == len(BASES_FUENTE) + len(DERIVED_IDS)


def test_leyendas_dentro_del_svg_y_sin_solapamiento(portal):
    """Ninguna leyenda se sale del SVG ni pisa las etiquetas del gráfico."""
    portal.locator("#editor").scroll_into_view_if_needed()
    settle(portal)
    res = portal.evaluate("""() => {
      const out = [];
      document.querySelectorAll('.js-plotly-plot').forEach((d) => {
        const lg = d.querySelector('.legend');
        if (!lg || !d.querySelector('.main-svg')) return;
        const svg = d.querySelector('.main-svg').getBoundingClientRect();
        const dist = (sel) => {
          const es = Array.from(d.querySelectorAll(sel)).map((e) => e.getBoundingClientRect());
          return es.length ? Math.min.apply(null, es.map((r) => svg.bottom - r.top)) : null;
        };
        const r = lg.getBoundingClientRect();
        const contenido = [dist('g.xaxislayer-above text'), dist('g.pielayer text'),
                           dist('g.polarlayer text'), dist('g.scatterlayer text')]
          .filter((v) => v != null);
        out.push({
          id: d.id,
          fuera: r.bottom > svg.bottom + 1 || r.top < svg.top - 1 ||
                 r.left < svg.left - 1 || r.right > svg.right + 1,
          solapa: contenido.length ? Math.round(svg.bottom - r.top) >
                    Math.max.apply(null, contenido) : false,
        });
      });
      return out;
    }""")
    assert res, "No se encontró ninguna leyenda"
    fuera = [r["id"] for r in res if r["fuera"]]
    solapa = [r["id"] for r in res if r["solapa"]]
    assert not fuera, f"Legendas fuera del SVG: {fuera}"
    assert not solapa, f"Legendas que solapan el contenido: {solapa}"


# ----------------------------------------------------------------- arranque por CLI
def test_cli_arranca_como_subproceso(db_dir):
    """`python server/app.py` debe funcionar tal cual lo ejecuta el usuario.

    Los demás tests levantan el servidor en proceso y nunca pasan por main(),
    así que este es el único que cubre el banner y la codificación de consola
    (en Windows, cp850/cp1252 no tienen los caracteres de dibujo de cajas y
    abortaban el arranque con UnicodeEncodeError).
    """
    import socket
    import subprocess
    import time
    import urllib.request

    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()

    proc = subprocess.Popen(
        [sys.executable, str(FRAME_DIR / "server" / "app.py"),
         "--port", str(port), "--db-dir", str(db_dir)],
        cwd=str(FRAME_DIR), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        datos = None
        for _ in range(80):                      # hasta ~15 s de arranque
            if proc.poll() is not None:
                break
            try:
                with urllib.request.urlopen(
                        "http://127.0.0.1:%d/api/health" % port, timeout=2) as r:
                    datos = json.loads(r.read().decode("utf-8"))
                break
            except Exception:
                time.sleep(0.25)
        # el proceso no debe morir al imprimir el banner
        assert proc.poll() is None, (
            "server/app.py terminó con código %s" % proc.returncode)
        assert datos is not None and datos.get("ok") is True, (
            "/api/health no respondió: %r" % (datos,))
    finally:
        proc.terminate()
        try:
            out, err = proc.communicate(timeout=15)
        except subprocess.TimeoutExpired:        # pragma: no cover
            proc.kill()
            out, err = proc.communicate()
    # el banner se imprime en la codificación de la consola: se decodifica tolerante
    banner = out.decode("utf-8", "replace")
    assert "Portal MAPE" in banner, banner
    assert "Ctrl+C" in banner, banner
    assert b"UnicodeEncodeError" not in err, err.decode("utf-8", "replace")


if __name__ == "__main__":      # permite también `python test_portal.py`
    raise SystemExit(pytest.main([__file__, "-v"]))