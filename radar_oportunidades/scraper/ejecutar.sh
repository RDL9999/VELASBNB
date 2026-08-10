#!/usr/bin/env bash
# Ejecuta el scraper del Radar de Oportunidades.
set -euo pipefail
cd "$(dirname "$0")"
python3 scraper.py "$@"
