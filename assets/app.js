/* Portal de Transferencia Tecnológica y Observatorio Operativo · MAPE
 * Aplicación web: todo el estado vive en los .db del servidor (API REST).
 * No hay datos embebidos ni ficheros JSON de datos: si cambia un .db, la
 * página lo detecta (polling de /api/health) y se repinta sola. */
(function () {
  "use strict";
  const Plotly = window.Plotly;

  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => Array.from(document.querySelectorAll(sel));

  /* ---------------- utils ---------------- */
  const esc = (s) => String(s == null ? "" : s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  const fmt = (n) => Number(n || 0).toLocaleString("es-CO");
  const clamp = (x, a, b) => Math.max(a, Math.min(b, x));
  const trunc = (s, n) => { s = String(s || ""); return s.length > n ? s.slice(0, n - 1) + "…" : s; };
  const num = (v, d) => (v === "" || v == null || isNaN(v) ? (d === undefined ? null : d) : +v);
  const td = (t, cls) => { const e = document.createElement("td"); e.className = cls || ""; e.innerHTML = t; return e; };
  const qs = (o) => Object.entries(o)
    .filter(([, v]) => v !== "" && v != null && !Array.isArray(v))
    .map(([k, v]) => encodeURIComponent(k) + "=" + encodeURIComponent(v)).join("&");

  function saveBlob(name, blob) {
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob); a.download = name;
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 4000);
  }
  const download = (name, text, mime) =>
    saveBlob(name, new Blob([text], { type: mime || "text/plain;charset=utf-8" }));
  async function downloadUrl(url, name) {
    const r = await fetch(url);
    if (!r.ok) throw new Error("No se pudo descargar " + url);
    const cd = r.headers.get("content-disposition") || "";
    const m = /filename="?([^";]+)"?/.exec(cd);
    saveBlob(name || (m ? m[1] : url.split("/").pop()), await r.blob());
  }

  /* ---------------- colores ---------------- */
  const CLUSTER_COL = { 0: "#D55E00", 1: "#0072B2", 2: "#009E73", 3: "#56B4E9", 4: "#CC79A7", 5: "#E69F00", 6: "#F0E442", 7: "#999999" };
  const CAT_COL = {
    "Sensórica y monitoreo": "#56B4E9", "Modelado y simulación": "#0072B2",
    "Inteligencia artificial": "#E69F00", "Geomática": "#009E73",
    "Automatización y robótica": "#D55E00", "Comunicaciones y datos": "#CC79A7",
    "Operación y ambiente": "#F0E442", "Gobernanza": "#999999"
  };
  const CAPEX_COL = { "Bajo": "#2e7d42", "Medio": "#b07a1a", "Alto": "#a83232" };
  const ACCESO_COL = { "Acceso libre": "#2e7d42", "No abierto": "#5d7280", "Sin dato": "#b07a1a" };
  const CONT_COL = { "Africa": "#56B4E9", "LatAm": "#009E73", "Asia": "#E69F00", "AsiaPac": "#E69F00", "Europe": "#0072B2", "Global": "#888888" };
  let contColor = (id) => CONT_COL[id] || "#0b4f6c";
  const escColor = (c) => c || "#888";
  const textColor = (hex) => {
    const c = hex.replace("#", "");
    const r = parseInt(c.slice(0, 2), 16), g = parseInt(c.slice(2, 4), 16), b = parseInt(c.slice(4, 6), 16);
    return (0.299 * r + 0.587 * g + 0.114 * b) > 140 ? "#1c2b36" : "#ffffff";
  };
  const badge = (txt, col) =>
    `<span class="badge" style="background:${escColor(col)};color:${textColor(escColor(col))}">${esc(txt)}</span>`;

  /* ---------------- estado ---------------- */
  let D = null;                 // bootstrap (= window.APP_DATA)
  let cur = { id: "124", meta: null, clusters: null, series: null, source: null, top5: [] };
  let version = "";
  /* Ficha de cada base derivada (`<gid>.db`): metadatos + filas que se pintan. */
  const GB = {};
  /* `filas` solo llega cuando la base se ha leído entera: si un payload llega
     solo con la ficha (p. ej. las tablas pesadas), no se pisan las filas ya leídas */
  const absorberGraficos = (lista) => (lista || []).forEach((g) => {
    const prev = GB[g.id];
    GB[g.id] = (!g.filas && prev && prev.filas)
      ? Object.assign({}, prev, g, { filas: prev.filas })
      : g;
  });
  const ficha = (gid) => GB[gid] || null;
  const filasDe = (gid) => { const g = GB[gid]; return (g && g.filas) || []; };
  const metaDe = (gid) => { const g = GB[gid]; return (g && g.meta) || {}; };
  const cstate = { search: "", cluster: "", tec: "", acceso: "", y0: "", y1: "", page: 1, per: 25, req: 0 };
  const tstate = { search: "", cat: "", geo: "", trl: 0, seg: 0, amb: 0, sel: null, req: 0 };
  const ed = { corpus: "124", page: 1, per: 20, search: "", docId: null, req: 0 };

  /* ---------------- API ---------------- */
  const P = window.__portal = { pending: 0, timers: 0, llamadas: 0 };
  /* debounce visible para las pruebas: mientras haya temporizadores vivos,
     el frontend aún no ha pintado el resultado. */
  function debounce(fn, ms) {
    let h = null;
    return function () {
      const ctx = this;
      if (h) { clearTimeout(h); P.timers--; }
      P.timers++;
      h = setTimeout(() => { h = null; P.timers--; fn.call(ctx); }, ms);
    };
  }
  async function api(path, opts) {
    P.pending++;
    P.llamadas++;
    try {
      const r = await fetch(path, opts);
      const ct = r.headers.get("content-type") || "";
      if (!r.ok) {
        let msg = r.status + " · " + path;
        try { const j = await r.json(); if (j && j.error) msg = j.error; } catch (e) { }
        throw new Error(msg);
      }
      return ct.indexOf("json") >= 0 ? r.json() : r.text();
    } finally {
      P.pending--;
    }
  }
  const apiJSON = (path, method, body) => api(path, {
    method: method || "GET",
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined
  });

  /* ========================== NAVEGACIÓN ========================== */
  const ids = ["inicio", "observatorio", "matriz", "red", "corpus", "editor"];
  function setActiveNav(id) {
    $$(".nav a").forEach((a) => a.classList.toggle("active", a.dataset.nav === id));
  }
  function goSection(id) {
    setActiveNav(id);
    const s = document.getElementById(id);
    if (s) s.scrollIntoView({ behavior: "smooth", block: "start" });
  }
  function navEvents() {
    $$(".nav a, [data-nav]").forEach((a) => a.addEventListener("click", (e) => {
      e.preventDefault();
      goSection(a.dataset.nav);
    }));
    if ("IntersectionObserver" in window) {
      const obs = new IntersectionObserver((es) => {
        es.forEach((e) => { if (e.isIntersecting) setActiveNav(e.target.id); });
      }, { rootMargin: "-35% 0px -55% 0px" });
      ids.forEach((id) => { const s = document.getElementById(id); if (s) obs.observe(s); });
    }
  }

  /* ========================== KPI ========================== */
  function renderKpis() {
    const m = cur.meta || {};
    const cards = [
      [fmt(m.n_docs), "documentos Scopus"],
      [fmt(m.citas_totales), "citas totales"],
      [(m.oa || 0) + " · " + (m.oa_pct || 0) + "%", "acceso abierto"],
      [m.n_clusters, "clústeres temáticos"],
      [m.n_tecs, "tecnologías catalogadas"],
      [(m.rango || []).join("–"), "años analizados"]
    ];
    $("#kpis").innerHTML = cards.map(([v, l]) =>
      `<div class="kpi"><div class="v">${v}</div><div class="l">${l}</div></div>`).join("");
  }

  /* ========================== PLOTLY ========================== */
  const PLOT_CONFIG = {
    displaylogo: false,
    responsive: true,
    modeBarButtonsToRemove: ["lasso2d", "select2d", "autoScale2d"],
    toImageButtonOptions: { format: "svg", scale: 1, filename: "grafico" }
  };
  const BASE_FONT = { family: "Segoe UI, Arial, sans-serif", size: 12, color: "#1c2b36" };
  const baseLayout = (extra) => Object.assign({
    height: 340, font: BASE_FONT,
    paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)",
    hoverlabel: { font: { family: "Segoe UI, Arial", size: 12 }, bgcolor: "rgba(28,43,54,.94)", bordercolor: "#fff", font: { color: "#fff" } },
    margin: { l: 58, r: 26, t: 48, b: 56, automargin: true }
  }, extra || {});

  function makePlot(id, fig) {
    const gd = document.getElementById(id);
    if (!gd || !Plotly) return Promise.resolve(null);
    const cfg = Object.assign({}, PLOT_CONFIG, { filename: id + "_plotly" });
    return Plotly.newPlot(gd, fig.data, Object.assign(baseLayout(), fig.layout), cfg)
      .then(() => gd).catch(() => null);
  }

  /* ---------- leyenda compartida ----------
   * Coloca siempre la leyenda en una franja **fuera del área de trazado**
   * (debajo del eje X) y reserva el alto necesario según cuántas filas ocupe,
   * de modo que nunca se solape con las marcas ni con el título. */
  const LEYENDA_BASE = {
    orientation: "h", x: 0.5, xanchor: "center", yanchor: "top",
    font: { size: 11 }, itemsizing: "constant", traceorder: "normal",
    bgcolor: "rgba(255,255,255,0.72)", bordercolor: "rgba(0,0,0,0)"
  };
  const ALTO_FILA_LEYENDA = 17;
  function filasLeyenda(n, porFila) {
    return Math.max(1, Math.ceil(Math.max(0, n) / Math.max(1, porFila || 3)));
  }
  function altoLeyenda(n, opts) {
    const o = opts || {};
    const base = baseLayout().margin.b || 56;
    return Math.max(o.min || 0, base, ALTO_FILA_LEYENDA * filasLeyenda(n, o.porFila) + 22);
  }
  function conLeyenda(layout, n, opts) {
    const o = opts || {};
    const src = layout || {};
    const margen = Object.assign({}, baseLayout().margin, src.margin || {});
    const alto = altoLeyenda(n, o);
    const h = src.height || baseLayout().height;
    /* el alto reservado se traduce a fracción `paper` exacta: así la leyenda
       cae SIEMPRE por debajo del área de trazado, sin solaparse ni recortarse */
    const area = Math.max(60, h - (margen.t || 48) - alto);
    const leyenda = Object.assign({}, LEYENDA_BASE, o.legend || {}, {
      y: -clamp((alto - 12) / area, 0.08, 0.6), yanchor: "top"
    });
    return Object.assign({}, src, {
      showlegend: true,
      legend: leyenda,
      margin: Object.assign({}, margen, { b: alto }),
      height: h
    });
  }
  /* traces de leyenda sin datos: sirven para etiquetar colores/niveles */
  function claveLeyenda(nombre, color, tipo) {
    return {
      type: tipo || "scatter", mode: "markers", x: [null], y: [null],
      name: nombre, marker: { color: escColor(color), size: 9 }, hoverinfo: "skip"
    };
  }
  function downloadSvg(id) {
    const gd = document.getElementById(id);
    if (!gd || !Plotly) return;
    const w = (gd._fullLayout && gd._fullLayout.width) || 900;
    const h = (gd._fullLayout && gd._fullLayout.height) || 480;
    return Plotly.toImage(gd, { format: "svg", width: w, height: h, scale: 1 })
      .then((url) => {
        const a = document.createElement("a");
        a.href = url; a.download = id + ".svg";
        document.body.appendChild(a); a.click(); a.remove();
      })
      .catch(() => download(id + ".svg", "", "image/svg+xml"));
  }

  /* ---------- barras: publicaciones por año ---------- */
  function renderAnios() {
    const S = filasDe("chart_anios");
    if (!S.length) return;
    makePlot("chart_anios", {
      data: [{
        type: "bar", x: S.map((d) => d.anio), y: S.map((d) => d.publicaciones),
        text: S.map((d) => String(d.publicaciones)), texttemplate: "%{text}",
        textposition: "outside", cliponaxis: false,
        marker: { color: "#0b4f6c" },
        customdata: S.map((d) => [d.etiqueta]),
        hovertemplate: "%{customdata[0]}<br><b>%{y}</b> publicaciones<extra></extra>"
      }],
      layout: {
        title: { text: "Publicaciones por año (" + S[0].etiqueta + "–" + S[S.length - 1].etiqueta + ")", font: { size: 13 } },
        xaxis: { title: "Año", tickangle: -45, automargin: true, dtick: 1 },
        yaxis: { title: "Documentos", rangemode: "tozero", automargin: true },
        uniformtext: { mode: "hide", minsize: 9 },
        bargap: 0.3, height: 330
      }
    });
  }

  /* ---------- donuts ---------- */
  /* el dominio se recorta por abajo para que las etiquetas interiores de la
     dona nunca invadan la franja reservada para la leyenda */
  function donutPlot(id, items, opts) {
    const o = Object.assign({ title: "", height: 330, porFila: 2, dominio: 0.22 }, opts);
    const alto = altoLeyenda(items.length, o);
    makePlot(id, {
      data: [{
        type: "pie", labels: items.map((d) => d.l), values: items.map((d) => d.v),
        hole: 0.56, sort: false, textinfo: "percent+value",
        insidetextorientation: "horizontal", textfont: { size: 11 },
        uniformtext: { mode: "hide", minsize: 10 },
        marker: { colors: items.map((d) => escColor(d.c)) },
        domain: { x: [0.05, 0.95], y: [o.dominio, 1] },
        hovertemplate: "%{label}<br><b>%{value}</b> docs · %{percent}<extra></extra>"
      }],
      layout: conLeyenda({
        title: { text: o.title, font: { size: 13 } },
        height: o.height + alto - altoLeyenda(0, o),
        margin: { l: 16, r: 16, t: 44, b: 30, automargin: true }
      }, items.length, o)
    });
  }
  function renderDonuts() {
    const cls = filasDe("chart_donut_cluster");
    if (cls.length) {
      donutPlot("chart_donut_cluster", cls.map((k) => ({
        l: k.etiqueta || ("Clúster " + k.cluster), v: k.docs, c: k.color
      })), { title: "Clústeres temáticos del corpus (docs)", porFila: 2 });
    }
    const ac = filasDe("chart_donut_acceso");
    if (ac.length) {
      donutPlot("chart_donut_acceso", ac.map((a) => ({
        l: a.etiqueta || a.acceso, v: a.docs, c: a.color
      })), { title: "Perfil de acceso abierto (docs)", porFila: 3 });
    }
  }

  /* ---------- top 5 citados ---------- */
  function renderTop5() {
    const top = filasDe("chart_top5");
    if (!top.length) return;
    makePlot("chart_top5", {
      data: [{
        type: "bar", orientation: "h",
        y: top.map((d) => trunc(d.etiqueta, 72) + " · " + d.anio),
        x: top.map((d) => d.citas),
        text: top.map((d) => fmt(d.citas) + " cit."), texttemplate: "%{text}",
        textposition: "outside", cliponaxis: false,
        marker: { color: "#0b4f6c" },
        hovertemplate: "%{y}<br><b>%{x}</b> citas<extra></extra>"
      }],
      layout: {
        title: { text: "Documentos más citados del corpus", font: { size: 13 } },
        xaxis: { title: "Citas", rangemode: "tozero", automargin: true },
        yaxis: { automargin: true, tickfont: { size: 11 } },
        uniformtext: { mode: "hide", minsize: 9 }, height: 300
      }
    });
  }

  /* ---------- radar ---------- */
  function renderRadar() {
    const filas = filasDe("chart_radar");
    if (!filas.length) return;
    const ejes = [];
    filas.forEach((f) => { if (ejes.indexOf(f.eje) < 0) ejes.push(f.eje); });
    ejes.sort((a, b) => (filas.find((f) => f.eje === a) || {}).orden_eje -
      (filas.find((f) => f.eje === b) || {}).orden_eje);
    const theta = ejes.map((l) => String(l).replace(/\n/g, " "));
    const orden = [];
    filas.forEach((f) => { if (orden.indexOf(f.etiqueta) < 0) orden.push(f.etiqueta); });
    const series = orden.map((nombre) => {
      const rs = filas.filter((f) => f.etiqueta === nombre);
      return {
        nombre: nombre, color: escColor((rs[0] || {}).color || contColor(rs[0] && rs[0].serie)),
        v: ejes.map((e) => { const r = rs.find((f) => f.eje === e); return r ? r.valor : 0; })
      };
    });
    makePlot("chart_radar", {
      data: series.map((s) => ({
        type: "scatterpolar", r: s.v, theta: theta, fill: "toself", name: s.nombre,
        line: { color: s.color, width: 2 },
        marker: { size: 4, color: s.color },
        hovertemplate: "%{theta}: <b>%{r:.0f}</b>/100<extra>" + esc(s.nombre) + "</extra>"
      })),
      layout: conLeyenda({
        title: { text: "Perfil regional multidimensional (0–100)", font: { size: 13 } },
        polar: {
          radialaxis: { visible: true, range: [0, 100], tickfont: { size: 10 }, tickmode: "linear", dtick: 20 },
          angularaxis: { tickfont: { size: 10 }, color: "#1c2b36", tickangle: 0 }
        },
        height: 380,
        margin: { l: 30, r: 30, t: 46, b: 30, automargin: true }
      }, series.length, { porFila: 3 })
    });
  }

  /* ---------- burbuja países ---------- */
  function bubbleFig() {
    const pts = filasDe("chart_bubble");
    if (!pts.length) return null;
    const reg = pearson_log(pts.map((p) => ({ gdp_pc: p.gdp_pc, adopcion: p.adopcion })));
    const meta = metaDe("chart_bubble").regresion || reg;
    const x0 = Math.min.apply(null, pts.map((p) => p.gdp_pc).filter((v) => v > 0));
    const x1 = Math.max.apply(null, pts.map((p) => p.gdp_pc).filter((v) => v > 0));
    const recta = {
      type: "scatter", mode: "lines", name: "Regresión (r = " + (meta.r || 0).toFixed(2) + ")",
      x: [x0, x1],
      y: [meta.intercept + meta.slope * Math.log10(x0),
          meta.intercept + meta.slope * Math.log10(x1)],
      line: { color: "#e8772e", width: 1.8, dash: "dash" }, hoverinfo: "skip"
    };
    const regiones = [];
    pts.forEach((p) => {
      const r = p.region || "Global";
      if (regiones.indexOf(r) < 0) regiones.push(r);
    });
    const puntos = {
      type: "scatter", mode: "markers", name: "Países modelo",
      x: pts.map((p) => p.gdp_pc), y: pts.map((p) => p.adopcion),
      marker: {
        size: pts.map((p) => 9 + Math.sqrt(p.n_pubs || 1) * 5.4), sizemode: "diameter",
        color: pts.map((p) => escColor(p.color)), opacity: 0.82,
        line: { color: "#fff", width: 1.2 }
      },
      customdata: pts.map((p) => [p.pais, p.region, p.gdp_pc, p.adopcion, p.seg, p.amb, p.n_pubs]),
      hovertemplate: "<b>%{customdata[0]}</b> · %{customdata[1]}<br>PIB pc: %{customdata[2]:,.0f} US$<br>Adopción: %{customdata[3]}/100<br>Seguridad: %{customdata[4]} · Ambiente: %{customdata[5]}<br>Publicaciones modelo: %{customdata[6]}<extra></extra>",
      showlegend: false
    };
    const etiquetas = {
      type: "scatter", mode: "text", x: pts.map((p) => p.gdp_pc), y: pts.map((p) => p.adopcion),
      text: pts.map((p) => p.pais), textposition: "middle center",
      textfont: { size: 10, color: "#1c2b36" }, hoverinfo: "none", showlegend: false
    };
    const claves = regiones.map((r) => claveLeyenda(REGION_LBL[r] || r,
      (pts.find((p) => p.region === r) || {}).color));
    return {
      claves: claves,
      datos: [recta, puntos, etiquetas],
      layout: {
        title: { text: "Adopción tecnológica vs. PIB per cápita (países modelo)", font: { size: 13 } },
        xaxis: {
          title: "PIB per cápita (US$, escala log)", type: "log", automargin: true,
          tickvals: [500, 1000, 2000, 5000, 10000, 20000], ticktext: ["500", "1k", "2k", "5k", "10k", "20k"]
        },
        yaxis: { title: "Adopción tecnológica (0–100)", automargin: true, range: [0, 70] },
        height: 360
      }
    };
  }
  /* regresión log10(PIB) → adopción, por si el .db no la trae calculada */
  function pearson_log(pts) {
    const vs = pts.filter((p) => p.gdp_pc > 0);
    const n = vs.length;
    if (n < 3) return { r: 0, slope: 0, intercept: 0, n: n };
    const lx = vs.map((p) => Math.log10(p.gdp_pc)), ly = vs.map((p) => p.adopcion);
    const mx = lx.reduce((a, b) => a + b, 0) / n, my = ly.reduce((a, b) => a + b, 0) / n;
    const sxy = lx.reduce((a, v, i) => a + (v - mx) * (ly[i] - my), 0);
    const sxx = lx.reduce((a, v) => a + (v - mx) * (v - mx), 0) || 1e-9;
    const syy = ly.reduce((a, v) => a + (v - my) * (v - my), 0) || 1e-9;
    const slope = sxy / sxx;
    return { r: sxy / Math.sqrt(sxx * syy), slope: slope, intercept: my - slope * mx, n: n };
  }
  function fitBubbleLabels(gd) {
    try {
      const pts = filasDe("chart_bubble");
      if (!pts.length) return Promise.resolve();
      const xaxis = gd._fullLayout.xaxis, yaxis = gd._fullLayout.yaxis;
      const xpx = pts.map((p) => xaxis.l2p(p.gdp_pc));
      const ypx = pts.map((p) => yaxis.l2p(p.adopcion));
      const n = pts.length, dy = new Array(n).fill(0);
      const minDx = 92, minDy = 24;
      for (let i = 0; i < n; i++) {
        for (let j = 0; j < n; j++) {
          if (i === j) continue;
          if (Math.abs(xpx[i] - xpx[j]) > minDx) continue;
          const d = Math.abs((ypx[i] + dy[i]) - (ypx[j] + dy[j]));
          if (d < minDy) dy[j] += ((ypx[j] >= ypx[i]) ? 1 : -1) * (minDy - d);
        }
      }
      const range = (yaxis._range[1] - yaxis._range[0]);
      const yData = pts.map((p, i) => dy[i] ? p.adopcion + (dy[i] * range) / yaxis._length : p.adopcion);
      return Plotly.restyle(gd, {
        y: [yData],
        textposition: [pts.map((p, i) => dy[i] !== 0 ? (dy[i] < 0 ? "top center" : "bottom center") : "middle center")]
      }, [2]);
    } catch (err) { return Promise.resolve(); }
  }
  function renderBubble() {
    if (!Plotly) return;
    const fig = bubbleFig();
    if (!fig) return;
    makePlot("chart_bubble", {
      data: fig.claves.concat(fig.datos),
      layout: conLeyenda(fig.layout, fig.claves.length + 1, { porFila: 3 })
    })
      .then((gd) => { if (gd) return fitBubbleLabels(gd); return null; })
      .catch(() => { });
  }

  /* ---------- serie temporal compuesta ---------- */
  function renderSeries() {
    const S = filasDe("chart_series");
    if (!S.length) return;
    makePlot("chart_series", {
      data: [
        { type: "bar", x: S.map((d) => d.anio), y: S.map((d) => d.publicaciones), name: "Publicaciones", yaxis: "y", marker: { color: "#0b4f6c", opacity: 0.85 }, hovertemplate: "%{x}<br>Publicaciones: <b>%{y}</b><extra></extra>" },
        { type: "scatter", mode: "lines+markers", x: S.map((d) => d.anio), y: S.map((d) => d.educacion), name: "Índice educativo (×100)", yaxis: "y2", line: { color: "#e8772e", width: 2.4 }, marker: { size: 5 }, hovertemplate: "%{x}<br>Índice educativo: <b>%{y:.1f}</b><extra></extra>" },
        { type: "scatter", mode: "lines+markers", x: S.map((d) => d.anio), y: S.map((d) => d.inversion), name: "Inversión tecnológica", yaxis: "y2", line: { color: "#d55e00", width: 2.4 }, marker: { size: 5 }, hovertemplate: "%{x}<br>Inversión: <b>%{y:.1f}</b><extra></extra>" }
      ],
      layout: conLeyenda({
        title: { text: "Convergencia temporal: publicaciones · inversión · educación", font: { size: 13 } },
        xaxis: { title: "Año", tickangle: -45, automargin: true, dtick: 1 },
        yaxis: { title: "Publicaciones", rangemode: "tozero", automargin: true },
        yaxis2: { title: "Índice 0–100", overlaying: "y", side: "right", automargin: true, range: [0, 100] },
        hovermode: "x unified",
        bargap: 0.3, height: 350
      }, 3, { porFila: 3 })
    });
  }

  /* ---------- matriz de correlaciones ---------- */
  function renderCorr() {
    const filas = filasDe("chart_corr");
    if (!filas.length) return;
    const cols = [];
    filas.forEach((f) => { if (cols.indexOf(f.fila) < 0) cols.push(f.fila); });
    const z = cols.map((f) => cols.map((c) => {
      const r = filas.find((x) => x.fila === f && x.col === c);
      return r ? r.r : 0;
    }));
    makePlot("chart_corr", {
      data: [{
        type: "heatmap", z: z, x: cols, y: cols, zmid: 0,
        colorscale: [[0, "rgb(165,0,38)"], [0.5, "rgb(247,247,247)"], [1, "rgb(49,54,149)"]],
        text: z.map((r) => r.map((v) => v.toFixed(2))), texttemplate: "%{text}",
        textfont: { size: 10, color: z.map((r) => r.map((v) => Math.abs(v) > 0.55 ? "#ffffff" : "#1c2b36")) },
        xgap: 1, ygap: 1,
        hovertemplate: "%{x} × %{y}<br>r = %{z:.2f}<extra></extra>",
        colorbar: { title: { text: "r", side: "right" }, len: 0.8, thickness: 12, outlinewidth: 0 }
      }],
      layout: {
        title: { text: "Matriz de correlaciones del corpus e indicadores", font: { size: 13 } },
        xaxis: { automargin: true, tickangle: -30, tickfont: { size: 10 } },
        yaxis: { automargin: true, tickfont: { size: 10 } },
        height: 400
      }
    });
  }

  /* ---------- fondos IGF ---------- */
  function renderIgf() {
    const items = filasDe("chart_igf");
    if (!items.length) return;
    const total = items.reduce((a, b) => a + (b.pct || 0), 0);
    makePlot("chart_igf", {
      data: items.map((d) => ({
        type: "bar", x: [d.etiqueta || d.region], y: [d.pct],
        text: [d.pct + "%"], texttemplate: "%{text}",
        textposition: "outside", cliponaxis: false,
        marker: { color: escColor(d.color) },
        name: d.etiqueta || d.region, showlegend: false,
        hovertemplate: "<b>%{x}</b><br>%{y}% de los fondos IGF<extra></extra>"
      })),
      layout: {
        title: { text: "Asignación de fondos IGF por región (sintética)", font: { size: 13 } },
        xaxis: { title: "Región beneficiaria", automargin: true, tickfont: { size: 11 } },
        yaxis: { title: "% de fondos", range: [0, 44], automargin: true },
        uniformtext: { mode: "hide", minsize: 9 }, bargap: 0.35,
        annotations: [{
          text: "Remanente: " + (100 - total).toFixed(1) + "%. Asignación sintética calibrada (IGF).",
          xref: "paper", yref: "paper", x: 0, y: 1.12, showarrow: false,
          font: { size: 10, color: "#5d7280" }
        }],
        height: 350, margin: { l: 50, r: 20, t: 60, b: 50, automargin: true }
      }
    });
  }

  /* ---------- producción científica por país ---------- */
  function renderPaisesPub() {
    const P = filasDe("chart_paises_pub");
    if (!P.length) return;
    makePlot("chart_paises_pub", {
      data: [{
        type: "bar", orientation: "h", y: P.map((p) => p.etiqueta || p.pais), x: P.map((p) => p.n),
        text: P.map((p) => p.n + " (" + Number(p.pct).toFixed(1) + "%)"), texttemplate: "%{text}",
        textposition: "outside", cliponaxis: false,
        marker: { color: "#1a7f8e" },
        hovertemplate: "<b>%{y}</b><br>%{x} documentos<extra></extra>"
      }],
      layout: {
        title: { text: "Producción científica real por país (revisión ampliada Scopus)", font: { size: 13 } },
        xaxis: { title: "Documentos", rangemode: "tozero", automargin: true },
        yaxis: { automargin: true, tickfont: { size: 11 } },
        uniformtext: { mode: "hide", minsize: 9 },
        height: 40 + P.length * 24
      }
    });
  }

  /* ---------- red de convergencia ----------
   * Las coordenadas, los niveles de enlace y el color salen de `chart_red.db`
   * (layout determinista calculado en Python y editable desde el portal). */
  const NIVEL_LBL = { fuerte: "Fuerte (≥2 co-ocurrencias)", media: "Media (1 o similitud alta)", debil: "Débil (puente de similitud)" };
  function renderRed() {
    const filas = filasDe("chart_red");
    const nodos = filas.filter((f) => f.tipo === "nodo");
    const enlaces = filas.filter((f) => f.tipo === "enlace");
    if (!nodos.length) return;
    const conPos = nodos.filter((n) => n.x != null && n.y != null);
    if (conPos.length !== nodos.length) return;   /* layout aún no calculado */
    const W = 760, H = 460;
    const xs = nodos.map((n) => n.x), ys = nodos.map((n) => n.y);
    const x0 = Math.min.apply(null, xs), x1 = Math.max.apply(null, xs);
    const y0 = Math.min.apply(null, ys), y1 = Math.max.apply(null, ys);
    const dx = (x1 - x0) || 1, dy = (y1 - y0) || 1;
    const pos = {};
    nodos.forEach((n) => {
      pos[n.id] = [24 + ((n.x - x0) / dx) * (W - 48), 20 + ((n.y - y0) / dy) * (H - 40)];
    });
    const rmax = Math.max.apply(null, nodos.map((n) => Math.sqrt(n.valor || 0) || 1));
    const radio = (n) => 10 + 16 * (Math.sqrt(n.valor || 0) / rmax);

    const edges = enlaces.map((e) => {
      const a = pos[String(e.id).split("|")[0]], b = pos[String(e.id).split("|")[1]];
      if (!a || !b) return null;
      return {
        type: "scatter", mode: "lines",
        x: [a[0], b[0], null], y: [a[1], b[1], null],
        line: {
          color: escColor(e.color),
          width: e.nivel === "fuerte" ? 2.4 : e.nivel === "media" ? 1.4 : 0.9
        },
        hoverinfo: "skip", showlegend: false
      };
    }).filter(Boolean);

    const nodeTrace = {
      type: "scatter", mode: "markers+text",
      x: nodos.map((n) => pos[n.id][0]), y: nodos.map((n) => pos[n.id][1]),
      text: nodos.map((n) => trunc(n.etiqueta, 26)),
      textposition: nodos.map((n) => (pos[n.id][1] > H / 2 ? "top center" : "bottom center")),
      textfont: { size: 9, color: "#1c2b36" },
      customdata: nodos.map((n) => [n.categoria, n.valor, n.valor2]),
      hovertemplate: "<b>%{text}</b><br>%{customdata[0]}<br>Documentos: %{customdata[1]}<br>Grado: %{customdata[2]}<extra></extra>",
      marker: {
        size: nodos.map((n) => radio(n)),
        color: nodos.map((n) => escColor(n.color)),
        opacity: 0.88, line: { color: "#fff", width: 1.4 }
      },
      showlegend: false
    };
    const m = metaDe("chart_red");
    const niveles = m.niveles || {};
    const claves = ["fuerte", "media", "debil"].map((n) => {
      const color = (enlaces.find((e) => e.nivel === n) || {}).color ||
        { fuerte: "#0b4f6c", media: "#7ba7bb", debil: "#c4d6de" }[n];
      return claveLeyenda(NIVEL_LBL[n] + " · " + (niveles[n] || 0), color);
    });
    makePlot("chart_red", {
      data: claves.concat(edges, [nodeTrace]),
      layout: conLeyenda({
        title: { text: "Red de co-ocurrencia de tecnologías · " +
          (nodos.length) + " tecnologías unidas por " + enlaces.length + " enlaces", font: { size: 13 } },
        xaxis: { visible: false, range: [0, W], fixedrange: true, showgrid: false, zeroline: false },
        yaxis: { visible: false, range: [0, H], fixedrange: true, showgrid: false, zeroline: false },
        height: 460,
        margin: { l: 10, r: 10, t: 44, b: 10, automargin: true }, dragmode: "pan"
      }, claves.length, { porFila: 1, min: 40 })
    });
  }

  /* ---------- categorías y frecuencia por tecnología ---------- */
  function renderCat() {
    const items = filasDe("chart_cat");
    if (!items.length) return;
    donutPlot("chart_cat", items.map((k) => ({
      l: k.etiqueta || k.cat, v: k.docs, c: k.color
    })), { title: "Categorías representadas (docs)", porFila: 2, dominio: 0.34 });
  }
  function renderTecBar() {
    const ts = filasDe("chart_tec_bar").slice().sort((a, b) => b.docs - a.docs);
    if (!ts.length) return;
    makePlot("chart_tec_bar", {
      data: [{
        type: "bar", orientation: "h",
        y: ts.map((t) => trunc(t.etiqueta, 42)), x: ts.map((t) => t.docs),
        text: ts.map((t) => String(t.docs)), texttemplate: "%{text}",
        textposition: "outside", cliponaxis: false,
        marker: { color: ts.map((t) => escColor(t.color)) },
        hovertemplate: "<b>%{y}</b><br>%{x} documentos<extra></extra>"
      }],
      layout: {
        title: { text: "Frecuencia por tecnología (docs del corpus)", font: { size: 13 } },
        xaxis: { title: "Documentos", rangemode: "tozero", automargin: true },
        yaxis: { automargin: true, tickfont: { size: 11 } },
        uniformtext: { mode: "hide", minsize: 9 },
        height: 40 + ts.length * 22
      }
    });
  }

  function renderCharts() {
    renderAnios(); renderDonuts(); renderTop5(); renderRadar(); renderBubble();
    renderSeries(); renderCorr(); renderIgf(); renderPaisesPub(); renderRed();
    renderCat(); renderTecBar();
  }

  /* ========================== TABLAS ========================== */
  const REGION_LBL = { Africa: "África", LatAm: "Latinoamérica", Asia: "Asia", AsiaPac: "Asia-Pacífico", Europe: "Europa", Global: "Global" };
  function tablaObs(container) {
    const rows = filasDe("tabla_paises_obs").slice().sort((a, b) => b.tech - a.tech);
    if (!rows.length) return;
    const t = document.createElement("table");
    t.className = "tbl";
    t.innerHTML = '<thead><tr><th>País</th><th>Región</th><th class="num">PIB pc (US$)</th><th class="num">Tech</th><th class="num">Seg.</th><th class="num">Amb.</th><th class="num">Minería% PIB</th></tr></thead>';
    const tb = document.createElement("tbody");
    rows.forEach((p) => {
      const tr = document.createElement("tr");
      tr.appendChild(td("<b>" + esc(p.pais) + "</b>"));
      tr.appendChild(td('<span style="color:' + contColor(p.cont) + ';font-weight:600">' + esc(REGION_LBL[p.cont] || p.cont) + "</span>"));
      tr.appendChild(td(fmt(p.gdp_pc), "num"));
      tr.appendChild(td('<span style="color:' + (p.tech > 30 ? "#1a7f8e" : p.tech > 15 ? "#b07a1a" : "#a83232") + ';font-weight:700">' + p.tech + "</span>", "num"));
      tr.appendChild(td(String(p.seg), "num"));
      tr.appendChild(td(String(p.amb), "num"));
      tr.appendChild(td(Number(p.mining_gdp).toFixed(1), "num"));
      tb.appendChild(tr);
    });
    t.appendChild(tb);
    container.innerHTML = "";
    container.appendChild(t);
  }

  /* entrega científica: los 124 documentos cualitativos (tabla_deliverable.db) */
  async function renderDeliverable(container) {
    let list = filasDe("tabla_deliverable");
    if (!list.length) {
      try {
        const r = await api("/api/grafico/tabla_deliverable" + qCorpus());
        absorberGraficos([r]);
        list = r.filas || [];
      } catch (e) {
        container.innerHTML = '<p class="card-note">No se pudo leer <code>tabla_deliverable.db</code>: ' +
          esc(e.message) + "</p>";
        return;
      }
    }
    const docs = list.slice().sort((a, b) => a.anio - b.anio || a.n - b.n);
    const t = document.createElement("table");
    t.className = "tbl";
    t.innerHTML = `<thead><tr>
      <th class="num">N</th><th class="num">Año</th><th>Título</th><th>Autores</th><th>Fuente</th>
      <th class="num">Citas</th><th>Acceso</th><th>Clúster</th>
      <th>Hallazgos principales</th><th>Limitaciones</th><th>Novedad</th>
    </tr></thead>`;
    const tb = document.createElement("tbody");
    docs.forEach((d, i) => {
      const tr = document.createElement("tr");
      const cname = (cur.clusters && d.cluster != null && cur.clusters[d.cluster])
        ? cur.clusters[d.cluster].nombre : null;
      tr.appendChild(td(d.n || String(i + 1), "num"));
      tr.appendChild(td(d.anio || "—", "num"));
      tr.appendChild(td(esc(trunc(d.titulo, 110))));
      tr.appendChild(td(esc(trunc(d.autores, 40))));
      tr.appendChild(td(esc(trunc(d.fuente, 46))));
      tr.appendChild(td("<b>" + d.citas + "</b>", "num"));
      tr.appendChild(td(badge(d.acceso, ACCESO_COL[d.acceso] || "#5d7280")));
      tr.appendChild(td(cname ? badge(cname, CLUSTER_COL[d.cluster]) : "—"));
      tr.appendChild(td(esc(trunc(d.hallazgos, 300))));
      tr.appendChild(td(esc(trunc(d.limitaciones, 300))));
      tr.appendChild(td(esc(trunc(d.novedad, 300))));
      tb.appendChild(tr);
    });
    t.appendChild(tb);
    container.innerHTML = "";
    container.appendChild(t);
  }

  /* ========================== MATRIZ DE TECNOLOGÍAS ========================== */
  function techFiltrosOpciones() {
    const cats = [...new Set((D.tecnologias || []).map((t) => t.cat_out))];
    const geos = [...new Set((D.tecnologias || []).flatMap((t) => t.geoma_lbl))];
    $("#f_mat_cat").innerHTML = '<option value="">Todas las categorías</option>' +
      cats.map((c) => "<option>" + esc(c) + "</option>").join("");
    $("#f_mat_geo").innerHTML = '<option value="">Todas las geometrías</option>' +
      geos.map((g) => '<option value="' + esc(g) + '">' + esc(g) + "</option>").join("");
    $("#f_mat_trl").innerHTML = '<option value="">Cualquier TRL</option>' +
      [1, 2, 3, 4, 5, 6, 7, 8, 9].map((v) => '<option value="' + v + '">TRL ' + v + "</option>").join("");
    ["f_mat_seg", "f_mat_amb"].forEach((id) => {
      $("#" + id).innerHTML = '<option value="">—</option>' +
        [1, 2, 3, 4, 5].map((v) => '<option value="' + v + '">' + v + " (mín.)</option>").join("");
    });
  }
  function techFiltrosEventos() {
    const leer = () => {
      tstate.search = $("#f_mat_search").value.toLowerCase().trim();
      tstate.cat = $("#f_mat_cat").value;
      tstate.geo = $("#f_mat_geo").value;
      tstate.trl = +$("#f_mat_trl").value || 0;
      tstate.seg = +$("#f_mat_seg").value || 0;
      tstate.amb = +$("#f_mat_amb").value || 0;
    };
    const repintar = debounce(() => { haltDetail(); renderMatriz(); }, 90);
    ["f_mat_search", "f_mat_cat", "f_mat_geo", "f_mat_trl", "f_mat_seg", "f_mat_amb"].forEach((id) => {
      const ev = (id === "f_mat_search") ? "input" : "change";
      $("#" + id).addEventListener(ev, () => { leer(); repintar(); });
    });
  }
  function filtradas() {
    return (D.tecnologias || []).filter((t) => {
      if (tstate.search && !((t.nombre || "").toLowerCase().includes(tstate.search) ||
        (t.cat_out || "").toLowerCase().includes(tstate.search))) return false;
      if (tstate.cat && t.cat_out !== tstate.cat) return false;
      if (tstate.geo && !(t.geoma_lbl || []).includes(tstate.geo)) return false;
      if (tstate.trl && t.trl < tstate.trl) return false;
      if (tstate.seg && (t.seg || 0) < tstate.seg) return false;
      if (tstate.amb && (t.amb || 0) < tstate.amb) return false;
      return true;
    }).sort((a, b) => b.trl - a.trl || b.n_docs - a.n_docs);
  }
  function trlCell(t) {
    const w = Math.max(18, 64 * (t.trl / 9));
    const col = t.trl >= 8 ? "#2e7d42" : t.trl >= 5 ? "#b07a1a" : "#a83232";
    return '<span class="trl">' + t.trl + "</span> / 9" +
      '<div style="width:64px;height:7px;background:#e5ebef;border-radius:4px;margin-top:3px">' +
      '<div style="width:' + w + 'px;height:7px;background:' + col + ';border-radius:4px"></div></div>';
  }
  function renderMatriz() {
    const rows = filtradas();
    const tb = $("#tabla_tecnologias tbody");
    tb.innerHTML = "";
    rows.forEach((t) => {
      const tr = document.createElement("tr");
      tr.dataset.tec = t.id;
      tr.addEventListener("click", () => renderDetail(t));
      tr.appendChild(td("<b>" + esc(t.nombre) + "</b>"));
      tr.appendChild(td(badge(t.cat_out, CAT_COL[t.cat_out])));
      tr.appendChild(td('<span class="trl">' + t.n_docs + "</span>", "num"));
      tr.appendChild(td(trlCell(t)));
      tr.appendChild(td((t.geoma_lbl || []).map((g) => '<span class="tag">' + esc(g) + "</span>").join("")));
      tr.appendChild(td(badge(t.capex, CAPEX_COL[t.capex])));
      tr.appendChild(td(badge(t.opex, CAPEX_COL[t.opex])));
      tr.appendChild(td('<span style="color:' + (t.seg >= 4 ? "#2e7d42" : t.seg >= 3 ? "#b07a1a" : "#a83232") + ';font-weight:700">' + t.seg + "/5</span>", "num"));
      tr.appendChild(td('<span style="color:' + (t.amb >= 4 ? "#2e7d42" : t.amb >= 3 ? "#b07a1a" : "#a83232") + ';font-weight:700">' + t.amb + "/5</span>", "num"));
      tb.appendChild(tr);
    });
    if (!rows.length) tb.innerHTML = '<tr><td colspan="9" style="text-align:center;color:#5d7280">Ninguna tecnología coincide con los filtros.</td></tr>';
  }
  const haltDetail = () => { tstate.sel = null; $("#tech_detail").classList.add("hidden"); };

  function renderDetail(t) {
    tstate.sel = t.id;
    const dd = $("#tech_detail");
    dd.innerHTML = '<h3>' + esc(t.nombre) + " " +
      badge(t.cat_out, CAT_COL[t.cat_out]) + "</h3><p class=\"detail-kw\">Cargando documentos…</p>";
    dd.classList.remove("hidden");
    api("/api/tecnologias/" + encodeURIComponent(t.id) + "?n=12")
      .then((d) => {
        if (tstate.sel !== t.id) return;
        const relDocs = d.docs || [];
        const citas = relDocs.reduce((a, x) => a + (x.citas || 0), 0);
        const porAnio = relDocs.length ? Math.round(relDocs.reduce((a, x) => a + x.anio, 0) / relDocs.length) : "—";
        const docsHtml = relDocs.slice().sort((a, b) => b.citas - a.citas).map((x) => {
          const href = x.enlace || (x.doi ? "https://doi.org/" + encodeURIComponent(x.doi) : "#");
          return "<li>" + x.anio + ' — <a href="' + esc(href) + '" target="_blank" rel="noopener">' + esc(x.titulo) +
            '</a> <span class="detail-kw">(' + x.citas + " cit.)</span></li>";
        }).join("") || "<li>Sin documentos directos en el corpus. (Tecnología inferida por vocabulario de experto.)</li>";
        dd.innerHTML =
          "<h3>" + esc(d.nombre) + " " + badge(d.cat_out, CAT_COL[d.cat_out]) + "</h3>" +
          '<p class="detail-kw">TRL <b>' + d.trl + "/9</b> · " + d.n_docs + " documentos · ~" + fmt(citas) +
          " citas · año típico " + porAnio + " · CAPEX <b>" + esc(d.capex) + "</b> · OPEX <b>" + esc(d.opex) +
          "</b> · Seguridad <b>" + d.seg + "/5</b> · Ambiente <b>" + d.amb + "/5</b> · Geometrías: " +
          (d.geoma_lbl || []).map(esc).join(", ") + "</p>" +
          '<div class="grid2"><div><h4 style="margin:.6em 0 .3em">Documentos del corpus (máx. 12, por citas)</h4>' +
          '<ol class="docs" style="margin:0;padding-left:1.2em">' + docsHtml + "</ol></div>" +
          '<div><h4 style="margin:.6em 0 .3em">Acciones</h4>' +
          '<p>Filtrar el <a href="#corpus" data-nav="corpus" data-set-tech="' + d.id + '">explorador del corpus</a> por esta tecnología.</p>' +
          '<button class="btn btn-sec btn-sm" data-corpus-tech="' + d.id + '">Ver documentos en Corpus</button> ' +
          '<button class="btn btn-ghost btn-sm" style="border-color:#dfe6eb;color:#5d7280;margin-left:.4em" data-close-detail>Cerrar</button>' +
          "</div></div>";
        dd.querySelector("[data-close-detail]").addEventListener("click", haltDetail);
        dd.querySelectorAll("[data-corpus-tech],[data-nav=corpus]").forEach((b) =>
          b.addEventListener("click", (e) => { e.preventDefault(); setCorpusTech(d.id); }));
      })
      .catch((e) => { dd.innerHTML = "<h3>" + esc(t.nombre) + "</h3><p class=\"detail-kw\">No se pudo consultar: " + esc(e.message) + "</p>"; });
  }

  /* ========================== CORPUS ========================== */
  function corporaList() {
    const list = (D.corpora || []).slice();
    const byId = {};
    list.forEach((c) => { byId[c.id] = c; });
    if (!byId["124"]) list.unshift({ id: "124", meta: D.meta, clusters: D.clusters });
    return list;
  }
  function renderCorpusTabs() {
    const host = $("#corpus_tabs");
    host.innerHTML = "";
    corporaList().forEach((t) => {
      const b = document.createElement("button");
      b.className = "tab" + (t.id === cur.id ? " active" : "");
      b.dataset.corpus = t.id;
      b.setAttribute("role", "tab");
      b.innerHTML = t.id + " · <b>" + fmt(t.meta.n_docs) + '</b> docs<span class="tab-sub"> · ' +
        esc(String(t.meta.nombre).replace(/^\d+ · /, "")) + "</span>";
      host.appendChild(b);
    });
  }
  function corpusFiltrosOpciones() {
    const clusters = cur.clusters || {};
    $("#f_cor_cluster").innerHTML = '<option value="">Todos los clústeres</option>' +
      Object.keys(clusters).map((k) => '<option value="' + k + '">' + esc(clusters[k].nombre) + "</option>").join("");
    $("#f_cor_tec").innerHTML = '<option value="">Todas las tecnologías</option>' +
      (D.tecnologias || []).slice().sort((a, b) => a.nombre.localeCompare(b.nombre))
        .map((t) => '<option value="' + t.id + '">' + esc(t.nombre) + "</option>").join("");
    $("#f_cor_acceso").innerHTML = '<option value="">Cualquier acceso</option>' +
      ["Acceso libre", "No abierto", "Sin dato"].map((v) => "<option>" + esc(v) + "</option>").join("");
  }
  function corpusFiltrosEventos() {
    const leer = () => {
      cstate.search = $("#f_cor_search").value.toLowerCase().trim();
      cstate.cluster = $("#f_cor_cluster").value;
      cstate.tec = $("#f_cor_tec").value;
      cstate.acceso = $("#f_cor_acceso").value;
      cstate.y0 = $("#f_cor_y0").value;
      cstate.y1 = $("#f_cor_y1").value;
      cstate.page = 1;
      renderCorpus();
    };
    const repintar = debounce(leer, 90);
    ["f_cor_search", "f_cor_cluster", "f_cor_tec", "f_cor_acceso", "f_cor_y0", "f_cor_y1"].forEach((id) => {
      const ev = ["f_cor_search", "f_cor_y0", "f_cor_y1"].includes(id) ? "input" : "change";
      $("#" + id).addEventListener(ev, () => { leer(); repintar(); });
    });
  }
  function setCorpusTech(techId) {
    cstate.tec = techId; cstate.page = 1;
    $("#f_cor_tec").value = techId;
    goSection("corpus");
    renderCorpus();
    haltDetail();
  }
  async function renderCorpus() {
    const my = ++cstate.req;
    const q = qs({
      page: cstate.page, per: cstate.per, search: cstate.search,
      cluster: cstate.cluster, tec: cstate.tec, acceso: cstate.acceso,
      y0: cstate.y0, y1: cstate.y1
    });
    let r;
    try { r = await api("/api/corpora/" + cur.id + "/docs?" + q); }
    catch (e) { $("#corpus_count").textContent = "Error: " + e.message; return; }
    if (my !== cstate.req) return;

    const total = r.total || 0;
    $("#corpus_count").textContent = fmt(total) + " documento" + (total === 1 ? "" : "s");
    const pages = Math.max(1, r.pages || 1);
    if (cstate.page > pages) cstate.page = pages;

    const tb = $("#tabla_corpus tbody");
    tb.innerHTML = "";
    (r.docs || []).forEach((d) => {
      const tr = document.createElement("tr");
      const href = d.enlace || (d.doi ? "https://doi.org/" + encodeURIComponent(d.doi) : "#");
      const cname = (cur.clusters && cur.clusters[d.cluster]) ? cur.clusters[d.cluster].nombre : null;
      tr.appendChild(td(d.anio || "—", "num"));
      tr.appendChild(td(esc(d.titulo)));
      tr.appendChild(td(esc(d.autores)));
      tr.appendChild(td(esc(d.fuente) || "—"));
      tr.appendChild(td("<b>" + d.citas + "</b>", "num"));
      tr.appendChild(td(cname ? badge(cname, CLUSTER_COL[d.cluster]) : "—"));
      tr.appendChild(td(badge(d.acceso, ACCESO_COL[d.acceso] || "#5d7280")));
      tr.appendChild(td('<a href="' + esc(href) + '" target="_blank" rel="noopener" style="color:#1a7f8e">' + esc(d.doi || "enlace") + "</a>"));
      tb.appendChild(tr);
    });
    if (!(r.docs || []).length) tb.innerHTML = '<tr><td colspan="8" style="text-align:center;color:#5d7280">Sin resultados.</td></tr>';

    const pg = $("#corpus_paginacion");
    pg.innerHTML = "";
    const mk = (label, page, cls, disabled) => {
      const b = document.createElement("button");
      b.textContent = label;
      if (cls) b.className = cls;
      b.disabled = Boolean(disabled);
      b.addEventListener("click", () => { cstate.page = page; renderCorpus(); });
      pg.appendChild(b);
    };
    mk("«", 1, "", cstate.page === 1);
    mk("‹", cstate.page - 1, "", cstate.page === 1);
    for (let p = Math.max(1, cstate.page - 3); p <= Math.min(pages, cstate.page + 3); p++) {
      mk(String(p), p, p === cstate.page ? "active" : null);
    }
    mk("›", cstate.page + 1, "", cstate.page === pages);
    mk("»", pages, "", cstate.page === pages);
    pg.appendChild(Object.assign(document.createElement("span"), { textContent: "Página " + cstate.page + " / " + pages }));
  }

  async function setActiveCorpus(id) {
    const t = corporaList().find((x) => x.id === id) || corporaList()[0];
    cur.id = t.id;
    cur.meta = t.meta; cur.clusters = t.clusters; cur.source = t.meta.csv || t.meta.db;
    cur.series = null; cur.top5 = [];
    renderCorpusTabs();
    renderKpis();
    $("#corpus_nombre").textContent = "";
    $("#corpus_fuente").textContent = cur.source || t.id;
    ["f_cor_search", "f_cor_y0", "f_cor_y1"].forEach((i) => { $("#" + i).value = ""; });
    cstate.search = ""; cstate.cluster = ""; cstate.acceso = ""; cstate.y0 = ""; cstate.y1 = ""; cstate.page = 1;
    corpusFiltrosOpciones();
    renderCorpus();
    /* las gráficas derivadas (`chart_*.db`) se recalculan para este corpus */
    refrescarGraficos();
  }

  /* ========================== EXPORTAR ========================== */
  function corpusQuery() {
    return qs({
      per: 5000, search: cstate.search, cluster: cstate.cluster, tec: cstate.tec,
      acceso: cstate.acceso, y0: cstate.y0, y1: cstate.y1
    });
  }
  function addExportHandlers() {
    $$("[data-svg]").forEach((b) => b.addEventListener("click", (e) => { e.preventDefault(); downloadSvg(b.dataset.svg); }));
    $$("[data-csv]").forEach((b) => b.addEventListener("click", (e) => {
      e.preventDefault();
      downloadUrl("/api/export/table/" + encodeURIComponent(b.dataset.csv) + ".csv", b.dataset.csv + ".csv")
        .catch((err) => alert("Error al exportar: " + err.message));
    }));
    $$("[data-corpus-csv]").forEach((b) => b.addEventListener("click", (e) => {
      e.preventDefault();
      downloadUrl("/api/export/corpus/" + b.dataset.corpusCsv + ".csv", "corpus_" + b.dataset.corpusCsv + ".csv")
        .catch((err) => alert("Error al exportar: " + err.message));
    }));
    $$("[data-corpus-json]").forEach((b) => b.addEventListener("click", (e) => {
      e.preventDefault();
      downloadUrl("/api/export/corpus/" + b.dataset.corpusJson + ".json", "corpus_" + b.dataset.corpusJson + ".json")
        .catch((err) => alert("Error al exportar: " + err.message));
    }));
    $("#btn_corpus_csv").addEventListener("click", (e) => {
      e.preventDefault();
      downloadUrl("/api/export/corpus/" + cur.id + ".csv?" + corpusQuery(),
        "corpus_" + cur.id + "_filtrado.csv")
        .catch((err) => alert("Error al exportar: " + err.message));
    });
    $("#btn_data_json").addEventListener("click", (e) => {
      e.preventDefault();
      downloadUrl("/api/export/app_data.json", "app_data.json")
        .catch((err) => alert("Error al exportar: " + err.message));
    });
  }

  /* ========================== EDITOR .db ========================== */
  function rolDb(d) {
    if (d.derivada) return "derivada · " + (d.titulo || d.gid);
    const name = d.name;
    if (/^corpus_/.test(name)) {
      const cid = name.match(/corpus_(\d+)\.db/)[1];
      const m = (corporaList() || []).find((c) => c.id === cid);
      return m ? m.meta.nombre : ("corpus " + cid);
    }
    return name === "catalogo_tecnologias.db" ? "catálogo de tecnologías" : "observatorio";
  }
  function renderDbList(dbs, dir) {
    $("#db_dir").textContent = "Carpeta de bases: " + (dir || "") +
      " · edite con sqlite3 / DBeaver y el portal se recalcula solo.";
    const tb = $("#tabla_dbs tbody");
    tb.innerHTML = "";
    (dbs || []).forEach((d) => {
      const tr = document.createElement("tr");
      if (d.derivada) tr.className = "db-derivada";
      tr.appendChild(td("<b>" + esc(d.name) + "</b>" +
        (d.derivada ? ' <a href="#" data-goto="' + esc(d.gid || "") +
          '" title="Editar esta base derivada">✎</a>' : "")));
      tr.appendChild(td(esc(rolDb(d))));
      tr.appendChild(td((d.bytes / 1024).toFixed(1) + " KB", "num"));
      tr.appendChild(td(fmt(d.filas), "num"));
      tr.appendChild(td(Object.keys(d.tablas || {}).map((k) => esc(k) + ":" + d.tablas[k]).join(" · ")));
      tr.appendChild(td(d.existe ? esc(d.iso) : "<span style='color:#a83232'>falta</span>"));
      tr.appendChild(td(d.existe ? '<a href="/api/db/download/' + d.name + '" download>↓ ' + esc(d.name) + "</a>" : "—"));
      tb.appendChild(tr);
    });
    tb.querySelectorAll("[data-goto]").forEach((a) => a.addEventListener("click", (e) => {
      e.preventDefault();
      if (a.dataset.goto) irAEditorGrafico(a.dataset.goto);
    }));
  }
  async function loadDbList() {
    try {
      const r = await api("/api/db");
      renderDbList(r.dbs, r.dir);
    } catch (e) {
      $("#db_dir").textContent = "No se pudo leer el inventario: " + e.message;
    }
  }
  async function mostrarEsquema(name) {
    try {
      const r = await api("/api/db/" + encodeURIComponent(name) + "/schema");
      const box = $("#db_esquema");
      box.innerHTML = Object.entries(r.objetos || {}).map(([k, v]) =>
        "<div><b>" + esc(k) + "</b><br>" + esc(typeof v === "string" ? v : JSON.stringify(v)) + "</div>").join("<hr>");
      box.classList.remove("hidden");
    } catch (e) { $("#db_esquema").textContent = "Error: " + e.message; }
  }

  function corpusDbName() { return "corpus_" + ed.corpus + ".db"; }
  function renderCorpusSelects() {
    const sel = $("#ed_corpus"), sd = $("#sql_db");
    const ids = corporaList().map((c) => c.id);
    sel.innerHTML = ids.map((i) => '<option value="' + i + '">' + esc((corporaList().find((c) => c.id === i) || {}).meta.nombre || i) + "</option>").join("");
    sel.value = ed.corpus;
    const dbs = ((D.dbs || []).map((d) => d.name));
    sd.innerHTML = dbs.map((n) => '<option value="' + esc(n) + '">' + esc(n) + "</option>").join("");
  }
  async function renderEditorList() {
    const my = ++ed.req;
    let r;
    try { r = await api("/api/corpora/" + ed.corpus + "/docs?" + qs({ page: ed.page, per: ed.per, search: ed.search })); }
    catch (e) { $("#ed_info").textContent = "Error: " + e.message; return; }
    if (my !== ed.req) return;
    const tb = $("#tabla_ed tbody");
    tb.innerHTML = "";
    (r.docs || []).forEach((d) => {
      const tr = document.createElement("tr");
      tr.appendChild(td(String(d.id), "num"));
      tr.appendChild(td(String(d.anio || ""), "num"));
      tr.appendChild(td(esc(trunc(d.titulo, 70))));
      tr.appendChild(td(String(d.citas), "num"));
      tr.appendChild(td(badge(d.acceso, ACCESO_COL[d.acceso] || "#5d7280")));
      tr.appendChild(td(d.cluster == null ? "—" : String(d.cluster), "num"));
      const acc = document.createElement("td");
      const b = document.createElement("button");
      b.className = "btn btn-sm btn-ghost";
      b.textContent = "Editar";
      b.addEventListener("click", () => { ed.docId = d.id; abrirFormDoc(d); });
      acc.appendChild(b);
      tr.appendChild(acc);
      tb.appendChild(tr);
    });
    $("#ed_info").textContent = fmt(r.total || 0) + " filas · página " + r.page + "/" + (r.pages || 1) +
      " en " + corpusDbName();
    $("#ed_prev").disabled = (r.page || 1) <= 1;
    $("#ed_next").disabled = (r.page || 1) >= (r.pages || 1);
  }
  function abrirFormDoc(d) {
    const f = $("#ed_form");
    f.classList.remove("hidden");
    $("#ed_form_title").textContent = d.id ? ("Documento #" + d.id) : "Nuevo documento";
    $("#ed_dbname").textContent = corpusDbName();
    $("#ed_id").value = d.id || "";
    $("#ed_n").value = d.n || "";
    $("#ed_anio").value = d.anio || "";
    $("#ed_citas").value = d.citas || 0;
    $("#ed_titulo").value = d.titulo || "";
    $("#ed_autores").value = d.autores || "";
    $("#ed_fuente").value = d.fuente || "";
    $("#ed_doi").value = d.doi || "";
    $("#ed_enlace").value = d.enlace || "";
    $("#ed_hallazgos").value = d.hallazgos || "";
    $("#ed_limitaciones").value = d.limitaciones || "";
    $("#ed_novedad").value = d.novedad || "";
    $("#ed_acceso").value = d.acceso || "Sin dato";
    const cls = cur.clusters || {};
    $("#ed_cluster").innerHTML = '<option value="">—</option>' +
      Object.keys(cls).map((k) => '<option value="' + k + '">' + esc(cls[k].nombre) + "</option>").join("");
    $("#ed_cluster").value = (d.cluster == null) ? "" : String(d.cluster);
    $("#ed_delete").disabled = !d.id;
    f.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }
  function docPayload() {
    const cl = $("#ed_cluster").value;
    return {
      n: num($("#ed_n").value), anio: num($("#ed_anio").value), titulo: $("#ed_titulo").value.trim(),
      autores: $("#ed_autores").value.trim(), fuente: $("#ed_fuente").value.trim(),
      citas: num($("#ed_citas").value, 0), doi: $("#ed_doi").value.trim(),
      enlace: $("#ed_enlace").value.trim(), acceso: $("#ed_acceso").value,
      cluster: cl === "" ? null : +cl,
      hallazgos: $("#ed_hallazgos").value, limitaciones: $("#ed_limitaciones").value,
      novedad: $("#ed_novedad").value
    };
  }
  async function guardarDoc(ev) {
    ev.preventDefault();
    const msg = $("#ed_msg");
    msg.textContent = "Guardando…";
    const id = $("#ed_id").value;
    const path = id ? "/api/db/" + corpusDbName() + "/docs/" + id : "/api/db/" + corpusDbName() + "/docs";
    try {
      const r = await apiJSON(path, id ? "PATCH" : "POST", docPayload());
      msg.textContent = "Guardado (#" + r.doc.id + ") en " + corpusDbName();
      await trasEscritura();
      ed.docId = r.doc.id;
      abrirFormDoc(r.doc);
      renderEditorList();
    } catch (e) { msg.textContent = "Error: " + e.message; }
  }
  async function borrarDoc() {
    const id = $("#ed_id").value;
    if (!id || !confirm("¿Eliminar el documento #" + id + " de " + corpusDbName() + "?")) return;
    const msg = $("#ed_msg");
    try {
      await apiJSON("/api/db/" + corpusDbName() + "/docs/" + id, "DELETE");
      msg.textContent = "Eliminado";
      ed.docId = null;
      $("#ed_form").classList.add("hidden");
      await trasEscritura();
      renderEditorList();
    } catch (e) { msg.textContent = "Error: " + e.message; }
  }

  function cargarTecForm(t) {
    $("#tec_nombre").value = t.nombre || "";
    $("#tec_trl").value = t.trl || 1;
    $("#tec_capex").value = t.capex || "Medio";
    $("#tec_opex").value = t.opex || "Medio";
    $("#tec_seg").value = t.seg || 3;
    $("#tec_amb").value = t.amb || 3;
    $("#tec_cat").value = t.cat_out || t.cat;
    $("#tec_kws").value = (t.kws || []).join("\n");
    $("#tec_msg").textContent = t.n_docs + " documentos asignados";
  }
  async function cargarTec() {
    const tid = $("#ed_tec").value;
    if (!tid) return;
    try {
      const d = await api("/api/tecnologias/" + encodeURIComponent(tid));
      cargarTecForm(d);
      const cats = [...new Set((D.tecnologias || []).map((x) => x.cat_out))];
      $("#tec_cat").innerHTML = cats.map((c) => "<option>" + esc(c) + "</option>").join("");
      $("#tec_cat").value = d.cat_out;
    } catch (e) { $("#tec_msg").textContent = "Error: " + e.message; }
  }
  async function guardarTec() {
    const tid = $("#ed_tec").value;
    const msg = $("#tec_msg");
    msg.textContent = "Guardando…";
    try {
      await apiJSON("/api/tecnologias/" + encodeURIComponent(tid), "PATCH", {
        nombre: $("#tec_nombre").value.trim(), trl: num($("#tec_trl").value, 1),
        capex: $("#tec_capex").value, opex: $("#tec_opex").value,
        seg: num($("#tec_seg").value, 3), amb: num($("#tec_amb").value, 3),
        cat: $("#tec_cat").value,
        kws: $("#tec_kws").value.split(/\r?\n/).map((s) => s.trim()).filter(Boolean)
      });
      msg.textContent = "Guardado · reindexando…";
      await trasEscritura({ reindex: true });
      cargarTec();
    } catch (e) { msg.textContent = "Error: " + e.message; }
  }

  function cargarPaisForm(p) {
    $("#p_pais").value = p.pais || "";
    $("#p_cont").value = p.cont || "Global";
    $("#p_gdp_pc").value = p.gdp_pc || "";
    $("#p_tech").value = p.tech || "";
    $("#p_edu").value = p.edu == null ? "" : p.edu;
    $("#p_mining_gdp").value = p.mining_gdp == null ? "" : p.mining_gdp;
    $("#p_seg").value = p.seg == null ? "" : p.seg;
    $("#p_amb").value = p.amb == null ? "" : p.amb;
    $("#p_n_pubs").value = p.n_pubs == null ? "" : p.n_pubs;
  }
  async function guardarPais() {
    const msg = $("#p_msg");
    msg.textContent = "Guardando…";
    try {
      await apiJSON("/api/observatorio/paises_obs", "POST", {
        pais: $("#p_pais").value.trim(), cont: $("#p_cont").value,
        gdp_pc: num($("#p_gdp_pc").value, 0), tech: num($("#p_tech").value, 0),
        edu: num($("#p_edu").value, 0), mining_gdp: num($("#p_mining_gdp").value, 0),
        seg: num($("#p_seg").value, 0), amb: num($("#p_amb").value, 0),
        n_pubs: num($("#p_n_pubs").value, 0)
      });
      msg.textContent = "Guardado";
      await trasEscritura();
    } catch (e) { msg.textContent = "Error: " + e.message; }
  }
  function renderIgfEditor() {
    const host = $("#ed_igf");
    host.innerHTML = "";
    const fondos = filasDe("chart_igf").length
      ? filasDe("chart_igf").map((f) => ({ region: f.region || f.etiqueta, pct: f.pct }))
      : (D.igf_funds || []);
    fondos.forEach((f) => {
      const wrap = document.createElement("label");
      wrap.className = "igf-item";
      wrap.innerHTML = "<span>" + esc(f.region) + "</span>";
      const inp = document.createElement("input");
      inp.type = "number"; inp.step = "0.1"; inp.min = "0"; inp.max = "100";
      inp.value = f.pct;
      inp.dataset.region = f.region;
      inp.addEventListener("change", async () => {
        try {
          await apiJSON("/api/observatorio/igf", "POST", { region: f.region, pct: +inp.value });
          await trasEscritura();
        } catch (e) { alert("Error: " + e.message); }
      });
      wrap.appendChild(inp);
      host.appendChild(wrap);
    });
  }

  async function runSql() {
    const out = $("#sql_out");
    out.textContent = "Ejecutando…";
    try {
      const r = await apiJSON("/api/db/" + encodeURIComponent($("#sql_db").value) + "/query", "POST",
        { sql: $("#sql_txt").value, max_rows: 200 });
      const cols = r.columns || [];
      const t = document.createElement("table");
      t.className = "tbl";
      t.innerHTML = "<thead><tr>" + cols.map((c) => "<th>" + esc(c) + "</th>").join("") + "</tr></thead>";
      const tb = document.createElement("tbody");
      (r.rows || []).forEach((row) => {
        const tr = document.createElement("tr");
        row.forEach((v) => tr.appendChild(td(esc(v == null ? "" : v))));
        tb.appendChild(tr);
      });
      t.appendChild(tb);
      out.innerHTML = "";
      out.appendChild(t);
      const note = document.createElement("p");
      note.className = "card-note";
      note.textContent = (r.truncated ? "Mostrando las primeras filas. " : "") + (r.rows || []).length + " filas.";
      out.appendChild(note);
    } catch (e) { out.textContent = "Error: " + e.message; }
  }

  /* ========================== EDITOR DE BASES DERIVADAS ==========================
   * Cada gráfica/tabla del portal tiene su propio `<gid>.db` (tablas `base`,
   * `datos`, `overrides`, `columnas`, `meta`, `fuentes`). Lo que se pinta sale
   * de `datos`; `base` es el cálculo del servidor. Editar aquí —o con
   * sqlite3/DBeaver sobre la tabla `datos`— deja una versión en `overrides`
   * que sobrevive a las recargas hasta que se pulse «Restablecer». */
  const ged = { gid: "chart_anios", fila: null, req: 0 };
  const qCorpus = () => (cur && cur.id ? "?cid=" + encodeURIComponent(cur.id) : "");

  function renderGraficoOpciones() {
    const sel = $("#gd_sel");
    // `graficos` trae las ligeras; las pesadas (tabla_corpus, tabla_deliverable)
    // llegan solo como `graficos_meta`, pero también son editables.
    const lista = (D.graficos || []).concat(D.graficos_meta || []);
    if (!lista.length) return;
    const actual = sel.value || ged.gid;
    sel.innerHTML = lista.map((g) =>
      '<option value="' + esc(g.id) + '">' + esc(g.id) + " · " + esc(g.titulo) + "</option>").join("");
    sel.value = lista.some((g) => g.id === actual) ? actual : lista[0].id;
    ged.gid = sel.value;
  }
  async function cargarGrafico(gid) {
    const my = ++ged.req;
    ged.gid = gid; ged.fila = null;
    const info = $("#gd_info");
    info.textContent = "Cargando " + gid + ".db…";
    let r;
    try { r = await api("/api/grafico/" + encodeURIComponent(gid) + qCorpus()); }
    catch (e) { info.textContent = "Error: " + e.message; return; }
    if (my !== ged.req) return;               // llegó una respuesta más reciente
    absorberGraficos([r]);
    const f = ficha(gid);
    const meta = f.meta || {};
    $("#gd_titulo").textContent = f.titulo + " · " + f.db;
    info.innerHTML = esc(f.desc || "") +
      ' · fuente: <code>' + esc(f.fuente || "") + "</code>" +
      ' · <b>' + fmt((f.filas || []).length) + "</b> filas (cálculo: " + fmt(meta.filas_base || 0) + ")" +
      (meta.ediciones ? ' · <b>' + meta.ediciones + "</b> ediciones manuales" : " · sin ediciones") +
      ' · <a href="/api/grafico/' + esc(gid) + '.db' + qCorpus() + '" download>↓ .db</a>' +
      ' · <a href="/api/grafico/' + esc(gid) + '.csv' + qCorpus() + '" download>↓ CSV</a>' +
      ' · <a href="/api/grafico/' + esc(gid) + '.json' + qCorpus() + '" download>↓ JSON</a>';

    const cols = f.columnas || [];
    const t = document.createElement("table");
    t.className = "tbl tbl-editable";
    t.innerHTML = "<thead><tr><th>clave</th>" +
      cols.map((c) => '<th class="' + (c.tipo === "num" || c.tipo === "int" ? "num" : "") + '">' +
        esc(c.titulo) + "</th>").join("") +
      "<th></th></tr></thead>";
    const tb = document.createElement("tbody");
    (f.filas || []).forEach((fila) => {
      const tr = document.createElement("tr");
      tr.dataset.clave = fila.clave;
      tr.appendChild(td("<code>" + esc(fila.clave) + "</code>"));
      cols.forEach((c) => {
        const v = fila[c.nombre];
        const txt = v == null ? "" : String(v);
        tr.appendChild(td(c.tipo === "color" ? badge(txt, txt) : esc(trunc(txt, 70)),
          (c.tipo === "num" || c.tipo === "int") ? "num" : ""));
      });
      const acc = document.createElement("td");
      acc.appendChild(Object.assign(document.createElement("button"), {
        className: "btn btn-sm btn-ghost", textContent: "Editar",
        onclick: () => abrirFormGrafico(fila)
      }));
      acc.appendChild(document.createTextNode(" "));
      acc.appendChild(Object.assign(document.createElement("button"), {
        className: "btn btn-sm btn-danger", textContent: "Eliminar",
        onclick: () => borrarFilaGrafico(fila.clave)
      }));
      tr.appendChild(acc);
      tb.appendChild(tr);
    });
    t.appendChild(tb);
    const wrap = $("#gd_tabla");
    wrap.innerHTML = "";
    wrap.appendChild(t);
  }
  function abrirFormGrafico(fila) {
    const f = ficha(ged.gid);
    const esNueva = !fila;
    const datos = esNueva ? {} : (fila || {});
    const campos = (f.columnas || []).map((c) => {
      const v = datos[c.nombre];
      const tipo = c.tipo === "num" || c.tipo === "int" ? "number" : "text";
      const val = v == null ? "" : String(v);
      const control = tipo === "number"
        ? '<input type="number" step="any" data-campo="' + esc(c.nombre) + '" value="' + esc(val) + '">'
        : '<input type="text" data-campo="' + esc(c.nombre) + '" value="' + esc(val) + '">';
      return "<label>" + esc(c.titulo) + control + "</label>";
    }).join("");
    const form = document.createElement("form");
    form.className = "ed-form";
    form.innerHTML =
      "<h4>" + (esNueva ? "Nueva fila en " : "Editar " + esc(datos.clave) + " · ") +
      "<code>" + esc(ged.gid) + ".db</code></h4>" +
      '<div class="form-grid">' + campos + "</div>" +
      (esNueva ? '<label>Clave<input type="text" id="gd_clave" required></label>' : "") +
      '<label>Nota interna (columna <code>extra</code>, no se pinta)<input type="text" id="gd_extra" value="' +
      esc(datos.extra || "") + '"></label>' +
      '<div class="form-actions">' +
      '<button type="submit" class="btn btn-sm">Guardar</button>' +
      '<button type="button" class="btn btn-sm btn-ghost" id="gd_cancel">Cancelar</button>' +
      '<span class="ed-msg"></span></div>';
    const host = $("#gd_form");
    host.innerHTML = "";
    host.appendChild(form);
    form.addEventListener("submit", async (ev) => {
      ev.preventDefault();
      const msg = form.querySelector(".ed-msg");
      msg.textContent = "Guardando…";
      const payload = { clave: datos.clave };
      if (esNueva) payload.clave = String($("#gd_clave").value).trim();
      form.querySelectorAll("[data-campo]").forEach((i) => {
        const col = (f.columnas || []).find((c) => c.nombre === i.dataset.campo);
        if (!col) return;
        const v = i.value;
        payload[col.nombre] = (col.tipo === "num" || col.tipo === "int")
          ? num(v, v === "" ? null : 0) : v;
      });
      payload.extra = $("#gd_extra").value;
      try {
        await apiJSON("/api/grafico/" + encodeURIComponent(ged.gid) + "/fila", "POST", payload);
        msg.textContent = "Guardado";
        await trasEscritura();
        await cargarGrafico(ged.gid);
      } catch (e) { msg.textContent = "Error: " + e.message; }
    });
    form.querySelector("#gd_cancel").addEventListener("click", () => { host.innerHTML = ""; });
    host.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }
  async function borrarFilaGrafico(clave) {
    if (!confirm("¿Eliminar la fila «" + clave + "» de " + ged.gid + ".db?")) return;
    try {
      await apiJSON("/api/grafico/" + encodeURIComponent(ged.gid) + "/fila/" +
        encodeURIComponent(clave), "DELETE");
      await trasEscritura();
      await cargarGrafico(ged.gid);
    } catch (e) { alert("Error: " + e.message); }
  }
  async function restablecerGrafico() {
    if (!confirm("¿Descartar las ediciones manuales de " + ged.gid +
      ".db y volver al cálculo del servidor?")) return;
    try {
      await apiJSON("/api/grafico/" + encodeURIComponent(ged.gid) + "/reset", "POST", {});
      await trasEscritura();
      await cargarGrafico(ged.gid);
    } catch (e) { alert("Error: " + e.message); }
  }
  async function sincronizarGraficos() {
    const msg = $("#gd_sync_msg");
    msg.textContent = "Sincronizando…";
    try {
      const r = await apiJSON("/api/graficos/sync", "POST", {});
      msg.textContent = (r.sincronizados || []).length
        ? "Actualizadas: " + (r.sincronizados || []).join(", ")
        : "Todo al día (no se ha escrito nada)";
      await recargarTodo();
      await cargarGrafico(ged.gid);
    } catch (e) { msg.textContent = "Error: " + e.message; }
  }
  function irAEditorGrafico(gid) {
    renderGraficoOpciones();
    $("#gd_sel").value = gid;
    ged.gid = gid;
    goSection("editor");
    cargarGrafico(gid);
  }

  /* ========================== RECARGA DE GRÁFICAS DERIVADAS ========================== */
  let refreshReq = 0;
  async function refrescarGraficos() {
    const my = ++refreshReq;
    let r;
    try { r = await api("/api/graficos" + qCorpus()); }
    catch (e) { return null; }
    if (my !== refreshReq) return null;
    absorberGraficos(r.graficos || []);
    Object.assign(GB, { graficos_meta: r.meta || null });
    renderCharts();
    tablaObs($("#tabla_paises_obs"));
    renderGraficoOpciones();
    if (ged.gid) await cargarGrafico(ged.gid);
    return r;
  }

  async function recargarDbs(msg) {
    try {
      const r = await apiJSON("/api/admin/reload", "POST", {});
      renderDbList(r.dbs, $("#db_dir").textContent);
      if (msg) $("#tec_msg").textContent = msg;
    } catch (e) { alert("Error: " + e.message); }
  }
  async function recargarTodo() {
    D = window.APP_DATA = await api("/api/bootstrap");
    Object.assign(CONT_COL, D.cont_col || {});
    absorberGraficos(D.graficos || []);
    const t = corporaList().find((x) => x.id === cur.id) || corporaList()[0];
    cur.meta = t.meta; cur.clusters = t.clusters;
    renderKpis();
    renderCharts();
    tablaObs($("#tabla_paises_obs"));
    renderDeliverable($("#tabla_deliverable"));
    techFiltrosOpciones();
    renderMatriz();
    renderCorpusTabs();
    renderEditorSelects();
    renderGraficoOpciones();
    renderIgfEditor();
    await setActiveCorpus(cur.id);
    await loadDbList();
  }
  async function trasEscritura(opts) {
    await recargarDbs();
    await recargarTodo();
  }
  async function rebuildDbs() {
    if (!confirm("¿Recrear los .db desde los CSV fuente? Sobrescribe los cambios.")) return;
    try {
      const r = await apiJSON("/api/admin/rebuild", "POST", { force: true });
      await recargarTodo();
      $("#tec_msg").textContent = "Bases recreadas (" + (r.log || []).length + " líneas de registro)";
    } catch (e) { alert("Error: " + e.message); }
  }

  function editorEvents() {
    $("#btn_db_reload").addEventListener("click", () => recargarDbs("Bases recargadas"));
    $("#btn_db_rebuild").addEventListener("click", rebuildDbs);
    $("#btn_db_schema").addEventListener("click", () => {
      const first = (D.dbs || []).find((d) => d.existe);
      if (first) mostrarEsquema(first.name);
    });
    $("#ed_corpus").addEventListener("change", (e) => {
      ed.corpus = e.target.value; ed.page = 1;
      corpusFiltrosOpciones();
      renderEditorList();
    });
    const repintar = debounce(renderEditorList, 160);
    $("#ed_search").addEventListener("input", (e) => {
      ed.search = e.target.value.trim(); ed.page = 1;
      repintar();
    });
    $("#ed_prev").addEventListener("click", () => { if (ed.page > 1) { ed.page--; renderEditorList(); } });
    $("#ed_next").addEventListener("click", () => { ed.page++; renderEditorList(); });
    $("#ed_new").addEventListener("click", () => {
      ed.docId = null;
      abrirFormDoc({ acceso: "Sin dato", citas: 0, anio: new Date().getFullYear() });
    });
    $("#ed_form").addEventListener("submit", guardarDoc);
    $("#ed_cancel").addEventListener("click", () => $("#ed_form").classList.add("hidden"));
    $("#ed_delete").addEventListener("click", borrarDoc);
    $("#ed_reindex").addEventListener("click", async () => {
      try {
        const r = await apiJSON("/api/corpora/" + ed.corpus + "/reindex", "POST", {});
        $("#ed_msg").textContent = "Reindexado: " + JSON.stringify(r.cambios || {});
        await trasEscritura();
      } catch (e) { $("#ed_msg").textContent = "Error: " + e.message; }
    });
    $("#ed_tec").addEventListener("change", cargarTec);
    $("#tec_save").addEventListener("click", guardarTec);
    $("#gd_sel").addEventListener("change", (e) => cargarGrafico(e.target.value));
    $("#gd_new").addEventListener("click", () => abrirFormGrafico(null));
    $("#gd_reset").addEventListener("click", restablecerGrafico);
    $("#gd_sync").addEventListener("click", sincronizarGraficos);
    $$("[data-edit]").forEach((b) => b.addEventListener("click", (e) => {
      e.preventDefault();
      irAEditorGrafico(b.dataset.edit);
    }));
    $("#ed_pais").addEventListener("change", (e) => {
      const p = (D.paises_obs || []).find((x) => x.pais === e.target.value);
      if (p) cargarPaisForm(p);
    });
    $("#p_save").addEventListener("click", guardarPais);
    $("#sql_run").addEventListener("click", runSql);
  }
  function renderEditorSelects() {
    renderCorpusSelects();
    $("#ed_tec").innerHTML = '<option value="">—</option>' +
      (D.tecnologias || []).map((t) => '<option value="' + t.id + '">' + esc(t.nombre) + "</option>").join("");
    $("#ed_pais").innerHTML = '<option value="">—</option>' +
      (D.paises_obs || []).map((p) => '<option value="' + esc(p.pais) + '">' + esc(p.pais) + "</option>").join("");
  }

  /* ========================== VIGILANCIA DE .db ========================== */
  function pintarEstado(h) {
    const dbs = h.dbs || [];
    const ok = dbs.filter((d) => d.existe).length;
    const filas = dbs.reduce((a, d) => a + (d.filas || 0), 0);
    $("#db_status").innerHTML = '<span class="dot live"></span> Conectado · ' + ok + "/" + dbs.length +
      " bases <code>.db</code> · " + fmt(filas) + " filas · versión <code>" + esc(h.version || "") + "</code>" +
      ' · el portal se recarga solo si cambia una base';
  }
  async function vigilar() {
    try {
      const h = await api("/api/health");
      pintarEstado(h);
      if (version && h.version !== version) {
        version = h.version;
        await recargarTodo();
      }
    } catch (e) {
      $("#db_status").innerHTML = '<span class="dot"></span> Sin conexión con el servidor (' + esc(e.message) + ")";
    }
  }

  /* ========================== ARRANQUE ========================== */
  async function init() {
    try {
      D = await api("/api/bootstrap");
    } catch (e) {
      document.body.innerHTML = '<main style="padding:3rem"><h1>Portal MAPE</h1>' +
        "<p>No se pudo leer <code>/api/bootstrap</code>: " + esc(e.message) +
        "</p><p>Arranque el servidor con <code>python server/app.py</code>.</p></main>";
      return;
    }
    window.APP_DATA = D;
    Object.assign(CONT_COL, D.cont_col || {});
    absorberGraficos(D.graficos || []);
    cur.clusters = D.clusters;
    cur.meta = D.meta;
    cur.id = "124";
    version = "";

    navEvents();
    renderKpis();
    renderCharts();
    tablaObs($("#tabla_paises_obs"));
    renderDeliverable($("#tabla_deliverable"));
    techFiltrosOpciones();
    techFiltrosEventos();
    renderMatriz();
    renderCorpusTabs();
    $("#corpus_tabs").addEventListener("click", (e) => {
      const b = e.target.closest(".tab");
      if (b) setActiveCorpus(b.dataset.corpus);
    });
    corpusFiltrosOpciones();
    corpusFiltrosEventos();
    $("#corpus_fuente").textContent = cur.meta.csv || cur.meta.db;
    renderCorpus();
    addExportHandlers();

    renderEditorSelects();
    renderGraficoOpciones();
    editorEvents();
    renderIgfEditor();
    await cargarGrafico(ged.gid);
    await loadDbList();

    await vigilar();
    setInterval(vigilar, 8000);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();