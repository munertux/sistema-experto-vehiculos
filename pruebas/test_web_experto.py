# -*- coding: utf-8 -*-
"""API del motor experto: /api/conocimiento/kb y campos nuevos de la
consulta (por_que, certeza, como, hipotesis_en_curso). Sin base de datos."""
from test_web import HIPOTESIS, PREGUNTA, app, cliente, ingresar, servicios, token  # noqa: F401 (fixtures)

KB = {"areas": [], "preguntas": [], "hipotesis": [], "hechos": [{"codigo": "FALLA_CARGA", "descripcion": "x"}],
      "reglas": [{"codigo": "R72", "tipo": "compuesta",
                  "condiciones": [{"tipo": "hecho", "referencia": "FALLA_CARGA", "valor_esperado": "si"}]}],
      "testigos": [], "obd": []}


def test_kb_solo_para_ingeniero(cliente, servicios):
    servicios["conocimiento"].base_conocimiento = lambda: KB
    assert cliente.get("/api/conocimiento/kb").status_code in (302, 401)
    ingresar(cliente, "consultante1")
    assert cliente.get("/api/conocimiento/kb").status_code == 403
    cliente.get("/logout")
    ingresar(cliente, "ingeniero1")
    r = cliente.get("/api/conocimiento/kb")
    assert r.status_code == 200 and r.get_json()["reglas"][0]["codigo"] == "R72"


def test_campos_nuevos_con_tildes(cliente, servicios):
    diag = servicios["diagnostico"]
    pregunta = dict(PREGUNTA, por_que="Le pregunto esto porque la hipotesis lider es 'Bateria'")
    en_curso = [{"id_hipotesis": 5, "nombre": "Bateria descargada", "puntaje": 1.0, "probabilidad": 50.0,
                 "certeza": 0.4, "nivel_atencion": "Revision proxima", "posicion": 1}]
    diag.estado = lambda id_atencion: {"estado": "en_curso", "pregunta": pregunta, "hipotesis_en_curso": en_curso}
    resultado = [dict(HIPOTESIS[0], certeza=0.7,
                      como=[{"codigo": "R72", "tipo": "compuesta", "premisas": ["hecho FALLA_CARGA (bateria)"],
                             "texto": "R72: SI ... ENTONCES 'Bateria'"}])]
    diag.responder = lambda *a: {"estado": "finalizado", "resultado": resultado, "hipotesis_en_curso": en_curso}
    ingresar(cliente, "consultante1")
    r = cliente.get("/api/atenciones/500").get_json()
    assert "hipótesis" in r["pregunta"]["por_que"]
    assert r["hipotesis_en_curso"][0]["nombre"] == "Batería descargada"
    assert r["hipotesis_en_curso"][0]["nivel_texto"] == "Revisión próxima" and r["hipotesis_en_curso"][0]["nivel_clase"]
    r = cliente.post("/api/atenciones/500/respuestas", json={"id_pregunta": 7, "respuesta": "si"},
                     headers={"X-CSRF-Token": token(cliente)}).get_json()
    h = r["resultado"][0]
    assert h["certeza"] == 0.7 and h["como"][0]["premisas"] == ["hecho FALLA_CARGA (batería)"]
    assert "Batería" in h["como"][0]["texto"]
