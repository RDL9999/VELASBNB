# ⚽ Simulador de Fútbol Dixon-Coles (versión mejorada)

Simulador estadístico de partidos de fútbol basado en el **modelo Dixon-Coles**:
dos distribuciones de Poisson (una por equipo) con una corrección bivariada para
los marcadores bajos (0-0, 0-1, 1-0 y 1-1).

> ⚠️ **Importante:** los resultados son una **estimación probabilística** basada
> en supuestos estadísticos. **No** constituyen una predicción garantizada ni una
> recomendación de apuestas. No se afirman resultados reales de Liga MX: todos los
> datos de ejemplo son ilustrativos.

---

## 📁 ¿Qué hace cada archivo?

| Archivo | Descripción |
|---------|-------------|
| `simulador_futbol_mejorado.py` | Módulo principal en Python: modelo, matriz exacta, Monte Carlo reproducible, intervalos Wilson, CLI y reportes JSON. |
| `simulador_futbol_mejorado.html` | Versión web autónoma (sin servidores ni CDN). Mismo modelo y mismos números que Python. |
| `test_simulador_futbol.py` | Pruebas unitarias con `unittest` para el módulo Python. |
| `ejemplo_partido.json` | Configuración de ejemplo lista para usar (Pachuca vs Querétaro). |
| `README_SIMULADOR_FUTBOL.md` | Este documento. |
| `simulador_original_respaldo.txt` | **Copia intacta del código original** proporcionado, guardada como referencia. |

---

## 🚀 Ejecución en GitHub Codespaces

1. Abre el repositorio en Codespaces.
2. Abre una terminal (por defecto en el directorio del proyecto).
3. Verifica Python 3:

   ```bash
   python3 --version
   ```

4. Ejecuta el simulador con la configuración de ejemplo:

   ```bash
   python3 simulador_futbol_mejorado.py --config ejemplo_partido.json
   ```

5. Guarda el reporte como JSON:

   ```bash
   python3 simulador_futbol_mejorado.py --config ejemplo_partido.json --output reporte.json
   ```

6. Otras opciones:

   ```bash
   # Solo matriz exacta (sin Monte Carlo)
   python3 simulador_futbol_mejorado.py --config ejemplo_partido.json --sin-montecarlo

   # Sobrescribir número de simulaciones y semilla
   python3 simulador_futbol_mejorado.py --config ejemplo_partido.json --n 100000 --semilla 12345
   ```

---

## 🧪 Ejecutar las pruebas

```bash
python3 -m unittest -v test_simulador_futbol.py
```

Las pruebas cubren: `poisson_pmf` con valores conocidos, suma ≈ 1 de la matriz y
del mercado 1X2, validación de parámetros, rechazo de `tau` inválido, cálculo
correcto de lambdas, reproducibilidad del Monte Carlo con la misma semilla y
rango válido de probabilidades.

---

## 🌐 Abrir el HTML

El archivo `simulador_futbol_mejorado.html` es **100% autónomo**: no necesita
servidor ni conexión a internet. Funciona offline y es responsive (cómodo en
iPad y en pantallas pequeñas).

**Opciones para abrirlo en Codespaces:**

- Desde la pestaña **Explorador** (archivos), haz clic derecho sobre
  `simulador_futbol_mejorado.html` y elige **"Open Preview"** o **"Open with Live Server"**.
- O ejecuta un mini servidor local y ábrelo en el navegador:

  ```bash
  python3 -m http.server 8000
  ```

  Luego abre `http://localhost:8000/simulador_futbol_mejorado.html`.

**Desde tu propia máquina:** haz doble clic en el archivo y se abrirá en tu navegador.

---

## 🎯 Explicación de los parámetros

| Parámetro | Qué es | Cómo se usa |
|-----------|--------|-------------|
| `alpha` (α) | Fuerza de ataque. 1.0 = promedio de la liga. | `(goles_a_favor / partidos) / mu` |
| `delta` (δ) | Fuerza de defensa. 1.0 = promedio de la liga. | `(goles_en_contra / partidos) / mu` |
| `mu` (μ) | Goles promedio por equipo por partido de la liga. | Editable según la liga. |
| `gamma` (γ) | Factor de localía (multiplica los goles del local). | Debe **calibrarse** con datos históricos. |
| `rho` (ρ) | Correlación entre los goles de ambos equipos (Dixon-Coles). | Debe **calibrarse**; se valida en [-0.30, 0.30]. |

**Fórmulas del modelo:**

```
lambda_local     = alpha_local  * delta_visitante * gamma * mu
lambda_visitante = alpha_visitante * delta_local * mu

tau(0,0) = 1 - lambda_local * lambda_visitante * rho
tau(0,1) = 1 + lambda_local * rho
tau(1,0) = 1 + lambda_visitante * rho
tau(1,1) = 1 - rho
tau(x,y) = 1 para el resto de marcadores
```

`gamma` y `rho` **no** se ajustan automáticamente por altitud, rachas, lesiones,
rivalidad ni motivación. Esos factores, si se quieren considerar, deben:
1. reflejarse en `alpha`/`delta` mediante la **calibración manual**, o
2. registrarse en el campo `notas` del JSON como **información contextual
   opcional**, que se muestra pero **nunca modifica el cálculo**.

Puedes estimar ratings desde estadísticas históricas con:

```python
from simulador_futbol_mejorado import estimar_ratings
alpha, delta = estimar_ratings(goles_a_favor=9, goles_en_contra=3,
                               partidos=5, mu=0.65)
```

---

## 📊 Qué calcula

- **Matriz exacta** de marcadores (0-0 hasta el máximo configurado, con
  **expansión automática** si queda demasiada masa fuera y posterior normalización).
- Mercado **1X2**, **doble oportunidad** (1X, 12, X2), **ambos marcan**,
  **over/under 1.5 · 2.5 · 3.5 · 4.5**, **porterías a cero** de cada equipo,
  **xG** local/visitante/total y **top 10 marcadores** más probables.
- **Masa cubierta** por la matriz.
- **Monte Carlo opcional** con semilla reproducible (generador Mulberry32
  idéntico al del HTML) e **intervalos de confianza de Wilson al 95%**,
  comparados contra la matriz exacta.
- Reporte en consola y opción de guardar el reporte como JSON.

---

## 🔧 Ejemplo de uso con `ejemplo_partido.json`

```bash
python3 simulador_futbol_mejorado.py --config ejemplo_partido.json
```

Parámetros del ejemplo:

```json
{
  "equipo_local": "Pachuca",
  "equipo_visitante": "Querétaro",
  "alpha_local": 1.85, "delta_local": 0.70,
  "alpha_visitante": 0.70, "delta_visitante": 1.15,
  "mu": 0.65, "gamma": 1.30, "rho": -0.15,
  "max_goles": 10, "n_simulaciones": 50000, "semilla": 20260726
}
```

**Nota:** estos valores son **solo un ejemplo ilustrativo**. No representan datos
reales verificados de ningún club.

---

## 📉 Límites y supuestos del modelo

- **Suposición de Poisson:** los goles de cada equipo se modelan como un proceso
  de Poisson con media constante. En la práctica la varianza real suele ser mayor
  que la media (sobredispersión), por lo que el modelo puede subestimar las colas.
- **Dixon-Coles** corrige la independencia solo para los marcadores bajos
  (0-0, 0-1, 1-0, 1-1); para el resto asume independencia.
- **`tau` debe ser positivo.** Si con los parámetros dados algún `tau <= 0`, el
  cálculo se detiene con un mensaje claro (típicamente por ratings demasiado
  extremos o `|rho|` muy grande).
- **Parámetros no validados:** `gamma` y `rho` deben calibrarse con datos
  históricos de la liga; usarlos por defecto no garantiza precisión.
- **Sin ajustes automáticos de contexto:** rachas, lesiones, altitud, motivación,
  etc. no se incorporan automáticamente. Son campos informativos o ajustes
  manuales explícitamente marcados como **no validados**.
- **Esto NO es una apuesta:** las probabilidades son estimaciones; el azar real
  del deporte siempre puede producir resultados distintos.

---

## 🔁 Coherencia entre Python y HTML

Ambos usan las **mismas fórmulas**, la **misma normalización** de la matriz y el
**mismo generador Mulberry32** (aritmética de 32 bits replicada exactamente), de
modo que con los mismos parámetros producen **números idénticos** tanto en la
matriz exacta como en el Monte Carlo.
