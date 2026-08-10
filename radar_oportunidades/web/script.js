/* ===== Radar de Oportunidades · script.js ===== */
(function () {
  "use strict";

  const DATOS = "datos/todos.json";
  const STORAGE_PREMIUM = "radar_premium";
  const STORAGE_ALERTAS = "radar_alertas";
  const VENTANA_FREE_DIAS = 3;

  let TODOS = [];
  let filtro = {
    q: "",
    tipo: "todos",
    categoria: "todas",
    certificado: "todos",
    duracionMax: 0,
  };

  const $ = (s) => document.querySelector(s);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  function esPremium() {
    try { return localStorage.getItem(STORAGE_PREMIUM) === "activo"; }
    catch (e) { return false; }
  }

  function diasDesde(fechaISO) {
    const hoy = new Date();
    hoy.setHours(0, 0, 0, 0);
    const d = new Date(fechaISO + "T00:00:00");
    return Math.round((hoy - d) / 86400000);
  }

  function enVentanaFree(item) {
    return diasDesde(item.fecha_deteccion) <= VENTANA_FREE_DIAS;
  }

  async function cargarDatos() {
    try {
      const r = await fetch(DATOS + "?v=" + Date.now());
      if (!r.ok) throw new Error("HTTP " + r.status);
      const j = await r.json();
      TODOS = j.items || [];
    } catch (e) {
      $("#carga").textContent = "No se pudo cargar el radar. Revisa la conexión o vuelve en unos minutos.";
      $("#carga").className = "vacio";
      return;
    }
    const meta = TODOS.length;
    $("#stats").textContent = meta
      ? `${meta} oportunidades gratuitas verificadas · actualizadas automáticamente`
      : "";
    renderChips();
    renderFiltros();
    render();
  }

  function renderChips() {
    const tipos = [
      ["todos", "Todos"],
      ["cursos", "Cursos"],
      ["becas", "Becas"],
      ["empleos", "Empleos"],
      ["concursos", "Concursos"],
    ];
    const c = $("#chips");
    c.innerHTML = "";
    tipos.forEach(([v, label]) => {
      const b = document.createElement("button");
      b.className = "chip" + (filtro.tipo === v ? " activo" : "");
      b.textContent = label;
      b.onclick = () => { filtro.tipo = v; renderChips(); render(); };
      c.appendChild(b);
    });
  }

  function renderFiltros() {
    const cats = new Set();
    TODOS.forEach((i) => i.categoria && cats.add(i.categoria));
    const catArr = [...cats].sort();
    const f = $("#filtros");
    f.innerHTML = `
      <span class="filtro-label">Filtros:</span>
      <select id="f-cat" title="Categoría">
        <option value="todas">Todas las categorías</option>
        ${catArr.map((c) => `<option value="${esc(c)}">${esc(c)}</option>`).join("")}
      </select>
      <select id="f-cert" title="Certificado">
        <option value="todos">Certificado: todos</option>
        <option value="si">Solo con certificado</option>
        <option value="no">Sin certificado</option>
      </select>
      <input id="f-duracion" type="number" min="1" placeholder="Duración máx (h)" style="width:150px" title="Duración máxima en horas">
    `;
    $("#f-cat").onchange = (e) => { filtro.categoria = e.target.value; render(); };
    $("#f-cert").onchange = (e) => { filtro.certificado = e.target.value; render(); };
    $("#f-duracion").oninput = (e) => { filtro.duracionMax = Number(e.target.value) || 0; render(); };
    $("#f-cat").value = filtro.categoria;
  }

  function filtrar(lista) {
    const q = filtro.q.toLowerCase();
    return lista.filter((i) => {
      if (filtro.tipo !== "todos" && i.tipo !== filtro.tipo) return false;
      if (filtro.categoria !== "todas" && i.categoria !== filtro.categoria) return false;
      if (filtro.certificado === "si" && !i.certificado) return false;
      if (filtro.certificado === "no" && i.certificado) return false;
      if (filtro.duracionMax && i.duracion_h && i.duracion_h > filtro.duracionMax) return false;
      if (q) {
        const hay = (i.titulo + " " + (i.descripcion || "") + " " + (i.fuente || "") + " " + (i.categoria || "")).toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });
  }

  function coincidenAlertas(item) {
    try {
      const a = JSON.parse(localStorage.getItem(STORAGE_ALERTAS) || "null");
      if (!a || !a.palabras) return false;
      const texto = (item.titulo + " " + (item.descripcion || "") + " " + (item.categoria || "")).toLowerCase();
      return a.palabras.some((p) => p && texto.includes(p.toLowerCase()));
    } catch (e) { return false; }
  }

  const TIPO_TAG = {
    curso: "tag-curso", beca: "tag-beca", empleo: "tag-empleo", concurso: "tag-concurso",
  };
  const TIPO_LABEL = { curso: "Curso", beca: "Beca", empleo: "Empleo", concurso: "Concurso" };

  function tarjeta(item, bloqueada) {
    const et = `<span class="tag ${TIPO_TAG[item.tipo] || "tag-curso"}">${TIPO_LABEL[item.tipo] || item.tipo}</span>` +
      (item.certificado ? `<span class="tag tag-cert">Certificado</span>` : "") +
      (diasDesde(item.fecha_deteccion) <= 1 ? `<span class="tag tag-nuevo">Nuevo</span>` : "");
    const meta = [
      item.fuente ? `<span>🏛 ${esc(item.fuente)}</span>` : "",
      item.duracion_h ? `<span>⏱ ${item.duracion_h} h</span>` : "",
      item.pais ? `<span>🌎 ${esc(item.pais)}</span>` : "",
      item.categoria ? `<span>🏷 ${esc(item.categoria)}</span>` : "",
    ].join("");
    const alerta = coincidenAlertas(item) ? `<span class="tag tag-nuevo">🔔 alerta</span>` : "";
    const enlace = bloqueada
      ? ""
      : `<a class="ver" href="${esc(item.url)}" target="_blank" rel="noopener noreferrer">Ver oportunidad →</a>`;
    return `
      <article class="tarjeta${bloqueada ? " premium-bloqueada" : ""}">
        <div class="etiquetas">${et}${alerta}</div>
        <h3>${esc(item.titulo)}</h3>
        <p>${esc(item.descripcion || "")}</p>
        <div class="meta">${meta}</div>
        ${enlace}
      </article>`;
  }

  function tarjetaUpsell(nBloqueadas) {
    return `
      <article class="tarjeta upsell-card">
        <div class="etiquetas"><span class="tag tag-beca">Premium</span></div>
        <h3>🔒 Hay ${nBloqueadas} más oportunidades ocultas</h3>
        <p>Con Radar Premium desbloqueas todo el historial y activas alertas por correo cuando aparezca tu tema.</p>
        <a class="btn btn-cta" href="premium.html">Desbloquear todo por $5 USD</a>
      </article>`;
  }

  function render() {
    const gratis = !esPremium();
    let lista = filtrar(TODOS);

    if (gratis) {
      lista = lista.filter(enVentanaFree);
    }

    const grid = $("#grid");
    grid.innerHTML = "";
    if (!lista.length) {
      grid.innerHTML = `<div class="vacio">Sin resultados${gratis ? " en los últimos 3 días. Prueba otra búsqueda o hazte Premium para ver todo el historial." : "."}</div>`;
    } else {
      lista.forEach((i) => { grid.insertAdjacentHTML("beforeend", tarjeta(i, false)); });
    }

    // Teaser bloqueado para usuarios gratis
    if (gratis && TODOS.length) {
      const bloqueadas = TODOS.filter((i) => !enVentanaFree(i)).length;
      if (bloqueadas > 0) {
        const teaser = TODOS.filter((i) => !enVentanaFree(i)).slice(0, 1);
        if (teaser.length) {
          grid.insertAdjacentHTML("beforeend", tarjeta(teaser[0], true));
        }
        grid.insertAdjacentHTML("beforeend", tarjetaUpsell(bloqueadas));
      }
    }

    const totalVistas = gratis ? lista.length : filtrar(TODOS).length;
    $("#contador").textContent = gratis
      ? `${totalVistas} recientes (modo gratis) · historial completo con Premium`
      : `${totalVistas} oportunidades`;
  }

  // Buscador
  let tBusqueda;
  $("#busqueda").addEventListener("input", (e) => {
    clearTimeout(tBusqueda);
    tBusqueda = setTimeout(() => { filtro.q = e.target.value.trim(); render(); }, 200);
  });
  $("#btn-buscar").addEventListener("click", () => {
    filtro.q = $("#busqueda").value.trim();
    render();
  });

  // Modal aviso
  $("#enlace-avios") && ($("#enlace-aviso").onclick = (e) => { e.preventDefault(); $("#modal-aviso").classList.remove("oculto"); });
  $("#cerrar-aviso") && ($("#cerrar-aviso").onclick = () => $("#modal-aviso").classList.add("oculto"));
  $("#modal-aviso") && ($("#modal-aviso").addEventListener("click", (e) => { if (e.target.id === "modal-aviso") $("#modal-aviso").classList.add("oculto"); }));

  cargarDatos();
})();
