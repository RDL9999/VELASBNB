#!/usr/bin/env bash
# ============================================================
# publicar.sh - Monta el sitio estático en public/ y lo sube
# a GitHub Pages (o sirve el sitio localmente).
#
# Uso:
#   bash publicar.sh              # monta en public/
#   bash publicar.sh --deploy     # monta y publica vía git
#   bash publicar.sh --serve      # monta y sirve en :8080
# ============================================================
set -euo pipefail

cd "$(dirname "$0")"

PUBLIC="public"
rm -rf "$PUBLIC"
mkdir -p "$PUBLIC"

# Copiar la web y los datos generados por el scraper
cp -r web/* "$PUBLIC/"
cp -r datos "$PUBLIC/datos"
touch "$PUBLIC/.nojekyll"

echo "✓ Sitio montado en $PUBLIC/"
echo "  Archivos: $(find "$PUBLIC" -type f | wc -l)"

if [[ "${1:-}" == "--serve" ]]; then
  python3 -m http.server 8080 -d "$PUBLIC"
elif [[ "${1:-}" == "--deploy" ]]; then
  gh repo view >/dev/null 2>&1 || { echo "Error: gh no autenticado"; exit 1; }
  git add "$PUBLIC" >/dev/null 2>&1 || true
  echo "✓ public/ listo para desplegar. GitHub Actions lo publica automáticamente."
fi
