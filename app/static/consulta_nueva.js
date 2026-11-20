/* Nueva consulta: validación en vivo de códigos OBD-II y contador de
   testigos marcados. La validación del servidor sigue siendo la que manda
   (ServicioDiagnostico.normalizar_obd): aquí solo se adelanta el aviso. */
(function () {
  const PATRON = /^[PCBU][0-9A-F]{4}$/;
  const SISTEMA = { P: "Tren motriz", C: "Chasis", B: "Carrocería", U: "Red de comunicación" };
  const campo = document.getElementById("codigos_obd");
  const estado = document.getElementById("obd-estado");

  function escapar(t) {
    const d = document.createElement("div");
    d.textContent = t;
    return d.innerHTML;
  }

  function motivo(c) {
    if (!/^[PCBU]/.test(c)) return "debe empezar por P, C, B o U";
    if (c.length < 5) return "faltan caracteres";
    if (c.length > 5) return "sobran caracteres";
    return "solo se admiten dígitos y letras A–F después de la letra";
  }

  function validar() {
    const tokens = campo.value.toUpperCase().split(/[\s,;]+/).filter(Boolean);
    const vistos = new Set();
    let errores = 0;
    const chips = tokens.map((c) => {
      if (vistos.has(c)) {
        return `<span class="obd-chip repetido"><span class="mono">${escapar(c)}</span> repetido, se tomará una vez</span>`;
      }
      vistos.add(c);
      if (PATRON.test(c)) {
        const tipo = c[1] === "0" ? "genérico" : "del fabricante";
        return `<span class="obd-chip valido"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m5 12 5 5 9-10"/></svg><span class="mono">${c}</span> ${SISTEMA[c[0]]} · ${tipo}</span>`;
      }
      errores += 1;
      return `<span class="obd-chip invalido"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12M18 6 6 18"/></svg><span class="mono">${escapar(c)}</span> no válido: ${motivo(c)}</span>`;
    });
    estado.innerHTML = chips.join("");
    campo.setAttribute("aria-invalid", errores ? "true" : "false");
    campo.classList.toggle("con-error", errores > 0);
    campo.setCustomValidity(errores ? "Corrija los códigos OBD-II marcados como no válidos." : "");
  }

  if (campo && estado) {
    campo.addEventListener("input", validar);
    campo.addEventListener("blur", () => {
      campo.value = campo.value.toUpperCase();
    });
    validar();
  }

  // contador de testigos
  const cuenta = document.getElementById("testigos-cuenta");
  const casillas = document.querySelectorAll('.testigos input[type="checkbox"]');
  function contar() {
    const n = Array.from(casillas).filter((c) => c.checked).length;
    cuenta.textContent = n === 0 ? "Ningún testigo marcado." : n === 1 ? "1 testigo marcado." : `${n} testigos marcados.`;
  }
  if (cuenta && casillas.length) {
    casillas.forEach((c) => c.addEventListener("change", contar));
    contar();
  }
})();
