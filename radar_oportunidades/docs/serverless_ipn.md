# IPN serverless — entrega automática de Premium por correo

Cuando no quieres tocar nada después de publicar, este pequeño endpoint
(serverless gratuito) verifica los pagos de PayPal **y** envía el correo de
acceso automáticamente. Compatible con Vercel, Netlify o Cloudflare Workers.

## Cómo funciona el flujo

1. El comprador paga el botón **paypal.me** o el **Smart Button** en
   `premium.html`.
2. PayPal envía una notificación **IPN** a tu endpoint `/api/ipn`.
3. Tu endpoint le pide a PayPal que verifique (`VERIFIED`) la notificación.
4. Si es válida y el monto es `5.00 USD` hacia tu email de negocio, tu endpoint
   envía al correo del comprador su **enlace de activación** y te notifica a ti.
5. El correo incluye `premium.html?pago=ok&email=...` que activa el acceso.

## Código (Vercel, `api/ipn.py` o `api/ipn.js`)

```python
# api/ipn.py  (Vercel serverless, Python)
import json, os, urllib.parse, urllib.request

def handler(event, context):
    body = event.get("body", "")
    # 1. Reenviar la notificación a PayPal para verificar (IPN)
    data = body + "&cmd=_notify-validate"
    req = urllib.request.Request(
        "https://www.paypal.com/cgi-bin/webscr", data=data.encode(),
        headers={"Content-Type": "application/x-www-form-urlencoded"})
    veredicto = urllib.request.urlopen(req).read().decode()
    if veredicto != "VERIFIED":
        return {"statusCode": 200, "body": "ignored"}

    params = urllib.parse.parse_qs(body)
    monto = params.get("mc_gross", [""])[0]
    moneda = params.get("mc_currency", [""])[0]
    email_comprador = params.get("payer_email", [""])[0]
    negocio = params.get("receiver_email", [""])[0]
    estado = params.get("payment_status", [""])[0]

    # 2. Reglas de negocio (ajusta monto y email)
    if (estado == "Completed" and moneda == "USD" and
            float(monto) >= 5.00 and negocio == "rdl2.job@gmail.com"):
        enviar_correo(email_comprador)   # implementa con Resend/SendGrid
        avisar_al_dueno(email_comprador, monto)
    return {"statusCode": 200, "body": "ok"}
```

### Configuración en PayPal (una vez)
1. En tu PayPal Business: **Configuración → Notificaciones → IPN**.
2. Activa IPN y pon la URL de tu endpoint (ej. `https://tu-app.vercel.app/api/ipn`).
3. En `pago_config.js` define el botón con tu `client_id` o usa paypal.me.

### Nota importante
El endpoint **no debe estar en GitHub Pages** (es estático). Usa un servicio
serverless gratuito (Vercel/Netlify/Workers). Es la única pieza "en la nube" y
es gratis en el plan base.
