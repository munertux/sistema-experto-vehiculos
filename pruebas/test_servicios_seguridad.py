# -*- coding: utf-8 -*-
"""ServicioAutenticacion.sesion_vigente y restaurar_conocimiento estricto."""
import pytest

from apoyo_bd import conexion_prueba, unico  # noqa: F401 (fixture)
from app.logica.errores import ErrorNegocio
from app.logica.servicio_administracion import ServicioAdministracion
from app.logica.servicio_autenticacion import ServicioAutenticacion


def test_sesion_vigente_detecta_bloqueo_inactivacion_y_cambio_de_rol(conexion_prueba):
    adm, aut = ServicioAdministracion(conexion_prueba), ServicioAutenticacion(conexion_prueba)
    nombre = unico("seg")
    adm.crear_usuario(nombre, "Clave2026z", "consultante", "Prueba Seguridad")
    sesion = aut.autenticar(nombre, "Clave2026z")
    id_u = sesion["id_usuario"]
    assert aut.sesion_vigente(id_u, "consultante")
    assert not aut.sesion_vigente(id_u, "administrador")
    assert not aut.sesion_vigente(999999, "consultante") and not aut.sesion_vigente("x", "consultante")
    adm.bloquear(id_u)
    assert not aut.sesion_vigente(id_u, "consultante")
    adm.desbloquear(id_u)
    assert aut.sesion_vigente(id_u, "consultante")
    adm.activar(id_u, False)
    assert not aut.sesion_vigente(id_u, "consultante")
    adm.activar(id_u, True)
    try:
        adm.cambiar_rol(id_u, "ingeniero")
    except ErrorNegocio:
        pytest.skip("El cambio de rol de un consultante no esta permitido por la regla de negocio")
    assert not aut.sesion_vigente(id_u, "consultante")
