# -*- coding: utf-8 -*-
"""Pruebas de extremo a extremo de la consulta por la web con la base real
(esquema aislado se_pruebas_experto) y los servicios reales:

  - P1: un consultante que responde "No" a todo recibe "Sin falla
    identificada" en el JSON de la API y en el detalle/reporte HTML, sin el
    aviso rojo de "no debe seguir usándose".
  - P2: todas las salidas visibles (JSON de /api que consume consulta.js y
    HTML del detalle) salen con tildes; los códigos (FALLA_CARGA, T:FRENOS,
    R100) no se alteran.
"""
import re

import pytest

from apoyo_bd import conexion_experto, unico  # noqa: F401 (fixture)
from app.logica import servicio_diagnostico as modulo_diag
from app.web.presentacion import tildes
from main import crear_app

CLAVE = "Clave2026z"
# Palabras sin tilde que nunca deben llegar a la interfaz. Se calculan del
# propio conocimiento: toda palabra de la base o de las plantillas del
# motor cuya forma con tildes difiere ("bateria" -> "batería").
_PALABRA = re.compile(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]+")
AMBIGUAS = {"si"}      # "si" condicional es correcto ("si responde que sí")


@pytest.fixture(scope="module")
def prohibidas(conexion_experto):
    textos = []
    for sql in ("SELECT nombre AS t FROM areas", "SELECT enunciado AS t FROM preguntas",
                "SELECT nombre AS t FROM hipotesis", "SELECT recomendacion AS t FROM reglas",
                "SELECT nivel_atencion AS t FROM reglas", "SELECT descripcion AS t FROM hechos"):
        textos += [f["t"] for f in conexion_experto.consultar(sql)]
    textos += ["hipotesis lider certeza area evaluacion confirmaria codigo regla intermedia minima "
               "Revision proxima prioritaria usandose Atencion preventiva Pregunta asi Si Probablemente si No se"]
    salida = set()
    for t in textos:
        for w in _PALABRA.findall(t or ""):
            if w.lower() not in AMBIGUAS and tildes(w.lower()) != w.lower():
                salida.add(w.lower())
    assert {"bateria", "vehiculo", "revision", "proxima", "hipotesis", "usandose", "corroidas"} <= salida
    return salida


def textos_de(valor, clave=""):
    """Todas las cadenas visibles de una respuesta JSON (sin los codigos)."""
    if isinstance(valor, dict):
        for k, v in valor.items():
            if k in ("hechos", "nivel_clase", "codigo", "reglas_activadas", "respuesta", "clave", "resultado_estado",
                     "tipo", "nivel", "motivo", "rama", "adaptador", "estado"):   # identificadores, no texto
                continue
            yield from textos_de(v, k)
    elif isinstance(valor, list):
        for v in valor:
            yield from textos_de(v, clave)
    elif isinstance(valor, str):
        yield valor


def sin_tildes(texto, prohibidas):
    return sorted({w for w in _PALABRA.findall(texto) if not w.isupper() and w.lower() in prohibidas})


@pytest.fixture(scope="module")
def cliente(conexion_experto):
    from app.logica.servicio_administracion import ServicioAdministracion
    from app.logica.servicio_autenticacion import ServicioAutenticacion
    from app.logica.servicio_diagnostico import ServicioDiagnostico
    from app.logica.servicio_historial import ServicioHistorial
    from app.logica.servicio_vehiculos import ServicioVehiculos
    nombre = unico("e2e")
    ServicioAdministracion(conexion_experto).crear_usuario(nombre, CLAVE, "consultante", "Consultante E2E")
    servicios = {"autenticacion": ServicioAutenticacion(conexion_experto),
                 "diagnostico": ServicioDiagnostico(conexion_experto),
                 "historial": ServicioHistorial(conexion_experto),
                 "vehiculos": ServicioVehiculos(conexion_experto)}
    app = crear_app(config={"TESTING": True, "SECRET_KEY": "prueba-e2e", "SESSION_COOKIE_SECURE": False},
                    servicios=servicios)
    c = app.test_client()
    c.get("/login")
    with c.session_transaction() as s:
        csrf = s["csrf"]
    r = c.post("/login", data={"usuario": nombre, "clave": CLAVE, "csrf_token": csrf})
    assert r.status_code == 302
    with c.session_transaction() as s:
        c.csrf = s["csrf"]
    modulo_diag._SESIONES.clear()
    yield c
    modulo_diag._SESIONES.clear()


def consultar(cliente, id_area, respuestas, testigos=(), obd="", defecto="no"):
    """Recorre la consulta por la API. Devuelve (id_atencion, [respuestas JSON])."""
    h = {"X-CSRF-Token": cliente.csrf}
    r = cliente.post("/api/atenciones", json={"id_area": id_area, "testigos": list(testigos), "codigos_obd": obd},
                     headers=h)
    assert r.status_code == 200, r.get_json()
    datos = r.get_json()
    id_at, pregunta, salidas = datos["id_atencion"], datos["pregunta"], [datos]
    for _ in range(30):
        r = cliente.post(f"/api/atenciones/{id_at}/respuestas", headers=h,
                         json={"id_pregunta": pregunta["id_pregunta"],
                               "respuesta": respuestas.get(pregunta["id_pregunta"], defecto)})
        assert r.status_code == 200, r.get_json()
        salidas.append(r.get_json())
        if salidas[-1]["estado"] == "finalizado":
            break
        pregunta = salidas[-1]["pregunta"]
    return id_at, salidas


def test_todo_no_en_la_web_es_sin_falla_identificada(cliente, prohibidas):
    id_at, salidas = consultar(cliente, 9, {})
    final = salidas[-1]
    assert final["estado"] == "finalizado" and final["resultado"] == []
    assert final["sin_resultado"] is True and final["resultado_estado"] == "sin_resultado"
    assert final["mensaje"].startswith("Con la evidencia aportada no se identificó una falla en el área")
    html = cliente.get(f"/historial/{id_at}").get_data(as_text=True)
    assert "Sin falla identificada" in html and "consulte un técnico" in html
    assert 'class="advertencia"' not in html and "no debe seguir usándose" not in html.lower()
    reporte = cliente.get(f"/historial/{id_at}/reporte").get_data(as_text=True)
    assert "Sin falla identificada" in reporte and 'class="advertencia"' not in reporte
    estado = cliente.get(f"/api/atenciones/{id_at}").get_json()
    assert estado["sin_resultado"] and estado["resultado"] == []
    historial = cliente.get("/historial").get_data(as_text=True)
    assert "Sin falla identificada" in historial


def test_diagnostico_critico_muestra_aviso_y_todo_sale_con_tildes(cliente, prohibidas):
    id_at, salidas = consultar(cliente, 2, {2: "si", 44: "si"}, testigos=["Frenos o freno de estacionamiento"])
    final = salidas[-1]
    lider = final["resultado"][0]
    assert lider["nombre"] == "Aire en el circuito hidráulico o fuga de líquido de frenos"
    assert lider["advertencia"] is True and lider["nivel_texto"].startswith("No debe seguir usándose")
    # el "como" conserva los codigos y trae su forma legible
    pasos = {p["codigo"]: p for p in lider["como"]}
    assert {"T:FRENOS", "R20", "R100", "R102"} <= set(pasos)
    assert pasos["R102"]["hechos"] == ["PERDIDA_PRESION_FRENO"]
    assert pasos["R102"]["hechos_texto"] == ["Pérdida presión freno"]
    assert any("testigo FRENOS encendido" in p for p in pasos["R100"]["premisas"])
    # ninguna palabra sin tilde en el JSON (por_que, como, en curso, resultado)
    for salida in salidas:
        malas = sorted({w for t in textos_de(salida) for w in sin_tildes(t, prohibidas)})
        assert malas == [], malas
    assert "líder" in salidas[0]["pregunta"]["por_que"] or "hipótesis" in salidas[0]["pregunta"]["por_que"]
    html = cliente.get(f"/historial/{id_at}").get_data(as_text=True)
    assert 'class="advertencia"' in html and "Aire en el circuito hidráulico" in html
    assert "¿Cómo llegó a esta conclusión?" in html and "R102" in html
    texto = re.sub(r"<[^>]+>", " ", html)
    assert sin_tildes(texto, prohibidas) == []


def test_api_areas_y_preguntas_con_tildes(cliente, prohibidas, conexion_experto):
    areas = cliente.get("/api/areas").get_json()
    assert any(a["nombre"] == "Arranque del vehículo" for a in areas)
    for a in areas:
        assert sin_tildes(a["nombre"] + " " + a["descripcion"], prohibidas) == []
    # cada pregunta de entrada, tal como la entrega la API al iniciar
    for a in areas[:24]:
        r = cliente.post("/api/atenciones", json={"id_area": a["id_area"]}, headers={"X-CSRF-Token": cliente.csrf})
        p = r.get_json()["pregunta"]
        assert sin_tildes(p["enunciado"] + " " + p["por_que"] + " " + " ".join(o["etiqueta"] for o in p["opciones"]),
                          prohibidas) == []
        assert {o["etiqueta"] for o in p["opciones"]} >= {"Sí", "Probablemente sí", "No sé"}


def test_arbol_publicado_sin_palabras_sin_tilde(prohibidas):
    import json
    import os
    from apoyo_bd import RAIZ
    with open(os.path.join(RAIZ, "app", "static", "arbol_datos.json"), encoding="utf-8") as f:
        datos = json.load(f)
    malas = sorted({w for t in textos_de(datos) for w in sin_tildes(t, prohibidas)})
    assert malas == [], malas


def test_tildes_respeta_codigos_y_es_idempotente():
    casos = {
        "testigo BATERIA encendido": "testigo BATERIA encendido",
        "hecho FALLA_CARGA (El sistema de carga no recarga la bateria)":
            "hecho FALLA_CARGA (El sistema de carga no recarga la batería)",
        "P26 '¿clic rapido?' = Si": "P26 '¿clic rápido?' = Sí",
        "la regla R72 la confirmaria si responde que si": "la regla R72 la confirmaría si responde que sí",
        "El alternador no esta generando carga": "El alternador no está generando carga",
        "Conexiones de bateria flojas, sulfatadas o corroidas": "Conexiones de batería flojas, sulfatadas o corroídas",
        "la hipotesis lider es 'Bateria' (certeza 0.30)": "la hipótesis líder es 'Batería' (certeza 0.30)",
    }
    for entrada, esperado in casos.items():
        assert tildes(entrada) == esperado
        assert tildes(esperado) == esperado
