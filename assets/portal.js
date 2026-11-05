/* Portal UASM · versión autónoma (sin servidor).
 * Todos los datos proceden de los ficheros .db (SQLite) que carga el usuario.
 * La lectura se hace en el navegador con sql.js y las figuras con Plotly. */
(function () {
  "use strict";
  const Plotly = window.Plotly;
  const $ = (s) => document.querySelector(s);
  const esc = (s) => String(s == null ? "" : s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  const fmt = (n) => Number(n || 0).toLocaleString("es-CO");
  const num = (v, d) => (v === "" || v == null || isNaN(v) ? (d === undefined ? null : d) : +v);
  const trunc = (s, n) => { s = String(s || ""); return s.length > n ? s.slice(0, n - 1) + "…" : s; };
  
  // Idioma actual (se sincronizará con translation.js)
  window.currentLang = 'es';

  const OI = { azul: "#0072B2", naranja: "#E69F00", verde: "#009E73", rojo: "#D55E00",
    morado: "#CC79A7", celeste: "#56B4E9", amarillo: "#F0E442", negro: "#1A1A1A",
    gris: "#7F7F7F", grisclaro: "#BFBFBF" };

  const PLOT_CONFIG = {
    displaylogo: false, responsive: true, displayModeBar: true,
    modeBarButtonsToRemove: ["lasso2d", "select2d", "autoScale2d"]
  };
  const BASE_FONT = { family: "Segoe UI, Arial, sans-serif", size: 12 };
  function themeColors() {
    const cs = getComputedStyle(document.documentElement);
    const g = (n, d) => (cs.getPropertyValue(n) || "").trim() || d;
    return { ink: g("--ink", "#1c2b36"), line: g("--line", "#dfe6eb"),
      muted: g("--muted", "#5d7280"), card: g("--card", "#ffffff") };
  }
  const baseLayout = (extra) => Object.assign({
    font: Object.assign({ color: themeColors().ink }, BASE_FONT), autosize: true,
    paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)",
    margin: { l: 58, r: 26, t: 44, b: 52, automargin: true },
    legend: { orientation: "h", y: -0.22, x: 0, font: { size: 11 } }
  }, extra || {});
  function plot(gd, fig, height) {
    if (!gd || !Plotly) return;
    const tc = themeColors();
    const lay = baseLayout(Object.assign({ height: height || 340 }, fig.layout || {}));
    lay.font = Object.assign({ color: tc.ink }, BASE_FONT, lay.font || {});
    ["xaxis", "yaxis", "xaxis2", "yaxis2", "xaxis3", "yaxis3", "xaxis4", "yaxis4"]
      .forEach((k) => {
        const ax = lay[k]; if (!ax) return;
        lay[k] = Object.assign({ gridcolor: tc.line, zerolinecolor: tc.line, linecolor: tc.line }, ax);
        lay[k].tickfont = Object.assign({ color: tc.ink }, ax.tickfont || {});
      });
    if (lay.polar && lay.polar.radialaxis) {
      lay.polar.radialaxis = Object.assign({ gridcolor: tc.line, linecolor: tc.line,
        tickfont: { color: tc.ink } }, lay.polar.radialaxis);
    }
    Plotly.react(gd, fig.data, lay, PLOT_CONFIG);
  }

  /* ---------------- estado ---------------- */
  const DER = {};   /* gid   -> {meta, cols, rows} */
  const RAW = {};   /* nombre-> {db, tabs, filas} */
  let SQL = null;

  /* ============================ sql.js ============================ */
  async function initSql() {
    if (SQL) return SQL;
    const wasm = Uint8Array.from(atob(window.SQL_WASM_BASE64), (c) => c.charCodeAt(0));
    SQL = await window.initSqlJs({ wasmBinary: wasm });
    return SQL;
  }
  function tablaNombres(db) {
    const r = db.exec("SELECT name FROM sqlite_master WHERE type='table'");
    return r.length ? r[0].values.map((v) => v[0]) : [];
  }
  function qRows(db, sql, params) {
    const st = db.prepare(sql);
    if (params) st.bind(params);
    const out = [];
    while (st.step()) out.push(st.getAsObject());
    st.free();
    return out;
  }
  function filasTabla(db, tabla) {
    if (!tablaNombres(db).includes(tabla)) return [];
    return qRows(db, "SELECT * FROM " + tabla);
  }

  async function cargarArchivos(files) {
    const arr = Array.from(files || []);
    if (!arr.length) return;
    await initSql();
    let ok = 0;
    for (const f of arr) {
      if (!/\.db$/i.test(f.name)) continue;
      try {
        const buf = new Uint8Array(await f.arrayBuffer());
        const db = new SQL.Database(buf);
        const tabs = tablaNombres(db);
        const nombre = f.name.replace(/\.db$/i, "");
        if (tabs.includes("meta") && tabs.includes("datos") && tabs.includes("columnas")) {
          const meta = {};
          filasTabla(db, "meta").forEach((r) => { meta[r.key] = r.value; });
          const gid = meta.grafico || nombre;
          DER[gid] = { gid, meta, cols: filasTabla(db, "columnas"),
                       rows: filasTabla(db, "datos"), name: f.name, tabs, db };
        } else {
          RAW[nombre] = { name: f.name, tabs, db, filas: null };
        }
        ok++;
      } catch (e) {
        console.warn("No se pudo abrir " + f.name, e);
      }
    }
    actualizarEstadoCarga(ok);
    try {
      renderizarTodo();
      // Reaplicar tema y traducción después de cargar
      aplicarTema(temaInicial());
      if (typeof translateAll === 'function') {
        setTimeout(translateAll, 100);
      }
      // Re-conectar eventos de tema
      temaEvents();
    } catch (e) {
      console.error('Error al renderizar todo:', e);
    }
  }

  function actualizarEstadoCarga(ok) {
    const nd = Object.keys(DER).length, nr = Object.keys(RAW).length;
    $("#load_msg").innerHTML = ok
      ? `${nd} bases derivadas y ${nr} bases fuente cargadas.`
      : "Ninguna base cargada todavía.";
    const st = $("#db_status");
    st.innerHTML = `<span class="dot live"></span> ${nd + nr} bases cargadas · ` +
      `${nd} gráficas/tablas · ${nr} vistas del corpus`;
  }

  /* ============================ KPIs ============================ */
  function renderKpis() {
    const cor = DER["tabla_corpus"];
    const clus = DER["chart_donut_cluster"];
    const acc = DER["chart_donut_acceso"];
    const tec = DER["chart_tec_bar"];
    const anios = DER["chart_anios"];
    if (!cor && !clus && !anios) { $("#kpis").innerHTML = ""; return; }
    const nDocs = cor ? cor.rows.length : (clus ? clus.rows.reduce((s, r) => s + num(r.docs, 0), 0) : 0);
    const citas = cor ? cor.rows.reduce((s, r) => s + num(r.citas, 0), 0) : 0;
    let oa = 0;
    if (acc) acc.rows.forEach((r) => { if (String(r.acceso) === "Acceso libre" || String(r.acceso) === "Open access") oa = num(r.docs, 0); });
    const oaPct = nDocs ? Math.round(oa / nDocs * 100) : 0;
    const rango = anios && anios.rows.length
      ? Math.min(...anios.rows.map((r) => num(r.anio, 0))) + "–" +
        Math.max(...anios.rows.map((r) => num(r.anio, 0))) : "";
    const clusT = clus ? clustersTematicos(clus.rows) : null;
    const lang = window.currentLang || 'es';
    const kpiLabels = {
      es: ["documentos Scopus", "citas totales", "acceso abierto", "clústeres temáticos", "tecnologías catalogadas", "rango analítico"],
      en: ["Scopus documents", "total citations", "open access", "thematic clusters", "cataloged technologies", "analytical range"]
    };
    const cards = [
      [fmt(nDocs), kpiLabels[lang][0]],
      [fmt(citas), kpiLabels[lang][1]],
      [oa + " · " + oaPct + "%", kpiLabels[lang][2]],
      [clusT ? clusT.length : "—", kpiLabels[lang][3]],
      ["23", kpiLabels[lang][4]],
      [rango || "—", kpiLabels[lang][5]]
    ];
    $("#kpis").innerHTML = cards.map(([v, l]) =>
      `<div class="kpi"><div class="v">${v}</div><div class="l">${l}</div></div>`).join("");
  }

  /* ============================ renderers ============================ */
  const R = {};

  R.chart_anios = (el, rows) => plot(el, {
    data: [{ type: "bar", x: rows.map((r) => num(r.anio)), y: rows.map((r) => num(r.publicaciones)),
      marker: { color: OI.azul, line: { color: "#fff", width: .6 } },
      hovertemplate: "%{x}: %{y} documentos<extra></extra>" }],
    layout: { xaxis: { title: "Año", dtick: 4, tickangle: -45 }, yaxis: { title: "Documentos" }, showlegend: false }
  });

  function donut(el, rows, valKey) {
    plot(el, {
      data: [{ type: "pie", hole: .56, labels: rows.map((r) => r.etiqueta),
        values: rows.map((r) => num(r[valKey])), sort: false,
        marker: { colors: rows.map((r) => r.color || OI.azul) },
        textinfo: "label+percent", textposition: "outside",
        hovertemplate: "%{label}: %{value} (%{percent})<extra></extra>" }],
      layout: { showlegend: false }
    }, 360);
  }
  R.chart_donut_cluster = (el, rows) => donut(el, clustersTematicos(rows), "docs");
  R.chart_donut_acceso = (el, rows) => donut(el, rows, "docs");
  R.chart_cat = (el, rows) => donut(el, rows, "docs");

  /* Una fila es "sin clúster temático" si no tiene clúster asignado. */
  function sinCluster(r) {
    return String(r.cluster == null ? "" : r.cluster).trim() === "" ||
      /sin cl/i.test(String(r.etiqueta || ""));
  }
  function clustersTematicos(rows) { return rows.filter((r) => !sinCluster(r)); }

  R.chart_top5 = (el, rows) => {
    const rr = rows.slice().reverse();
    plot(el, {
      data: [{ type: "bar", orientation: "h", x: rr.map((r) => num(r.citas)),
        y: rr.map((r) => trunc(r.etiqueta, 52)),
        marker: { color: OI.naranja }, text: rr.map((r) => fmt(r.citas)),
        textposition: "auto", hovertemplate: "%{y}<br>%{x} citas<extra></extra>" }],
      layout: { xaxis: { title: "Citas" }, showlegend: false, margin: { l: 320, r: 20, t: 20, b: 40 } }
    }, 300);
  };

  R.chart_igf = (el, rows) => plot(el, {
    data: [{ type: "bar", x: rows.map((r) => r.etiqueta), y: rows.map((r) => num(r.pct)),
      marker: { color: rows.map((r) => r.color || OI.azul) }, text: rows.map((r) => num(r.pct) + "%"),
      textposition: "auto", hovertemplate: "%{x}: %{y}%<extra></extra>" }],
    layout: { yaxis: { title: "% de fondos" }, showlegend: false }
  }, 320);

  R.chart_paises_pub = (el, rows) => {
    const rr = rows.slice().reverse();
    plot(el, {
      data: [{ type: "bar", orientation: "h", x: rr.map((r) => num(r.n)),
        y: rr.map((r) => r.etiqueta), marker: { color: OI.verde },
        text: rr.map((r) => fmt(r.n)), textposition: "auto",
        hovertemplate: "%{y}: %{x} documentos<extra></extra>" }],
      layout: { xaxis: { title: "Documentos" }, showlegend: false, margin: { l: 130, r: 20, t: 20, b: 40 } }
    }, 420);
  };

  R.chart_tec_bar = (el, rows) => {
    const rr = rows.filter((r) => num(r.docs, 0) > 0).slice().reverse();
    plot(el, {
      data: [{ type: "bar", orientation: "h", x: rr.map((r) => num(r.docs)),
        y: rr.map((r) => trunc(r.etiqueta, 40)),
        marker: { color: rr.map((r) => r.color || OI.azul) },
        hovertemplate: "%{y}: %{x} documentos<extra></extra>" }],
      layout: { xaxis: { title: "Documentos" }, showlegend: false, margin: { l: 230, r: 20, t: 20, b: 40 } }
    }, 440);
  };

  R.chart_series = (el, rows) => plot(el, {
    data: [
      { type: "bar", name: "Publicaciones", x: rows.map((r) => r.etiqueta),
        y: rows.map((r) => num(r.publicaciones)), marker: { color: OI.azul } },
      { type: "scatter", mode: "lines+markers", name: "Índice de inversión tecnológica",
        x: rows.map((r) => r.etiqueta), y: rows.map((r) => num(r.inversion)),
        line: { color: OI.naranja, width: 2 } },
      { type: "scatter", mode: "lines+markers", name: "Índice educativo",
        x: rows.map((r) => r.etiqueta), y: rows.map((r) => num(r.educacion)),
        line: { color: OI.verde, width: 2 } }
    ],
    layout: { xaxis: { title: "Año", dtick: 4, tickangle: -45 }, yaxis: { title: "Valor" } }
  }, 340);

  R.chart_radar = (el, rows) => {
    const series = [...new Set(rows.map((r) => r.serie))];
    const ejes = [...rows].sort((a, b) => num(a.orden_eje) - num(b.orden_eje))
      .map((r) => r.eje).filter((v, i, a) => a.indexOf(v) === i);
    const data = series.map((s) => {
      const rr = rows.filter((r) => r.serie === s);
      const byOrden = {};
      rr.forEach((r) => { byOrden[num(r.orden_eje)] = r; });
      const vals = ejes.map((e, i) => { const x = byOrden[i]; return x ? num(x.valor) : 0; });
      const col = (rr[0] && rr[0].color) || OI.azul;
      return { type: "scatterpolar", r: vals.concat(vals[0]), theta: ejes.concat(ejes[0]),
        name: (rr[0] && rr[0].etiqueta) || s, fill: "toself", opacity: .35,
        line: { color: col, width: 2 } };
    });
    plot(el, { data, layout: { polar: { radialaxis: { range: [0, 100], visible: true } } } }, 400);
  };

  R.chart_corr = (el, rows) => {
    const filas = [...new Set(rows.map((r) => r.fila))];
    const cols = [...new Set(rows.map((r) => r.col))];
    const z = filas.map((f) => cols.map((c) => {
      const x = rows.find((r) => r.fila === f && r.col === c);
      return x ? num(x.r) : null;
    }));
    const txt = z.map((row) => row.map((v) => (v == null ? "" : v.toFixed(2))));
    plot(el, {
      data: [{ type: "heatmap", x: cols, y: filas, z, text: txt, texttemplate: "%{text}",
        colorscale: "RdBu", zmid: 0, zmin: -1, zmax: 1, hovertemplate: "%{y} × %{x}: r=%{z:.2f}<extra></extra>" }],
      layout: { xaxis: { tickangle: -35, automargin: true }, yaxis: { automargin: true }, margin: { l: 150, b: 120, t: 20, r: 20 } }
    }, 460);
  };

  R.chart_bubble = (el, rows, meta) => {
    const region = [...new Set(rows.map((r) => r.region))];
    const RC = { Africa: "#56B4E9", LatAm: "#009E73", Asia: "#E69F00", AsiaPac: "#E69F00",
      Europe: "#0072B2", Global: "#888888" };
    const RN = { Africa: "África", LatAm: "Latinoamérica", Asia: "Asia", AsiaPac: "Asia-Pacífico",
      Europe: "Europa", Global: "Global" };
    const traces = region.map((rg) => {
      const rr = rows.filter((r) => r.region === rg);
      return { type: "scatter", mode: "markers+text", name: RN[rg] || rg,
        x: rr.map((r) => num(r.gdp_pc)), y: rr.map((r) => num(r.adopcion)),
        text: rr.map((r) => r.etiqueta), textposition: "top center", textfont: { size: 9 },
        marker: { size: rr.map((r) => 8 + Math.sqrt(num(r.n_pubs, 0)) * 3.2),
          color: RC[rg] || OI.azul, opacity: .78, line: { color: "#fff", width: 1 } },
        customdata: rr.map((r) => [num(r.n_pubs), num(r.seg), num(r.amb)]),
        hovertemplate: "<b>%{text}</b><br>PIB pc: %{x}<br>Adopción: %{y}<br>" +
          "Publicaciones: %{customdata[0]}<br>Seg.: %{customdata[1]} · Amb.: %{customdata[2]}<extra></extra>" };
    });
    let reg = null;
    try { reg = meta.regresion ? JSON.parse(meta.regresion) : null; } catch (e) { }
    if (reg) {
      const xs = rows.map((r) => Math.log10(Math.max(1, num(r.gdp_pc))));
      const x0 = Math.min(...xs), x1 = Math.max(...xs);
      traces.push({ type: "scatter", mode: "lines", name: "Regresión log-PIB",
        x: [10 ** x0, 10 ** x1], y: [reg.slope * x0 + reg.intercept, reg.slope * x1 + reg.intercept],
        line: { color: OI.negro, dash: "dot", width: 2 }, hoverinfo: "skip" });
    }
    plot(el, { data: traces, layout: {
      xaxis: { type: "log", title: "PIB per cápita (US$, log)" }, yaxis: { title: "Adopción tecnológica (0–100)" } } }, 420);
  };

  R.chart_casos_pais = (el, rows, meta) => {
    const prod = rows.map((r) => num(r.produccion, 0));
    const pmax = Math.max(1, ...prod);
    const x = rows.map((r) => num(r.casos_estudio, 0));
    const y = rows.map((r) => num(r.idx_colaboracion, 0));
    const ic = num(meta.ic_medio, y.reduce((a, b) => a + b, 0) / (y.length || 1));
    const med = num(meta.mediana_casos, 0);
    const data = [{
      type: "scatter", mode: "markers+text", x, y, text: rows.map((r) => r.pais),
      textposition: "top center", textfont: { size: 10 },
      marker: { size: prod.map((p) => 14 + 46 * (p / pmax)), color: rows.map((r) => r.color || OI.azul),
        opacity: .75, line: { color: "#fff", width: 1 } },
      customdata: rows.map((r) => [r.produccion, num(r.pct_casos)]),
      hovertemplate: "<b>%{text}</b><br>Casos de estudio: %{x}<br>Índice de colaboración: %{y}<br>" +
        "Producción: %{customdata[0]}<br>% de su producción: %{customdata[1]}%<extra></extra>"
    }];
    const shapes = [
      { type: "line", x0: med, x1: med, yref: "paper", y0: 0, y1: 1, line: { color: OI.gris, dash: "dot", width: 1 } },
      { type: "line", xref: "paper", x0: 0, x1: 1, y0: ic, y1: ic, line: { color: OI.gris, dash: "dash", width: 1 } }
    ];
    plot(el, { data, layout: {
      xaxis: { title: "Volumen de artículos que son casos de estudio" },
      yaxis: { title: "Índice de colaboración (países / artículo)" },
      shapes, showlegend: false } }, 420);
  };

  R.chart_periodos = (el, rows, meta) => {
    const per = rows.map((r) => r.periodo);
    const colores = rows.map((r) => r.color);
    plot(el, {
      data: [
        { type: "bar", name: "Documentos por año", x: rows.map((r) => num(r.anio)),
          y: rows.map((r) => num(r.publicaciones)), marker: { color: colores, line: { color: "#fff", width: .6 } },
          hovertemplate: "%{x} · %{y} documentos<extra></extra>" },
        { type: "scatter", mode: "lines+markers", name: "% impacto acumulado (citas)",
          x: rows.map((r) => num(r.anio)), y: rows.map((r) => num(r.pct_acum)), yaxis: "y2",
          line: { color: OI.azul, width: 2 }, marker: { size: 4 } }
      ],
      layout: {
        xaxis: { title: "Año de publicación", dtick: 4, tickangle: -45 },
        yaxis: { title: "Nº de documentos" },
        yaxis2: { title: "% impacto acumulado", overlaying: "y", side: "right", range: [0, 108],
          showgrid: false, ticksuffix: "%" },
        shapes: [2005.5, 2011.5, 2019.5].map((xb) => ({ type: "line", x0: xb, x1: xb, yref: "paper",
          y0: 0, y1: 1, line: { color: OI.negro, dash: "dash", width: 1, opacity: .6 } })),
        annotations: [
          meta.pico_anio ? { x: num(meta.pico_anio), y: num(meta.pico_n), xref: "x", yref: "y",
            text: "Pico: " + meta.pico_anio + " (" + meta.pico_n + " docs)", showarrow: true,
            arrowhead: 2, ax: -45, ay: -35, font: { size: 10 } } : null,
          meta.anio80 ? { x: num(meta.anio80), y: 80, xref: "x", yref: "y2",
            text: "80 % del impacto en " + meta.anio80, showarrow: true, arrowhead: 2, ax: -50, ay: 35,
            font: { size: 10, color: OI.rojo } } : null
        ].filter(Boolean)
      }
    }, 420);
  };

  R.chart_panel_integrado = (el, rows, meta) => {
    const A = rows.filter((r) => r.bloque === "anual");
    const B = rows.filter((r) => r.bloque === "pareto");
    plot(el, {
      data: [
        { type: "bar", name: "Documentos / año", x: A.map((r) => num(r.x)), y: A.map((r) => num(r.valor)),
          marker: { color: OI.azul }, xaxis: "x", yaxis: "y", hovertemplate: "%{x}: %{y} docs<extra></extra>" },
        { type: "scatter", mode: "lines+markers", name: "Citas acumuladas", x: A.map((r) => num(r.x)),
          y: A.map((r) => num(r.acum)), xaxis: "x", yaxis: "y2", line: { color: OI.rojo, width: 2 } },
        { type: "bar", name: "Documentos / fuente", x: B.map((r) => trunc(r.etiqueta, 22)),
          y: B.map((r) => num(r.valor)), marker: { color: B.map((r) => r.color || OI.azul) },
          xaxis: "x2", yaxis: "y3", hovertemplate: "%{x}: %{y} docs<extra></extra>" },
        { type: "scatter", mode: "lines+markers", name: "% acumulado", x: B.map((r) => trunc(r.etiqueta, 22)),
          y: B.map((r) => num(r.pct_acum)), xaxis: "x2", yaxis: "y4",
          line: { color: OI.rojo, width: 2 } }
      ],
      layout: {
        height: 620, showlegend: true, legend: { orientation: "h", y: -0.12, font: { size: 10 } },
        xaxis: { anchor: "y", dtick: 3, tickangle: -45, title: "Año" },
        yaxis: { domain: [0.58, 1], title: "Documentos" },
        yaxis2: { domain: [0.58, 1], overlaying: "y", side: "right", showgrid: false, title: "Citas acum." },
        xaxis2: { anchor: "y3", tickangle: -40, title: "Fuente (top " + B.length + ")" },
        yaxis3: { domain: [0, 0.44], title: "Documentos" },
        yaxis4: { domain: [0, 0.44], overlaying: "y3", side: "right", showgrid: false, title: "% acum." },
        shapes: [80].map((v) => ({ type: "line", xref: "x2 domain", x0: 0, x1: 1, y0: v, y1: v, yref: "y4",
          line: { color: OI.gris, dash: "dash", width: 1 } })),
        margin: { l: 58, r: 60, t: 30, b: 90 }
      }
    });
  };

  function redNetwork(el, rows) {
    const nodos = rows.filter((r) => r.tipo === "nodo" && num(r.valor, 0) > 0);
    const aristas = rows.filter((r) => r.tipo === "enlace");
    const pos = {}; nodos.forEach((n) => { pos[n.id] = n; });
    const NIV = { fuerte: OI.negro, media: "#7ba7bb", debil: "#c4d6de" };
    const NIVN = { fuerte: "fuerte", media: "media", debil: "débil" };
    const lin = {};
    aristas.forEach((a) => {
      const [o, d] = String(a.id).split("|");
      const no = pos[o], nd = pos[d]; if (!no || !nd) return;
      const s = a.nivel || "debil";
      if (!lin[s]) lin[s] = { x: [], y: [], hover: [] };
      lin[s].x.push(num(no.x), num(nd.x), null);
      lin[s].y.push(num(no.y), num(nd.y), null);
      lin[s].hover.push(no.etiqueta, nd.etiqueta, null);
    });
    const data = Object.keys(lin).map((s) => ({
      type: "scatter", mode: "lines", name: "enlace " + (NIVN[s] || s), x: lin[s].x, y: lin[s].y,
      line: { color: NIV[s] || "#ccc", width: s === "fuerte" ? 2.4 : 1.3 },
      hoverinfo: "text", text: lin[s].hover, showlegend: true
    }));
    data.push({
      type: "scatter", mode: "markers+text", name: "tecnología",
      x: nodos.map((n) => num(n.x)), y: nodos.map((n) => num(n.y)),
      text: nodos.map((n) => n.etiqueta), textposition: "top center", textfont: { size: 9 },
      marker: { size: nodos.map((n) => 12 + Math.sqrt(num(n.valor, 0) + 1) * 4.5),
        color: nodos.map((n) => n.color || OI.azul), opacity: .9, line: { color: "#fff", width: 1 } },
      customdata: nodos.map((n) => [num(n.valor), num(n.valor2)]),
      hovertemplate: "<b>%{text}</b><br>Docs: %{customdata[0]}<br>Grado: %{customdata[1]}<extra></extra>"
    });
    plot(el, { data, layout: { xaxis: { visible: false }, yaxis: { visible: false, scaleanchor: "x" },
      hovermode: "closest" } }, 520);
  }
  R.chart_red = (el, rows) => redNetwork(el, rows);

  R.chart_red_vos = (el, rows, meta) => {
    const nodos = rows.filter((r) => r.tipo === "nodo");
    const enl = rows.filter((r) => r.tipo === "enlace");
    const grupos = {};
    enl.forEach((r) => { const k = r.id; (grupos[k] = grupos[k] || []).push(r); });
    const data = Object.keys(grupos).map((k) => {
      const g = grupos[k];
      return { type: "scatter", mode: "lines", showlegend: false, hoverinfo: "skip",
        x: g.map((r) => num(r.x)), y: g.map((r) => num(r.y)),
        line: { color: "#c9d3da", width: 1 } };
    });
    data.push({
      type: "scatter", mode: "markers", name: "término",
      x: nodos.map((n) => num(n.x)), y: nodos.map((n) => num(n.y)),
      marker: { size: nodos.map((n) => 10 + Math.sqrt(num(n.frecuencia, 0)) * 5),
        color: nodos.map((n) => n.color || OI.azul), opacity: .9, line: { color: "#fff", width: 1 } },
      text: nodos.map((n) => n.cluster_nombre + "<br>frecuencia " + n.frecuencia + " · grado " + num(n.grado).toFixed(1)),
      hovertemplate: "%{text}<extra></extra>"
    });
    let cl = [];
    try { cl = meta.clusters ? JSON.parse(meta.clusters) : []; } catch (e) { }
    plot(el, { data, layout: {
      xaxis: { visible: false }, yaxis: { visible: false, scaleanchor: "x" },
      annotations: cl.map((c, i) => ({ xref: "paper", yref: "paper", x: 0.02, y: 0.98 - i * 0.06,
        text: "● " + c.nombre + " (" + c.n + ")", showarrow: false, xanchor: "left",
        font: { size: 11, color: c.color } })) } }, 560);
  };

  R.chart_ronda1 = (el, rows) => {
    const byId = {}; rows.forEach((r) => { byId[r.id] = r; });
    const hijos = {}; rows.forEach((r) => { (hijos[r.padre] = hijos[r.padre] || []).push(r); });
    rows.forEach((r) => { if (!r.padre) r.valor = (hijos[r.id] || []).length; });
    plot(el, {
      data: [{ type: "sunburst", labels: rows.map((r) => r.etiqueta), ids: rows.map((r) => r.id),
        parents: rows.map((r) => r.padre || ""), values: rows.map((r) => num(r.valor, 0) || 1),
        branchvalues: "total", marker: { colors: rows.map((r) => r.color || OI.azul) },
        hovertemplate: "%{label}<extra></extra>" }],
      layout: { margin: { l: 10, r: 10, t: 30, b: 10 } }
    }, 560);
  };

  R.chart_ronda2 = (el, rows, meta) => {
    const ejes = ["tecnologia", "viabilidad", "impacto", "kpi", "riesgo"];
    const LAB = ["Technology", "Feasibility", "Financial impact", "Main KPI", "Dominant risk"];
    const labels = [], x = [], color = [], ejeDe = [], clave = [];
    const idx = {};
    ejes.forEach((eje, i) => rows.forEach((r) => {
      const v = String(r[eje] || "—");
      const k = i + "|" + v;
      if (idx[k] == null) {
        idx[k] = labels.length; labels.push(v); x.push(i / (ejes.length - 1));
        color.push(r.color || OI.azul); ejeDe.push(i); clave.push(k);
      }
    }));
    /* posición vertical por nodo dentro de su eje */
    const enEje = {}; ejeDe.forEach((i, j) => { (enEje[i] = enEje[i] || []).push(j); });
    const y = new Array(labels.length);
    Object.keys(enEje).forEach((i) => {
      const js = enEje[i];
      js.forEach((j, rank) => { y[j] = 1 - (rank + 0.5) / js.length; });
    });
    const src = [], tgt = [], val = [], linkCol = [];
    for (let i = 0; i < ejes.length - 1; i++) {
      const agg = {};
      rows.forEach((r) => {
        const a = idx[i + "|" + String(r[ejes[i]] || "—")];
        const b = idx[(i + 1) + "|" + String(r[ejes[i + 1]] || "—")];
        const k = a + ">" + b; agg[k] = (agg[k] || 0) + 1;
      });
      Object.keys(agg).forEach((k) => {
        const [a, b] = k.split(">").map(Number);
        src.push(a); tgt.push(b); val.push(agg[k]);
        linkCol.push(("rgba(" + hexRgb(color[a]) + ",.30)"));
      });
    }
    const anot = LAB.map((t, i) => ({ xref: "paper", yref: "paper",
      x: i / (LAB.length - 1), y: 1.04, text: t, showarrow: false,
      xanchor: "center", font: { size: 11, color: "#1c2b36" } }));
    plot(el, {
      data: [{ type: "sankey", orientation: "h",
        node: { label: labels.map((l) => trunc(l, 26)), x, y, color, thickness: 15, pad: 10,
          line: { color: "rgba(0,0,0,.2)", width: .5 }, hovertemplate: "%{label}<extra></extra>" },
        link: { source: src, target: tgt, value: val, color: linkCol },
        arrangement: "snap" }],
      layout: { font: { size: 9 }, margin: { l: 10, r: 10, t: 34, b: 10 }, annotations: anot }
    }, 500);
  };
  function hexRgb(hex) {
    const c = String(hex || "#888").replace("#", "");
    const n = c.length === 3 ? c.split("").map((x) => x + x).join("") : c;
    const r = parseInt(n.slice(0, 2), 16), g = parseInt(n.slice(2, 4), 16), b = parseInt(n.slice(4, 6), 16);
    return (isNaN(r) ? "120,120,120" : r + "," + g + "," + b);
  }

  R.chart_ronda3 = (el, rows) => {
    const tecs = [...new Set(rows.map((r) => r.tecnologia))];
    const crits = [...new Set(rows.map((r) => r.criterio))];
    const z = tecs.map((t) => crits.map((c) => {
      const x = rows.find((r) => r.tecnologia === t && r.criterio === c); return x ? num(x.valor) : null;
    }));
    plot(el, {
      data: [{ type: "heatmap", x: crits, y: tecs.map((t) => trunc(t, 42)), z,
        colorscale: [[0, "#f7f7f7"], [.2, "#d7ebf0"], [.5, "#4fa3b8"], [.8, "#1a6f86"], [1, "#0b4f6c"]],
        zmin: 1, zmax: 5, text: z.map((r) => r.map((v) => (v == null ? "" : v.toFixed(2).replace(".", ",")))),
        texttemplate: "%{text}", hovertemplate: "%{y}<br>%{x}: %{z:.2f}<extra></extra>" }],
      layout: { margin: { l: 300, b: 40, t: 20, r: 20 }, xaxis: { side: "top" } }
    }, 420);
  };

  const RENDER = R;

  /* ============================ tablas ============================ */
  function tablaGenerica(cont, info, opts) {
    opts = opts || {};
    const max = opts.maxRows || info.rows.length;
    const cols = info.cols.slice().sort((a, b) => a.orden - b.orden);
    const th = cols.map((c) => `<th class="${c.tipo === "num" || c.tipo === "int" ? "num" : ""}">${esc(c.titulo)}</th>`).join("");
    const body = info.rows.slice(0, max).map((r) => "<tr>" + cols.map((c) => {
      const v = r[c.nombre];
      const txt = v == null ? "" : (c.tipo === "num" || c.tipo === "int" ? fmt(v) : esc(v));
      return `<td class="${c.tipo === "num" || c.tipo === "int" ? "num" : ""}">${txt}</td>`;
    }).join("") + "</tr>").join("");
    cont.innerHTML = `<table class="tbl"><thead><tr>${th}</tr></thead><tbody>${body}</tbody></table>`;
  }

  R.tabla_tecnologias = (el, rows, meta) => {
    const info = ficha('tabla_tecnologias');
    if (!info || !info.cols) {
      el.innerHTML = '<p class="warn">Cargue <code>tabla_tecnologias.db</code> para ver esta tabla.</p>';
      return;
    }
    const colsToExclude = ["docs", "trl", "capex", "opex", "seg", "amb"];
    const cols = info.cols.filter(c => !colsToExclude.includes(c.nombre.toLowerCase()))
      .sort((a, b) => a.orden - b.orden);
    const th = cols.map((c) => `<th class="${c.tipo === "num" || c.tipo === "int" ? "num" : ""}">${esc(c.titulo)}</th>`).join("");
    const body = rows.slice(0, 300).map((r) => "<tr>" + cols.map((c) => {
      const v = r[c.nombre];
      const txt = v == null ? "" : (c.tipo === "num" || c.tipo === "int" ? fmt(v) : esc(v));
      return `<td class="${c.tipo === "num" || c.tipo === "int" ? "num" : ""}">${txt}</td>`;
    }).join("") + "</tr>").join("");
    el.innerHTML = `<table class="tbl"><thead><tr>${th}</tr></thead><tbody>${body}</tbody></table>`;
  };

  R.tabla_perfil_regional = (el, rows, meta) => {
    const info = ficha('tabla_perfil_regional');
    if (!info || !info.cols) {
      el.innerHTML = '<p class="warn">Cargue <code>tabla_perfil_regional.db</code> para ver esta tabla.</p>';
      return;
    }
    const cols = info.cols.slice().sort((a, b) => a.orden - b.orden);
    const th = cols.map((c) => `<th class="${c.tipo === "num" || c.tipo === "int" ? "num" : ""}" contenteditable="false">${esc(c.titulo)}</th>`).join("");
    const body = rows.slice(0, 300).map((r, rowIdx) => "<tr>" + cols.map((c) => {
      const v = r[c.nombre];
      const isEditable = c.tipo === "num" || c.tipo === "int";
      const txt = v == null ? "" : (c.tipo === "num" || c.tipo === "int" ? fmt(v) : esc(v));
      return `<td class="${c.tipo === "num" || c.tipo === "int" ? "num" : ""}" ${isEditable ? 'contenteditable="true" data-row="' + rowIdx + '" data-col="' + c.nombre + '"' : ''}>${txt}</td>`;
    }).join("") + "</tr>").join("");
    el.innerHTML = `<table class="tbl" id="tbl_perfil_regional"><thead><tr>${th}</tr></thead><tbody>${body}</tbody></table>`;
  };

  /* ============================ tarjetas ============================ */
  const LAYOUT = {
    inicio: [["chart_donut_cluster", "chart_top5"]],
    metodologia: [["chart_periodos"]],
    observatorio: [["chart_panel_integrado"]],
    matriz: [["tabla_tecnologias"], ["chart_ronda3"], ["chart_ronda2"]],
    red: [["chart_red"], ["chart_cat", "chart_tec_bar"]]
  };

  function ficha(gid) {
    return DER[gid] || null;
  }
  function getCustomTitle(gid) {
    const lang = window.currentLang || 'es';
    const customTitles = {
      es: {
        "chart_ronda1": "Resultado PRISMA · Etapas operativas y tecnologías identificadas",
        "chart_ronda2": "Ronda 2 · Análisis de barreras y viabilidad",
        "chart_ronda3": "Ronda 1 · Priorización multicriterio de tecnologías",
        "tabla_perfil_regional": "Perfil regional multidimensional",
        "chart_periodos": "Figura 2 - Producción anual por periodos e impacto acumulado",
        "chart_panel_integrado": "Panel integrado: evolución anual y concentración de fuentes"
      },
      en: {
        "chart_ronda1": "PRISMA Result · Operational Stages and Identified Technologies",
        "chart_ronda2": "Round 2 · Barriers and Feasibility Analysis",
        "chart_ronda3": "Round 1 · Multicriteria Prioritization of Technologies",
        "tabla_perfil_regional": "Multidimensional Regional Profile",
        "chart_periodos": "Figure 2 - Annual Production by Periods and Accumulated Impact",
        "chart_panel_integrado": "Integrated Panel: Annual Evolution and Source Concentration"
      }
    };
    return customTitles[lang] ? customTitles[lang][gid] : customTitles['es'][gid];
  }

  function translateTitle(title) {
    if (typeof window.currentLang === 'undefined' || window.currentLang === 'es') return title;
    const titlesMap = {
      "Producción anual por periodos e impacto acumulado": "Annual production by periods and accumulated impact",
      "donut_cluster": "Cluster Distribution",
      "donut_acceso": "Access Distribution",
      "top5": "Top 5 Most Cited",
      "tecnologias": "Technologies Table",
      "ronda1": "PRISMA Result - Operational Stages and Identified Technologies",
      "ronda2": "Round 2 - Barriers and Feasibility Analysis",
      "ronda3": "Round 1 - Multicriteria Prioritization of Technologies",
      "red": "Technology Co-occurrence Network",
      "cat": "Technology Categories",
      "tec_bar": "Technology Frequency",
      "panel_integrado": "Integrated Panel - Annual Evolution and Source Concentration"
    };
    const key = Object.keys(titlesMap).find(k => title.toLowerCase().includes(k.toLowerCase()));
    return key ? titlesMap[key] : title;
  }

  function translateDescription(desc) {
    if (typeof window.currentLang === 'undefined' || window.currentLang === 'es') return desc;
    const descsMap = {
      "barras anuales coloreadas por periodo (pre-corte, 2006–11, 2012–19 y 2020–26) superpuestas con la curva de citas acumuladas (impacto científico)": 
        "Annual bars colored by period (pre-cut, 2006–11, 2012–19 and 2020–26) overlaid with the accumulated citation curve (scientific impact)",
      "Evolución anual de documentos por período y concentración por fuente": 
        "Annual evolution of documents by period and concentration by source",
      "Documentos por año": "Documents by year",
      "Documentos por clúster temático": "Documents by thematic cluster",
      "Documentos por tipo de acceso": "Documents by access type",
      "Top 5 documentos más citados": "Top 5 most cited documents",
      "Red de co-ocurrencia de tecnologías": "Technology co-occurrence network",
      "Tecnologías por categoría": "Technologies by category",
      "Frecuencia de tecnologías": "Technology frequency"
    };
    const key = Object.keys(descsMap).find(k => desc.toLowerCase().includes(k.toLowerCase()));
    return key ? descsMap[key] : desc;
  }

  function renderSeccion(nombre) {
    const cont = $("#cards_" + nombre);
    if (!cont) return;
    const filas = LAYOUT[nombre] || [];
    cont.innerHTML = "";
    filas.forEach((grupo) => {
      const wrap = document.createElement("div");
      wrap.className = grupo.length > 1 ? "grid2" : "";
      wrap.style.marginBottom = "1rem";
      grupo.forEach((gid) => {
        const info = ficha(gid);
        const esTabla = info ? info.meta.tipo === "tabla" : /^tabla_/.test(gid);
        const card = document.createElement("div");
        card.className = "card";
        const customTitle = getCustomTitle(gid);
        let titulo = customTitle || (info ? info.meta.titulo : gid);
        let desc = info ? info.meta.desc : "Base no cargada.";
        
        card.innerHTML =
          `<div class="card-head"><h3>${esc(titulo)}</h3>
             <span class="card-btns">
               ${esTabla ? `<button class="btn-export" data-csv="${gid}">` + (window.currentLang === 'en' ? 'CSV' : 'CSV') + `</button>`
                         : `<button class="btn-export" data-svg="${gid}">` + (window.currentLang === 'en' ? 'SVG' : 'SVG') + `</button>`}
             </span></div>
           <div id="box_${gid}" class="chart-box"></div>
           <p class="card-note">${esc(desc)}</p>`;
        wrap.appendChild(card);
        const box = card.querySelector("#box_" + gid);
        if (!info) {
          const loadMsg = window.currentLang === 'en' ? 
            'Database <code>' + gid + '.db</code> not loaded. Load it in the &quot;Data&quot; section.' :
            'Base <code>' + gid + '.db</code> no cargada. Cárguela en la sección &laquo;Datos&raquo;.';
          box.innerHTML = `<p class="warn">${loadMsg}</p>`;
          return;
        }
        if (esTabla) tablaGenerica(box, info, { maxRows: nombre === "corpus" ? 200 : 300 });
        else if (RENDER[gid]) RENDER[gid](box, info.rows, info.meta);
        else box.innerHTML = `<p class="warn">No renderer for <code>${gid}</code>.</p>`;
      });
      cont.appendChild(wrap);
    });
  }

  /* ============================ corpus explorer ============================ */
  const CORPUS_ORDER = ["124", "360", "269", "258", "207"];
  const CS = { cid: "124", page: 1, per: 25, search: "", cluster: "", acceso: "", y0: "", y1: "" };

  /* Filas normalizadas de una vista del corpus:
   * {anio, titulo, autores, fuente, citas, cluster(nombre), acceso, doi, enlace, keywords}
   * El corpus 124 se toma de tabla_corpus.db; el resto, de corpus_<id>.db. */
  function viewDe(cid) {
    const raw = RAW["corpus_" + cid];
    if (raw) {
      if (!raw._view) {
        const clus = {};
        filasTabla(raw.db, "clusters").forEach((c) => { clus[String(c.id)] = c.nombre; });
        const meta = {};
        filasTabla(raw.db, "meta").forEach((r) => { meta[r.key] = r.value; });
        const rows = qRows(raw.db,
          "SELECT n,anio,titulo,autores,fuente,citas,doi,enlace,acceso,cluster,tecnologias_txt FROM docs")
          .map((d) => Object.assign(d, {
            cluster: d.cluster == null ? "" : (clus[String(d.cluster)] || String(d.cluster)),
            keywords: d.tecnologias_txt || ""
          }));
        raw._view = { rows, meta, fuente: "corpus_" + cid + ".db" };
      }
      return raw._view;
    }
    if (cid === "124" && DER["tabla_corpus"]) {
      return { rows: DER["tabla_corpus"].rows,
        meta: { nombre: "124 · corpus final cualitativo", csv: "thirdPass_124.csv" },
        fuente: "tabla_corpus.db" };
    }
    return null;
  }
  function corporaDisponibles() {
    const ids = CORPUS_ORDER.filter((id) => viewDe(id));
    Object.keys(RAW).forEach((n) => {
      const m = /^corpus_(\d+)$/.exec(n);
      if (m && ids.indexOf(m[1]) < 0) ids.push(m[1]);
    });
    return ids;
  }
  function corpusActivo() {
    const ids = corporaDisponibles();
    if (!ids.length) return null;
    if (ids.indexOf(CS.cid) < 0) CS.cid = ids[0];
    return { id: CS.cid, v: viewDe(CS.cid) };
  }
  function corpusFiltrado(v) {
    const q = CS.search.toLowerCase();
    return v.rows.filter((r) => {
      if (CS.cluster && String(r.cluster) !== CS.cluster) return false;
      if (CS.acceso && String(r.acceso) !== CS.acceso) return false;
      const a = num(r.anio, 0);
      if (CS.y0 && a < +CS.y0) return false;
      if (CS.y1 && a > +CS.y1) return false;
      if (q && !(String(r.titulo) + " " + r.autores + " " + r.fuente + " " + r.keywords).toLowerCase().includes(q))
        return false;
      return true;
    });
  }
  function renderCorpusTabs(ids) {
    const el = $("#corpus_tabs");
    if (!el) return;
    el.innerHTML = ids.map((id) => {
      const v = viewDe(id);
      const nom = (v.meta && v.meta.nombre) ? v.meta.nombre.replace(/^\d+\s*·\s*/, "") : "";
      return `<button class="ctab ${id === CS.cid ? "active" : ""}" data-cid="${esc(id)}">` +
        `<b>${esc(id)}</b><span>${esc(nom)}</span><em>${fmt(v.rows.length)} documentos</em></button>`;
    }).join("");
    el.querySelectorAll("button").forEach((b) => b.addEventListener("click", () => {
      if (b.dataset.cid === CS.cid) return;
      CS.cid = b.dataset.cid; CS.page = 1; CS.cluster = ""; CS.acceso = "";
      CS.search = ""; CS.y0 = ""; CS.y1 = "";
      ["f_cor_search", "f_cor_cluster", "f_cor_acceso", "f_cor_y0", "f_cor_y1"]
        .forEach((id) => { const e = $("#" + id); if (e) e.value = ""; });
      CS._cid = null;
      renderCorpus();
    }));
  }
  function renderCorpus() {
    const act = corpusActivo();
    if (!act) {
      const t = $("#corpus_tabs"); if (t) t.innerHTML = "";
      $("#tabla_corpus tbody").innerHTML =
        '<tr><td colspan="8" class="warn">Cargue las bases <code>corpus_*.db</code> ' +
        '(o <code>tabla_corpus.db</code>) para explorar el corpus.</td></tr>';
      return;
    }
    renderCorpusTabs(corporaDisponibles());
    const v = act.v;
    if (CS._cid !== CS.cid) {
      const cl = [...new Set(v.rows.map((r) => r.cluster))].filter((x) => x != null && x !== "").sort();
      $("#f_cor_cluster").innerHTML = '<option value="">Todos los clústeres</option>' +
        cl.map((c) => `<option value="${esc(c)}">${esc(c)}</option>`).join("");
      const ac = [...new Set(v.rows.map((r) => r.acceso))].filter((x) => x != null && x !== "").sort();
      $("#f_cor_acceso").innerHTML = '<option value="">Cualquier acceso</option>' +
        ac.map((c) => `<option value="${esc(c)}">${esc(c)}</option>`).join("");
      CS._cid = CS.cid;
    }
    const f = corpusFiltrado(v);
    $("#corpus_count").textContent = f.length + " / " + v.rows.length;
    const ft = $("#corpus_fuente");
    if (ft) ft.textContent = v.fuente + (v.meta && v.meta.csv ? " · " + v.meta.csv : "");
    const ini = (CS.page - 1) * CS.per;
    const pagina = f.slice(ini, ini + CS.per);
    const lang = (typeof window.currentLang !== 'undefined' ? window.currentLang : 'es');
    const trans = {
      es: { view: 'ver' },
      en: { view: 'view' }
    };
    const t = trans[lang] || trans.es;
    
    $("#tabla_corpus tbody").innerHTML = pagina.map((r) =>
      `<tr><td class="num">${esc(r.anio)}</td><td>${esc(trunc(r.titulo, 110))}</td>` +
      `<td>${esc(trunc(r.autores, 40))}</td><td>${esc(trunc(r.fuente, 40))}</td>` +
      `<td class="num">${fmt(r.citas)}</td><td>${esc(trunc(r.cluster, 34))}</td><td>${esc(r.acceso)}</td>` +
      `<td>${r.enlace ? `<a href="${esc(r.enlace)}" target="_blank" rel="noopener">${t.view}</a>` : esc(r.doi)}</td></tr>`).join("");
    const total = Math.ceil(f.length / CS.per) || 1;
    let pag = "";
    for (let p = 1; p <= total; p++) {
      if (p === 1 || p === total || Math.abs(p - CS.page) <= 2)
        pag += `<button class="${p === CS.page ? "active" : ""}" data-p="${p}">${p}</button>`;
      else if (Math.abs(p - CS.page) === 3) pag += "<span>…</span>";
    }
    $("#corpus_paginacion").innerHTML = pag;
    $("#corpus_paginacion").querySelectorAll("button").forEach((b) =>
      b.addEventListener("click", () => { CS.page = +b.dataset.p; renderCorpus(); }));
  }

  /* ============================ inventario .db ============================ */
  function renderInventario() {
    const filas = [];
    Object.keys(DER).sort().forEach((gid) => {
      const d = DER[gid];
      filas.push(`<tr><td><b>${esc(gid)}</b></td><td>${esc(d.meta.tipo || "derivada")}</td>` +
        `<td class="num">${fmt(d.rows.length)}</td><td>${esc((d.tabs || []).join(", "))}</td>` +
        `<td>${d.meta.tipo === "tabla" ? `<button class="btn-export" data-csv="${esc(gid)}">CSV</button>`
          : `<button class="btn-export" data-svg="${esc(gid)}">SVG</button>`}</td></tr>`);
    });
    Object.keys(RAW).sort().forEach((n) => {
      const d = RAW[n];
      filas.push(`<tr><td><b>${esc(n)}</b></td><td>vista corpus</td><td class="num">—</td>` +
        `<td>${esc((d.tabs || []).join(", "))}</td><td></td></tr>`);
    });
    const lang = window.currentLang || 'es';
    $("#tabla_dbs tbody").innerHTML = filas.join("") ||
      `<tr><td colspan="5" class="warn">${lang === 'en' ? 'No databases loaded.' : 'Sin bases cargadas.'}</td></tr>`;
    $("#db_dir").textContent = Object.keys(DER).length || Object.keys(RAW).length
      ? (lang === 'en' ? 'Databases loaded in memory (browser cannot list local folders for security).' : 
         'Bases cargadas en memoria (el navegador no puede listar carpetas locales por seguridad).')
      : (lang === 'en' ? 'Load the <code>.db</code> files to view the inventory.' : 'Cargue los <code>.db</code> para ver el inventario.');
    const sel = $("#sql_db");
    const todas = [...Object.keys(DER), ...Object.keys(RAW)];
    sel.innerHTML = todas.map((n) => `<option value="${esc(n)}">${esc(n)}</option>`).join("");
  }

  /* ============================ descargas ============================ */
  function filasDe(gid) {
    if (DER[gid]) return DER[gid].rows;
    return [];
  }
  function csvDe(gid) {
    const info = DER[gid];
    if (!info) return "";
    const cols = info.cols.slice().sort((a, b) => a.orden - b.orden);
    const head = ["clave"].concat(cols.map((c) => c.titulo), ["extra"]);
    const lines = info.rows.map((r) => [r.clave].concat(cols.map((c) => r[c.nombre]), [r.extra || ""])
      .map((v) => { v = v == null ? "" : String(v); return /[";\n]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v; })
      .join(";"));
    return "\ufeff" + [head.join(";")].concat(lines).join("\r\n");
  }
  function descargar(nombre, texto, mime) {
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([texto], { type: mime || "text/plain;charset=utf-8" }));
    a.download = nombre; document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 4000);
  }
  function conectarBotones(raiz) {
    raiz.querySelectorAll("[data-csv]").forEach((b) => b.onclick = () => {
      descargar(b.dataset.csv + ".csv", csvDe(b.dataset.csv), "text/csv;charset=utf-8");
    });
    raiz.querySelectorAll("[data-svg]").forEach((b) => b.onclick = () => {
      const gd = document.getElementById("box_" + b.dataset.svg);
      if (gd && gd.data && Plotly) Plotly.downloadImage(gd, { format: "svg", filename: b.dataset.svg });
    });
  }

  /* ============================ consola SQL ============================ */
  function ejecutarSql() {
    const nombre = $("#sql_db").value;
    const sql = $("#sql_txt").value.trim();
    const out = $("#sql_out");
    const lang = window.currentLang || 'es';
    if (!nombre || !sql) { out.innerHTML = ""; return; }
    if (!/^select|^with|^pragma|^explain/i.test(sql)) {
      out.innerHTML = `<p class="warn">${lang === 'en' ? 'Only read queries (SELECT) are allowed.' : 'Solo se permiten consultas de lectura (SELECT).'}</p>`; return;
    }
    const db = DER[nombre] ? DER[nombre].db : (RAW[nombre] ? RAW[nombre].db : null);
    if (!db) { 
      out.innerHTML = `<p class="warn">${lang === 'en' ? 'Database not available.' : 'Base no disponible.'}</p>`; 
      return; 
    }
    try {
      const res = db.exec(sql);
      if (!res.length) { 
        out.innerHTML = `<p class='card-note'>${lang === 'en' ? 'No results.' : 'Sin resultados.'}</p>`; 
        return; 
      }
      const { columns, values } = res[0];
      out.innerHTML = `<table class="tbl"><thead><tr>${columns.map((c) => `<th>${esc(c)}</th>`).join("")}</tr></thead>` +
        `<tbody>${values.slice(0, 200).map((row) => "<tr>" + row.map((v) => `<td>${esc(v)}</td>`).join("") + "</tr>").join("")}</tbody></table>`;
    } catch (e) { 
      out.innerHTML = `<p class="warn">${lang === 'en' ? 'SQL Error: ' : 'Error SQL: '}${esc(e.message)}</p>`; 
    }
  }

  /* Perfil regional multidimensional - carga y renderizado */
  function renderPerfilRegional() {
    const graficaEl = $("#perfil_regional_grafica");
    const tablaEl = $("#tabla_perfil_regional");
    
    if (!graficaEl || !tablaEl) return;
    
    const info = ficha("chart_radar");
    if (info) {
      graficaEl.innerHTML = "";
      // Translate title if in English
      if (window.currentLang === 'en') {
        info.meta.titulo = 'Multidimensional Regional Profile';
      }
      RENDER.chart_radar(graficaEl, info.rows, info.meta);
    } else {
      const lang = window.currentLang || 'es';
      const msg = lang === 'en' ? 'Load <code>chart_radar.db</code> to view the graph.' : 'Cargue <code>chart_radar.db</code> para ver la gráfica.';
      graficaEl.innerHTML = `<p class="warn">${msg}</p>`;
    }
    
    const infoTabla = ficha("tabla_perfil_regional");
    if (infoTabla) {
      tablaEl.innerHTML = "";
      RENDER.tabla_perfil_regional(tablaEl, infoTabla.rows, infoTabla.meta);
    } else {
      const lang = window.currentLang || 'es';
      const msg = lang === 'en' ? 'Load <code>tabla_perfil_regional.db</code> to view the table.' : 'Cargue <code>tabla_perfil_regional.db</code> para ver la tabla.';
      tablaEl.innerHTML = `<p class="warn">${msg}</p>`;
    }
  }

  /* Carga de archivo para perfil regional */
  function cargarPerfilRegional(file) {
    if (!file) return;
    if (!/\.db$/i.test(file.name)) {
      alert("Por favor seleccione un archivo .db");
      return;
    }
    
    const reader = new FileReader();
    reader.onload = async function(e) {
      try {
        await initSql();
        const buf = new Uint8Array(e.target.result);
        const db = new SQL.Database(buf);
        const tabs = tablaNombres(db);
        
        if (tabs.includes("meta") && tabs.includes("datos") && tabs.includes("columnas")) {
          const meta = {};
          filasTabla(db, "meta").forEach((r) => { meta[r.key] = r.value; });
          
          DER["tabla_perfil_regional"] = {
            gid: "tabla_perfil_regional",
            meta: meta,
            cols: filasTabla(db, "columnas"),
            rows: filasTabla(db, "datos"),
            name: file.name,
            tabs: tabs,
            db: db
          };
          
          renderPerfilRegional();
          alert("Tabla de perfil regional cargada y actualizada correctamente.");
        } else {
          alert("El archivo no tiene el formato correcto de base de datos.");
        }
      } catch (e) {
        console.error("Error cargando perfil regional:", e);
        alert("Error al cargar el archivo: " + e.message);
      }
    };
    reader.readAsArrayBuffer(file);
  }

  /* ============================ orquestación ============================ */
  function renderizarTodo() {
    renderKpis();
    ["inicio", "metodologia", "observatorio", "matriz", "red"].forEach(renderSeccion);
    renderCorpus();
    renderInventario();
    renderPerfilRegional();
    const dv = $("#tabla_deliverable");
    if (dv) {
      const inf = ficha("tabla_deliverable");
      if (inf) tablaGenerica(dv, inf, { maxRows: 130 });
      else dv.innerHTML = '<p class="warn">' + (window.currentLang === 'en' ? 'Load <code>tabla_deliverable.db</code> to view the scientific delivery.' : 'Cargue <code>tabla_deliverable.db</code> para ver la entrega científica.') + '</p>';
    }
    const box = $("#metodo_periodos");
    if (box) { 
      box.innerHTML = ""; 
      const info = ficha("chart_periodos");
      if (info) RENDER.chart_periodos(box, info.rows, info.meta);
      else box.innerHTML = '<p class="warn">' + (window.currentLang === 'en' ? 'Load <code>chart_periodos.db</code>.' : 'Cargue <code>chart_periodos.db</code>.') + '</p>'; 
    }
    
    // Conectar botones de perfil regional
    const btnCargar = $("#btn_cargar_perfil");
    const fileInput = $("#file_perfil_regional");
    if (btnCargar && fileInput) {
      btnCargar.onclick = () => fileInput.click();
      fileInput.onchange = (e) => { if (e.target.files && e.target.files[0]) cargarPerfilRegional(e.target.files[0]); };
    }
    
    ["#cards_inicio", "#cards_observatorio", "#cards_matriz", "#cards_red", "main", "#datos", "#observatorio"]
      .forEach((s) => { const el = document.querySelector(s); if (el) conectarBotones(el); });
    conectarBotones($("#datos"));
    
    // Translate load message
    const loadMsg = $("#load_msg");
    if (loadMsg) {
      loadMsg.textContent = window.currentLang === 'en' ? 'No databases loaded yet.' : 'Ninguna base cargada todavía.';
    }
  }

  /* ============================ eventos ============================ */
  function navEvents() {
    document.querySelectorAll(".nav a, [data-nav]").forEach((a) => a.addEventListener("click", (e) => {
      e.preventDefault();
      const s = document.getElementById(a.dataset.nav);
      if (s) s.scrollIntoView({ behavior: "smooth", block: "start" });
    }));
  }
  function filtroEvents() {
    const bind = (id, key) => {
      const el = $("#" + id);
      if (el) el.addEventListener("input", () => { CS[key] = el.value; CS.page = 1; renderCorpus(); });
    };
    bind("f_cor_search", "search"); bind("f_cor_cluster", "cluster");
    bind("f_cor_acceso", "acceso"); bind("f_cor_y0", "y0"); bind("f_cor_y1", "y1");
    $("#btn_corpus_csv").onclick = () => {
      const act = corpusActivo(); if (!act) return;
      const f = corpusFiltrado(act.v);
      const head = ["Año", "Título", "Autores", "Fuente", "Citas", "Clúster", "Acceso", "DOI", "Enlace"];
      const lines = f.map((r) => [r.anio, r.titulo, r.autores, r.fuente, r.citas, r.cluster, r.acceso, r.doi, r.enlace]
        .map((v) => { v = v == null ? "" : String(v);
          return /[";\n]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v; }).join(";"));
      descargar("corpus_" + act.id + ".csv", "\ufeff" + [head].concat(lines).join("\r\n"), "text/csv;charset=utf-8");
    };
  }
  async function elegirArchivos() {
    if (window.showDirectoryPicker) {
      try {
        const dir = await window.showDirectoryPicker();
        const files = [];
        for await (const h of dir.values()) if (h.kind === "file" && /\.db$/i.test(h.name)) files.push(await h.getFile());
        if (files.length) { await cargarArchivos(files); return; }
      } catch (e) { }
    }
    $("#file_input").click();
  }
  function cargaEvents() {
    $("#btn_elegir").onclick = elegirArchivos;
    $("#btn_cargar_todo").onclick = elegirArchivos;
    $("#file_input").onchange = (e) => cargarArchivos(e.target.files);
    const dz = $("#drop_zone");
    ["dragenter", "dragover"].forEach((ev) => dz.addEventListener(ev, (e) => { e.preventDefault(); dz.classList.add("drag"); }));
    ["dragleave", "drop"].forEach((ev) => dz.addEventListener(ev, (e) => { e.preventDefault(); dz.classList.remove("drag"); }));
    dz.addEventListener("drop", (e) => { if (e.dataTransfer && e.dataTransfer.files) cargarArchivos(e.dataTransfer.files); });
    $("#sql_run").onclick = ejecutarSql;
  }

  function temaInicial() {
    try { const t = localStorage.getItem("mape_theme"); if (t) return t; } catch (e) { }
    return (window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches) ? "dark" : "light";
  }
  function aplicarTema(t) {
    document.documentElement.setAttribute("data-theme", t);
    try { localStorage.setItem("mape_theme", t); } catch (e) { }
    const b = $("#theme_toggle");
    if (b) {
      b.setAttribute('data-i18n', t === "dark" ? "Modo día" : "Modo noche");
      b.textContent = t === "dark" ? "Modo día" : "Modo noche";
    }
  }
  function temaEvents() {
    const b = $("#theme_toggle");
    if (!b) return;
    b.onclick = () => {
      const t = document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark";
      aplicarTema(t);
      renderizarTodo();
    };
  }

  /* Carga automática de db/ cuando la página se sirve por HTTP (p. ej. GitHub Pages). */
  async function cargarRemoto() {
    if (location.protocol === "file:") return;
    const st = $("#db_status");
    const msg = $("#load_msg");
    try {
      if (st) st.innerHTML = "Cargando bases <code>.db</code>…";
      if (msg) msg.textContent = "Descargando bases desde db/…";
      let nombres = [];
      try {
        const r = await fetch("db/manifest.json", { cache: "no-store" });
        if (r.ok) {
          const j = await r.json();
          nombres = Array.isArray(j) ? j : (j.files || []);
        }
      } catch (e) { /* sin manifiesto */ }
      if (!nombres.length) {
        nombres = [
          "catalogo_tecnologias.db", "observatorio.db",
          "corpus_124.db", "corpus_207.db", "corpus_258.db", "corpus_269.db", "corpus_360.db",
          "tabla_corpus.db", "tabla_deliverable.db", "tabla_paises_obs.db", "tabla_tecnologias.db",
          "chart_anios.db", "chart_bubble.db", "chart_casos_pais.db", "chart_cat.db", "chart_corr.db",
          "chart_donut_acceso.db", "chart_donut_cluster.db", "chart_igf.db", "chart_paises_pub.db",
          "chart_panel_integrado.db", "chart_periodos.db", "chart_radar.db", "chart_red.db",
          "chart_red_vos.db", "chart_ronda1.db", "chart_ronda2.db", "chart_ronda3.db",
          "chart_series.db", "chart_tec_bar.db", "chart_top5.db"
        ];
      }
      await initSql();
      const files = [];
      for (const name of nombres) {
        try {
          const r = await fetch("db/" + encodeURIComponent(name));
          if (!r.ok) continue;
          const buf = await r.arrayBuffer();
          files.push(new File([buf], name));
        } catch (e) {
          console.warn("No se pudo descargar " + name, e);
        }
      }
      if (files.length) await cargarArchivos(files);
      else if (msg) msg.textContent = "No se encontraron bases en db/. Use el selector manual.";
    } catch (e) {
      console.warn("Carga remota falló", e);
      if (msg) msg.textContent = "No se pudieron cargar las bases automáticamente.";
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    aplicarTema(temaInicial());
    navEvents(); filtroEvents(); cargaEvents(); temaEvents();
    renderizarTodo();
    cargarRemoto();
  });
})();
