/* Árbol de decisión del motor de inferencia — visualización con D3 v7.
 *
 * Datos: app/static/arbol_datos.json (scripts/generar_arbol_decision.py),
 * o window.ARBOL_DATOS si la página los incrusta.
 * Contenedor: <div id="arbol" data-src="/static/arbol_datos.json" data-area="9"></div>
 *
 * Nodo pregunta  -> píldora con rombo (síntoma que pregunta el motor).
 * Rama           -> respuesta Sí (verde) / No (gris); grosor = caminos que lleva.
 * Hoja           -> tarjeta con hipótesis principal, certeza y nivel de atención.
 *
 * API pública: window.ArbolDecision = { seleccionarArea, expandirTodo,
 *   contraerTodo, ajustar, buscar, recorrido, paso, exportarSVG, exportarPNG,
 *   modoExportacion, datos }
 */
(function () {
  "use strict";

  const D = window.d3;
  const ANCHO_PREG = 280;
  const ANCHO_HOJA = 310;
  const COL = 400;            // distancia horizontal entre niveles
  const SEP = 22;             // separación vertical mínima entre hojas
  const PAD = 12;
  const LINEA = 20;           // alto de línea del texto de 15-16 px
  const FUENTE = '"Segoe UI", system-ui, -apple-system, "Helvetica Neue", Arial, sans-serif';

  const NIVELES = {
    "atencion-preventiva": { texto: "Atención preventiva", icono: "info" },
    "revision-proxima": { texto: "Revisión próxima", icono: "reloj" },
    "revision-prioritaria": { texto: "Revisión prioritaria", icono: "alerta" },
    "no-debe-seguir-usandose": { texto: "No debe seguir usándose", icono: "alto" },
    "sin-informacion": { texto: "Sin información", icono: "nada" },
  };

  // ------------------------------------------------------------ utilidades
  const lienzoMedida = document.createElement("canvas").getContext("2d");
  function anchoTexto(txt, px, peso) {
    lienzoMedida.font = `${peso || 400} ${px}px ${FUENTE}`;
    return lienzoMedida.measureText(txt).width;
  }
  function envolver(txt, anchoMax, px, peso, maxLineas) {
    const palabras = String(txt || "").split(/\s+/).filter(Boolean);
    const lineas = [];
    let actual = "";
    for (const p of palabras) {
      const prueba = actual ? actual + " " + p : p;
      if (anchoTexto(prueba, px, peso) <= anchoMax || !actual) actual = prueba;
      else { lineas.push(actual); actual = p; }
    }
    if (actual) lineas.push(actual);
    if (maxLineas && lineas.length > maxLineas) {
      const corte = lineas.slice(0, maxLineas);
      let ult = corte[maxLineas - 1];
      while (ult.length > 1 && anchoTexto(ult + "…", px, peso) > anchoMax) ult = ult.slice(0, -1);
      corte[maxLineas - 1] = ult.replace(/[\s,;]+$/, "") + "…";
      return corte;
    }
    return lineas;
  }
  function el(tag, attrs, hijos) {
    const n = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (k === "texto") n.textContent = v;
      else if (k.startsWith("on")) n.addEventListener(k.slice(2), v);
      else if (v !== undefined && v !== null && v !== false) n.setAttribute(k, v === true ? "" : v);
    }
    (hijos || []).forEach((h) => h && n.appendChild(typeof h === "string" ? document.createTextNode(h) : h));
    return n;
  }
  const pct = (v) => (Math.round(v * 10) / 10).toLocaleString("es-CO", { maximumFractionDigits: 1 }) + " %";
  const etiquetaRama = (r) => (r === "si" ? "Sí" : "No");

  function iconoNivel(g, tipo, r) {
    // g: selección d3 <g> ya posicionada en el centro del ícono
    g.selectAll("*").remove();
    if (tipo === "info") {
      g.append("circle").attr("r", r).attr("class", "ar-color-nivel");
      g.append("rect").attr("x", -1.6).attr("y", -1).attr("width", 3.2).attr("height", r * 0.95).attr("class", "ar-icono-blanco");
      g.append("circle").attr("cy", -r * 0.5).attr("r", 1.9).attr("class", "ar-icono-blanco");
    } else if (tipo === "reloj") {
      g.append("circle").attr("r", r).attr("class", "ar-color-nivel");
      g.append("path").attr("d", `M0 ${-r * 0.6} V0 L${r * 0.45} ${r * 0.35}`).attr("class", "ar-icono-blanco")
        .style("fill", "none").attr("stroke-width", 2.2).attr("stroke-linecap", "round");
    } else if (tipo === "alerta") {
      const h = r * 1.9;
      g.append("path").attr("d", `M0 ${-h * 0.58} L${h * 0.58} ${h * 0.42} L${-h * 0.58} ${h * 0.42} Z`)
        .attr("class", "ar-color-nivel").attr("stroke-linejoin", "round");
      g.append("rect").attr("x", -1.5).attr("y", -h * 0.25).attr("width", 3).attr("height", h * 0.36).attr("class", "ar-icono-blanco");
      g.append("circle").attr("cy", h * 0.26).attr("r", 1.7).attr("class", "ar-icono-blanco");
    } else if (tipo === "alto") {
      const pts = D.range(8).map((i) => {
        const a = Math.PI / 8 + (i * Math.PI) / 4;
        return [Math.cos(a) * r * 1.08, Math.sin(a) * r * 1.08];
      });
      g.append("path").attr("d", "M" + pts.map((p) => p.join(" ")).join(" L") + " Z").attr("class", "ar-color-nivel");
      g.append("rect").attr("x", -r * 0.55).attr("y", -1.6).attr("width", r * 1.1).attr("height", 3.2).attr("class", "ar-icono-blanco");
    } else {
      g.append("circle").attr("r", r).attr("class", "ar-color-nivel");
      g.append("rect").attr("x", -r * 0.5).attr("y", -1.4).attr("width", r).attr("height", 2.8).attr("class", "ar-icono-blanco");
    }
  }

  function svgIconoLeyenda(clase, tipo) {
    const svg = D.create("svg").attr("width", 22).attr("height", 22).attr("viewBox", "-11 -11 22 22").attr("aria-hidden", "true");
    const g = svg.append("g").attr("class", "nivel-" + clase);
    iconoNivel(g, tipo, 8.5);
    return svg.node();
  }

  // ------------------------------------------------------------- estado
  const E = {
    datos: null, area: null, raiz: null, svg: null, zoom: null, capa: null,
    fijados: null, recorrido: null, pasoActual: -1, temporizador: null, nombresArea: {},
  };

  // --------------------------------------------------------- jerarquía
  function crearJerarquia(area) {
    const raiz = D.hierarchy(area.raiz, (n) => (n.tipo === "pregunta" ? n.hijos.map((h) => Object.assign(h.nodo, { _rama: h.rama })) : null));
    let id = 0;
    raiz.each((d) => {
      d.uid = `a${area.id}-n${id++}`;
      d.rama = d.data._rama || null;
      medirNodo(d);
    });
    return raiz;
  }

  function medirNodo(d) {
    const n = d.data;
    if (n.tipo === "pregunta") {
      d.ancho = ANCHO_PREG;
      const cab = n.contraste ? `Contraste · ${E.nombresArea[n.id_area] || "otra área"}` : n.es_entrada ? "Pregunta de entrada" : "Pregunta";
      d.cabeza = envolver(cab, ANCHO_PREG - 52 - PAD, 14, 600, 2);
      d.lineas = envolver(n.sintoma, ANCHO_PREG - 52 - PAD, 15, 400, 4);
      d.alto = PAD + 20 + (d.cabeza.length - 1) * 18 + d.lineas.length * LINEA + PAD;
    } else {
      d.ancho = ANCHO_HOJA;
      const titulo = n.con_evidencia ? n.hipotesis : "Sin falla identificada";
      d.lineas = envolver(titulo, ANCHO_HOJA - 24 - PAD, 16, 700, 4);
      d.lineasSig = n.motivo === "profundidad" ? envolver("Seguiría con: " + (n.siguiente_pregunta || ""), ANCHO_HOJA - 24 - PAD, 14, 400, 2) : [];
      d.alto = PAD + 22 + d.lineas.length * LINEA + 12 + 24 + 26 + d.lineasSig.length * 19 + PAD - 4;
    }
  }

  // Disposición compacta: hojas apiladas según su alto real; cada padre
  // queda centrado entre su primer y último hijo visibles.
  function disponer(raiz) {
    let y = 0;
    (function rec(d) {
      d.y = d.depth * COL;
      if (d.children && d.children.length) {
        d.children.forEach(rec);
        const a = d.children[0], b = d.children[d.children.length - 1];
        d.x = (a.x + b.x) / 2;
      } else {
        d.x = y + d.alto / 2;
        y += d.alto + SEP;
      }
    })(raiz);
  }

  // --------------------------------------------------------- construcción
  function montar(contenedor, datos) {
    E.datos = datos;
    datos.areas.forEach((a) => { E.nombresArea[a.id] = a.nombre; });
    contenedor.innerHTML = "";

    const selArea = el("select", { id: "ar-area", "aria-label": "Área de diagnóstico", onchange: (e) => seleccionarArea(+e.target.value) },
      datos.areas.map((a) => el("option", { value: a.id, texto: a.nombre })));
    const lista = el("datalist", { id: "ar-lista-hipotesis" });
    const buscador = el("input", {
      id: "ar-buscar", type: "search", list: "ar-lista-hipotesis", placeholder: "Escriba una hipótesis…", autocomplete: "off",
      onchange: (e) => buscar(e.target.value), onkeydown: (e) => { if (e.key === "Enter") buscar(e.target.value); },
    });
    const b = (txt, fn, extra) => el("button", Object.assign({ type: "button", class: "ar-boton", texto: txt, onclick: fn }, extra || {}));

    const barra = el("div", { class: "ar-barra" }, [
      el("label", { class: "ar-campo" }, ["Área", selArea]),
      el("label", { class: "ar-campo" }, ["Buscar hipótesis", buscador, lista]),
      el("div", { class: "ar-botones" }, [
        b("Expandir todo", () => expandirTodo()),
        b("Contraer", () => contraerTodo()),
        b("Ajustar vista", () => ajustar(true)),
        b("Limpiar resaltado", () => limpiarFijado()),
        b("SVG", () => descargar("svg"), { title: "Descargar el árbol del área como SVG" }),
        b("PNG", () => descargar("png"), { title: "Descargar el árbol del área como PNG (2×)" }),
        b("Tema", () => alternarTema(), { title: "Alternar modo claro / oscuro" }),
      ]),
    ]);
    const mensaje = el("div", { class: "ar-mensaje", id: "ar-mensaje", "aria-live": "polite" });
    const stats = el("div", { class: "ar-stats", id: "ar-stats" });

    const lienzo = el("div", { class: "ar-lienzo" });
    const selCamino = el("select", { id: "ar-camino", "aria-label": "Camino a recorrer", onchange: (e) => recorrido(+e.target.value) });
    const panelTour = el("section", { class: "ar-panel", "aria-label": "Recorrido guiado" }, [
      el("h3", { texto: "Recorrido guiado" }),
      el("label", { class: "ar-campo" }, ["Camino", selCamino]),
      el("div", { class: "ar-botones", style: "margin:10px 0 8px" }, [
        b("◀ Anterior", () => paso(-1), { id: "ar-ant" }),
        b("Siguiente ▶", () => paso(1), { id: "ar-sig", class: "ar-boton ar-primario" }),
        b("Reproducir", () => reproducir(), { id: "ar-play" }),
        b("Reiniciar", () => recorrido(E.recorridoIdx || 0)),
      ]),
      el("div", { class: "ar-paso", id: "ar-paso", "aria-live": "polite" }),
    ]);
    const panelDetalle = el("section", { class: "ar-panel ar-detalle", id: "ar-detalle", "aria-label": "Detalle del nodo" }, [
      el("h3", { texto: "Detalle" }),
      el("p", { class: "ar-vacio", texto: "Pase el mouse sobre un nodo para resaltar su camino; haga clic en una pregunta para contraerla o expandirla y en una hoja para ver su diagnóstico completo." }),
    ]);
    const lateral = el("div", { class: "ar-lateral" }, [panelTour, panelDetalle]);
    const cuerpo = el("div", { class: "ar-cuerpo" }, [lienzo, lateral]);

    const leyenda = el("div", { class: "ar-leyenda", "aria-label": "Leyenda" });
    contenedor.appendChild(el("div", { class: "ar-app" }, [barra, mensaje, stats, cuerpo, leyenda]));
    construirLeyenda(leyenda);

    // SVG con zoom/pan
    E.svg = D.select(lienzo).append("svg").attr("class", "ar-svg").attr("role", "img")
      .attr("aria-label", "Árbol de decisión del área seleccionada");
    E.capa = E.svg.append("g").attr("class", "ar-capa");
    E.capa.append("g").attr("class", "ar-enlaces");
    E.capa.append("g").attr("class", "ar-etiquetas");
    E.capa.append("g").attr("class", "ar-nodos");
    E.zoom = D.zoom().scaleExtent([0.15, 2.5]).on("zoom", (ev) => E.capa.attr("transform", ev.transform));
    E.svg.call(E.zoom).on("dblclick.zoom", null);

    // lista de hipótesis (todas las áreas) para el buscador
    const vistas = new Map();
    datos.areas.forEach((a) => recorrerHojas(a.raiz, (h) => {
      if (h.con_evidencia && !vistas.has(h.hipotesis)) vistas.set(h.hipotesis, a.nombre);
    }));
    [...vistas.entries()].sort((x, y) => x[0].localeCompare(y[0], "es")).forEach(([h, a]) =>
      lista.appendChild(el("option", { value: h, label: a })));

    const params = new URLSearchParams(location.search);
    const inicial = +(params.get("area") || contenedor.dataset.area || datos.areas[0].id);
    seleccionarArea(datos.areas.some((a) => a.id === inicial) ? inicial : datos.areas[0].id);
    if (params.get("tema")) document.documentElement.dataset.theme = params.get("tema") === "oscuro" ? "dark" : "light";
  }

  function construirLeyenda(c) {
    const muestraLinea = (clase, ancho) => {
      const s = D.create("svg").attr("width", 40).attr("height", 14).attr("aria-hidden", "true");
      s.append("line").attr("x1", 2).attr("x2", 38).attr("y1", 7).attr("y2", 7)
        .attr("class", "ar-enlace " + clase).attr("stroke-width", ancho);
      return s.node();
    };
    const muestraPreg = (clase) => {
      const s = D.create("svg").attr("width", 34).attr("height", 22).attr("aria-hidden", "true");
      const g = s.append("g").attr("class", "ar-pregunta " + clase);
      g.append("rect").attr("x", 1).attr("y", 2).attr("width", 32).attr("height", 18).attr("rx", 9).attr("class", "ar-forma");
      g.append("path").attr("d", "M11 4 L18 11 L11 18 L4 11 Z").attr("class", "ar-rombo");
      return s.node();
    };
    const item = (graf, txt) => el("span", { class: "ar-item" }, [graf, txt]);
    c.appendChild(el("strong", { texto: "Leyenda:" }));
    c.appendChild(item(muestraPreg("entrada"), "Pregunta de entrada"));
    c.appendChild(item(muestraPreg(""), "Pregunta del motor"));
    c.appendChild(item(muestraPreg("contraste"), "Contraste con otra área"));
    c.appendChild(item(muestraLinea("si", 4), "Sí / Probablemente sí"));
    c.appendChild(item(muestraLinea("no", 4), "No / Probablemente no"));
    c.appendChild(el("span", { class: "ar-item", texto: "Grosor = caminos que pasan por la rama" }));
    Object.entries(NIVELES).forEach(([k, v]) => c.appendChild(item(svgIconoLeyenda(k, v.icono), v.texto)));
    const corte = D.create("svg").attr("width", 34).attr("height", 22).attr("aria-hidden", "true");
    corte.append("g").attr("class", "ar-hoja corte").append("rect").attr("x", 1).attr("y", 2).attr("width", 32)
      .attr("height", 18).attr("rx", 4).attr("class", "ar-forma");
    c.appendChild(item(corte.node(), "Vista cortada (el motor seguiría preguntando)"));
  }

  function recorrerHojas(n, fn) {
    if (n.tipo === "diagnostico") fn(n);
    else n.hijos.forEach((h) => recorrerHojas(h.nodo, fn));
  }

  // ------------------------------------------------------------ áreas
  function seleccionarArea(id) {
    detenerReproduccion();
    const area = E.datos.areas.find((a) => a.id === +id);
    if (!area) return;
    E.area = area;
    E.raiz = crearJerarquia(area);
    E.raiz.descendants().forEach((d) => { d._children = null; });
    E.fijados = null;
    const sel = document.getElementById("ar-area");
    if (sel) sel.value = area.id;
    pintarStats();
    llenarCaminos();
    render(false);
    ajustar(false, false);
    recorrido(E.recorridoIdx, true);
    mensaje("");
  }

  function pintarStats() {
    const s = E.area.estadisticas;
    const c = document.getElementById("ar-stats");
    c.innerHTML = "";
    const chip = (v, t) => c.appendChild(el("span", { class: "ar-stat" }, [el("b", { texto: String(v) }), t]));
    chip(s.preguntas, "nodos de pregunta");
    chip(s.hojas, "hojas (diagnósticos)");
    chip(s.profundidad_media.toLocaleString("es-CO"), "preguntas por camino (media)");
    chip(s.profundidad_max, "profundidad máxima");
    chip(s.hipotesis_distintas, "hipótesis alcanzables");
    if (s.hojas_por_corte) chip(s.hojas_por_corte, `caminos cortados en ${E.datos.profundidad_max} preguntas`);
  }

  function hojasDe(raiz) {
    // incluye hojas ocultas en nodos contraídos
    const salida = [];
    (function rec(d) {
      const hijos = d.children || d._children;
      if (!hijos) salida.push(d); else hijos.forEach(rec);
    })(raiz);
    return salida;
  }

  function llenarCaminos() {
    const sel = document.getElementById("ar-camino");
    sel.innerHTML = "";
    const hojas = hojasDe(E.raiz);
    // orden: diagnósticos reales (por parada) primero, luego por profundidad descendente
    E.hojasTour = hojas.slice().sort((a, b) => {
      const ra = a.data.motivo === "profundidad" ? 1 : 0, rb = b.data.motivo === "profundidad" ? 1 : 0;
      return ra - rb || (b.data.con_evidencia - a.data.con_evidencia) || b.depth - a.depth || a.x - b.x;
    });
    E.hojasTour.forEach((h, i) => {
      const ruta = h.ancestors().reverse().slice(1).map((d) => etiquetaRama(d.rama)).join("→");
      const titulo = h.data.con_evidencia ? h.data.hipotesis : "Sin falla identificada";
      const extra = h.data.motivo === "profundidad" ? " (cortado)" : "";
      sel.appendChild(el("option", { value: i, texto: `${ruta} ⇒ ${titulo} · ${pct(h.data.probabilidad)}${extra}` }));
    });
    // camino inicial didáctico: diagnóstico real, mezcla de Sí y No, 3-5 preguntas
    const idx = E.hojasTour.findIndex((h) => {
      const ramas = new Set(h.ancestors().slice(0, -1).map((d) => d.rama));
      return h.data.motivo !== "profundidad" && h.data.con_evidencia && ramas.size === 2 && h.depth >= 3 && h.depth <= 5;
    });
    E.recorridoIdx = Math.max(0, idx);
  }

  // ------------------------------------------------------------ render
  function render(animar) {
    const raiz = E.raiz;
    disponer(raiz);
    const nodos = raiz.descendants();
    const enlaces = raiz.links();
    const maxCaminos = raiz.data.caminos || 1;
    const t = E.svg.transition().duration(animar ? 350 : 0);

    // enlaces
    const camino = (l) => {
      const x0 = l.source.y + l.source.ancho, y0 = l.source.x;
      const x1 = l.target.y, y1 = l.target.x;
      const m = (x0 + x1) / 2;
      return `M${x0},${y0} C${m},${y0} ${m},${y1} ${x1},${y1}`;
    };
    E.capa.select(".ar-enlaces").selectAll("path").data(enlaces, (l) => l.target.uid)
      .join((ent) => ent.append("path").attr("d", camino).style("opacity", 0))
      .attr("class", (l) => `ar-enlace ${l.target.rama}`)
      .attr("data-uid", (l) => l.target.uid)
      .attr("stroke-width", (l) => 2 + 9 * Math.sqrt((l.target.data.caminos || 1) / maxCaminos))
      .transition(t).style("opacity", 1).attr("d", camino);

    // etiquetas de rama
    E.capa.select(".ar-etiquetas").selectAll("g.ar-etiqueta-rama").data(enlaces, (l) => l.target.uid)
      .join((ent) => {
        const g = ent.append("g");
        g.append("rect").attr("rx", 11).attr("height", 22).attr("y", -11);
        g.append("text").attr("dy", "0.35em").attr("text-anchor", "middle");
        return g;
      })
      .attr("class", (l) => `ar-etiqueta-rama ${l.target.rama}`)
      .attr("data-uid", (l) => l.target.uid)
      .each(function (l) {
        const g = D.select(this);
        const txt = etiquetaRama(l.target.rama) + (l.target.data.caminos > 1 ? ` · ${l.target.data.caminos}` : "");
        const w = anchoTexto(txt, 14, 700) + 18;
        g.select("rect").attr("x", -w / 2).attr("width", w);
        g.select("text").text(txt);
        g.attr("aria-label", `Rama ${etiquetaRama(l.target.rama)}, ${l.target.data.caminos} camino(s)`);
      })
      .transition(t)
      .attr("transform", (l) => {
        const x0 = l.source.y + l.source.ancho, x1 = l.target.y;
        return `translate(${(x0 + x1) / 2},${(l.source.x + l.target.x) / 2})`;
      });

    // nodos
    const sel = E.capa.select(".ar-nodos").selectAll("g.ar-nodo").data(nodos, (d) => d.uid)
      .join((ent) => ent.append("g").attr("transform", (d) => `translate(${d.y},${d.x - d.alto / 2})`).style("opacity", 0)
        .each(function (d) { dibujarNodo(D.select(this), d); }))
      .attr("data-uid", (d) => d.uid);
    sel.each(function (d) { actualizarPlegado(D.select(this), d); });
    sel.on("mouseenter", (ev, d) => resaltarCamino(d, false))
      .on("mouseleave", () => restaurarResaltado())
      .on("click", (ev, d) => clicNodo(d))
      .on("keydown", (ev, d) => { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); clicNodo(d); } });
    sel.transition(t).style("opacity", 1).attr("transform", (d) => `translate(${d.y},${d.x - d.alto / 2})`);
    restaurarResaltado();
  }

  function dibujarNodo(g, d) {
    const n = d.data;
    g.attr("tabindex", 0);
    if (n.tipo === "pregunta") {
      const clases = ["ar-nodo", "ar-pregunta"];
      if (n.es_entrada && !n.contraste) clases.push("entrada");
      if (n.contraste) clases.push("contraste");
      g.attr("class", clases.join(" "));
      g.attr("aria-label", `Pregunta: ${n.texto}`);
      g.append("title").text(n.texto);
      g.append("rect").attr("class", "ar-forma").attr("width", d.ancho).attr("height", d.alto).attr("rx", Math.min(22, d.alto / 2));
      // rombo con el número de pregunta del camino
      const cy = d.alto / 2;
      g.append("path").attr("class", "ar-rombo").attr("d", `M24 ${cy - 17} L41 ${cy} L24 ${cy + 17} L7 ${cy} Z`);
      g.append("text").attr("class", "ar-rombo-texto").attr("x", 24).attr("y", cy).attr("dy", "0.35em")
        .attr("text-anchor", "middle").text(String(n.profundidad + 1));
      const tc = g.append("text").attr("class", "ar-cabeza").attr("x", 50).attr("y", PAD + 14);
      d.cabeza.forEach((l, i) => tc.append("tspan").attr("x", 50).attr("dy", i ? 18 : 0).text(l));
      const tx = g.append("text").attr("class", "ar-cuerpo-texto").attr("x", 50)
        .attr("y", PAD + 20 + 15 + (d.cabeza.length - 1) * 18);
      d.lineas.forEach((l, i) => tx.append("tspan").attr("x", 50).attr("dy", i ? LINEA : 0).text(l));
      const pg = g.append("g").attr("class", "ar-plegado").attr("transform", `translate(${d.ancho},${cy})`).style("display", "none");
      pg.append("circle").attr("r", 14);
      pg.append("text").attr("text-anchor", "middle").attr("dy", "0.35em");
    } else {
      const corte = n.motivo === "profundidad";
      const nivel = n.con_evidencia ? (n.nivel || "sin-informacion") : "sin-informacion";
      g.attr("class", `ar-nodo ar-hoja nivel-${nivel}${corte ? " corte" : ""}${n.con_evidencia ? "" : " sin-evidencia"}`);
      const info = NIVELES[nivel] || NIVELES["sin-informacion"];
      g.attr("aria-label", `Diagnóstico: ${n.hipotesis}, certeza ${pct(n.probabilidad)}, ${info.texto}`);
      g.append("title").text(n.motivo_texto);
      g.append("rect").attr("class", "ar-forma").attr("width", d.ancho).attr("height", d.alto).attr("rx", 10);
      g.append("rect").attr("class", "ar-franja ar-color-nivel").attr("width", 8).attr("height", d.alto - 2).attr("x", 1).attr("y", 1).attr("rx", 5);
      const x = 22;
      let y = PAD + 14;
      g.append("text").attr("class", "ar-meta").attr("x", x).attr("y", y)
        .text(corte ? `Vista cortada · líder tras ${n.profundidad} respuestas` : n.con_evidencia ? "Diagnóstico" : "Diagnóstico · sin evidencia");
      y += 8;
      const tt = g.append("text").attr("class", "ar-titulo").attr("x", x).attr("y", y + 16);
      d.lineas.forEach((l, i) => tt.append("tspan").attr("x", x).attr("dy", i ? LINEA : 0).text(l));
      y += d.lineas.length * LINEA + 12;
      // certeza
      const anchoBarra = 110;
      g.append("rect").attr("class", "ar-barra-fondo").attr("x", x).attr("y", y + 2).attr("width", anchoBarra).attr("height", 10).attr("rx", 5);
      g.append("rect").attr("class", "ar-color-nivel").attr("x", x).attr("y", y + 2).attr("rx", 5).attr("height", 10)
        .attr("width", Math.max(4, anchoBarra * Math.min(1, (n.probabilidad || 0) / 100)));
      g.append("text").attr("class", "ar-meta").attr("x", x + anchoBarra + 10).attr("y", y + 12)
        .text(`Certeza ${pct(n.probabilidad || 0)}`);
      y += 24;
      // nivel de atención: ícono + texto
      const ic = g.append("g").attr("transform", `translate(${x + 9},${y + 9})`);
      iconoNivel(ic, info.icono, 9);
      g.append("text").attr("class", "ar-nivel-texto ar-texto-nivel").attr("x", x + 26).attr("y", y + 14)
        .text(n.con_evidencia ? info.texto : "Sin hipótesis con evidencia");
      y += 26;
      if (d.lineasSig.length) {
        const ts = g.append("text").attr("class", "ar-meta").attr("x", x).attr("y", y + 14);
        d.lineasSig.forEach((l, i) => ts.append("tspan").attr("x", x).attr("dy", i ? 19 : 0).text(l));
      }
    }
  }

  function actualizarPlegado(g, d) {
    if (d.data.tipo !== "pregunta") return;
    const pg = g.select(".ar-plegado");
    if (d._children) {
      pg.style("display", null).select("text").text("+" + d.data.caminos);
      g.attr("aria-expanded", "false");
    } else {
      pg.style("display", "none");
      g.attr("aria-expanded", "true");
    }
  }

  // ------------------------------------------------------- interacción
  function clicNodo(d) {
    if (d.data.tipo === "pregunta") {
      if (d.children) { d._children = d.children; d.children = null; }
      else if (d._children) { d.children = d._children; d._children = null; }
      render(true);
    }
    mostrarDetalle(d);
  }

  function rutaDe(d) { return d.ancestors().reverse(); }

  function marcar(nodos, actual) {
    const ids = new Set(nodos.map((d) => d.uid));
    E.svg.classed("atenuar", ids.size > 0);
    E.capa.selectAll(".ar-nodo").classed("resaltado", (d) => ids.has(d.uid)).classed("actual", (d) => actual && d.uid === actual.uid);
    E.capa.selectAll(".ar-enlace").classed("resaltado", (l) => ids.has(l.target.uid) && ids.has(l.source.uid));
    E.capa.selectAll(".ar-etiqueta-rama").classed("resaltado", (l) => ids.has(l.target.uid) && ids.has(l.source.uid));
  }

  function resaltarCamino(d) {
    // desde la raíz hasta el nodo; si es pregunta, también sus descendientes visibles
    const nodos = rutaDe(d);
    marcar(nodos, d);
  }

  function restaurarResaltado() {
    if (E.fijados) marcar(E.fijados.nodos, E.fijados.actual);
    else marcar([], null);
  }

  function limpiarFijado() {
    detenerReproduccion();
    E.fijados = null;
    E.pasoActual = -1;
    restaurarResaltado();
    pintarPaso();
    mensaje("");
  }

  function expandirAncestros(d) {
    let cambio = false;
    // los ancestros pueden estar contraídos: se busca desde la raíz por _children
    d.ancestors().forEach((a) => {
      if (a._children) { a.children = a._children; a._children = null; cambio = true; }
    });
    return cambio;
  }

  function expandirTodo(sinAnimar) {
    (function rec(d) {
      if (d._children) { d.children = d._children; d._children = null; }
      (d.children || []).forEach(rec);
    })(E.raiz);
    render(!sinAnimar);
  }

  function contraerTodo() {
    E.raiz.each((d) => {
      if (d.depth >= 2 && d.children) { d._children = d.children; d.children = null; }
    });
    render(true);
    ajustar(true);
  }

  function mostrarDetalle(d) {
    const c = document.getElementById("ar-detalle");
    const n = d.data;
    c.innerHTML = "";
    const filas = [];
    const fila = (k, v) => { if (v !== undefined && v !== null && v !== "") filas.push(el("dt", { texto: k }), el("dd", { texto: String(v) })); };
    const ruta = rutaDe(d).slice(1).map((x) => etiquetaRama(x.rama)).join(" → ") || "(raíz)";
    if (n.tipo === "pregunta") {
      c.appendChild(el("h3", { texto: "Pregunta" }));
      c.appendChild(el("p", { texto: n.texto }));
      fila("Área", E.nombresArea[n.id_area]);
      fila("Tipo", n.contraste ? "Contraste con otra área" : n.es_entrada ? "Pregunta de entrada" : "Pregunta específica");
      fila("Camino", ruta);
      fila("Caminos que pasan", n.caminos);
    } else {
      c.appendChild(el("h3", { texto: n.con_evidencia ? n.hipotesis : "Sin falla identificada" }));
      fila("Certeza", pct(n.probabilidad));
      fila("Nivel de atención", n.con_evidencia ? n.nivel_atencion : "—");
      fila("Recomendación", n.con_evidencia ? n.recomendacion : "Ninguna hipótesis recibió evidencia positiva.");
      fila("Reglas activadas", (n.reglas || []).join(", ") || "—");
      fila("Síntoma confirmado", n.sintoma_confirmado ? "Sí" : "No");
      if (n.alternativas && n.alternativas.length) fila("Alternativas", n.alternativas.map((a) => `${a.hipotesis} (${pct(a.probabilidad)})`).join("; "));
      fila("Camino", ruta);
      fila("Por qué termina", n.motivo_texto + (n.siguiente_pregunta ? `. Siguiente pregunta: ${n.siguiente_pregunta}` : ""));
    }
    c.appendChild(el("dl", {}, filas));
  }

  // partes: texto o [texto] (las listas se muestran en negrita)
  function mensaje(...partes) {
    const m = document.getElementById("ar-mensaje");
    if (!m) return;
    m.textContent = "";
    partes.forEach((p) => {
      if (p === undefined || p === null || p === "") return;
      m.appendChild(Array.isArray(p) ? el("strong", { texto: p.join("") }) : document.createTextNode(String(p)));
    });
  }

  // ------------------------------------------------------------- buscar
  function buscar(texto) {
    const q = String(texto || "").trim().toLowerCase();
    if (!q) return;
    const normal = (s) => s.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "");
    const qn = normal(q);
    // área actual primero; si no está, se busca en las demás
    const areas = [E.area].concat(E.datos.areas.filter((a) => a !== E.area));
    for (const area of areas) {
      let encontrada = null;
      recorrerHojas(area.raiz, (h) => { if (!encontrada && h.con_evidencia && normal(h.hipotesis).includes(qn)) encontrada = h.hipotesis; });
      if (!encontrada) continue;
      if (area !== E.area) seleccionarArea(area.id);
      const hojas = hojasDe(E.raiz).filter((h) => h.data.con_evidencia && h.data.hipotesis === encontrada);
      hojas.sort((a, b) => (a.data.motivo === "profundidad") - (b.data.motivo === "profundidad") || a.depth - b.depth);
      hojas.forEach(expandirAncestros);
      render(true);
      const nodos = new Set();
      hojas.forEach((h) => rutaDe(h).forEach((x) => nodos.add(x)));
      E.fijados = { nodos: [...nodos], actual: hojas[0] };
      restaurarResaltado();
      centrarEn(hojas[0], 0.9);
      mostrarDetalle(hojas[0]);
      const reales = hojas.filter((h) => h.data.motivo !== "profundidad").length;
      mensaje([String(hojas.length)], ` camino(s) llegan a «${encontrada}» en ${area.nombre}` +
        (reales < hojas.length ? ` (${hojas.length - reales} en vista cortada)` : "") + ". Camino más corto: ",
        [rutaDe(hojas[0]).slice(1).map((x) => etiquetaRama(x.rama)).join(" → ")], ".");
      return true;
    }
    mensaje(`No se encontró ninguna hipótesis que contenga «${texto}».`);
    return false;
  }

  // ---------------------------------------------------- recorrido guiado
  function recorrido(idx, silencioso) {
    detenerReproduccion();
    const hojas = E.hojasTour || [];
    if (!hojas.length) return;
    E.recorridoIdx = Math.max(0, Math.min(hojas.length - 1, +idx || 0));
    const sel = document.getElementById("ar-camino");
    if (sel) sel.value = E.recorridoIdx;
    E.recorrido = rutaDe(hojas[E.recorridoIdx]);
    E.pasoActual = -1;
    if (silencioso) { E.fijados = null; restaurarResaltado(); pintarPaso(); return; }
    paso(1);
  }

  function paso(delta) {
    if (!E.recorrido) return;
    const n = E.recorrido.length;
    E.pasoActual = Math.max(0, Math.min(n - 1, E.pasoActual + delta));
    const hoja = E.recorrido[n - 1];
    if (expandirAncestros(hoja)) render(true);
    const visibles = E.recorrido.slice(0, E.pasoActual + 1);
    const actual = visibles[visibles.length - 1];
    E.fijados = { nodos: visibles, actual };
    restaurarResaltado();
    centrarEn(actual, Math.max(1, D.zoomTransform(E.svg.node()).k));
    mostrarDetalle(actual);
    pintarPaso();
    return E.pasoActual;
  }

  function pintarPaso() {
    const c = document.getElementById("ar-paso");
    if (!c) return;
    c.innerHTML = "";
    const ant = document.getElementById("ar-ant"), sig = document.getElementById("ar-sig");
    if (!E.recorrido || E.pasoActual < 0) {
      c.appendChild(el("p", { class: "ar-vacio", texto: "Elija un camino y pulse «Siguiente» para ver, pregunta por pregunta, cómo el motor llega al diagnóstico." }));
      if (ant) ant.disabled = true;
      if (sig) sig.disabled = !E.recorrido;
      return;
    }
    const n = E.recorrido.length;
    const d = E.recorrido[E.pasoActual];
    if (ant) ant.disabled = E.pasoActual <= 0;
    if (sig) sig.disabled = E.pasoActual >= n - 1;
    c.appendChild(el("div", { class: "ar-paso-num", texto: `Paso ${E.pasoActual + 1} de ${n}` }));
    if (d.data.tipo === "pregunta") {
      c.appendChild(el("p", {}, [el("strong", { texto: "El sistema pregunta: " }), d.data.texto]));
      const sigNodo = E.recorrido[E.pasoActual + 1];
      if (sigNodo) {
        c.appendChild(el("p", {}, ["Respuesta: ", el("span", { class: "ar-resp " + sigNodo.rama, texto: sigNodo.rama === "si" ? "Sí" : "No" })]));
      }
    } else {
      const h = d.data;
      c.appendChild(el("p", {}, [el("strong", { texto: h.motivo === "profundidad" ? "Vista cortada. Hipótesis líder: " : "Diagnóstico: " }),
        h.con_evidencia ? h.hipotesis : "Sin falla identificada"]));
      c.appendChild(el("p", { texto: `Certeza ${pct(h.probabilidad)} · ${h.con_evidencia ? h.nivel_atencion : "sin nivel"}` }));
      c.appendChild(el("p", { class: "ar-vacio", texto: h.motivo_texto + "." }));
    }
  }

  function reproducir() {
    if (E.temporizador) { detenerReproduccion(); return; }
    if (!E.recorrido) return;
    if (E.pasoActual >= E.recorrido.length - 1) E.pasoActual = -1;
    const btn = document.getElementById("ar-play");
    if (btn) btn.textContent = "Pausa";
    paso(1);
    E.temporizador = setInterval(() => {
      if (E.pasoActual >= E.recorrido.length - 1) { detenerReproduccion(); return; }
      paso(1);
    }, 2200);
  }
  function detenerReproduccion() {
    if (E.temporizador) clearInterval(E.temporizador);
    E.temporizador = null;
    const btn = document.getElementById("ar-play");
    if (btn) btn.textContent = "Reproducir";
  }

  // --------------------------------------------------------------- vista
  function limites() {
    const nodos = E.raiz.descendants();
    const x0 = D.min(nodos, (d) => d.y), x1 = D.max(nodos, (d) => d.y + d.ancho);
    const y0 = D.min(nodos, (d) => d.x - d.alto / 2), y1 = D.max(nodos, (d) => d.x + d.alto / 2);
    return { x0, y0, x1, y1, w: x1 - x0, h: y1 - y0 };
  }

  // completo=true: todo el árbol en pantalla; si no, escala legible (≥0.8)
  // con la raíz a la izquierda y centrada en vertical.
  function ajustar(animar, completo) {
    if (completo === undefined) completo = true;
    const caja = E.svg.node().getBoundingClientRect();
    const W = caja.width || 1200, H = caja.height || 700;
    const b = limites();
    const margen = 30;
    let k = Math.min((W - 2 * margen) / b.w, (H - 2 * margen) / b.h);
    k = Math.max(completo ? 0.15 : 1, Math.min(1.1, k));
    const tx = margen - b.x0 * k + Math.max(0, (W - 2 * margen - b.w * k) / 2);
    let ty = (H - b.h * k) / 2 - b.y0 * k;
    if (b.h * k > H) ty = H / 2 - E.raiz.x * k; // árbol muy alto: raíz centrada
    const tr = D.zoomIdentity.translate(tx, ty).scale(k);
    (animar ? E.svg.transition().duration(450) : E.svg).call(E.zoom.transform, tr);
  }

  function centrarEn(d, k) {
    if (!d) return;
    const caja = E.svg.node().getBoundingClientRect();
    const W = caja.width || 1200, H = caja.height || 700;
    k = k || D.zoomTransform(E.svg.node()).k;
    const cx = d.y + d.ancho / 2, cy = d.x;
    const tr = D.zoomIdentity.translate(W / 2 - cx * k, H / 2 - cy * k).scale(k);
    E.svg.transition().duration(500).call(E.zoom.transform, tr);
  }

  function alternarTema() {
    const raiz = document.documentElement;
    const oscuro = raiz.dataset.theme ? raiz.dataset.theme === "dark" : window.matchMedia("(prefers-color-scheme: dark)").matches;
    raiz.dataset.theme = oscuro ? "light" : "dark";
  }

  // ----------------------------------------------------------- exportar
  const PROPS = ["fill", "stroke", "stroke-width", "stroke-dasharray", "stroke-linecap", "stroke-linejoin", "opacity",
    "font-family", "font-size", "font-weight", "text-anchor", "display"];

  function exportarSVG(opciones) {
    const op = Object.assign({ titulo: true }, opciones || {});
    const original = E.svg.node();
    const b = limites();
    const m = 28;
    const cabecera = op.titulo ? 64 : 0;
    const W = Math.ceil(b.w + 2 * m), H = Math.ceil(b.h + 2 * m + cabecera);
    const clon = original.cloneNode(true);
    // estilos computados en línea (el SVG queda autónomo)
    const origEls = original.querySelectorAll("*");
    const clonEls = clon.querySelectorAll("*");
    origEls.forEach((o, i) => {
      const cs = getComputedStyle(o);
      const c = clonEls[i];
      PROPS.forEach((p) => {
        const v = cs.getPropertyValue(p);
        if (v && v !== "normal") c.style.setProperty(p, v);
      });
      c.style.removeProperty("transition");
    });
    clon.removeAttribute("style");
    clon.setAttribute("xmlns", "http://www.w3.org/2000/svg");
    clon.setAttribute("width", W);
    clon.setAttribute("height", H);
    clon.setAttribute("viewBox", `0 0 ${W} ${H}`);
    clon.querySelector(".ar-capa").setAttribute("transform", `translate(${m - b.x0},${m + cabecera - b.y0})`);
    const fondo = getComputedStyle(document.documentElement).getPropertyValue("--ar-lienzo").trim() || "#ffffff";
    const texto = getComputedStyle(document.documentElement).getPropertyValue("--ar-texto").trim() || "#1f2328";
    const texto2 = getComputedStyle(document.documentElement).getPropertyValue("--ar-texto-2").trim() || "#57606a";
    const ns = "http://www.w3.org/2000/svg";
    const rect = document.createElementNS(ns, "rect");
    rect.setAttribute("width", W); rect.setAttribute("height", H); rect.setAttribute("fill", fondo);
    clon.insertBefore(rect, clon.firstChild);
    if (op.titulo) {
      const t1 = document.createElementNS(ns, "text");
      t1.setAttribute("x", m); t1.setAttribute("y", m + 10);
      t1.setAttribute("style", `font: 700 24px ${FUENTE}; fill: ${texto}`);
      t1.textContent = `Árbol de decisión · ${E.area.nombre}`;
      const t2 = document.createElementNS(ns, "text");
      t2.setAttribute("x", m); t2.setAttribute("y", m + 38);
      t2.setAttribute("style", `font: 400 15px ${FUENTE}; fill: ${texto2}`);
      const s = E.area.estadisticas;
      t2.textContent = `${s.preguntas} preguntas · ${s.hojas} hojas · ${s.profundidad_media.toLocaleString("es-CO")} preguntas por camino en promedio · ` +
        "ramas: Sí (verde) / No (gris), grosor = caminos · generado desde el motor de inferencia";
      clon.insertBefore(t2, rect.nextSibling);
      clon.insertBefore(t1, rect.nextSibling);
    }
    clon.classList.remove("atenuar");
    return { svg: '<?xml version="1.0" encoding="UTF-8"?>\n' + new XMLSerializer().serializeToString(clon), ancho: W, alto: H };
  }

  function exportarPNG(escala) {
    escala = escala || 2;
    const { svg, ancho, alto } = exportarSVG();
    return new Promise((ok, mal) => {
      const img = new Image();
      img.onload = () => {
        const cv = document.createElement("canvas");
        cv.width = Math.round(ancho * escala); cv.height = Math.round(alto * escala);
        const ctx = cv.getContext("2d");
        ctx.scale(escala, escala);
        ctx.drawImage(img, 0, 0);
        ok(cv.toDataURL("image/png"));
      };
      img.onerror = mal;
      img.src = "data:image/svg+xml;charset=utf-8," + encodeURIComponent(svg);
    });
  }

  function nombreArchivo(ext) {
    const base = E.area.nombre.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/[^a-z0-9]+/g, "_");
    return `arbol_${base}.${ext}`;
  }

  async function descargar(tipo) {
    const a = document.createElement("a");
    if (tipo === "svg") {
      const blob = new Blob([exportarSVG().svg], { type: "image/svg+xml" });
      a.href = URL.createObjectURL(blob);
    } else {
      a.href = await exportarPNG(2);
    }
    a.download = nombreArchivo(tipo);
    document.body.appendChild(a);
    a.click();
    a.remove();
  }

  // Expande todo, quita resaltados y deja el SVG listo para exportar.
  function modoExportacion(idArea) {
    if (idArea) seleccionarArea(idArea);
    limpiarFijado();
    expandirTodo(true);
    return limites();
  }

  // ------------------------------------------------------------- inicio
  async function iniciar() {
    const contenedor = document.getElementById("arbol");
    if (!contenedor) return;
    if (!D) { contenedor.textContent = "No se pudo cargar D3 (revise la conexión a cdnjs)."; return; }
    try {
      let datos = window.ARBOL_DATOS;
      if (!datos) {
        const src = contenedor.dataset.src || "/static/arbol_datos.json";
        const r = await fetch(src, { cache: "no-cache" });
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        datos = await r.json();
      }
      montar(contenedor, datos);
    } catch (err) {
      contenedor.textContent = "No se pudo cargar el árbol de decisión: " + err.message;
      throw err;
    }
  }

  window.ArbolDecision = {
    seleccionarArea, expandirTodo, contraerTodo, ajustar, buscar, recorrido, paso, reproducir,
    exportarSVG, exportarPNG, modoExportacion, limpiarFijado,
    get datos() { return E.datos; },
    get area() { return E.area; },
  };

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", iniciar);
  else iniciar();
})();
