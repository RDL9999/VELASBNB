# 📡 Radar de Oportunidades Gratuitas

Sistema **100% automático** que detecta y publica cursos gratuitos, becas, empleos
públicos y concursos, y las muestra en una landing page con buscador y filtros.
Modelo freemium: acceso gratuito limitado (últimos 3 días) + **Premium $5 USD**
con historial completo y alertas personalizadas. Pagos por **PayPal**.

---

## Estructura

```
radar_oportunidades/
├── scraper/
│   ├── scraper.py            # Motor principal (adaptadores + pipeline)
│   ├── seed_data.py          # Datos curados de fuentes con anti-bots
│   ├── capacitate_cache.json # IDs y duraciones de Capacítate (auto-generado)
│   ├── fuentes.json          # Configuración de las fuentes
│   ├── requirements.txt
│   └── ejecutar.sh
├── datos/                    # Generado por el scraper (JSON)
│   ├── todos.json
│   ├── cursos.json
│   ├── becas.json
│   ├── empleos.json
│   └── concursos.json
├── web/
│   ├── index.html            # Landing page principal
│   ├── premium.html          # Página de pago Premium
│   ├── premium.js
│   ├── pago_config.js        # ⬅ AQUÍ se configura PayPal
│   ├── script.js
│   └── estilo.css
├── .github/workflows/radar.yml   # Automatización CI (scrape cada 6 h + deploy)
├── publicar.sh               # Monta el sitio en public/
├── actualizar_auto.sh        # Actualización local (cron)
├── INGRESOS_REALES.md        # ⬅ Registro en vivo de ingresos
└── LEEME.md
```

## Cómo funciona

1. **Scrape automático** cada 6 horas (GitHub Actions) o por cron local:
   - **Capacítate para el Empleo** (Fundación Carlos Slim): 435+ cursos, en vivo.
   - **Google Actívate / Skillshop**: cursos gratuitos de Google, en vivo.
   - **MéxicoX, gob.mx (becas y convocatorias), Coursera, edX, LinkedIn Learning**:
     catálogo curado (sus portales usan protección anti-bots o JS pesado).
2. Limpieza, deduplicación y guardado en `datos/*.json`.
3. La landing page lee esos JSON (sin servidor) y muestra:
   - **Gratis**: oportunidades de los últimos 3 días.
   - **Premium ($5 USD)**: historial completo + alertas personalizadas.
4. El workflow publica el sitio en **GitHub Pages** automáticamente.

## Configurar pagos con PayPal (pasos para el dueño)

Necesitas una cuenta **PayPal Business** (https://www.paypal.com/business).
Son ~10 minutos, una sola vez.

### Opción A (recomendada, sin código) — botón paypal.me
1. En tu PayPal, ve a tu perfil y activa **PayPal.Me** (`paypal.me/tuusuario`).
2. Edita `web/pago_config.js`:
   ```js
   paypalMeUrl: "https://www.paypal.me/rdl2job",
   ```
3. Los compradores pagan con un clic y PayPal te deposita directo a
   `rdl2.job@gmail.com`. Al volver a la página se activa el acceso.

### Opción B — botones inteligentes (Smart Buttons)
1. Crea una app en https://developer.paypal.com/dashboard/applications
   (cuenta Business). Copia el **Client ID**.
2. Pégalo en `web/pago_config.js`:
   ```js
   paypalClientId: "AQxxxxxxxxxxxxxxxxxxxx",
   ```
3. El botón dorado de PayPal aparece solo en `premium.html`.

### Opción C — entrega automática por correo + verificación IPN (100% automático)
Para entregar el acceso por email y verificar los pagos sin intervención humana,
añade una función **serverless gratuita** (Vercel/Netlify/Cloudflare Workers) de
~15 líneas que:

1. Reciba la notificación **IPN** de PayPal en `/api/ipn`.
2. Verifique con PayPal que el pago es válido (`VERIFIED`).
3. Envíe un correo al comprador con su enlace de acceso (usando Resend/SendGrid).

El código de ejemplo está en `docs/serverless_ipn.md`.

## Actualización automática

| Mecanismo | Cuándo | Qué hace |
|-----------|--------|----------|
| GitHub Actions (`radar.yml`) | Cada 6 h | Correr scraper, commit de datos, deploy a Pages |
| Cron local (`actualizar_auto.sh`) | Cada 6-12 h | Scraper + commit si estás en git |
| Manual | `python3 scraper/scraper.py` | Scrape inmediato |

## Fuentes (todas públicas y legales)

- Capacítate para el Empleo — Fundación Carlos Slim
- Google Actívate / Skillshop
- MéxicoX — Gobierno de México
- gob.mx/becas y gob.mx/convocatorias
- Coursera (auditoría gratuita)
- edX (auditoría gratuita)
- LinkedIn Learning (prueba gratuita)

## Verificación del scraping local

```bash
cd radar_oportunidades
pip install -r scraper/requirements.txt
python -m playwright install --with-deps chromium   # 1 sola vez
python3 scraper/scraper.py
python3 -m http.server 8080 -d public               # previsualizar
# o montar el sitio:
bash publicar.sh --serve
```

## Notas éticas y legales

- Solo se publican oportunidades **gratuitas** de **portales oficiales**.
- El scraper es respetuoso: sin login, con esperas, y con fallback a datos curados
  si el portal bloquea el acceso automatizado (lo cual es legal y común).
- Este sitio no está afiliado con las plataformas listadas.
- Los datos se actualizan solos; pueden contener errores; verifica en el portal
  oficial antes de inscribirte.
