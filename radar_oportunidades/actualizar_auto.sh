#!/usr/bin/env bash
# ============================================================
# actualizar_auto.sh - Ejecuta el scraper localmente y actualiza
# los datos. Pensado para ejecutarse con cron cada 6-12 horas.
#
# Cron sugerido (cada 6 horas):
#   0 */6 * * * /workspaces/VELASBNB/radar_oportunidades/actualizar_auto.sh >> /tmp/radar.log 2>&1
# ============================================================
set -uo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

echo "[$(date -u +%FT%TZ)] Iniciando actualización del radar..."

python3 scraper/scraper.py
RESULTADO=$?

if [ $RESULTADO -eq 0 ]; then
  echo "[$(date -u +%FT%TZ)] ✓ Scraper terminado. Datos actualizados en datos/"
else
  echo "[$(date -u +%FT%TZ)] ✗ Scraper falló (código $RESULTADO)"
fi

# Si estamos dentro de un repo git, ofrecer commit automático
if git rev-parse --git-dir >/dev/null 2>&1; then
  git add datos/ scraper/capacitate_cache.json 2>/dev/null
  if ! git diff --cached --quiet; then
    git -c user.name="radar-bot" -c user.email="radar-bot@users.noreply.github.com" \
      commit -m "chore(radar): actualización automática $(date -u +%FT%TZ)" 2>/dev/null \
      && git push 2>/dev/null \
      && echo "[$(date -u +%FT%TZ)] ✓ Cambios subidos a GitHub"
  fi
fi

echo "[$(date -u +%FT%TZ)] Fin de la actualización."
exit $RESULTADO
