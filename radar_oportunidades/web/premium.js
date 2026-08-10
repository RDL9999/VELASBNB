/* ===== Radar Premium · premium.js ===== */
(function () {
  "use strict";

  var STORAGE_PREMIUM = "radar_premium";
  var STORAGE_ALERTAS = "radar_alertas";

  function $(s) { return document.querySelector(s); }
  function config() { return window.PAGO_CONFIG || {}; }

  function activarPremium(email) {
    try {
      localStorage.setItem(STORAGE_PREMIUM, "activo");
      if (email) localStorage.setItem("radar_premium_email", email);
    } catch (e) {}
  }

  function premiumActivo() {
    try { return localStorage.getItem(STORAGE_PREMIUM) === "activo"; } catch (e) { return false; }
  }

  function estado() {
    var cont = $("#estado-premium");
    if (!cont) return;
    if (premiumActivo()) {
      cont.innerHTML =
        '<div class="alerta-activo">' +
        "<span><strong>✓ Premium activo.</strong> Ya ves todo el historial del radar.</span>" +
        '<a class="btn btn-primario" href="index.html">Volver al radar</a></div>';
    } else {
      cont.innerHTML =
        '<div class="alerta-activo" style="background:#eef2ff;border-color:#c7d2fe;color:#3730a3">' +
        "<span><strong>Modo gratis activo.</strong> Compra el acceso para desbloquear todo.</span></div>";
    }
  }

  function notificarBackend(detalles) {
    var cfg = config();
    if (!cfg.apiBackend) return Promise.resolve();
    return fetch(cfg.apiBackend, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        evento: "pago_aprobado",
        id_transaccion: detalles.id,
        estado: detalles.status,
        email: (detalles.payer && detalles.payer.email_address) || "",
        email_negocio: cfg.emailNegocio,
      }),
    });
  }

  function renderizarBotonesPayPal() {
    var cfg = config();
    var cont = $("#botones-paypal");
    if (!cont) return;
    var tieneClientId = cfg.paypalClientId && !/^AQUI_/.test(cfg.paypalClientId);

    var link = $("#link-paypal-me");
    if (link) link.href = cfg.paypalMeUrl || "https://www.paypal.me/";

    if (!tieneClientId) {
      cont.innerHTML =
        '<p class="dim">Los botones inteligentes de PayPal se activan al configurar el <b>Client ID</b> ' +
        "en <code>pago_config.js</code> (ver LEEME.md). Mientras tanto puedes pagar con el botón directo de abajo.</p>";
      return;
    }

    if (!window.paypal) {
      var s = document.createElement("script");
      s.src = "https://www.paypal.com/sdk/js?client-id=" + encodeURIComponent(cfg.paypalClientId) +
              "&currency=" + cfg.moneda;
      s.onload = function () { renderizarBotonesPayPal(); };
      s.onerror = function () {
        cont.innerHTML = '<p class="dim">No se pudo cargar el SDK de PayPal. Usa el botón directo de abajo.</p>';
      };
      document.head.appendChild(s);
      return;
    }

    try {
      window.paypal.Buttons({
        style: { color: "gold", shape: "pill", label: "paypal" },
        createOrder: function (data, actions) {
          return actions.order.create({
            purchase_units: [{
              description: cfg.tituloProducto,
              amount: { currency_code: cfg.moneda, value: cfg.montoPremium },
            }],
          });
        },
        onApprove: function (data, actions) {
          return actions.order.capture().then(function (detalles) {
            activarPremium(detalles.payer && detalles.payer.email_address);
            if (window.__notificarBackend) window.__notificarBackend(detalles).catch(function () {});
            var msg = $("#msg-alertas");
            if (msg) { msg.textContent = "✓ Pago aprobado. ¡Premium activado!"; msg.className = "msg ok"; }
            if (detalles.payer && detalles.payer.email_address) {
              $("#alerta-email").value = detalles.payer.email_address;
            }
            estado();
          });
        },
        onError: function () {
          var msg = $("#msg-alertas");
          if (msg) {
            msg.textContent = "Error en el pago. Intenta de nuevo o usa el botón directo.";
            msg.className = "msg err";
          }
        },
      }).render("#botones-paypal");
    } catch (e) {
      cont.innerHTML = '<p class="dim">No se pudieron cargar los botones de PayPal. Usa el botón directo.</p>';
    }
  }

  function manejarRetornoPago() {
    var params = new URLSearchParams(location.search);
    if (params.get("pago") === "ok" || params.get("success") === "true") {
      activarPremium(params.get("email") || "");
      var msg = $("#msg-alertas");
      if (msg) { msg.textContent = "✓ Pago confirmado. ¡Premium activado!"; msg.className = "msg ok"; }
      if (params.get("email")) $("#alerta-email").value = params.get("email");
      history.replaceState(null, "", location.pathname);
      estado();
    }
  }

  function guardarAlertas(email, palabras, categoria) {
    var msg = $("#msg-alertas");
    try {
      var datos = {
        email: email,
        palabras: palabras.split(",").map(function (p) { return p.trim(); }).filter(Boolean),
        categoria: categoria,
        activo: true,
      };
      localStorage.setItem(STORAGE_ALERTAS, JSON.stringify(datos));
      msg.textContent = "✓ Alertas guardadas. Te avisaremos cuando aparezca algo que coincida.";
      msg.className = "msg ok";
    } catch (e) {
      msg.textContent = "No se pudieron guardar las alertas.";
      msg.className = "msg err";
    }
  }

  function precargarAlertas() {
    try {
      var a = JSON.parse(localStorage.getItem(STORAGE_ALERTAS) || "null");
      if (a) {
        if (a.email) $("#alerta-email").value = a.email;
        if (a.palabras) $("#alerta-palabras").value = a.palabras.join(", ");
        if (a.categoria) $("#alerta-categoria").value = a.categoria;
      }
    } catch (e) {}
  }

  function init() {
    estado();
    precargarAlertas();
    window.__notificarBackend = notificarBackend;
    manejarRetornoPago();
    renderizarBotonesPayPal();

    var form = $("#form-alertas");
    if (form) {
      form.addEventListener("submit", function (e) {
        e.preventDefault();
        guardarAlertas(
          $("#alerta-email").value.trim(),
          $("#alerta-palabras").value.trim(),
          $("#alerta-categoria").value
        );
      });
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
