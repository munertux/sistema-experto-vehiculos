# -*- coding: utf-8 -*-
"""Pruebas del árbol de decisión (app/static/arbol_datos.json).

Cada camino del árbol se reproduce en el motor real (MotorInferencia +
MemoriaTrabajo, con el mismo ciclo de ServicioDiagnostico.responder) y debe
producir exactamente la pregunta del nodo siguiente y, en la hoja, el
diagnóstico guardado. Corre sobre el esquema aislado se_pruebas_motor."""
import json
import os

import pytest

from apoyo_bd import RAIZ, conexion_motor  # noqa: F401 (fixture)
from app.datos.conexion import Conexion, _dsn_desde_env
from app.datos.repositorio_conocimiento import RepositorioConocimiento
from app.logica.memoria_trabajo import MemoriaTrabajo
from app.logica.modelos import ESCALA_CERTEZA
from app.logica.motor_inferencia import MotorInferencia

RUTA_JSON = os.path.join(RAIZ, "app", "static", "arbol_datos.json")


@pytest.fixture(scope="module")
def datos():
    with open(RUTA_JSON, encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def motor(conexion_motor):
    return MotorInferencia(RepositorioConocimiento(conexion_motor))


@pytest.fixture(scope="module")
def motor_fuente():
    """Motor sobre la BD de la que se generó el JSON (DATABASE_URL, esquema
    public). Nota: riesgo_por_area() desempata por orden físico de filas,
    así que la pregunta de contraste puede variar entre BDs distintas; por
    eso el JSON se valida contra su BD de origen."""
    conexion = Conexion(_dsn_desde_env())
    try:
        conexion.consultar("SELECT 1 FROM reglas LIMIT 1")
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"BD de origen del árbol no disponible: {exc}")
    return MotorInferencia(RepositorioConocimiento(conexion))


@pytest.fixture(scope="module")
def arbol_fresco(conexion_motor):
    """Árbol regenerado ahora mismo sobre el esquema de pruebas."""
    import sys
    sys.path.insert(0, os.path.join(RAIZ, "scripts"))
    from generar_arbol_decision import AdaptadorMotor, generar
    return generar(AdaptadorMotor(conexion_motor))


def caminos(nodo, prefijo=()):
    """(camino, nodo) para cada nodo; camino = ((id_pregunta, rama), ...)."""
    yield prefijo, nodo
    if nodo["tipo"] == "pregunta":
        for h in nodo["hijos"]:
            yield from caminos(h["nodo"], prefijo + ((nodo["id_pregunta"], h["rama"]),))


def reproducir(motor, id_area, camino):
    """Ciclo de ServicioDiagnostico: procesar -> debe_detenerse? -> siguiente.
    Devuelve (pregunta pendiente o None, memoria)."""
    memoria = MemoriaTrabajo(motor._p["puntaje_base"])
    pendiente = motor.iniciar(id_area, memoria)
    for id_pregunta, rama in camino:
        assert pendiente is not None, "el motor ya se había detenido"
        assert pendiente.id_pregunta == id_pregunta
        motor.procesar_respuesta(memoria, pendiente, rama, ESCALA_CERTEZA[rama])
        if motor.debe_detenerse(memoria):
            pendiente = None
        else:
            pendiente = motor.siguiente_pregunta(memoria, id_area)
    return pendiente, memoria


def test_estan_todas_las_areas(datos, conexion_motor):
    ids = {f["id_area"] for f in conexion_motor.consultar("SELECT id_area FROM areas")}
    assert {a["id"] for a in datos["areas"]} == ids
    assert len(datos["areas"]) == 24


def test_ninguna_hoja_vacia(datos):
    for area in datos["areas"]:
        for camino, nodo in caminos(area["raiz"]):
            if nodo["tipo"] == "pregunta":
                assert len(nodo["hijos"]) == 2 and nodo["texto"] and nodo["sintoma"]
                assert {h["rama"] for h in nodo["hijos"]} == {"si", "no"}
            else:
                assert nodo["hipotesis"] and nodo["id_hipotesis"], (area["nombre"], camino)
                assert nodo["nivel_atencion"] and nodo["motivo"]
                assert 0 <= nodo["probabilidad"] <= 100
                assert [tuple(x) for x in nodo["camino"]] == list(camino)


def test_la_raiz_es_la_pregunta_de_entrada(datos, motor):
    for area in datos["areas"]:
        entrada = motor._repo.pregunta_de_entrada_del_area(area["id"])
        assert area["raiz"]["tipo"] == "pregunta"
        assert area["raiz"]["id_pregunta"] == entrada.id_pregunta
        assert area["raiz"]["es_entrada"] is True


def verificar_caminos(datos, motor):
    revisados = 0
    for area in datos["areas"]:
        for camino, nodo in caminos(area["raiz"]):
            pendiente, memoria = reproducir(motor, area["id"], camino)
            if nodo["tipo"] == "pregunta":
                assert pendiente is not None and pendiente.id_pregunta == nodo["id_pregunta"], (area["nombre"], camino)
            else:
                if nodo["motivo"] == "profundidad":
                    # corte de visualización: el motor seguiría preguntando
                    assert pendiente is not None, (area["nombre"], camino)
                    assert len(camino) == datos["profundidad_max"]
                else:
                    assert pendiente is None, (area["nombre"], camino)
                lider = motor.hipotesis_ponderadas(memoria)[0]
                assert lider.hipotesis.id_hipotesis == nodo["id_hipotesis"], (area["nombre"], camino)
                assert round(lider.probabilidad * 100, 1) == nodo["probabilidad"]
                assert (lider.puntaje > 0) == nodo["con_evidencia"]
            revisados += 1
    assert revisados == sum(a["estadisticas"]["nodos"] for a in datos["areas"])


def test_generador_reproduce_el_motor(arbol_fresco, motor):
    """El generador (adaptador) y el ciclo real del motor coinciden en
    cada nodo y cada hoja."""
    verificar_caminos(arbol_fresco, motor)


def test_json_reproduce_el_motor(datos, motor_fuente):
    """Cada camino del JSON publicado da la misma pregunta siguiente y el
    mismo diagnóstico en el motor de su BD de origen."""
    verificar_caminos(datos, motor_fuente)


def test_estadisticas_coherentes(datos):
    for area in datos["areas"]:
        e = area["estadisticas"]
        hojas = [n for _, n in caminos(area["raiz"]) if n["tipo"] == "diagnostico"]
        assert e["hojas"] == len(hojas) == area["raiz"]["caminos"]
        assert e["nodos"] == e["preguntas"] + e["hojas"]
        assert e["profundidad_media"] == round(sum(h["profundidad"] for h in hojas) / len(hojas), 2)


def test_json_al_dia_con_el_conocimiento(datos, motor_fuente):
    """Si cambia la base de conocimiento, hay que regenerar el JSON."""
    import sys
    sys.path.insert(0, os.path.join(RAIZ, "scripts"))
    from generar_arbol_decision import AdaptadorMotor, generar
    adaptador = AdaptadorMotor.__new__(AdaptadorMotor)
    adaptador.repo, adaptador.motor = motor_fuente._repo, motor_fuente
    nuevo = generar(adaptador, datos["profundidad_max"])
    for a, b in zip(nuevo["areas"], datos["areas"]):
        assert a == b, f"arbol_datos.json desactualizado en {b['nombre']}: ejecute scripts/generar_arbol_decision.py"
