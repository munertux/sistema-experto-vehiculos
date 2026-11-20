/* Administración de usuarios: diálogo para restablecer la contraseña.
   El nombre de usuario y la ruta llegan en atributos data-* (escapados por
   Jinja) y se insertan con textContent: sin interpolación en JavaScript. */
(function () {
  document.addEventListener("click", (ev) => {
    const btn = ev.target instanceof Element ? ev.target.closest("[data-restablecer]") : null;
    if (!btn) return;
    const dlg = document.getElementById("dialogo-clave");
    const form = document.getElementById("form-clave");
    if (!dlg || !form) return;
    form.action = btn.dataset.restablecer;
    document.getElementById("clave-usuario").textContent = btn.dataset.usuario || "";
    form.reset();
    dlg.showModal();
  });
})();
