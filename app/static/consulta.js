/* Pantalla de consulta: preguntas sucesivas con la escala de certeza,
   explicación «¿por qué?», panel lateral de hipótesis en evaluación y
   presentación del resultado (top 5 de hipótesis con explicación «¿cómo?»).
   Es tolerante: si el servicio no envía por_que, certeza, como o
   hipotesis_en_curso, la parte correspondiente simplemente no se muestra. */
(function () {
  const { api, escapar } = window.SE;
  const el = (id) => document.getElementById(id);
  const datos = JSON.parse(el("datos-consulta").textContent);
  const idAtencion = datos.id_atencion;
  const PREGUNTAS_ESTIMADAS = 15;
  const CERTEZA = { si: "1,00", probablemente_si: "0,75", no_se: "0,50", probablemente_no: "0,25", no: "0,00" };
  const reducido = window.matchMedia("(prefers-reduced-motion: reduce)");
  const sinMovimiento = () => reducido.matches;
  const espera = (ms) => new Promise((r) => setTimeout(r, sinMovimiento() ? 0 : ms));
  let numero = datos.n || 1;
  let ocupado = false;

  // ------------------------------------------------------- niveles
  const NIVELES = {
    "nivel-atencion-preventiva": "Atención preventiva",
    "nivel-revision-proxima": "Revisión próxima",
    "nivel-revision-prioritaria": "Revisión prioritaria",
    "nivel-no-debe-seguir-usandose": "No debe seguir usándose",
  };
  const ICONOS_NIVEL = {
    "nivel-atencion-preventiva": '<path d="M12 3 5 6v5c0 4.4 3 8.2 7 9.5 4-1.3 7-5.1 7-9.5V6z"/><path d="m9 12 2 2 4-4"/>',
    "nivel-revision-proxima": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    "nivel-revision-prioritaria": '<path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/><path d="M12 9v4M12 17h.01"/>',
    "nivel-no-debe-seguir-usandose": '<path d="M8 2h8l6 6v8l-6 6H8l-6-6V8z"/><path d="M8 12h8"/>',
  };
  const ICONO_INFO = '<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8h.01"/>';

  function claseNivel(texto) {
    let base = String(texto || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
    base = base.replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
    if (base.startsWith("no-debe-seguir-usandose")) base = "no-debe-seguir-usandose";
    return base ? "nivel-" + base : "";
  }

  function insigniaNivel(h) {
    const clase = h.nivel_clase || claseNivel(h.nivel_atencion);
    const texto = h.nivel_texto || NIVELES[clase] || h.nivel_atencion || "";
    if (!texto) return "";
    const icono = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONOS_NIVEL[clase] || ICONO_INFO}</svg>`;
    return `<span class="nivel con-icono ${escapar(clase)}">${icono}${escapar(texto)}</span>`;
  }

  // ------------------------------------------------------- formatos
  function certezaPct(v) {
    if (v === undefined || v === null || v === "") return null;
    let n = Number(v);
    if (!Number.isFinite(n)) return null;
    if (n <= 1) n *= 100;
    return Math.max(0, Math.min(100, n));
  }
  const fmtCerteza = (p) => Math.round(p) + " %";
  const fmtProb = (p) => Number(p || 0).toFixed(1).replace(".", ",") + " %";
  const fmtDec = (v) => Number(v).toFixed(2).replace(".", ",");
  function hechoLegible(c) {
    const t = String(c || "").replace(/[_\s]+/g, " ").trim().toLowerCase();
    return t ? t[0].toUpperCase() + t.slice(1) : "";
  }

  // ------------------------------------------------------- utilidades
  function mostrarError(msg) {
    const caja = el("error-consulta");
    caja.textContent = msg;
    caja.classList.toggle("oculto", !msg);
  }

  function progreso() {
    const respondidas = numero - 1;
    el("texto-progreso").innerHTML = `Pregunta <strong>${numero}</strong>`;
    el("texto-respondidas").textContent =
      respondidas === 1 ? "1 respuesta registrada" : `${respondidas} respuestas registradas`;
    el("num-pregunta").textContent = `Pregunta ${numero}`;
    el("barra-progreso").style.width = Math.min(95, (numero / PREGUNTAS_ESTIMADAS) * 100) + "%";
  }

  function bloquear(valor) {
    ocupado = valor;
    document.querySelectorAll("#opciones-respuesta button, #btn-finalizar").forEach((b) => (b.disabled = valor));
    el("tarjeta-pregunta").setAttribute("aria-busy", valor ? "true" : "false");
  }

  // ------------------------------------------------------- ¿por qué?
  const btnPorQue = el("btn-por-que");
  const textoPorQue = el("texto-por-que");
  function plegarPorQue() {
    btnPorQue.setAttribute("aria-expanded", "false");
    textoPorQue.hidden = true;
  }
  btnPorQue.onclick = () => {
    const abrir = btnPorQue.getAttribute("aria-expanded") !== "true";
    btnPorQue.setAttribute("aria-expanded", String(abrir));
    textoPorQue.hidden = !abrir;
  };

  // ------------------------------------------------------- pregunta
  function pintarPregunta(pregunta) {
    el("texto-pregunta").textContent = pregunta.enunciado;
    const porQue = (pregunta.por_que || "").trim();
    el("caja-por-que").classList.toggle("oculto", !porQue);
    textoPorQue.textContent = porQue;
    plegarPorQue();
    const cont = el("opciones-respuesta");
    cont.innerHTML = "";
    (pregunta.opciones || []).forEach((op) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "opcion-" + op.clave;
      btn.innerHTML = `${escapar(op.etiqueta)}<small>certeza ${CERTEZA[op.clave] || ""}</small>`;
      btn.onclick = () => responder(pregunta.id_pregunta, op.clave, btn);
      cont.appendChild(btn);
    });
    progreso();
  }

  async function mostrarPregunta(pregunta, animar) {
    const tarjeta = el("tarjeta-pregunta");
    if (animar && !sinMovimiento()) {
      tarjeta.classList.add("saliendo");
      await espera(170);
    }
    pintarPregunta(pregunta);
    if (animar && !sinMovimiento()) {
      tarjeta.classList.remove("saliendo");
      tarjeta.classList.add("entrando");
      void tarjeta.offsetWidth; // reinicia la transición
      tarjeta.classList.remove("entrando");
    }
    if (animar) el("texto-pregunta").focus({ preventScroll: true });
  }

  // ------------------------------------------------------- hipótesis en evaluación
  const panelHip = el("panel-hipotesis");
  const listaHip = el("hip-lista");
  const previas = new Map(); // nombre -> certeza (0..100)

  function actualizarHipotesis(lista) {
    if (lista === undefined || lista === null) return; // campo no publicado
    panelHip.hidden = false;
    el("pantalla-pregunta").classList.remove("sin-lateral");
    const top = lista.slice(0, 5);
    el("hip-cuenta").textContent = top.length ? `Top ${top.length}` : "";

    if (!top.length) {
      listaHip.innerHTML = "";
      el("hip-estado").textContent = "Aún no hay evidencia suficiente. Responda la pregunta para empezar a evaluar hipótesis.";
      return;
    }

    // FLIP: posiciones antes del cambio
    const antes = new Map();
    listaHip.querySelectorAll("li").forEach((li) => antes.set(li.dataset.clave, li.getBoundingClientRect().top));
    const existentes = new Map();
    listaHip.querySelectorAll("li").forEach((li) => existentes.set(li.dataset.clave, li));
    const nuevas = [];

    top.forEach((h, i) => {
      const clave = String(h.nombre || "");
      const pct = certezaPct(h.certeza) ?? 0;
      const previa = previas.get(clave);
      let li = existentes.get(clave);
      const esNueva = !li;
      if (esNueva) {
        li = document.createElement("li");
        li.dataset.clave = clave;
        li.innerHTML = `
          <div class="hip-fila"><span class="hip-pos"></span><span class="hip-nombre"></span><span class="hip-valor"></span></div>
          <div class="hip-barra"><i style="width:0%"></i></div>
          <div class="hip-pie"><span class="hip-nivel"></span><span class="hip-cambio"></span></div>`;
        nuevas.push(li);
      }
      existentes.delete(clave);
      li.className = "hip-item " + (h.nivel_clase || claseNivel(h.nivel_atencion)) + (i === 0 ? " principal" : "");
      li.querySelector(".hip-pos").textContent = i + 1;
      li.querySelector(".hip-nombre").textContent = clave;
      li.querySelector(".hip-valor").textContent = fmtCerteza(pct);
      li.querySelector(".hip-nivel").innerHTML = insigniaNivel(h);
      const cambio = li.querySelector(".hip-cambio");
      if (previa === undefined) {
        cambio.textContent = previas.size ? "Nueva" : "";
        cambio.className = "hip-cambio" + (previas.size ? " nueva" : "");
      } else {
        const d = Math.round(pct - previa);
        cambio.textContent = d > 0 ? `▲ sube ${d} pts` : d < 0 ? `▼ baja ${-d} pts` : "sin cambio";
        cambio.className = "hip-cambio " + (d > 0 ? "sube" : d < 0 ? "baja" : "igual");
      }
      li.setAttribute("aria-label", `${i + 1}. ${clave}: certeza ${fmtCerteza(pct)}`);
      listaHip.appendChild(li); // reordena
      const barra = li.querySelector(".hip-barra i");
      if (esNueva) requestAnimationFrame(() => requestAnimationFrame(() => (barra.style.width = pct + "%")));
      else barra.style.width = pct + "%";
      previas.set(clave, pct);
    });
    existentes.forEach((li, clave) => {
      li.remove();
      previas.delete(clave);
    });

    if (!sinMovimiento()) {
      listaHip.querySelectorAll("li").forEach((li) => {
        const a = antes.get(li.dataset.clave);
        if (a === undefined) {
          li.animate([{ opacity: 0, transform: "translateY(6px)" }, { opacity: 1, transform: "none" }],
            { duration: 260, easing: "ease-out" });
          return;
        }
        const dy = a - li.getBoundingClientRect().top;
        if (dy) li.animate([{ transform: `translateY(${dy}px)` }, { transform: "none" }], { duration: 320, easing: "ease-out" });
      });
    }

    const p = top[0];
    el("hip-estado").textContent =
      `Tras ${numero - 1 === 1 ? "1 respuesta" : (numero - 1) + " respuestas"}, la hipótesis principal es ` +
      `${p.nombre} con certeza ${fmtCerteza(certezaPct(p.certeza) ?? 0)}.`;
  }

  // ------------------------------------------------------- flujo
  async function responder(idPregunta, clave, boton) {
    if (ocupado) return;
    bloquear(true);
    if (boton) boton.classList.add("elegida");
    mostrarError("");
    try {
      const r = await api(`/api/atenciones/${idAtencion}/respuestas`, {
        method: "POST",
        body: JSON.stringify({ id_pregunta: idPregunta, respuesta: clave }),
      });
      if (r.estado === "finalizado") {
        mostrarResultado(r.resultado || []);
      } else {
        numero += 1;
        actualizarHipotesis(r.hipotesis_en_curso);
        await mostrarPregunta(r.pregunta, true);
      }
    } catch (e) {
      if (boton) boton.classList.remove("elegida");
      mostrarError(e.message);
    } finally {
      bloquear(false);
    }
  }

  async function finalizar(sinConfirmar) {
    if (ocupado) return;
    if (sinConfirmar !== true && !confirm("¿Terminar la consulta con las respuestas dadas hasta ahora?")) return;
    bloquear(true);
    try {
      const r = await api(`/api/atenciones/${idAtencion}/finalizar`, { method: "POST", body: "{}" });
      mostrarResultado(r.resultado || []);
    } catch (e) {
      mostrarError(e.message);
    } finally {
      bloquear(false);
    }
  }

  // ------------------------------------------------------- resultado
  function pasosComo(como) {
    if (!como) return [];
    const lista = Array.isArray(como) ? como : [como];
    return lista
      .map((p) => {
        if (p && typeof p === "object") {
          const arr = (v) => (Array.isArray(v) ? v : v ? String(v).split(/[,;]\s*/) : []).filter((x) => String(x).trim());
          return { regla: p.regla || p.codigo || "", premisas: arr(p.premisas), evidencia: p.evidencia, hechos: arr(p.hechos), texto: p.texto || "" };
        }
        return String(p || "").trim() ? { regla: "", premisas: [], evidencia: null, hechos: [], texto: String(p) } : null;
      })
      .filter(Boolean);
  }

  function lineaTiempo(h, pasos, cp) {
    const items = pasos.map((p, i) => {
      const estructurado = p.regla || p.premisas.length || p.hechos.length;
      if (!estructurado) return `<li class="lt-paso"><span class="lt-marca" aria-hidden="true"></span><p class="lt-texto">${escapar(p.texto)}</p></li>`;
      const ev = p.evidencia !== undefined && p.evidencia !== null && p.evidencia !== "" ?
        `<span class="lt-evidencia" title="Factor de certeza aportado por la regla">evidencia ${fmtDec(p.evidencia)}</span>` : "";
      const premisas = p.premisas.length ?
        `<div class="lt-bloque"><span class="lt-etq">Si</span><ul class="lt-premisas">${p.premisas.map((x) => `<li>${escapar(x)}</li>`).join("")}</ul></div>` : "";
      const hechos = p.hechos.length ?
        `<div class="lt-bloque"><span class="lt-etq">Entonces</span><span class="lt-hechos">${p.hechos.map((x) => `<span class="lt-hecho" title="${escapar(x)}">${escapar(hechoLegible(x))}</span>`).join("")}</span></div>` : "";
      return `<li class="lt-paso"><span class="lt-marca" aria-hidden="true"></span>
        <div class="lt-cabeza">${p.regla ? `<span class="codigo-regla">${escapar(p.regla)}</span>` : ""}
          <span class="lt-titulo">Paso ${i + 1}${p.regla ? `: se activa la regla ${escapar(p.regla)}` : ""}</span>${ev}</div>
        ${premisas}${hechos}${p.texto ? `<p class="lt-texto">${escapar(p.texto)}</p>` : ""}</li>`;
    });
    items.push(`<li class="lt-paso lt-conclusion"><span class="lt-marca" aria-hidden="true"></span>
      <div class="lt-cabeza"><span class="lt-titulo">Conclusión: ${escapar(h.nombre)}</span>${cp !== null ? `<span class="lt-evidencia">certeza ${fmtCerteza(cp)}</span>` : ""}</div></li>`);
    return `<ol class="linea-tiempo">${items.join("")}</ol>`;
  }

  function tarjeta(h) {
    const clase = h.nivel_clase || claseNivel(h.nivel_atencion);
    const cp = certezaPct(h.certeza);
    const prob = Number(h.probabilidad) || 0;
    const pasos = pasosComo(h.como);
    const reglas = (h.reglas_activadas || []).map((c) => `<span class="codigo-regla">${escapar(c)}</span>`).join("")
      || '<span class="texto-3">—</span>';
    const idTit = `hip-${escapar(h.id_hipotesis)}-${escapar(h.posicion)}`;
    const art = document.createElement("article");
    art.className = "hipotesis-tarjeta " + clase;
    art.setAttribute("aria-labelledby", idTit);
    art.innerHTML = `
      <header class="ht-cabeza">
        <span class="ht-posicion" aria-label="Posición ${escapar(h.posicion)}">${escapar(h.posicion)}</span>
        <h3 id="${idTit}">${escapar(h.nombre)}</h3>
        ${insigniaNivel(h)}
      </header>
      <div class="ht-metricas">
        ${cp !== null ? `<div class="metrica">
          <div class="metrica-fila"><span class="metrica-etq">Certeza</span><strong class="metrica-valor">${fmtCerteza(cp)}</strong></div>
          <div class="medidor" role="img" aria-label="Certeza ${fmtCerteza(cp)}"><i data-ancho="${cp}"></i></div>
          <p class="metrica-ayuda">Qué tan respaldada está por la evidencia (0–100 %).</p></div>` : ""}
        <div class="metrica ${cp !== null ? "secundaria" : ""}">
          <div class="metrica-fila"><span class="metrica-etq">Probabilidad relativa</span><strong class="metrica-valor">${fmtProb(prob)}</strong></div>
          <div class="medidor relativo" role="img" aria-label="Probabilidad relativa ${fmtProb(prob)}"><i data-ancho="${Math.min(100, prob)}"></i></div>
          <p class="metrica-ayuda">Participación frente a las demás hipótesis.</p></div>
      </div>
      ${h.recomendacion ? `<p class="recomendacion"><strong>Recomendación:</strong> ${escapar(h.recomendacion)}</p>` : ""}
      <div class="resultado-meta"><span>Reglas activadas: ${reglas}</span></div>
      ${pasos.length ? `<details class="como">
        <summary><svg class="como-flecha" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m9 6 6 6-6 6"/></svg>¿Cómo llegó a esta conclusión? <span class="texto-3">(${pasos.length} ${pasos.length === 1 ? "paso" : "pasos"})</span></summary>
        ${lineaTiempo(h, pasos, cp)}</details>` : ""}
      <div class="resultado-acciones"></div>`;
    return art;
  }

  function mostrarResultado(hipotesis) {
    el("pantalla-pregunta").classList.add("oculto");
    el("pantalla-resultado").classList.remove("oculto");
    el("advertencia").classList.toggle("oculto", !hipotesis.some((h) => h.advertencia));

    const cont = el("resultados");
    cont.innerHTML = "";
    if (!hipotesis.length) {
      cont.innerHTML = '<p class="vacio">Con las respuestas dadas no fue posible identificar una hipótesis de falla.</p>';
      return;
    }
    hipotesis.forEach((h) => {
      const art = tarjeta(h);
      const acciones = art.querySelector(".resultado-acciones");
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "boton chico exito";
      btn.textContent = "Confirmar falla real";
      btn.onclick = () => confirmar(h, acciones);
      acciones.appendChild(btn);
      cont.appendChild(art);
    });
    // barras: crecen desde 0 (sin animación si se pidió movimiento reducido)
    requestAnimationFrame(() => requestAnimationFrame(() =>
      cont.querySelectorAll(".medidor i").forEach((i) => (i.style.width = i.dataset.ancho + "%"))));
    window.scrollTo({ top: 0, behavior: sinMovimiento() ? "auto" : "smooth" });
    el("titulo-resultado").focus({ preventScroll: true });
  }

  async function confirmar(h, acciones) {
    const observacion = prompt(`Confirmar «${h.nombre}» como la falla real.\nObservación del técnico (opcional):`, "");
    if (observacion === null) return;
    try {
      await api(`/api/atenciones/${idAtencion}/confirmar`, {
        method: "POST",
        body: JSON.stringify({ id_hipotesis: h.id_hipotesis, observacion }),
      });
      document.querySelectorAll(".resultado-acciones").forEach((a) => (a.innerHTML = ""));
      acciones.innerHTML = '<span class="confirmada">✓ Falla real confirmada</span>';
    } catch (e) {
      alert("No fue posible confirmar la falla: " + e.message);
    }
  }

  // ------------------------------------------------------- arranque
  el("btn-finalizar").onclick = () => finalizar(false);
  if (datos.pregunta) {
    pintarPregunta(datos.pregunta);
    actualizarHipotesis(datos.hipotesis_en_curso);
  } else {
    finalizar(true);
  }
})();
