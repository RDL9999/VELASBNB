# 📘 Guía de uso — Kit Analítico Dixon-Coles

Kit estadístico para estimar la distribución de marcadores de partidos de
fútbol usando el modelo Dixon-Coles (dos Poisson con corrección bivariada
para marcadores bajos).

> **Importante:** todos los resultados son **estimaciones probabilísticas**
> basadas en supuestos estadísticos. No constituyen predicciones
> garantizadas ni recomendaciones de apuestas.

---

## 1. ¿Qué contiene el kit?

| Archivo | Para qué sirve |
|---------|----------------|
| `simulador_futbol_mejorado.py` | Módulo Python: modelo, matriz exacta, Monte Carlo reproducible, intervalos de Wilson, CLI y reportes JSON. |
| `simulador_futbol_mejorado.html` | Versión web autónoma (sin internet ni servidor). Los números coinciden exactamente con Python. |
| `analisis_lote.py` | Analiza una jornada completa (varios partidos) a la vez y produce una tabla comparativa + reporte JSON. |
| `calibrar_equipo.py` | Calcula los ratings α y δ de un equipo desde sus estadísticas históricas. |
| `ejemplo_partido.json` | Configuración de un partido lista para usar. |
| `jornada_ejemplo.json` | Ejemplo de jornada para `analisis_lote.py`. |
| `test_simulador_futbol.py` | 28 pruebas unitarias incluidas. |

---

## 2. Empezar rápido

```bash
# 1) Partido individual
python3 simulador_futbol_mejorado.py --config ejemplo_partido.json

# 2) Jornada completa
python3 analisis_lote.py jornada_ejemplo.json

# 3) Calibrar ratings de un equipo
python3 calibrar_equipo.py --goles-a-favor 32 --goles-en-contra 18 --partidos 20
```

---

## 3. Parámetros del modelo

| Parámetro | Qué es | Recomendación |
|-----------|--------|---------------|
| `alpha` (α) | Fuerza de ataque (1.0 = promedio de liga) | Estimar con `calibrar_equipo.py` |
| `delta` (δ) | Fuerza de defensa (1.0 = promedio de liga) | Estimar con `calibrar_equipo.py` |
| `mu` (μ) | Goles promedio por equipo por partido | Calcular desde los datos de tu liga |
| `gamma` (γ) | Factor de localía | Calibrar con historial de resultados de local/visitante |
| `rho` (ρ) | Correlación Dixon-Coles (rango [-0.30, 0.30]) | Calibrar o dejar en -0.15 |

**Fórmulas:**

```
λ_local     = α_local  × δ_visitante × γ × μ
λ_visitante = α_visitante × δ_local × μ

τ(0,0) = 1 − λL·λV·ρ
τ(0,1) = 1 + λL·ρ
τ(1,0) = 1 + λV·ρ
τ(1,1) = 1 − ρ
```

---

## 4. Calibración paso a paso

1. **mu de tu liga:** promedio de goles totales por partido ÷ 2.
   Ej.: si tu liga promedia 2.5 goles/partido totales, `mu = 1.25`.
2. **α y δ de cada equipo** con las últimas 15–25 jornadas:
   ```bash
   python3 calibrar_equipo.py --goles-a-favor 32 --goles-en-contra 18 --partidos 20 --mu 1.25
   ```
3. **γ (localía):** compara el promedio de goles de los locales contra el
   promedio general de la liga. Si los locales anotan 15% más, `γ ≈ 1.15`.
4. Escribe los valores en tu JSON y ejecuta el simulador.
5. **Valida:** los taus deben ser positivos. Si el simulador se detiene,
   reduce la magnitud de α/δ o de |ρ|.

---

## 5. Qué calcula

- Matriz exacta de marcadores (con expansión automática y normalización).
- Mercado 1X2, doble oportunidad (1X, 12, X2), ambos marcan,
  over/under 1.5 · 2.5 · 3.5 · 4.5, porterías a cero, xG local/visitante/total.
- Top 10 marcadores más probables.
- Monte Carlo reproducible (semilla) con intervalos de confianza de Wilson
  al 95% y comparación contra la matriz exacta.
- Reportes JSON (`--output`) para integrar en tus propias herramientas.

---

## 6. Web offline

Abre `simulador_futbol_mejorado.html` con doble clic o sírvelo:

```bash
python3 -m http.server 8000
# abre http://localhost:8000/simulador_futbol_mejorado.html
```

Python y HTML producen exactamente los mismos números (mismo generador
Mulberry32 y mismas fórmulas).

---

## 7. Pruebas

```bash
python3 -m unittest -v test_simulador_futbol.py
```

---

## 8. Límites del modelo

- Supone goles Poisson independientes (corrección solo en 0-0, 0-1, 1-0, 1-1).
- `γ` y `ρ` deben calibrarse; no se ajustan automáticamente por lesiones,
  rachas, motivación ni altitud.
- La varianza real de los goles suele superar la media (sobredispersión).
- Es una estimación, no una verdad; el azar real del deporte siempre puede
  producir resultados distintos.
