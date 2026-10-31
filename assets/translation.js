/* Translation System for UASM Portal */
(function() {
  'use strict';

  const translations = {
    es: {},
    en: {
      'chart_donut_cluster': 'Cluster Distribution',
      'chart_donut_acceso': 'Access Distribution',
      'chart_top5': 'Top 5 Most Cited',
      'chart_anios': 'Documents by Year',
      'chart_periodos': 'Annual Production by Periods and Accumulated Impact',
      'chart_panel_integrado': 'Integrated Panel - Annual Evolution and Source Concentration',
      'chart_radar': 'Multidimensional Regional Profile',
      'chart_tec_bar': 'Technology Frequency',
      'chart_cat': 'Technology Categories',
      'chart_red': 'Technology Co-occurrence Network',
      'Producción anual de documentos por período con impacto acumulado de citas.': 'Annual document production by period with accumulated citation impact.',
      'Figura 3 · 23 tecnologías identificadas según z6.svg': 'Figure 3 - 23 technologies identified according to z6.svg',
      '23 tecnologías de integración identificadas en 5 etapas operativas': '23 integration technologies identified in 5 operational stages',
      'según el análisis del corpus': 'according to corpus analysis',
      'tabla_tecnologias': 'Technologies Table',
      'tabla_perfil_regional': 'Multidimensional Regional Profile',
      'tabla_corpus': 'Corpus Table',
      'tabla_deliverable': 'Scientific Delivery',
      'tabla_dbs': 'Databases Inventory',
      'tabla_cargadas': 'Loaded Databases',
      'Datos': 'Data',
      'Inicio': 'Home',
      'Metodología': 'Methodology',
      'Observatorio': 'Observatory',
      'Matriz de Tecnologías': 'Technology Matrix',
      'Red de Convergencia': 'Convergence Network',
      'Corpus': 'Corpus',
      'Bases .db': '.db Databases',
      'Modo noche': 'Dark mode',
      'Modo día': 'Light mode',
      'Revisión sistemática de literatura · Scopus · 1974–2026': 'Systematic literature review · Scopus · 1974–2026',
      'Portal de <span class="accent">Transferencia Tecnológica</span> y Observatorio Operativo de la Minería Subterránea Artesanal y de Pequeña Escala (UASM)': 'Technology <span class="accent">Transfer</span> Portal and Operational Observatory of Underground Artisanal and Small-Scale Mining (UASM)',
      'Explorar Observatorio': 'Explore Observatory',
      'Ver Matriz de Tecnologías': 'View Technology Matrix',
      'Explorar Corpus': 'Explore Corpus',
      'Cargar bases .db': 'Load .db databases',
      'Cargando bases… · si no aparecen, seleccione los archivos': 'Loading databases... · if they do not appear, select the',
      'Carga de datos · portabilidad sin servidor': 'Data Loading · Serverless Portability',
      'Este portal funciona <strong>íntegramente en el navegador</strong>: no necesita servidor ni conexión a internet. Toda la información se lee de los archivos': 'This portal works entirely in the browser: it does not require a server or internet connection. All information is read from the <code>.db</code> (SQLite) files accompanying the manuscript. Load the files from the <code>db/</code> folder using the selector or drag them here; the page will detect each database, repaint all graphs with Plotly, and enable downloads. No data is sent to any server.',
      'Cargar bases <code>.db</code>': 'Load <code>.db</code> databases',
      'Cargar todas': 'Load All',
      'Arrastre aquí los archivos': 'Drag files here',
      'Seleccionar archivos .db': 'Select .db files',
      'Ninguna base cargada todavía.': 'No databases loaded yet.',
      'Base': 'Database',
      'Tipo': 'Type',
      'Filas': 'Rows',
      'Estado': 'Status',
      'Resumen del portal': 'Portal Summary',
      'Este portal conecta el corpus final de la revisión sistemática': 'This portal connects the final corpus of the systematic review (124 Scopus documents, 2008-2026, delivered in <code>thirdPass_124.csv</code>) with an operational technology matrix for artisanal and small-scale mining. Each technology is cataloged by technology readiness level (TRL 1-9), compatibility with deposit geometry (including narrow veins of 2-3 m), investment requirements (CAPEX/OPEX) and impact on safety and environment, with values calibrated by an expert Delphi panel with 10-20 years of experience.',
      'corpus final de la revisión sistemática': 'final corpus of the systematic review',
      'matriz operativa de tecnologías': 'operational technology matrix',
      'minería artesanal y de pequeña escala': 'artisanal and small-scale mining',
      'nivel de madurez tecnológica': 'technology readiness level',
      'TRL 1–9': 'TRL 1–9',
      'geometría del yacimiento': 'deposit geometry',
      'incluidas vetas angostas de 2–3 m': 'including narrow veins of 2–3 m',
      'requerimientos de inversión': 'investment requirements',
      'CAPEX/OPEX': 'CAPEX/OPEX',
      'impacto en seguridad y ambiente': 'impact on safety and environment',
      'panel de expertos Delphi': 'expert Delphi panel',
      '10–20 años de experiencia': '10–20 years of experience',
      'Metodología · flujo de la revisión sistemática (PRISMA 2020)': 'Methodology · PRISMA 2020 systematic review flow',
      'El corpus se construyó siguiendo la guía': 'The corpus was built following the',
      'PRISMA 2020': 'PRISMA 2020',
      'y se procesó en tres fases': 'and was processed in three phases',
      'La fase I depura la exportación de Scopus': 'Phase I cleans the Scopus export',
      'la fase II aplica análisis bibliométrico': 'Phase II applies bibliometric analysis',
      'la fase III valida los resultados con un panel Delphi': 'Phase III validates the results with a Delphi panel',
      'Figura 1 · diagrama de flujo PRISMA 2020': 'Figure 1 · PRISMA 2020 flow diagram',
      'Diagrama de flujo PRISMA 2020 del proceso': 'PRISMA 2020 flow diagram of the identification, screening and inclusion process',
      'Flujo de selección del corpus': 'Selection flow of the corpus',
      'exportación de Scopus, 360 documentos': 'Scopus export, 360 documents',
      'validación de DOI y eliminación de duplicados, 269 con DOI': 'DOI validation and duplicate removal, 269 with DOI',
      'acotación al rango 2006–2026, 258': 'delimitation to range 2006–2026, 258',
      'aislamiento del clúster': 'isolation of the cluster',
      'Mina subterránea × tecnología minera': 'Underground Mine × Mining Technology',
      'corpus cualitativo final, 124 documentos, 2008–2026': 'final qualitative corpus, 124 documents, 2008–2026',
      'validado mediante panel Delphi': 'validated by Delphi panel',
      'Producción anual por periodos e impacto acumulado': 'Annual production by periods and accumulated impact',
      'Producción anual de documentos por período': 'Annual document production by period',
      'con impacto acumulado de citas': 'with accumulated citation impact',
      'Figura 2 · Producción anual por fuentes': 'Figure 2 · Annual production by sources',
      'Producción anual por fuentes': 'Annual production by sources',
      'Distribución de documentos por fuente y año': 'Document distribution by source and year',
      'Panel integrado: evolución anual y concentración de fuentes': 'Integrated Panel: Annual Evolution and Source Concentration',
      'Evolución anual de documentos por período': 'Annual evolution of documents by period',
      'Observatorio Operativo de la UASM': 'Operational Observatory of UASM',
      'Indicadores de adopción tecnológica': 'Technology adoption indicators',
      'seguridad, cumplimiento ambiental': 'safety, environmental compliance',
      'inversión y marco normativo': 'investment and regulatory framework',
      'por región y país': 'by region and country',
      'África, Latinoamérica, Asia-Pacífico y Europa': 'Africa, Latin America, Asia-Pacific and Europe',
      'fuentes públicas (UNESCO, Banco Mundial, IGF)': 'public sources (UNESCO, World Bank, IGF)',
      'validados con el panel de expertos (Delphi)': 'validated by the expert Delphi panel',
      'Perfil regional multidimensional': 'Multidimensional Regional Profile',
      'Gráfica, tabla y carga': 'Graphics, tables and loading',
      'Cargar/Actualizar tabla': 'Load/Update Table',
      'Cargue un archivo .db para actualizar la tabla': 'Load a .db file to update the table',
      'Matriz de Transferencia Tecnológica': 'Technology Transfer Matrix',
      'Catálogo de tecnologías identificadas en la literatura': 'Catalog of technologies identified in the literature',
      'ordenado por geometría del yacimiento y viabilidad económica': 'ordered by deposit geometry and economic viability',
      'Los campos DOCS, TRL, CAPEX, OPEX, SEG, AMB han sido eliminados': 'The DOCS, TRL, CAPEX, OPEX, SEG, AMB fields have been removed',
      'A continuación figuran las rondas Delphi:': 'Below are the Delphi rounds:',
      'Figura 4 · Resultado PRISMA según z7.svg': 'Figure 4 · PRISMA Result according to z7.svg',
      'Resultado PRISMA - Etapas operativas y tecnologías identificadas': 'PRISMA Result - Operational stages and identified technologies',
      'según z7.svg': 'according to z7.svg',
      'Figura 5 · Ronda 1 según z8.svg': 'Figure 5 · Round 1 according to z8.svg',
      'Ronda 1 - Priorización multicriterio de tecnologías': 'Round 1 - Multicriteria prioritization of technologies',
      'según z8.svg': 'according to z8.svg',
      'Red de convergencia tecnológica': 'Technology Convergence Network',
      'Red de co-ocurrencia de tecnologías del catálogo': 'Technology co-occurrence network from the catalog',
      'un vínculo une dos tecnologías': 'a link connects two technologies',
      'cuando comparten documentos del corpus': 'when they share documents from the corpus',
      'el grosor indica el número de co-ocurrencias': 'thickness indicates the number of co-occurrences',
      'Solo se muestran tecnologías con valor mayor a 0': 'Only technologies with a value greater than 0 are displayed',
      'Explorador del corpus': 'Corpus Explorer',
      'Cinco vistas del corpus Scopus': 'Five views of the Scopus corpus',
      'corpus final cualitativo': 'final qualitative corpus',
      'exportación original de Scopus': 'original Scopus export',
      'corpus depurado': 'cleaned corpus',
      'rango analítico 2006–2026': 'analytical range 2006–2026',
      'clúster': 'cluster',
      'Seleccione una pestaña para explorar': 'Select a tab to explore',
      'la vista correspondiente': 'the corresponding view',
      'se materializa en': 'is materialized in',
      'Buscar en título, autores, fuente, palabras clave…': 'Search in title, authors, source, keywords...',
      'Todos los clústeres': 'All clusters',
      'Cualquier acceso': 'Any access',
      'Año desde': 'Year from',
      'Año hasta': 'Year to',
      'Exportar CSV': 'Export CSV',
      'documentos': 'documents',
      'fuente:': 'source:',
      'ver': 'view',
      'Entrega científica · <code>tabla_deliverable.db</code>': 'Scientific Delivery · <code>tabla_deliverable.db</code>',
      'Análisis cualitativo completo por documento': 'Complete qualitative analysis per document',
      'hallazgos principales, limitaciones y novedad': 'main findings, limitations and novelty',
      'Descargue la tabla en CSV': 'Download the table in CSV',
      'Data availability': 'Data availability',
      'del manuscrito': 'of the manuscript',
      'Bases de datos <code>.db</code> · fuente única de verdad': '<code>.db</code> databases · single source of truth',
      'Todo lo que muestra el portal proviene': 'Everything shown by the portal comes from',
      'Cada gráfica y cada tabla tiene': 'Each graph and table has',
      'su propia base derivada': 'its own derived database',
      'con las tablas': 'with tables',
      'filas mostradas': 'rows shown',
      'cálculo de origen': 'source calculation',
      'metadatos de campos': 'field metadata',
      'descripción y ficha': 'description and sheet',
      'Inventario de bases cargadas': 'Loaded Databases Inventory',
      'Cargue los <code>.db</code> para ver el inventario.': 'Load the <code>.db</code> files to view the inventory.',
      'Consola SQL de solo lectura': 'Read-Only SQL Console',
      'Solo se permiten consultas de lectura sobre las bases cargadas.': 'Only read queries are allowed on loaded databases.',
      'Ejecutar SELECT': 'Run SELECT',
      'Solo se permiten consultas de lectura': 'Only read queries are allowed',
      'sobre las bases cargadas': 'on loaded databases',
      'SELECT anio, COUNT(*) AS n FROM datos GROUP BY anio ORDER BY anio DESC LIMIT 10': 'SELECT year, COUNT(*) AS n FROM data GROUP BY year ORDER BY year DESC LIMIT 10',
      'Año': 'Year',
      'Título': 'Title',
      'Autores': 'Authors',
      'Fuente': 'Source',
      'Citas': 'Citations',
      'Clúster': 'Cluster',
      'Acceso': 'Access',
      'DOI': 'DOI',
      'Portal UASM · Observatorio Operativo y Transferencia Tecnológica · Corpus Scopus 1974–2026': 'UASM Portal · Operational Observatory and Technology Transfer · Scopus Corpus 1974–2026',
      'El corpus se construyó siguiendo la guía <strong>PRISMA 2020</strong> y se procesó en tres fases.': 'The corpus was built following the <strong>PRISMA 2020</strong> guide and was processed in three phases.',
      'Flujo de selección del corpus: identificación': 'Corpus selection flow: identification (Scopus export, 360 documents), screening (DOI validation and duplicate removal, 269 with DOI; delimitation to range 2006–2026, 258; isolation of the cluster "Underground Mine × Mining Technology", 207) and inclusion (final qualitative corpus, 124 documents, 2008–2026) validated by Delphi panel.',
      '23 tecnologías de integración identificadas en 5 etapas operativas según el análisis del corpus': '23 integration technologies identified in 5 operational stages according to corpus analysis.',
      'Indicadores de adopción tecnológica, seguridad, cumplimiento ambiental': 'Technology adoption indicators, safety, environmental compliance, investment and regulatory framework by region and country (Africa, Latin America, Asia-Pacific and Europe). The values were calibrated with public sources (UNESCO, World Bank, IGF) and validated by the expert Delphi panel.',
      'Gráfica, tabla y carga de indicadores regionales multidimensionales.': 'Graphics, tables and loading of multidimensional regional indicators.',
      'Descargar CSV': 'Download CSV',
      'database': 'Database',
      'type': 'Type',
      'rows': 'Rows',
      'tables': 'Tables',
      'download': 'Download',
      'status': 'Status'
    }
  };

  let currentLang = 'es';

  function translateElement(el) {
    const text = el.textContent.trim();
    // Handle button translations
    const btnText = el.getAttribute('data-i18n-btn');
    if (btnText && translations[currentLang][btnText]) {
      el.textContent = translations[currentLang][btnText];
      return;
    }
    const key = Object.keys(translations.en).find(k => text === k);
    
    if (key && translations[currentLang][key] !== undefined) {
      if (el.innerHTML.includes('<span') || el.innerHTML.includes('<code>')) {
        // Preserve HTML tags
        let html = translations[currentLang][key];
        // Copy classes and tags from original
        const tempDiv = document.createElement('div');
        tempDiv.innerHTML = el.innerHTML;
        const tempNew = document.createElement('div');
        tempNew.innerHTML = html;
        
        // Copy span tags
        const spans = tempDiv.querySelectorAll('span');
        const newSpans = tempNew.querySelectorAll('span');
        for (let i = 0; i < spans.length && i < newSpans.length; i++) {
          newSpans[i].className = spans[i].className;
        }
        
        // Copy code tags
        const codes = tempDiv.querySelectorAll('code');
        const newCodes = tempNew.querySelectorAll('code');
        for (let i = 0; i < codes.length && i < newCodes.length; i++) {
          newCodes[i].textContent = codes[i].textContent;
        }
        
        el.innerHTML = tempNew.innerHTML;
      } else {
        el.textContent = translations[currentLang][key];
      }
    }
    
    // Handle placeholders
    if (el.hasAttribute('placeholder')) {
      const ph = el.getAttribute('placeholder');
      const phKey = Object.keys(translations.en).find(k => ph === k);
      if (phKey) el.setAttribute('placeholder', translations[currentLang][phKey]);
    }
    // Handle data-i18n-placeholder
    if (el.hasAttribute('data-i18n-placeholder')) {
      const ph = el.getAttribute('data-i18n-placeholder');
      const phKey = Object.keys(translations.en).find(k => ph === k);
      if (phKey) el.setAttribute('placeholder', translations[currentLang][phKey]);
    }
    
    // Handle alt text
    if (el.hasAttribute('alt') && !el.getAttribute('data-i18n-alt')) {
      const alt = el.getAttribute('alt');
      const altKey = Object.keys(translations.en).find(k => alt === k);
      if (altKey) el.setAttribute('alt', translations[currentLang][altKey]);
    }
    
    // Handle title attribute
    if (el.hasAttribute('title')) {
      const title = el.getAttribute('title');
      const titleKey = Object.keys(translations.en).find(k => title === k);
      if (titleKey) el.setAttribute('title', translations[currentLang][titleKey]);
    }
  }

  function translateTree(node) {
    if (node.nodeType === Node.ELEMENT_NODE) {
      // Translate element itself
      translateElement(node);
      
      // Handle button translations
      if (node.hasAttribute('data-i18n-btn')) {
        const btnKey = node.getAttribute('data-i18n-btn');
        if (translations[currentLang][btnKey]) {
          node.textContent = translations[currentLang][btnKey];
        }
      }
      
      // Translate children
      for (let child of node.childNodes) {
        translateTree(child);
      }
    }
  }

  function translateAll() {
    // Update currentLang for portal.js
    window.currentLang = currentLang;
    
    // Translate all elements in body
    translateTree(document.body);
    
    // Update active language button
    document.querySelectorAll('.lang-btn').forEach(btn => {
      btn.classList.toggle('active', btn.getAttribute('data-lang') === currentLang);
    });
    
    // Update theme button text
    const themeBtn = document.getElementById('theme_toggle');
    if (themeBtn) {
      const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
      themeBtn.textContent = currentLang === 'es' ? 
        (isDark ? 'Modo día' : 'Modo noche') : 
        (isDark ? 'Light mode' : 'Dark mode');
    }
    
    // Update SQL textarea placeholder
    const sqlTxt = document.getElementById('sql_txt');
    if (sqlTxt && currentLang === 'en') {
      sqlTxt.placeholder = 'SELECT year, COUNT(*) AS n FROM data GROUP BY year ORDER BY year DESC LIMIT 10';
    } else if (sqlTxt && currentLang === 'es') {
      sqlTxt.placeholder = 'SELECT anio, COUNT(*) AS n FROM datos GROUP BY anio ORDER BY anio DESC LIMIT 10';
    }
    
    // Re-render dynamic content
    if (typeof renderizarTodo === 'function') {
      setTimeout(renderizarTodo, 100);
    }
    if (typeof renderPerfilRegional === 'function') {
      setTimeout(renderPerfilRegional, 100);
    }
    if (typeof aplicarTema === 'function') {
      setTimeout(() => aplicarTema(temaInicial()), 100);
    }
  }

  function initTranslation() {
    // Load saved language
    const savedLang = localStorage.getItem('mape_lang');
    if (savedLang === 'es' || savedLang === 'en') {
      currentLang = savedLang;
    }
    
    // Set language buttons
    const btnEs = document.getElementById('lang_es');
    const btnEn = document.getElementById('lang_en');
    
    if (btnEs) {
      btnEs.addEventListener('click', () => {
        currentLang = 'es';
        translateAll();
        localStorage.setItem('mape_lang', 'es');
      });
    }
    
    if (btnEn) {
      btnEn.addEventListener('click', () => {
        currentLang = 'en';
        translateAll();
        localStorage.setItem('mape_lang', 'en');
      });
    }
    
    // Initial translation
    translateAll();
  }

  // Initialize
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initTranslation);
  } else {
    initTranslation();
  }
})();
