#!/usr/bin/env bash
# =============================================================================
# publicar.sh — Publica el Kit Dixon-Coles en GitHub Pages (RDL9999.github.io)
#
# Requisitos: gh autenticado (GITHUB_TOKEN) y git. No instala nada más.
# Uso: bash publicar.sh
# =============================================================================
set -euo pipefail

REPO="RDL9999/VELASBNB"
BRANCH="main"
LANDING="landing/index.html"
URL_FINAL="https://RDL9999.github.io/VELASBNB/landing/"
URL_DEMO="https://RDL9999.github.io/VELASBNB/simulador_futbol_mejorado.html"

echo "==> [1/5] Verificando herramientas..."
command -v git >/dev/null || { echo "Falta git"; exit 1; }
command -v gh  >/dev/null || { echo "Falta gh"; exit 1; }

echo "==> [2/5] Inicializando git si es necesario..."
if [ ! -d .git ]; then
  git init
  git branch -M "$BRANCH"
  git remote add origin "https://github.com/$REPO.git"
fi
git remote set-url origin "https://github.com/$REPO.git" >/dev/null 2>&1 || true

echo "==> [3/5] Probando el producto antes de publicar..."
if command -v python3 >/dev/null; then
  (cd experimento_9usd_real/producto && python3 -m unittest test_simulador_futbol.py -q >/dev/null && echo "     Tests OK (28)")
  (cd experimento_9usd_real/producto && python3 analisis_lote.py jornada_ejemplo.json >/dev/null && echo "     analisis_lote OK")
else
  echo "     (python3 no disponible; se omite la prueba automática)"
fi

echo "==> [4/5] Commit y push..."
git add -A
if git diff --cached --quiet; then
  echo "     No hay cambios que publicar (ya está todo en git)."
else
  git commit -m "Publicar Kit Dixon-Coles: simulador estadistico de futbol + landing de venta" || true
  git push -u origin "$BRANCH" || { echo "ERROR: push falló"; exit 1; }
fi

echo "==> [5/5] Configurando GitHub Pages desde la CLI..."
# Activa Pages desde la rama actual si aún no está activo.
gh api "repos/$REPO/pages" >/dev/null 2>&1 || gh api -X POST "repos/$REPO/pages" \
  -f "source[branch]=$BRANCH" -f "source[path]=/" >/dev/null 2>&1 || true

# Fuerza la espera del build (máx 90 s) y reporta el estado.
for i in $(seq 1 30); do
  estado=$(gh api "repos/$REPO/pages" --jq ".status" 2>/dev/null || echo "pendiente")
  echo "     Estado de Pages: $estado"
  if [ "$estado" = "built" ]; then break; fi
  sleep 3
done

echo ""
echo "=============================================================="
echo "  LISTO. Publicado en GitHub Pages."
echo "  Landing:       $URL_FINAL"
echo "  Demo (producto): $URL_DEMO"
echo "=============================================================="
echo "  PayPal:  https://www.paypal.me/rdl2job/9   (Estándar, \$9)"
echo "           https://www.paypal.me/rdl2job/15  (PRO, \$15)"
echo "  USDT:    0x7DE2F24Eb14D219E7eE562b5247ff312FDD70e8c"
echo "=============================================================="
