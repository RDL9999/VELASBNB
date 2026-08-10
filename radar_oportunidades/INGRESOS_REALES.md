# INGRESOS REALES — Registro en vivo del proyecto Radar de Oportunidades

> Estado: **$0.00 USD recibidos a la fecha.** El producto está construido,
> publicado y automatizado; los pagos requieren activar la cuenta PayPal
> (acción humana única) y que lleguen compradores reales.

## ⏱ Fecha del informe
**2026-08-10 · Sesión 4** (pivote: de trading BSC a producto SaaS real)

## Qué se construyó en esta sesión

| Entregable | Estado |
|-----------|--------|
| Scraper automático (Python + Playwright) con 8 fuentes | ✅ |
| Base de datos `datos/*.json` con **478 oportunidades** reales | ✅ |
| 435 cursos de Capacítate (Fundación Carlos Slim) con URL directa | ✅ |
| 26 cursos de Google Actívate / Skillshop con URL directa | ✅ |
| Landing page responsive (buscador, filtros, free/premium) | ✅ |
| Página de pago PayPal (botón + paypal.me) | ✅ (falta Client ID) |
| Automatización GitHub Actions (scrape cada 6 h + deploy) | ✅ |
| Sitio publicado en GitHub Pages | ✅ |
| Registro de ingresos (este archivo) | ✅ |

## 💰 Ingresos

| Fecha | Monto | Fuente | Transacción | Estado |
|-------|-------|--------|-------------|--------|
| — | — | — | — | Sin pagos aún |

**Total recibido: $0.00 USD**

## ¿Por qué aún no hay ingresos? (análisis honesto)

1. **Los pagos necesitan una acción humana única que el bot no puede hacer:**
   crear/verificar la cuenta **PayPal Business** a nombre del dueño
   (requiere identidad real). El código ya está listo para procesar pagos.
2. **Tráfico:** un producto no vende sin visitantes. El enlace inicial debe
   compartirse (redes, foros, grupos de estudio, WhatsApp).
3. **Conveniencia de pago:** el botón `paypal.me` funciona al instante; los
   Smart Buttons se activan pegando el Client ID (10 min).

## ✔ Acciones del dueño para activar los ingresos (una sola vez, ~15 min)

1. Activar **PayPal.Me** en tu cuenta y pegarlo en
   `radar_oportunidades/web/pago_config.js` (`paypalMeUrl`).
   → Cambio publicado automáticamente por GitHub Actions.
2. (Opcional, recomendado) Crear app en developer.paypal.com y pegar el
   **Client ID** en `pago_config.js` para los botones inteligentes.
3. (Opcional, para entrega 100% por email) Desplegar el endpoint IPN de
   `docs/serverless_ipn.md` en Vercel y activarlo en PayPal.
4. **Compartir el enlace del sitio** en: grupos de estudiantes y
   buscadores de empleo, Facebook/WhatsApp, Reddit (r/mexico, r/empleos),
   TikTok/IG con el ángulo "cursos gratis del gobierno".
   ~100-500 visitas suelen convertir 1-3 ventas a $5 USD.

## Qué funcionó y qué no

**Funcionó**
- Scraping en vivo de Capacítate (435 cursos, 100% funcional vía Playwright).
- Scraping en vivo de Skillshop/Google Actívate (26 cursos).
- Pipeline tolerante a fallos: si un portal bloquea, se usa catálogo curado.
- Modelo freemium con gating automático por fecha (últimos 3 días gratis).

**No funcionó**
- gob.mx, MéxicoX, edX y Coursera bloquean bots (Akamai/JS pesado) → se usan
  datos curados en lugar de scrape en vivo. Documentado y esperado.
- La extracción de Capacítate tardó ~12 min y requirió relanzar el navegador
  por cuelgues; resuelto con reintentos.

## Siguiente verificación
- Revisar este archivo en **7 días**. Si llegaron pagos: registrarlos aquí y
  celebrar 🎉. Si no: aumentar difusión (fase de tráfico), considerar $3 USD
  como precio de lanzamiento y añadir 2-3 fuentes más.
