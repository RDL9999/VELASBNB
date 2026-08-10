# Publicar.sh — instrucciones de uso

## Cómo publicar (todo automatizado excepto 1 paso)

1. Estás en la raíz del repositorio (VELASBNB). Ejecuta:

```bash
bash experimento_9usd_real/publicar.sh
```

El script: verifica herramientas, ejecuta las 28 pruebas del producto, hace
commit + push a `main` e intenta activar GitHub Pages por API.

## ⚠ El único paso manual (1 minuto)

El token actual **no tiene permiso "Pages"**, así que GitHub rechaza la
activación por API (error 403 *"Resource not accessible by integration"*).
Esto no depende del script: es una restricción del token.

Para activar Pages a mano:

1. Abre https://github.com/RDL9999/VELASBNB/settings/pages
2. En **Build and deployment · Source** elige **GitHub Actions**
3. Pulsa **Save**

Listo. La workflow `.github/workflows/pages.yml` (ya subida) despliega la
landing automáticamente. Si el despliegue no arranca solo, ejecuta:

```bash
gh workflow run "Deploy Landing y Demo a GitHub Pages"
```

## URLs finales

- Landing:  https://RDL9999.github.io/VELASBNB/landing/
- Raíz (redirige a la landing): https://RDL9999.github.io/VELASBNB/
- Demo:     https://RDL9999.github.io/VELASBNB/simulador_futbol_mejorado.html

> Verificar estado: `gh api repos/RDL9999/VELASBNB/pages --jq '.status'`
> (respuesta `built` = publicado).
