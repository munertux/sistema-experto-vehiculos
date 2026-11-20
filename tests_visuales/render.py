# -*- coding: utf-8 -*-
"""Servidor Flask local con servicios simulados (sin base de datos) para
revisar visualmente las pantallas de consulta, y capturas con Playwright.

Uso:
    .venv/bin/python tests_visuales/render.py servir          # http://127.0.0.1:5077
    <python con playwright> tests_visuales/render.py capturar # capturas/ (servidor ya arriba)

Usuario: consultante1 / Clave123
"""
import os
import sys
from copy import deepcopy

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
PUERTO = int(os.environ.get("PUERTO", "5077"))
URL = f"http://127.0.0.1:{PUERTO}"


# ------------------------------------------------------------ datos simulados
def _datos():
    from app.logica.servicio_diagnostico import TESTIGOS_TABLERO
    opciones = [{"clave": k, "etiqueta": v} for k, v in
                (("si", "Si"), ("probablemente_si", "Probablemente si"), ("no_se", "No se"),
                 ("probablemente_no", "Probablemente no"), ("no", "No"))]
    preguntas = [
        {"id_pregunta": 7, "id_area": 1, "es_entrada": True, "opciones": opciones,
         "enunciado": "¿El testigo de batería se enciende con el motor en marcha?",
         "por_que": "Si el testigo sigue encendido con el motor andando, el alternador no está cargando. "
                    "Esto separa una falla del sistema de carga de una batería simplemente descargada."},
        {"id_pregunta": 8, "id_area": 1, "es_entrada": False, "opciones": opciones,
         "enunciado": "¿Las luces se atenúan al acelerar o al encender varios accesorios a la vez?",
         "por_que": "Una caída de brillo bajo carga indica que el voltaje no se sostiene: apunta al "
                    "regulador de voltaje o a la correa del alternador (regla R71)."},
        {"id_pregunta": 9, "id_area": 1, "es_entrada": False, "opciones": opciones,
         "enunciado": "¿Escucha un chillido agudo cerca de la correa al arrancar en frío?",
         "por_que": "El chillido en frío es típico de una correa patinando; confirma o descarta la "
                    "hipótesis de correa del alternador desgastada."},
    ]
    evolucion = [
        [],
        [{"nombre": "Alternador defectuoso", "certeza": 0.48, "nivel_atencion": "Revision prioritaria"},
         {"nombre": "Bateria al final de su vida util", "certeza": 0.35, "nivel_atencion": "Revision proxima"},
         {"nombre": "Correa del alternador desgastada", "certeza": 0.22, "nivel_atencion": "Revision proxima"}],
        [{"nombre": "Alternador defectuoso", "certeza": 0.66, "nivel_atencion": "Revision prioritaria"},
         {"nombre": "Regulador de voltaje averiado", "certeza": 0.41, "nivel_atencion": "Revision prioritaria"},
         {"nombre": "Bateria al final de su vida util", "certeza": 0.28, "nivel_atencion": "Revision proxima"},
         {"nombre": "Correa del alternador desgastada", "certeza": 0.24, "nivel_atencion": "Revision proxima"},
         {"nombre": "Borne de bateria sulfatado", "certeza": 0.12, "nivel_atencion": "Atencion preventiva"}],
    ]
    resultado = [
        {"posicion": 1, "id_hipotesis": 31, "nombre": "Alternador defectuoso", "descripcion": "",
         "puntaje": 2.3, "probabilidad": 41.2, "certeza": 0.78, "nivel_atencion": "No debe seguir usandose",
         "recomendacion": "Revisar la salida del alternador con un multímetro (13,8–14,4 V con el motor encendido).",
         "advertencia": True, "sintoma_confirmado": True, "reglas_activadas": ["R70", "R72"],
         "falla_confirmada": False, "observacion": None,
         "como": [
             {"codigo": "R70", "tipo": "testigo", "premisas": ["El testigo de batería se enciende con el motor en marcha (Sí)"],
              "evidencia": 0.6, "hechos": ["FALLA_CARGA"]},
             {"codigo": "R72", "tipo": "compuesta", "conclusion": "Alternador defectuoso", "premisas": ["Hecho: falla de carga", "Las luces se atenúan al acelerar (Probablemente sí)"],
              "evidencia": 0.45, "hechos": ["ALTERNADOR_NO_REGULA"]},
             "Se combinan las evidencias: 0,60 + 0,45 × (1 − 0,60) = 0,78"]},
        {"posicion": 2, "id_hipotesis": 32, "nombre": "Regulador de voltaje averiado", "descripcion": "",
         "puntaje": 1.5, "probabilidad": 27.0, "certeza": 0.51, "nivel_atencion": "Revision prioritaria",
         "recomendacion": "Medir el voltaje a 2000 rpm; si supera 14,8 V reemplazar el regulador.",
         "advertencia": False, "sintoma_confirmado": True, "reglas_activadas": ["R71"],
         "falla_confirmada": False, "observacion": None,
         "como": [{"codigo": "R71", "tipo": "directa", "hechos": [], "conclusion": "Regulador de voltaje averiado", "premisas": ["Las luces se atenúan al acelerar (Probablemente sí)"],
                   "evidencia": 0.51}]},
        {"posicion": 3, "id_hipotesis": 33, "nombre": "Bateria al final de su vida util", "descripcion": "",
         "puntaje": 1.0, "probabilidad": 17.6, "certeza": 0.3, "nivel_atencion": "Revision proxima",
         "recomendacion": "Hacer prueba de carga de la batería en un taller.", "advertencia": False,
         "sintoma_confirmado": False, "reglas_activadas": ["R68"], "falla_confirmada": False, "observacion": None},
        {"posicion": 4, "id_hipotesis": 34, "nombre": "Correa del alternador desgastada", "descripcion": "",
         "puntaje": 0.8, "probabilidad": 14.2, "nivel_atencion": "Atencion preventiva",
         "recomendacion": "Inspeccionar tensión y grietas de la correa.", "advertencia": False,
         "sintoma_confirmado": False, "reglas_activadas": [], "falla_confirmada": False, "observacion": None},
    ]
    return list(TESTIGOS_TABLERO), preguntas, evolucion, resultado


def crear_app_simulada():
    from pruebas import test_web as tw
    from main import crear_app
    testigos, preguntas, evolucion, resultado = _datos()

    class Diagnostico(tw.Diagnostico):
        paso = 0

        def areas(self):
            return [{"id_area": i, "nombre": n, "descripcion": ""} for i, n in enumerate(
                ["Sistema electrico y de carga", "Refrigeracion del motor", "Frenos", "Arranque y encendido",
                 "Suspension y direccion", "Transmision"], start=1)]

        def testigos_disponibles(self):
            return testigos

        def iniciar(self, *a, **k):
            Diagnostico.paso = 0
            return 500, deepcopy(preguntas[0])

        def estado(self, id_atencion):
            return {"estado": "en_curso", "pregunta": deepcopy(preguntas[Diagnostico.paso]),
                    "hipotesis_en_curso": deepcopy(evolucion[Diagnostico.paso])}

        def responder(self, id_atencion, id_pregunta, respuesta):
            Diagnostico.paso += 1
            if Diagnostico.paso >= len(preguntas):
                return {"estado": "finalizado", "resultado": deepcopy(resultado)}
            return {"estado": "en_curso", "pregunta": deepcopy(preguntas[Diagnostico.paso]),
                    "hipotesis_en_curso": deepcopy(evolucion[Diagnostico.paso])}

        def finalizar(self, id_atencion):
            return deepcopy(resultado)

    class Historial(tw.Historial):
        def detalle(self, id_consultante, id_atencion):
            d = super().detalle(id_consultante, id_atencion)
            d.update(area="Sistema electrico y de carga", testigos=["Bateria o sistema de carga"],
                     codigos_obd=["P0562"], hipotesis=deepcopy(resultado),
                     respuestas=[] if Diagnostico.paso == 0 else d["respuestas"])
            return d

    servicios = {"autenticacion": tw.Auth(), "vehiculos": tw.Vehiculos(), "diagnostico": Diagnostico(),
                 "historial": Historial(), "conocimiento": tw.Conocimiento(),
                 "administracion": tw.Administracion()}
    return crear_app(config={"SECRET_KEY": "visual", "SESSION_COOKIE_SECURE": False}, servicios=servicios)


# ------------------------------------------------------------------ capturas
def capturar():
    from playwright.sync_api import sync_playwright
    salida = os.path.join(RAIZ, "capturas")
    os.makedirs(salida, exist_ok=True)

    def foto(page, nombre, completa=False):
        page.wait_for_timeout(900)
        page.screenshot(path=os.path.join(salida, nombre), full_page=completa)
        print("captura:", nombre)

    with sync_playwright() as p:
        nav = p.chromium.launch()
        # 1920x1080 con zoom 125 % = viewport CSS de 1536x864 a escala 1,25
        for etiqueta, opciones in (("1920", {"viewport": {"width": 1536, "height": 864}, "device_scale_factor": 1.25}),
                                   ("movil", {"viewport": {"width": 390, "height": 844}, "device_scale_factor": 2,
                                              "is_mobile": True, "has_touch": True})):
            ctx = nav.new_context(**opciones)
            page = ctx.new_page()
            page.goto(URL + "/login")
            page.fill("input[name=usuario]", "consultante1")
            page.fill("input[name=clave]", "Clave123")
            page.click("button[type=submit]")
            page.wait_for_url("**/panel")

            page.goto(URL + "/consulta/nueva")
            page.check("input[name=id_area][value='1']", force=True)
            for t in ("Bateria o sistema de carga", "Check engine (falla del motor)", "ABS"):
                page.check(f"input[name=testigos][value='{t}']", force=True)
            page.fill("#codigos_obd", "P0562, p0300 X123 P0562")
            page.focus("#codigos_obd")
            foto(page, f"{etiqueta}-1-nueva-consulta.png", completa=True)

            page.fill("#codigos_obd", "P0562")  # el código inválido bloquea el envío (esperado)
            page.click("button[type=submit].grande")
            page.wait_for_url("**/consulta/500")
            page.click("#btn-por-que")
            foto(page, f"{etiqueta}-2a-consulta-primera.png")
            page.click("#opciones-respuesta button.opcion-si")
            page.wait_for_timeout(600)
            page.click("#opciones-respuesta button.opcion-probablemente_si")
            page.wait_for_timeout(400)
            page.click("#btn-por-que")
            foto(page, f"{etiqueta}-2b-consulta-en-curso.png", completa=(etiqueta == "movil"))

            page.click("#opciones-respuesta button.opcion-no")
            page.wait_for_selector("#pantalla-resultado:not(.oculto)")
            page.click("#resultados details.como summary")
            foto(page, f"{etiqueta}-3-resultado.png", completa=True)

            page.goto(URL + "/historial/500")
            page.click("details.como summary")
            foto(page, f"{etiqueta}-4-detalle.png", completa=True)
            page.goto(URL + "/historial/500/reporte")
            foto(page, f"{etiqueta}-5-reporte.png", completa=True)
            if etiqueta == "1920":
                page.goto(URL + "/arbol")
                foto(page, f"{etiqueta}-6-arbol.png")
                # foco visible con teclado
                page.goto(URL + "/consulta/nueva")
                for _ in range(14):
                    page.keyboard.press("Tab")
                foto(page, f"{etiqueta}-7-foco-teclado.png")
            ctx.close()
        nav.close()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "capturar":
        capturar()
    else:
        crear_app_simulada().run(host="127.0.0.1", port=PUERTO, debug=False)
