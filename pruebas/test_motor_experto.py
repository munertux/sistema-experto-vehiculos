# -*- coding: utf-8 -*-
"""Pruebas del motor experto (reglas compuestas, negacion, encadenamiento,
testigos/OBD, certeza MYCIN, explicacion, simular y reconstruccion) sobre
el esquema aislado se_pruebas_experto (sql 01, 02, 05, 06, 07 y 08)."""
import random

import pytest

from apoyo_bd import conexion_experto  # noqa: F401 (fixture)
from app.datos.repositorio_conocimiento import RepositorioConocimiento
from app.logica import servicio_diagnostico as modulo_diag
from app.logica.errores import ErrorNegocio
from app.logica.memoria_trabajo import MemoriaTrabajo, combinar_mycin, PESO_MAXIMO
from app.logica.modelos import ESCALA_CERTEZA
from app.logica.motor_inferencia import MotorInferencia
from app.logica.servicio_conocimiento import ServicioConocimiento
from app.logica.servicio_diagnostico import ServicioDiagnostico


@pytest.fixture(scope="module")
def repo(conexion_experto):
    return RepositorioConocimiento(conexion_experto)


@pytest.fixture(scope="module")
def ids(conexion_experto):
    """{codigo: id_regla} de las reglas nuevas."""
    return {f["codigo"]: f["id_regla"] for f in conexion_experto.consultar("SELECT codigo, id_regla FROM reglas")}


@pytest.fixture
def diag(conexion_experto):
    modulo_diag._SESIONES.clear()     # otros esquemas reutilizan los mismos id_atencion
    yield ServicioDiagnostico(conexion_experto)
    modulo_diag._SESIONES.clear()


def nuevo(repo, id_area=9, testigos=None, obd=None):
    motor = MotorInferencia(repo)
    memoria = MemoriaTrabajo(motor._p["puntaje_base"])
    entrada = motor.iniciar(id_area, memoria, testigos, obd)
    return motor, memoria, entrada


def responder(motor, repo, memoria, *pares):
    for id_p, clave in pares:
        motor.procesar_respuesta(memoria, repo.pregunta(id_p), clave, ESCALA_CERTEZA[clave])


# ------------------------------------------------------------ base
def test_base_experta_cargada(repo):
    reglas = repo.reglas_compuestas()
    intermedias = [r for r in reglas if r["concluye_hecho"]]
    assert len(reglas) - len(intermedias) >= 20 and len(intermedias) >= 8
    assert {"FALLA_CARGA", "MEZCLA_RICA", "PERDIDA_LUBRICACION", "SOBRECALENTAMIENTO",
            "FALLA_ENCENDIDO"} <= set(repo.hechos())
    assert any(c["valor_esperado"] == "no" for r in reglas for c in r["condiciones"])
    assert all(int(r["codigo"][1:]) >= 69 for r in reglas)
    # 07/08 son idempotentes: volver a aplicarlos no duplica nada
    antes = repo._db.consultar("SELECT (SELECT COUNT(*) FROM reglas) r, (SELECT COUNT(*) FROM regla_condicion) c")
    import os
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for nombre in ("07_motor_experto.sql", "08_conocimiento_experto.sql"):
        with open(os.path.join(raiz, "sql", nombre), encoding="utf-8") as f:
            with repo._db.transaccion() as cur:
                cur.execute(f.read())
    assert repo._db.consultar("SELECT (SELECT COUNT(*) FROM reglas) r, (SELECT COUNT(*) FROM regla_condicion) c") == antes


def test_las_68_reglas_simples_siguen_liderando(repo):
    """La capa experta es aditiva: con la base ampliada cada regla del
    manual sigue llevando su hipotesis al primer lugar."""
    simples = repo._db.consultar(
        "SELECT r.id_regla, r.codigo, r.id_pregunta, r.id_hipotesis, r.id_area FROM reglas r WHERE r.activa "
        "AND NOT EXISTS (SELECT 1 FROM regla_condicion c WHERE c.id_regla = r.id_regla) ORDER BY r.id_regla")
    assert len(simples) == 68
    fallas = []
    for r in simples:
        motor, memoria, pregunta = nuevo(repo, r["id_area"])
        n = 0
        while pregunta is not None and n < 40:
            n += 1
            clave = "si" if (pregunta.es_entrada and pregunta.id_area == r["id_area"]) \
                or pregunta.id_pregunta == r["id_pregunta"] else "no"
            motor.procesar_respuesta(memoria, pregunta, clave, ESCALA_CERTEZA[clave])
            if motor.debe_detenerse(memoria):
                break
            pregunta = motor.siguiente_pregunta(memoria, r["id_area"])
        lider = motor.hipotesis_ponderadas(memoria)[0]
        if lider.hipotesis.id_hipotesis != r["id_hipotesis"] or r["id_regla"] not in lider.reglas_activadas:
            fallas.append(r["codigo"])
    assert fallas == []


# ------------------------------------------------------- reglas compuestas
def test_compuesta_dispara_solo_con_todas_sus_condiciones(repo, ids):
    # R104: SI P91 Y P47 ENTONCES H68
    motor, memoria, _ = nuevo(repo, 3)
    responder(motor, repo, memoria, (91, "si"))
    assert ids["R104"] not in memoria.disparadas
    antes = memoria.puntajes.get(68, 0.0)
    responder(motor, repo, memoria, (47, "si"))
    assert memoria.disparadas[ids["R104"]] == ("H", 68)
    assert ids["R104"] in memoria.traza[68]
    # el granulo directo de P47 apunta a H23, no a H68: el aumento de H68 es solo la regla compuesta (peso 1.1)
    assert memoria.puntajes[68] - antes == pytest.approx(1.1)
    assert motor.sintoma_confirmado(memoria, 68)

    motor, memoria, _ = nuevo(repo, 3)
    responder(motor, repo, memoria, (91, "si"), (47, "no_se"))
    assert ids["R104"] not in memoria.disparadas   # no_se (e = 0) no satisface la premisa


def test_condicion_negada(repo, ids):
    # R105: SI P91 Y NO P47 ENTONCES H67
    motor, memoria, _ = nuevo(repo, 3)
    responder(motor, repo, memoria, (91, "si"), (47, "si"))
    assert ids["R105"] not in memoria.disparadas
    motor, memoria, _ = nuevo(repo, 3)
    responder(motor, repo, memoria, (91, "si"))
    antes = memoria.puntajes[67]
    responder(motor, repo, memoria, (47, "probablemente_no"))
    assert memoria.disparadas[ids["R105"]] == ("H", 67)
    # evidencia = min(e(P91)=1, 1-2c(P47)=0.5) = 0.5 -> 1.1 * 0.5
    assert memoria.puntajes[67] - antes == pytest.approx(0.55)


def test_encadenamiento_de_dos_niveles(repo, ids):
    # R69: P27 Y P26 -> TENSION_BATERIA_BAJA ; R70: P29 Y TENSION_BATERIA_BAJA -> FALLA_CARGA ;
    # R72: FALLA_CARGA Y NO P79 -> H5
    motor, memoria, _ = nuevo(repo, 9)
    responder(motor, repo, memoria, (27, "si"), (26, "si"))
    assert memoria.hechos == {"TENSION_BATERIA_BAJA": pytest.approx(0.9)}
    responder(motor, repo, memoria, (29, "si"))
    assert memoria.hechos["FALLA_CARGA"] == pytest.approx(0.9)
    assert ids["R72"] not in memoria.disparadas          # falta NO P79
    antes = memoria.puntajes[5]
    responder(motor, repo, memoria, (79, "no"))
    orden = list(memoria.disparadas)
    assert orden.index(ids["R69"]) < orden.index(ids["R70"]) < orden.index(ids["R72"])
    assert memoria.puntajes[5] - antes == pytest.approx(1.1 * 0.9)   # granulo P79 no toca H5
    assert [ids["R72"], ids["R70"], ids["R69"]] == [i for i in memoria.traza[5] if i in
                                                   (ids["R69"], ids["R70"], ids["R72"])]
    assert motor.encadenar(memoria) == []                # refraccion: punto fijo alcanzado
    # la alternativa con correa (R73: FALLA_CARGA Y P79) queda bloqueada
    assert ids["R73"] not in memoria.disparadas


def test_siguiente_pregunta_busca_premisas_de_la_cadena(repo, ids):
    motor, memoria, _ = nuevo(repo, 9)
    responder(motor, repo, memoria, (9, "si"), (27, "si"), (26, "si"), (29, "si"))
    for p in (25, 28):
        responder(motor, repo, memoria, (p, "no"))
    pregunta = motor.siguiente_pregunta(memoria, 9)
    assert pregunta.id_pregunta == 79 and memoria.motivo["id_regla"] == ids["R72"]


# --------------------------------------------------------- testigos y OBD
def test_testigo_y_obd_suben_la_hipotesis_correcta(repo):
    motor, memoria, entrada = nuevo(repo, 9, testigos=["BATERIA"])
    assert entrada.es_entrada
    lider = motor.hipotesis_ponderadas(memoria)[0]
    assert lider.hipotesis.id_hipotesis == 5 and lider.certeza == pytest.approx(0.6 / PESO_MAXIMO)

    motor, memoria, _ = nuevo(repo, 8, obd=["P0302"])
    ranking = [h.hipotesis.id_hipotesis for h in motor.hipotesis_ponderadas(memoria)]
    assert ranking[:2] == [10, 15]

    # prefijo mas largo: P0172 aplica 0.6 a H9 (no 0.6 + 0.4 de P017)
    motor, memoria, _ = nuevo(repo, 8, obd=["P0172"])
    assert memoria.puntajes[9] == pytest.approx(0.1 + 0.6)
    assert {e["codigo"] for e in memoria.eventos if e["tipo"] == "obd"} == {"OBD:P0172"}


def test_servicio_traduce_etiquetas_de_testigos(diag):
    assert diag.codigos_testigos(["Bateria o sistema de carga", "abs", "Batería o sistema de carga", "x"]) == \
        ["BATERIA", "ABS"]
    id_at, pregunta = diag.iniciar(9, testigos=["Bateria o sistema de carga"], codigos_obd="P0562")
    assert "por_que" in pregunta and "líder" in pregunta["por_que"]
    en_curso = diag.estado(id_at)["hipotesis_en_curso"]
    assert en_curso[0]["id_hipotesis"] == 5 and 0 < en_curso[0]["certeza"] <= 1
    assert set(en_curso[0]) >= {"id_hipotesis", "nombre", "puntaje", "probabilidad", "certeza", "nivel_atencion"}


# ---------------------------------------------------------------- certeza
def test_combinacion_mycin():
    assert combinar_mycin(0.0, 0.5) == pytest.approx(0.5)
    assert combinar_mycin(0.5, 0.5) == pytest.approx(0.75)
    assert combinar_mycin(0.9, 3.0) == pytest.approx(1.0)      # e se acota a 1
    assert combinar_mycin(0.3, -1.0) == pytest.approx(0.3)


def test_certeza_combinada_y_acotada(repo):
    motor, memoria, _ = nuevo(repo, 9, testigos=["BATERIA"])          # H5 +0.6 -> 0.3
    responder(motor, repo, memoria, (29, "si"))                       # R05 peso 1.1 -> 0.55
    assert memoria.certeza(5) == pytest.approx(0.3 + 0.55 * (1 - 0.3))
    motor, memoria, _ = nuevo(repo, 9)
    responder(motor, repo, memoria, (29, "probablemente_si"))         # +1.1*0.5 -> 0.275
    responder(motor, repo, memoria, (9, "no"))                        # rama: no cambia la certeza
    assert memoria.certeza(5) == pytest.approx(0.275)
    motor, memoria, _ = nuevo(repo, 9)
    responder(motor, repo, memoria, (29, "no"))                       # solo descreencia -> 0
    assert memoria.certeza(5) == 0.0 and memoria.md[5] == pytest.approx(0.55)

    rnd = random.Random(7)
    claves = list(ESCALA_CERTEZA)
    for id_area in (8, 9, 2, 20, 7):
        motor, memoria, pregunta = nuevo(repo, id_area, testigos=["BATERIA", "ACEITE"], obd=["P0300", "U0100"])
        n = 0
        while pregunta is not None and n < 20:
            n += 1
            clave = rnd.choice(claves)
            motor.procesar_respuesta(memoria, pregunta, clave, ESCALA_CERTEZA[clave])
            for id_h in memoria.puntajes:
                assert 0.0 <= memoria.certeza(id_h) <= 1.0
            if motor.debe_detenerse(memoria):
                break
            pregunta = motor.siguiente_pregunta(memoria, id_area)
        assert all(0.0 <= h.certeza <= 1.0 for h in motor.hipotesis_ponderadas(memoria))


# ------------------------------------------------------------ explicacion
def test_por_que_y_como_coherentes(repo, ids):
    motor, memoria, entrada = nuevo(repo, 9)
    assert "abrir el area" in motor.por_que(memoria, entrada)
    responder(motor, repo, memoria, (9, "si"), (27, "si"), (26, "si"), (29, "si"), (25, "no"), (28, "no"))
    pregunta = motor.siguiente_pregunta(memoria, 9)
    texto = motor.por_que(memoria, pregunta)
    lider = repo.hipotesis(memoria.ranking()[0][0]).nombre
    assert lider in texto and "R72" in texto and "NO P79" in texto and "certeza" in texto

    responder(motor, repo, memoria, (79, "no"))
    pasos = motor.como(memoria, 5)
    codigos = [p["codigo"] for p in pasos]
    assert codigos.index("R69") < codigos.index("R70") < codigos.index("R72")
    assert "R05" in codigos
    r72 = pasos[codigos.index("R72")]
    assert r72["tipo"] == "compuesta" and r72["hechos"] == ["FALLA_CARGA"]
    assert any(p.startswith("NO P79") for p in r72["premisas"])
    assert r72["aporte"] == pytest.approx(1.1 * 0.9, abs=1e-3)
    assert pasos[codigos.index("R70")]["conclusion"] == "Hecho FALLA_CARGA"
    assert sum(p["aporte"] for p in pasos if p["aporte"] is not None) == pytest.approx(
        memoria.puntajes[5] - 0.1 - 0.4, abs=1e-3)      # menos base y rama de entrada
    assert pasos[-1]["certeza"] == pytest.approx(memoria.certeza(5), abs=1e-4)


# ---------------------------------------------------------------- simular
def test_simular_es_determinista_y_sigue_al_motor(diag):
    a = diag.simular(9, ["BATERIA"], None, {})
    assert a["siguiente"]["id_pregunta"] == 9 and a["camino"] == [] and not a["detenido"]
    assert a["hipotesis"][0]["id_hipotesis"] == 5 and "por_que" in a["siguiente"]
    respuestas = {9: "si", 25: "no", 26: "no", 27: "si", 28: "no", 29: "si", 79: "no", 58: "no", 57: "no"}
    r1 = diag.simular(9, ["BATERIA"], None, respuestas)
    r2 = diag.simular(9, ["Bateria o sistema de carga"], [], dict(reversed(list(respuestas.items()))))
    assert r1 == r2
    assert r1["hipotesis"][0]["id_hipotesis"] == 5 and r1["hipotesis"][0]["como"]
    assert [p["id_pregunta"] for p in r1["camino"]][0] == 9
    assert a["motivo"] is None
    if r1["detenido"]:
        assert r1["siguiente"] is None and r1["motivo"] in ("confianza", "max_preguntas", "sin_preguntas")
    else:
        assert r1["siguiente"]["id_pregunta"] not in respuestas
    with pytest.raises(ErrorNegocio):
        diag.simular(9, None, None, {9: "tal_vez"})


def test_simular_coincide_con_una_atencion_real(diag):
    respuestas = {9: "si", 25: "no", 26: "si", 27: "si", 28: "no", 29: "si", 79: "no"}
    sim = diag.simular(9, ["BATERIA"], ["P0562"], respuestas)
    id_at, pregunta = diag.iniciar(9, testigos=["Bateria o sistema de carga"], codigos_obd="P0562")
    while pregunta is not None and pregunta["id_pregunta"] in respuestas:
        r = diag.responder(id_at, pregunta["id_pregunta"], respuestas[pregunta["id_pregunta"]])
        pregunta = r.get("pregunta")
        if r["estado"] == "finalizado":
            break
    real = diag.finalizar(id_at)
    assert [(h["id_hipotesis"], h["puntaje"], h["certeza"]) for h in real] == \
        [(h["id_hipotesis"], h["puntaje"], h["certeza"]) for h in sim["hipotesis"]]
    # lo guardado conserva certeza y como
    guardado = diag.resultado_guardado(id_at)
    assert [h["certeza"] for h in guardado] == [h["certeza"] for h in real]
    assert guardado[0]["como"] == real[0]["como"]


# ---------------------------------------------------------- reconstruccion
def test_atencion_reconstruida_da_el_mismo_resultado(conexion_experto, diag):
    id_at, p = diag.iniciar(8, testigos=["Check engine (falla del motor)"], codigos_obd="P0301, P0172")
    dadas = {}
    for _ in range(4):
        dadas[p["id_pregunta"]] = "si" if p["id_pregunta"] in (8, 33, 34, 39) else "no"
        r = diag.responder(id_at, p["id_pregunta"], dadas[p["id_pregunta"]])
        assert r["estado"] == "en_curso"
        p = r["pregunta"]
    antes = diag.estado(id_at)
    memoria_viva = modulo_diag._SESIONES[id_at]["memoria"]
    modulo_diag._SESIONES.clear()                       # simula reinicio del servidor
    otro = ServicioDiagnostico(conexion_experto)
    despues = otro.estado(id_at)
    assert despues == antes
    memoria = modulo_diag._SESIONES[id_at]["memoria"]
    assert memoria.puntajes == memoria_viva.puntajes and memoria.hechos == memoria_viva.hechos
    assert memoria.disparadas == memoria_viva.disparadas and memoria.eventos == memoria_viva.eventos
    final = otro.finalizar(id_at)
    sim = otro.simular(8, ["CHECK_ENGINE"], ["P0301", "P0172"], dadas)
    assert sim["siguiente"]["id_pregunta"] == p["id_pregunta"]
    assert final == sim["hipotesis"]


# ------------------------------------------------- conocimiento (CRUD) intacto
def test_crud_y_validacion_con_reglas_compuestas(conexion_experto, ids):
    sc = ServicioConocimiento(conexion_experto)
    assert [p for p in sc.validar() if p["tipo"] in ("regla_duplicada", "condicion_invalida",
                                                       "regla_area_inconsistente")] == []
    reglas = {r["codigo"]: r for r in sc.listar_reglas()}
    assert reglas["R72"]["condiciones"] and reglas["R69"]["hipotesis"].startswith("Hecho intermedio")
    original = reglas["R72"]["recomendacion"]
    sc.actualizar_regla(ids["R72"], {"recomendacion": original + " (editada)"}, None)
    assert sc.obtener_regla(ids["R72"])["version"] == 2
    sc.actualizar_regla(ids["R72"], {"recomendacion": original}, None)
    with pytest.raises(ErrorNegocio, match="intermedia"):
        sc.actualizar_regla(ids["R69"], {"recomendacion": "x"}, None)
    sc.cambiar_estado_regla(ids["R69"], False, None)
    sc.cambiar_estado_regla(ids["R69"], True, None)
    # una regla simple nueva sobre la misma pregunta/hipotesis que una compuesta no es duplicado
    granulos = sc.granulos_por_hipotesis(5)["granulos"]
    assert any(g["tipo"] == "compuesta" and g["codigo_regla"] == "R72" for g in granulos)
    kb = sc.base_conocimiento()
    assert {"areas", "preguntas", "hipotesis", "reglas", "hechos", "testigos", "obd"} <= set(kb)
    tipos = {r["codigo"]: r["tipo"] for r in kb["reglas"]}
    assert tipos["R01"] == "simple" and tipos["R72"] == "compuesta" and tipos["R69"] == "intermedia"


def test_memoria_vieja_de_otro_worker_se_reconstruye(conexion_experto, diag):
    """Con varios workers, un proceso puede tener en _SESIONES una memoria
    atrasada; debe reconstruirse en vez de repetir preguntas."""
    id_at, p = diag.iniciar(9, testigos=["Bateria o sistema de carga"])
    vieja = dict(modulo_diag._SESIONES[id_at])                # copia "del otro worker"
    r = diag.responder(id_at, p["id_pregunta"], "si")
    esperado = r["pregunta"]["id_pregunta"]
    modulo_diag._SESIONES[id_at] = vieja                      # este proceso quedo atrasado
    assert diag.estado(id_at)["pregunta"]["id_pregunta"] == esperado
