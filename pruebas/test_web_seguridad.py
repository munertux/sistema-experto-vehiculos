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
