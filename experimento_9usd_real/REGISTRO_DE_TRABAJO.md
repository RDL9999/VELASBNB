# Registro de trabajo — Experimento 9 USD reales

## Contexto
- **Fecha:** 2026-08-10 · **Entorno:** GitHub Codespaces (Linux, Node 24, Python 3.12, gh autenticado como RDL9999).
- **Objetivo:** generar ≥ 9 USD con un producto digital real publicado en GitHub Pages, cobrando por PayPal y USDT.

## Hallazgos iniciales
- El repositorio VELASBNB ya contenía `simulador_futbol_mejorado.py` (modelo Dixon-Coles),
  su versión web `simulador_futbol_mejorado.html` y `test_simulador_futbol.py`.
- Verificado: **28/28 pruebas unitarias pasan**. JS del HTML válido (node --check).
- GitHub Pages NO estaba activo en el repositorio (API devolvía 404 antes de configurarlo).

## Evaluación de ideas
Se evaluaron 5 ideas (documentadas en `estrategia_y_decision.md`). Ganadora:
**Kit Analítico Dixon-Coles** (29/30) por estar ya construido y probado, valor
demostrable con demo en vivo, precio $9 y publicación estática sin backend.

## Trabajo realizado (en orden)
1. Redactada `estrategia_y_decision.md` (evaluación de 5 ideas + decisión + riesgos).
2. Empaquetado del producto en `producto/`:
   - Copiados `simulador_futbol_mejorado.py`, `.html` y `test_simulador_futbol.py`.
   - Creados `analisis_lote.py` (jornadas completas) y `calibrar_equipo.py` (ratings).
   - Creados `ejemplo_partido.json` y `jornada_ejemplo.json`.
   - Escritas `guia_de_uso.md` y `README.md`.
   - Generado `kit_dixon_coles.zip` (28 KB) para entrega.
   - Pruebas: 28/28 OK · analisis_lote y calibrar_equipo ejecutados OK.
3. Construida `landing/index.html`: hero, beneficios, demo en vivo (iframe del
   simulador), precios ($9 / $15), pago PayPal + USDT, flujo de entrega, FAQ,
   aviso legal y footer. Responsive y sin dependencias externas.
4. Creado `publicar.sh` (automatiza git init/commit/push/Pages) y `LEEME_publicar.md`.
5. Creado `posts_x.md` (5 posts listos).
6. Creados `INGRESOS_REALES.md` (cero inventado) y este registro.
7. Habilitación de GitHub Pages vía CLI, commit y push (ver log del repo).

## Evidencia de publicación
- Repositorio: https://github.com/RDL9999/VELASBNB (rama main)
- Landing: https://RDL9999.github.io/VELASBNB/landing/
- Demo del producto: https://RDL9999.github.io/VELASBNB/simulador_futbol_mejorado.html

## Pendientes / seguimiento
- Monitorear `INGRESOS_REALES.md` y el buzón rdl2.job@gmail.com para entregas.
- Si llega un pago: verificar comprobante, enviar ZIP (Estándar) o análisis (PRO) y
  actualizar `INGRESOS_REALES.md` con el monto real.
