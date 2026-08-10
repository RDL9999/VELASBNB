/* ===== Configuración de pago (editable) =====
 * - Si tienes una cuenta PayPal Business, crea una app en
 *   https://developer.paypal.com/dashboard/applications y pega aquí el Client ID.
 * - También puedes usar tu enlace paypal.me (funciona sin Client ID).
 * - El tutorial completo está en LEEME.md, sección "Pagos".
 */
const PAGO_CONFIG = {
  paypalClientId: "AQUI_TU_CLIENT_ID_DE_PAYPAL",
  paypalMeUrl: "https://paypal.me/MEJIARDL",
  emailNegocio: "rdl2.job@gmail.com",
  moneda: "USD",
  montoPremium: "5.00",
  tituloProducto: "Radar de Oportunidades Gratuitas - Acceso Premium",
  // Para entrega real por correo + verificación de pagos, apunta aquí una
  // función serverless (ver LEEME.md). Ejemplo: "https://tu-api.vercel.app/api/ipn"
  apiBackend: ""
};

if (typeof window !== "undefined") {
  window.PAGO_CONFIG = PAGO_CONFIG;
}
