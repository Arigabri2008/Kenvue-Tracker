# Kenvue Price Tracker — España

Dashboard de precios Kenvue (Johnson's, Le Petit Marseillais, OGX, Carefree, o.b.) en 10 retailers españoles, con actualización automática semanal y publicación en GitHub Pages.

---

## Cómo funciona el sistema completo

```
Cada lunes 08:00h (automático)
        │
        ▼
  GitHub ejecuta scraper.py
  en la nube (gratis)
        │
        ▼
  Actualiza prices.json
  en el repositorio
        │
        ▼
  Publica dashboard en
  tu-usuario.github.io/kenvue-tracker
        │
        ▼
  Tú abres la URL y ves
  los precios de la semana
```

No necesitas tener el ordenador encendido. No necesitas hacer nada cada semana.

---

## Puesta en marcha — guía paso a paso

### Paso 1 · Crear cuenta en GitHub

Ve a **github.com** → clic en "Sign up" → introduce email, contraseña y nombre de usuario → confirma el email.

Es gratis. No hace falta instalar nada todavía.

---

### Paso 2 · Crear el repositorio

Una vez dentro de GitHub:

1. Clic en el botón verde **"New"** (esquina superior izquierda)
2. En "Repository name" escribe: `kenvue-tracker`
3. Selecciona **Private** (solo tú lo ves) o **Public** (cualquiera puede ver la URL del dashboard)
   > ⚠️ GitHub Pages gratuito solo funciona con repositorios **públicos**. Si necesitas que sea privado, necesitas plan de pago (GitHub Pro, ~4€/mes). Para uso interno de equipo, público suele ser suficiente porque la URL no está indexada por Google si no la compartes.
4. Deja el resto como está
5. Clic en **"Create repository"**

---

### Paso 3 · Subir los archivos

En la página del repositorio vacío, busca el enlace **"uploading an existing file"** y haz clic.

Se abre un área para arrastrar archivos. Sube estos archivos del ZIP:

```
✅ index.html
✅ prices.json
✅ scraper.py
✅ README.md
```

Para la carpeta `.github/workflows/` (los archivos .yml), GitHub no permite subir carpetas arrastrando. Hazlo así:

1. Clic en **"Add file" → "Create new file"**
2. En el campo de nombre escribe: `.github/workflows/scrape.yml`
   (GitHub crea las carpetas automáticamente)
3. Copia y pega el contenido del archivo `scrape.yml` del ZIP
4. Clic en **"Commit changes"**
5. Repite con `.github/workflows/pages.yml`

---

### Paso 4 · Activar GitHub Pages

1. Pestaña **"Settings"** → menú lateral **"Pages"**
2. En "Source" selecciona **"GitHub Actions"**
3. Guarda

---

### Paso 5 · Primer despliegue manual

1. Ve a la pestaña **"Actions"**
2. Clic en *"Publicar dashboard en GitHub Pages"*
3. Clic en **"Run workflow"** → confirmar
4. Espera ~30 segundos → marca verde ✓

Tu dashboard queda en:
```
https://TU-USUARIO.github.io/kenvue-tracker
```

---

### Paso 6 · Primer scraping de precios reales

1. **Actions** → *"Kenvue Price Tracker — Actualización semanal"*
2. **"Run workflow"** → confirmar
3. Tarda 15-25 minutos
4. Al terminar, `prices.json` se actualiza y el dashboard se republica solo

A partir de aquí todo es automático cada lunes.

---

## Flujo semanal automático

```
Lunes 08:00h
    │
    ├─ scrape.yml → instala Python + Chromium → ejecuta scraper.py
    ├─ Actualiza prices.json con git commit automático
    │
    └─ pages.yml se activa por el nuevo commit
        └─ Republica index.html + prices.json en GitHub Pages (~30 seg)
```

---

## Ver resultados de cada scraping

**Actions** → última ejecución → paso "Resumen del scraping":

```
Total: 52 URLs
OK:    48
Fallos: 4

URLs con precio no encontrado:
  El Corte Inglés     Champú Clásico Gold 300ml
  ...
```

Los fallos son normales (algunos retailers bloquean scrapers ocasionalmente).
El dashboard usa el precio estático como fallback — nunca aparece un hueco vacío.

---

## Añadir productos nuevos

1. Abre `scraper.py` en GitHub → lápiz ✏️ para editar
2. Añade la fila en `CATALOG`:
   ```python
   ("mi-group-key", "Nombre producto", "Marca", "Categoría", volumen_ml,
    "Retailer", "https://url-directa"),
   ```
3. Abre `index.html`, busca `GROUP_LABELS` y añade:
   ```js
   'mi-group-key': 'Nombre legible en el dashboard',
   ```
4. Commit → el próximo lunes aparece en el dashboard

---

## Estructura del repositorio

```
kenvue-tracker/
├── index.html                  ← Dashboard (GitHub Pages / navegador local)
├── prices.json                 ← Precios actualizados por el scraper
├── scraper.py                  ← Script de extracción
├── README.md                   ← Esta guía
└── .github/workflows/
    ├── scrape.yml              ← Scraping automático (lunes 08:00h)
    └── pages.yml               ← Publicación en GitHub Pages
```

*Marzo 2026*
