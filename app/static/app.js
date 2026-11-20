/* Utilidades comunes de la interfaz: llamadas a la API con token CSRF. */
(function () {
  const meta = document.querySelector('meta[name="csrf-token"]');
  const token = meta ? meta.getAttribute("content") : "";

  async function api(ruta, opciones = {}) {
    const metodo = (opciones.method || "GET").toUpperCase();
    const cabeceras = Object.assign({ Accept: "application/json" }, opciones.headers || {});
    if (metodo !== "GET") {
      cabeceras["X-CSRF-Token"] = token;
      if (opciones.body && !cabeceras["Content-Type"]) cabeceras["Content-Type"] = "application/json";
    }
    const resp = await fetch(ruta, Object.assign({}, opciones, { headers: cabeceras, credentials: "same-origin" }));
    if (resp.status === 401) {
      window.location.href = "/login";
      throw new Error("La sesión expiró. Ingrese de nuevo.");
    }
    const cuerpo = await resp.json().catch(() => ({}));
    if (!resp.ok) throw new Error(cuerpo.error || `Error ${resp.status}`);
    return cuerpo;
  }

  const ENTIDADES = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };

  function escapar(texto) {
    return (texto == null ? "" : String(texto)).replace(/[&<>"']/g, (c) => ENTIDADES[c]);
  }

  window.SE = { api, escapar, csrf: token };

  // Comportamientos declarativos (reemplazan los onclick/onsubmit inline,
  // que la Content-Security-Policy bloquea al no usar 'unsafe-inline').
  //   form[data-confirmar="texto"]  pide confirmacion antes de enviar
  //   form[data-sin-envio]          nunca se envia (filtros manejados por JS)
  //   select[data-autoenvio]        envia su formulario al cambiar
  //   select[data-navegar][data-url] va a data-url con /0/ -> /<valor>/
  //   [data-imprimir]               abre el dialogo de impresion
  //   [data-cerrar-dialogo="id"]    cierra el <dialog> con ese id
  document.addEventListener("submit", (ev) => {
    const form = ev.target;
    if (!(form instanceof HTMLFormElement)) return;
    if (form.hasAttribute("data-sin-envio")) { ev.preventDefault(); return; }
    const texto = form.dataset.confirmar;
    if (texto && !window.confirm(texto)) ev.preventDefault();
  });

  document.addEventListener("change", (ev) => {
    const el = ev.target;
    if (!(el instanceof HTMLSelectElement)) return;
    if (el.hasAttribute("data-autoenvio") && el.form) { el.form.submit(); return; }
    if (el.hasAttribute("data-navegar") && el.dataset.url && /^\d+$/.test(el.value)) {
      window.location.assign(el.dataset.url.replace("/0/", "/" + el.value + "/"));
    }
  });

  document.addEventListener("click", (ev) => {
    const el = ev.target instanceof Element ? ev.target.closest("[data-imprimir], [data-cerrar-dialogo]") : null;
    if (!el) return;
    if (el.hasAttribute("data-imprimir")) { window.print(); return; }
    const dlg = document.getElementById(el.dataset.cerrarDialogo);
    if (dlg && typeof dlg.close === "function") dlg.close();
  });
})();
