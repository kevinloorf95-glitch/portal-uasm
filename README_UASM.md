# Portal UASM - Guía de Implementación

## Descripción
Portal web autónomo para visualización de datos de la **Minería Subterránea Artesanal y de Pequeña Escala (UASM)**. El portal funciona completamente en el navegador sin necesidad de servidor.

## Estructura del Proyecto

```
resultados/frame/
├── index.html              # Página principal
├── assets/
│   ├── style.css           # Estilos CSS
│   ├── portal.js           # Lógica principal del portal
│   ├── translation.js      # Sistema de traducción
│   ├── plotly.min.js       # Librería Plotly
│   └── sql-wasm.*          # SQLite WASM
├── graficosIndex/
│   ├── z1.svg              # Diagrama PRISMA
│   ├── z2.svg              # Producción anual por periodos
│   ├── z3.svg              # Red de convergencia
│   ├── z4.svg              # Red VOS
│   ├── z5.svg              # Panel integrado
│   ├── z6.svg              # 23 tecnologías (Ronda 1)
│   ├── z7.svg              # Alluvial (Ronda 2)
│   └── z8.svg              # Mapa de calor (Ronda 3)
└── db/
    ├── chart_*.db          # Bases de datos de gráficas
    ├── corpus_*.db         # Bases de datos del corpus
    └── tabla_*.db          # Bases de datos de tablas
```

## Requisitos

- Navegador moderno (Chrome, Firefox, Edge)
- No requiere servidor web
- No requiere conexión a internet (después de la carga inicial)

## Instalación y Uso

### Opción 1: Abrir directamente en el navegador
Simplemente abra el archivo `index.html` en su navegador. El portal cargará automáticamente las bases de datos de la carpeta `db/`.

### Opción 2: Servidor local
Si prefiere usar un servidor local:

```bash
# Usando Python
python -m http.server 8000

# Usando Node.js
npx http-server

# Usando PHP
php -S localhost:8000
```

Luego abra `http://localhost:8000/resultados/frame/index.html` en su navegador.

### Opción 3: GitHub Pages

1. Cree un repositorio en GitHub
2. Suba todo el contenido de `resultados/frame/` al repositorio
3. Habilite GitHub Pages en la configuración del repositorio
4. Su portal estará disponible en `https://<username>.github.io/<repo>/`

## Características

- **Visualización interactiva** con Plotly
- **Traducción completa** español ↔ inglés
- **Modo día/noche** automático o manual
- **Carga de bases de datos** desde archivos `.db` (SQLite)
- **Exportación** a CSV y SVG
- **Consola SQL** de solo lectura

## Secciones del Portal

1. **Inicio**: Resumen del portal y KPIs
2. **Metodología**: Flujo PRISMA y producción anual
3. **Observatorio**: Indicadores por región y país
4. **Matriz de Transferencia**: Tecnologías con priorización multicriterio
5. **Red de Convergencia**: Red de co-ocurrencia de tecnologías
6. **Corpus**: Explorador del corpus Scopus
7. **Bases .db**: Inventario y consola SQL

## Archivos de Datos

Los archivos `.db` (SQLite) contienen todos los datos:

- **chart_anios.db**: Producción por años
- **chart_donut_cluster.db**: Distribución por clúster
- **chart_donut_acceso.db**: Distribución por tipo de acceso
- **chart_periodos.db**: Producción anual por periodos
- **chart_panel_integrado.db**: Panel integrado
- **chart_ronda1.db**: Resultados PRISMA
- **chart_ronda2.db**: Ronda 2 - Análisis de barreras
- **chart_ronda3.db**: Ronda 1 - Priorización multicriterio
- **tabla_corpus.db**: Corpus completo
- **tabla_tecnologias.db**: Catálogo de tecnologías
- **tabla_deliverable.db**: Análisis cualitativo
- **corpus_*.db**: Vistas del corpus (124, 207, 258, 269, 360)

## Personalización

### Cambiar el rango de años
Modificar en `index.html`:
```html
<div class="kicker">Revisión sistemática de literatura · Scopus · 1974–2026</div>
```

### Cambiar el nombre del portal
Modificar en `index.html`:
```html
<h1>Portal de <span class="accent">Transferencia Tecnológica</span> y Observatorio Operativo de la Minería Subterránea Artesanal y de Pequeña Escala (UASM)</h1>
```

### Añadir nuevas bases de datos
Colocar los archivos `.db` en la carpeta `db/` y el portal los cargará automáticamente.

## Solución de Problemas

### Los gráficos no se cargan
- Verifique que los archivos `.db` estén en la carpeta `db/`
- Asegúrese de que los archivos tengan el formato correcto (SQLite)
- Abra la consola del navegador (F12) para ver errores

### La traducción no funciona
- Verifique que el archivo `translation.js` esté cargado
- Asegúrese de que los elementos HTML tengan el atributo `data-i18n`

### El modo día/noche no funciona
- Verifique que el archivo `style.css` esté cargado
- Asegúrese de que el elemento `<html>` tenga el atributo `data-theme`

## Compartir el Portal

### Compartir por GitHub

1. **Crear repositorio**:
   ```bash
   cd /c/Users/USER/DataspellProjects/revision_03092026/resultados/frame
   git init
   git add .
   git commit -m "Portal UASM - Versión inicial"
   git remote add origin https://github.com/<username>/portal-uasm.git
   git push -u origin main
   ```

2. **Habilitar GitHub Pages**:
   - Ve a Configuración > Pages
   - Selecciona la rama `main` y la carpeta `/ (root)`
   - Guarda

3. **Compartir el enlace**:
   - El portal estará disponible en: `https://<username>.github.io/portal-uasm/`

### Compartir por archivo ZIP

1. Comprimir la carpeta `resultados/frame/`:
   ```bash
   cd /c/Users/USER/DataspellProjects/revision_03092026
   zip -r portal-uasm.zip resultados/frame/
   ```

2. Enviar el archivo ZIP a los destinatarios

### Compartir por Google Drive/Dropbox

1. Subir la carpeta `resultados/frame/` a Google Drive o Dropbox
2. Compartir el enlace con permisos de visualización

## Notas

- El portal funciona completamente en el navegador
- No se envían datos a ningún servidor
- Todas las visualizaciones son interactivas
- Los datos se cargan desde archivos `.db` locales

## Licencia

Este portal es parte de un proyecto de investigación académica. Consulte los términos de uso específicos de su institución.

---

**Versión**: 1.0  
**Última actualización**: 2026  
**Contacto**: Consulte al equipo de investigación
