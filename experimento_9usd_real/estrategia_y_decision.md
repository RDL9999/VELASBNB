# Estrategia y Decisión — Experimento 9 USD reales

**Fecha:** 2026-08-10 · **Objetivo:** generar ≥ 9 USD con un producto digital real, publicado de forma autónoma vía GitHub Pages, cobrando con PayPal y USDT.

---

## 1. Evaluación de ideas (obligatoria: 5 ideas)

Criterios puntuados del 1 al 5. Se exige evidencia razonable y honestidad: no se vende humo.

### Idea 1 — Simulador estadístico de fútbol (modelo Dixon-Coles) ✔ ELEGIDA
Producto de análisis de partidos: probabilidades 1X2, doble oportunidad, over/under, ambos marcan, xG, top marcadores, Monte Carlo reproducible con intervalos de Wilson.

- **Demanda real comprobable:** 5/5 — El fútbol es el deporte más seguido del mundo; el análisis de probabilidades de partidos tiene audiencia masiva (apostadores, analistas, fans con modelos propios). El modelo Dixon-Coles es un estándar académico real.
- **Tiempo de desarrollo:** 5/5 — El código ya existe, tiene 28 pruebas unitarias pasando, y la versión web funciona offline.
- **Precio realista:** 4/5 — $9 es un precio de impulso para un kit de herramientas estadísticas. Herramientas similares se venden desde $5 hasta $50.
- **Facilidad de demostrar valor:** 5/5 — Demo en vivo dentro de la propia landing page (iframe), sin registro ni descarga.
- **Funcionamiento offline:** 5/5 — HTML/JS vanilla puro, sin CDN ni servidor.
- **Publicable vía GitHub Pages:** 5/5 — Archivos estáticos, cero backend.
- **TOTAL: 29/30**

### Idea 2 — Bot de trading de criptomonedas
Existe código previo (velasBNB, velasSOL, etc.), pero:
- **Demanda real comprobable:** 2/5 — Hay demanda, pero es un mercado saturado y lleno de estafas; los compradores desconfían con razón.
- **Tiempo:** 3/5 — Requiere trabajo para empaquetarlo de forma segura y probarlo.
- **Precio realista:** 2/5 — Difícil fijar precio honesto sin prometer retornos (prohibido aquí).
- **Demostrar valor:** 2/5 — No se puede prometer rentabilidad sin ser deshonesto.
- **Offline:** 3/5 — Un bot necesita datos/mercado en vivo para demostrar algo.
- **GitHub Pages:** 2/5 — Un bot no se "demuestra" en una página estática.
- **TOTAL: 14/30** — Descartado por riesgo de falsedad y reputación.

### Idea 3 — Paquete de plantillas Excel/Sheets (finanzas personales o apuestas)
- **Demanda:** 3/5 — Genérica y saturada; diferencias mínimas frente a plantillas gratis.
- **Tiempo:** 3/5 — Construir plantillas robustas con fórmulas lleva horas.
- **Precio:** 2/5 — El mercado regala plantillas; precio máximo realista $3-7.
- **Demostrar valor:** 2/5 — Difícil de mostrar en navegador sin interactividad.
- **Offline:** 5/5.
- **GitHub Pages:** 3/5 — Se publica la doc/demo, no el producto en sí.
- **TOTAL: 18/30** — Descartado por bajo techo de precio.

### Idea 4 — Guía/libro corto "Cómo crear tu propio modelo de predicción de fútbol"
- **Demanda:** 4/5 — Hay audiencia dispuesta a pagar por conocimiento.
- **Tiempo:** 2/5 — Escribir contenido de calidad lleva muchas horas.
- **Precio:** 3/5 — E-books en nicho de nicho: $5-15.
- **Demostrar valor:** 3/5 — Solo texto, sin demo interactiva.
- **Offline:** 5/5.
- **GitHub Pages:** 4/5.
- **TOTAL: 21/30** — Buen complemento, pero no es el producto principal.

### Idea 5 — Dashboard web de probabilidades de deportes con datos en vivo
- **Demanda:** 4/5 — Atractivo, pero…
- **Tiempo:** 1/5 — Requiere API de datos externa (coste) o scraping (frágil).
- **Precio:** 3/5.
- **Demostrar valor:** 4/5.
- **Offline:** 1/5 — Sin conexión no funciona, contradice el requisito.
- **GitHub Pages:** 2/5 — CORS/API complican la publicación estática.
- **TOTAL: 15/30** — Descartado: coste de datos y dependencia de red.

---

## 2. Decisión

**Producto elegido: "Kit Analítico Dixon-Coles" — Simulador estadístico de partidos de fútbol.**

Razones:
1. Ya está construido, probado (28/28) y funciona sin servidor ni internet.
2. Valor demostrable al instante con una demo en vivo embebida en la landing.
3. Es un producto ORIGINAL y ÚTIL: aplica un modelo estadístico académico real (Dixon-Coles + Poisson) con Monte Carlo reproducible y comparación contra la matriz exacta.
4. Precio $9 = objetivo cumplido con una sola venta, precio de impulso.
5. Se publica en GitHub Pages sin backend (archivos estáticos).

### Modelo de monetización (honesto, sin APIs de pago)
- **Demo gratuita:** simulador web completo embebido en la landing (generosidad = prueba de valor).
- **Pago ($9):** el comprador paga vía PayPal (rdl2.job@gmail.com) o USDT
  (0x7DE2F24Eb14D219E7eE562b5247ff312FDD70e8c) y envía su comprobante por correo a
  rdl2.job@gmail.com; se le entrega el ZIP con la versión completa descargable:
  - Módulo Python (CLI, reportes JSON, intervalos Wilson)
  - Análisis por lotes (analizar N partidos a la vez) — nuevo
  - Calibrador de ratings desde estadísticas del equipo — nuevo
  - Versión web offline reutilizable fuera de la landing
  - Guía de calibración y uso
  - 28 pruebas unitarias incluidas
- La landing deja claro qué es gratis y qué incluye la versión de pago. La entrega es
  manual (estándar en productos indie sin pasarela), por lo que no hay automatización de
  entrega: es un modelo legítimo y transparente.

### Riesgos y mitigaciones
- **Sin automatización de entrega** → flujo manual por correo, claramente explicado en la landing.
- **El código es público en el repo** → se vende el paquete documentado + herramientas extra
  (lote, calibración) + soporte, no los bytes. La demo es gratuita por diseño.
- **Expectativas de "predicción"** → la landing y el producto insisten en que es una
  ESTIMACIÓN probabilística, no una predicción garantizada ni una recomendación de apuestas.
