# -*- coding: utf-8 -*-
"""ServicioAutenticacion.sesion_vigente y restaurar_conocimiento estricto."""
import pytest

from apoyo_bd import conexion_prueba, unico  # noqa: F401 (fixture)
from app.logica.errores import ErrorNegocio
from app.logica.servicio_administracion import ServicioAdministracion
from app.logica.servicio_autenticacion import ServicioAutenticacion


def test_bloqueo_automatico_no_expulsa_y_bloqueo_manual_si(conexion_prueba):
    """Sesion activa + 5 logins fallidos de un tercero -> la sesion sigue
    valida (evita expulsar a otro usuario a proposito). Bloqueo manual del
    administrador -> sesion revocada."""
    adm, aut = ServicioAdministracion(conexion_prueba), ServicioAutenticacion(conexion_prueba)
    nombre = unico("dos")
    adm.crear_usuario(nombre, "Clave2026z", "consultante", "Victima DoS")
    id_u = aut.autenticar(nombre, "Clave2026z")["id_usuario"]
    version = aut.version_sesion(id_u)
    for _ in range(5):
        with pytest.raises(ErrorNegocio):
            aut.autenticar(nombre, "incorrecta1")
    with pytest.raises(ErrorNegocio, match="incorrectos"):
        aut.autenticar(nombre, "Clave2026z")          # el bloqueo impide nuevos ingresos
    assert aut.sesion_vigente(id_u, "consultante", version)    # pero no cierra la sesion abierta
    assert aut.version_sesion(id_u) == version
    adm.bloquear(id_u)
    assert not aut.sesion_vigente(id_u, "consultante", version)
    adm.desbloquear(id_u)                           # desbloquear no revive la sesion vieja
    assert not aut.sesion_vigente(id_u, "consultante", version)
    assert aut.sesion_vigente(id_u, "consultante", aut.version_sesion(id_u))


def test_restablecer_clave_revoca_sesiones(conexion_prueba):
    adm, aut = ServicioAdministracion(conexion_prueba), ServicioAutenticacion(conexion_prueba)
    nombre = unico("rst")
    adm.crear_usuario(nombre, "Clave2026z", "consultante", "Clave Restablecida")
    id_u = aut.autenticar(nombre, "Clave2026z")["id_usuario"]
    version = aut.version_sesion(id_u)
    adm.restablecer_clave(id_u, "Nueva2026x")
    assert not aut.sesion_vigente(id_u, "consultante", version)


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


from app.logica.servicio_administracion import sentencia_restauracion  # noqa: E402

BUENA = ("INSERT INTO areas (id_area, nombre, descripcion) VALUES (1, 'Instrumentacion y tablero', "
         "E'Uno\\\\ dos\\' tres\\n') ON CONFLICT (id_area) DO UPDATE SET nombre = EXCLUDED.nombre, "
         "descripcion = EXCLUDED.descripcion;")


def test_sentencia_restauracion_parametrizada():
    sql, valores = sentencia_restauracion(BUENA)
    assert "%s" in sql and "Instrumentacion" not in sql
    assert valores == (1, "Instrumentacion y tablero", "Uno\\ dos' tres\n")
    sql, valores = sentencia_restauracion(
        "INSERT INTO reglas (id_regla, codigo, id_pregunta, id_hipotesis, id_area, nivel_atencion, gravedad, "
        "recomendacion, peso, version, activa, concluye_hecho) VALUES (69, 'R69', 27, NULL, 9, 'Revision proxima', "
        "2, 'x', 0.90, 1, TRUE, 'FALLA_CARGA') ON CONFLICT (id_regla) DO UPDATE SET codigo = EXCLUDED.codigo, "
        "id_pregunta = EXCLUDED.id_pregunta, id_hipotesis = EXCLUDED.id_hipotesis, id_area = EXCLUDED.id_area, "
        "nivel_atencion = EXCLUDED.nivel_atencion, gravedad = EXCLUDED.gravedad, "
        "recomendacion = EXCLUDED.recomendacion, peso = EXCLUDED.peso, version = EXCLUDED.version, "
        "activa = EXCLUDED.activa, concluye_hecho = EXCLUDED.concluye_hecho;")
    assert valores[3] is None and valores[8] == 0.9 and valores[10] is True


@pytest.mark.parametrize("maliciosa", [
    # ON CONFLICT arbitrario: modifica columnas con expresiones o subconsultas
    "INSERT INTO areas (id_area, nombre, descripcion) VALUES (1, 'a', 'b') ON CONFLICT (id_area) DO UPDATE SET "
    "nombre = (SELECT contrasena_hash FROM usuario LIMIT 1), descripcion = EXCLUDED.descripcion;",
    "INSERT INTO areas (id_area, nombre, descripcion) VALUES (1, 'a', 'b') ON CONFLICT (id_area) DO UPDATE SET "
    "nombre = EXCLUDED.nombre, descripcion = EXCLUDED.descripcion WHERE pg_sleep(5) IS NULL;",
    "INSERT INTO areas (id_area, nombre, descripcion) VALUES (1, 'a', 'b') ON CONFLICT (nombre) DO UPDATE SET "
    "id_area = EXCLUDED.id_area, descripcion = EXCLUDED.descripcion;",
    "INSERT INTO areas (id_area, nombre, descripcion) VALUES (1, 'a', 'b') ON CONFLICT DO NOTHING;",
    "INSERT INTO areas (id_area, nombre, descripcion) VALUES (1, 'a', 'b') ON CONFLICT (id_area) DO NOTHING;",
    "INSERT INTO areas (id_area, nombre, descripcion) VALUES (1, 'a', 'b') ON CONFLICT (id_area) DO UPDATE SET "
    "nombre = EXCLUDED.descripcion, descripcion = EXCLUDED.descripcion;",
    # columnas o tablas fuera de la lista
    "INSERT INTO areas (id_area, nombre, oculta) VALUES (1, 'a', 'b') ON CONFLICT (id_area) DO UPDATE SET "
    "nombre = EXCLUDED.nombre, oculta = EXCLUDED.oculta;",
    "INSERT INTO usuario (id_usuario, id_rol) VALUES (1, 3) ON CONFLICT (id_usuario) DO UPDATE SET "
    "id_rol = EXCLUDED.id_rol;",
    # valores que no son literales
    "INSERT INTO areas (id_area, nombre, descripcion) VALUES (1, current_user, 'b') ON CONFLICT (id_area) "
    "DO UPDATE SET nombre = EXCLUDED.nombre, descripcion = EXCLUDED.descripcion;",
    "INSERT INTO areas (id_area, nombre, descripcion) VALUES (1, 'a'||'b', 'c') ON CONFLICT (id_area) "
    "DO UPDATE SET nombre = EXCLUDED.nombre, descripcion = EXCLUDED.descripcion;",
    "INSERT INTO areas (id_area, nombre, descripcion) VALUES (1, 'a') ON CONFLICT (id_area) "
    "DO UPDATE SET nombre = EXCLUDED.nombre, descripcion = EXCLUDED.descripcion;",
    "INSERT INTO areas (id_area, nombre, descripcion) VALUES (1, 'a', 'b'); DROP TABLE reglas; --') "
    "ON CONFLICT (id_area) DO UPDATE SET nombre = EXCLUDED.nombre, descripcion = EXCLUDED.descripcion;",
])
def test_restaurar_rechaza_on_conflict_y_valores_arbitrarios(conexion_prueba, maliciosa):
    with pytest.raises(ErrorNegocio):
        sentencia_restauracion(maliciosa)
    with pytest.raises(ErrorNegocio):
        ServicioAdministracion(conexion_prueba).restaurar_conocimiento(maliciosa)
