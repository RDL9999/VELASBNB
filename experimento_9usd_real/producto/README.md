# ⚽ Kit Analítico Dixon-Coles — Simulador Estadístico de Fútbol

Kit de herramientas para estimar probabilidades de marcadores de partidos de
fútbol con el **modelo Dixon-Coles**: matriz exacta de Poisson, Monte Carlo
reproducible, intervalos de confianza de Wilson y análisis por jornada.

Los resultados son **estimaciones probabilísticas**, no predicciones
garantizadas ni recomendaciones de apuestas.

## Contenido

- `simulador_futbol_mejorado.py` — módulo principal (Python 3 estándar, sin dependencias).
- `simulador_futbol_mejorado.html` — versión web autónoma y offline.
- `analisis_lote.py` — análisis de jornadas completas.
- `calibrar_equipo.py` — ratings α/δ desde estadísticas del equipo.
- `ejemplo_partido.json` y `jornada_ejemplo.json` — configuraciones de ejemplo.
- `guia_de_uso.md` — manual completo.
- `test_simulador_futbol.py` — 28 pruebas unitarias.

## Inicio rápido

```bash
python3 -m unittest test_simulador_futbol.py
python3 simulador_futbol_mejorado.py --config ejemplo_partido.json
python3 analisis_lote.py jornada_ejemplo.json
python3 calibrar_equipo.py --goles-a-favor 32 --goles-en-contra 18 --partidos 20
```

Ver `guia_de_uso.md` para la guía completa.
