# -*- coding: utf-8 -*-
"""Correcciones de seguridad de la capa web (sin base de datos)."""
from test_web import app, cliente, servicios  # noqa: F401 (fixtures)


def test_salud_no_filtra_detalles_internos(cliente, servicios, caplog):
    def falla():
        raise RuntimeError("password=secreta host=db.interno")
    servicios["conocimiento"].resumen = falla
    r = cliente.get("/api/salud")
    assert r.status_code == 500
    cuerpo = r.get_data(as_text=True)
    assert "secreta" not in cuerpo and "db.interno" not in cuerpo
    assert r.get_json()["estado"] == "error"
    assert any("salud" in rec.getMessage() for rec in caplog.records)


def test_sesion_se_corta_si_el_usuario_deja_de_ser_valido(cliente, servicios):
    from test_web import ingresar
    estado = {"vigente": True}
    servicios["autenticacion"].sesion_vigente = lambda id_usuario, rol: estado["vigente"] and rol == "consultante"
    ingresar(cliente, "consultante1")
    assert cliente.get("/panel").status_code == 200
    estado["vigente"] = False                 # p. ej. el administrador lo bloqueo
    r = cliente.get("/panel")
    assert r.status_code == 302 and "/login" in r.headers["Location"]
    with cliente.session_transaction() as s:
        assert "id_usuario" not in s
    estado["vigente"] = True
    ingresar(cliente, "consultante1")
    estado["vigente"] = False
    assert cliente.get("/api/areas").status_code == 401
