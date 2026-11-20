# -*- coding: utf-8 -*-
"""ServicioAdministracion: usuarios, auditoria y respaldos (rol
administrador, CU-06)."""
import re
from datetime import datetime

from app.datos.dao.bitacora_dao import BitacoraDAO
from app.datos.dao.consultante_dao import ConsultanteDAO
from app.datos.dao.empleado_dao import EmpleadoDAO
from app.datos.dao.respaldo_dao import (RespaldoDAO, ORDEN_RESPALDO, TABLAS_CONOCIMIENTO,
                                       COLUMNAS_CONOCIMIENTO)
from app.datos.dao.usuario_dao import UsuarioDAO
from app.logica.entidades import CLAVES_ROL, IDS_ROL
from app.logica.errores import ErrorNegocio
from app.logica.servicio_autenticacion import hashear_clave, validar_clave

PATRON_USUARIO = re.compile(r"^[a-zA-Z0-9._-]{3,40}$")
PATRON_CORREO = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
CARGO_POR_ROL = {"ingeniero": "Ingeniero del conocimiento", "administrador": "Administrador del sistema"}

# Forma exacta de las sentencias que genera RespaldoDAO.sentencias_insert para
# las tablas de conocimiento. Cualquier otra forma se rechaza.
_INSERT_CONOCIMIENTO = re.compile(
    r"^INSERT INTO (?P<tabla>[a-z_]+) \((?P<columnas>[a-z_]+(?:, [a-z_]+)*)\) VALUES \((?P<valores>.*)\) "
    r"ON CONFLICT \((?P<pk>[a-z_]+(?:, [a-z_]+)*)\) (?P<accion>DO NOTHING|DO UPDATE SET (?P<sets>.+));$")
_SET = re.compile(r"^([a-z_]+) = EXCLUDED\.([a-z_]+)$")
# Valores admitidos: NULL, TRUE, FALSE, numeros y literales '...' o E'...' (los que produce literal_sql).
_VALOR = re.compile(r"\s*(?:(?P<nulo>NULL)|(?P<booleano>TRUE|FALSE)|(?P<numero>-?\d+(?:\.\d+)?)"
                    r"|E'(?P<escapado>(?:[^'\\]|\\.)*)'|'(?P<texto>(?:[^']|'')*)')\s*(?:,|$)")
_ESCAPES = {"\\": "\\", "'": "'", "n": "\n", "r": "\r", "t": "\t"}


def _valores_sql(texto: str) -> list:
    """Convierte la lista VALUES en valores de Python o lanza ErrorNegocio."""
    valores, pos = [], 0
    while pos < len(texto):
        m = _VALOR.match(texto, pos)
        if not m or m.end() == pos:
            raise ErrorNegocio("Valor no permitido en el respaldo.")
        if m.group("nulo"):
            valores.append(None)
        elif m.group("booleano"):
            valores.append(m.group("booleano") == "TRUE")
        elif m.group("numero") is not None:
            n = m.group("numero")
            valores.append(float(n) if "." in n else int(n))
        elif m.group("escapado") is not None:
            valores.append(re.sub(r"\\(.)", lambda e: _ESCAPES.get(e.group(1), e.group(1)), m.group("escapado")))
        else:
            valores.append(m.group("texto").replace("''", "'"))
        pos = m.end()
        if pos == len(texto) and texto.rstrip().endswith(","):
            raise ErrorNegocio("Valor no permitido en el respaldo.")
    return valores


def sentencia_restauracion(linea: str):
    """Valida un INSERT de conocimiento contra la forma exacta del respaldo
    (tabla y columnas de la lista permitida, ON CONFLICT (<pk>) DO UPDATE
    SET col = EXCLUDED.col para todas las columnas no llave) y devuelve
    (sql parametrizado, valores). Lanza ErrorNegocio si no coincide."""
    m = _INSERT_CONOCIMIENTO.match(linea)
    if not m or m.group("tabla") not in COLUMNAS_CONOCIMIENTO:
        raise ErrorNegocio("El archivo contiene sentencias no permitidas: " + linea[:80])
    permitidas, pk_esperada = COLUMNAS_CONOCIMIENTO[m.group("tabla")]
    columnas = m.group("columnas").split(", ")
    pk = tuple(m.group("pk").split(", "))
    resto = [c for c in columnas if c not in pk]
    if (len(set(columnas)) != len(columnas) or not set(columnas) <= set(permitidas) or pk != pk_esperada
            or not set(pk) <= set(columnas)):
        raise ErrorNegocio("El archivo contiene columnas o llaves no permitidas: " + linea[:80])
    if m.group("sets") is None:
        if resto:
            raise ErrorNegocio("El archivo contiene sentencias no permitidas: " + linea[:80])
    else:
        pares = [_SET.match(s) for s in m.group("sets").split(", ")]
        if any(p is None or p.group(1) != p.group(2) for p in pares) or [p.group(1) for p in pares] != resto:
            raise ErrorNegocio("El archivo contiene una clausula ON CONFLICT no permitida: " + linea[:80])
    valores = _valores_sql(m.group("valores"))
    if len(valores) != len(columnas):
        raise ErrorNegocio("El numero de valores no coincide con las columnas: " + linea[:80])
    accion = ("DO UPDATE SET " + ", ".join(f"{c} = EXCLUDED.{c}" for c in resto)) if resto else "DO NOTHING"
    sql = (f"INSERT INTO {m.group('tabla')} ({', '.join(columnas)}) VALUES ({', '.join(['%s'] * len(columnas))}) "
           f"ON CONFLICT ({', '.join(pk)}) {accion}")
    return sql, tuple(valores)


class ServicioAdministracion:
    def __init__(self, conexion):
        self._db = conexion
        self._usuarios = UsuarioDAO(conexion)
        self._consultantes = ConsultanteDAO(conexion)
        self._empleados = EmpleadoDAO(conexion)
        self._bitacora = BitacoraDAO(conexion)
        self._respaldo = RespaldoDAO(conexion)

    # ------------------------------------------------------------ usuarios
    def listar_usuarios(self) -> list:
        salida = []
        for f in self._usuarios.listar_detallado():
            f = dict(f)
            f["rol"] = CLAVES_ROL.get(f["id_rol"], "")
            salida.append(f)
        return salida

    def obtener_usuario(self, id_usuario: int) -> dict:
        for u in self.listar_usuarios():
            if u["id_usuario"] == int(id_usuario):
                return u
        raise ErrorNegocio("El usuario no existe.")

    def crear_usuario(self, nombre_usuario: str, clave: str, rol: str, nombres: str, correo: str = None,
                      telefono: str = None, cargo: str = None, id_empleado: int = None) -> int:
        """Crea el usuario y su perfil (consultante o empleado) en una sola transaccion."""
        nombre_usuario = (nombre_usuario or "").strip()
        nombres = (nombres or "").strip()
        rol = (rol or "").strip().lower()
        if not PATRON_USUARIO.match(nombre_usuario):
            raise ErrorNegocio("El usuario debe tener de 3 a 40 caracteres (letras, numeros, punto, guion).")
        if rol not in IDS_ROL:
            raise ErrorNegocio("El rol debe ser consultante, ingeniero o administrador.")
        if len(nombres) < 3:
            raise ErrorNegocio("Indique los nombres de la persona.")
        correo = (correo or "").strip() or None
        if correo and not PATRON_CORREO.match(correo):
            raise ErrorNegocio("El correo no es valido.")
        telefono = (telefono or "").strip() or None
        validar_clave(clave)
        if self._usuarios.existe_nombre(nombre_usuario):
            raise ErrorNegocio(f"El usuario '{nombre_usuario}' ya existe.")

        with self._db.transaccion() as tx:
            id_usuario = self._usuarios.crear(IDS_ROL[rol], nombre_usuario, hashear_clave(clave), tx=tx)
            if rol == "consultante":
                self._consultantes.crear(id_usuario, nombres, correo, telefono, tx=tx)
            else:
                self._empleados.crear(id_usuario, nombres, (cargo or "").strip() or CARGO_POR_ROL[rol], tx=tx)
            self._bitacora.registrar("usuario", id_usuario, "crear", id_empleado,
                                     detalle=f"Usuario {nombre_usuario} ({rol})", tx=tx)
        return id_usuario

    def cambiar_rol(self, id_usuario: int, rol: str, id_empleado: int = None):
        """Cambia el rol y crea el perfil que falte (consultante o empleado)."""
        usuario = self._usuario(id_usuario)
        rol = (rol or "").strip().lower()
        if rol not in IDS_ROL:
            raise ErrorNegocio("El rol debe ser consultante, ingeniero o administrador.")
        if usuario.rol == rol:
            return
        if usuario.rol == "administrador" and self._contar_admins_activos() <= 1:
            raise ErrorNegocio("No se puede quitar el rol al unico administrador activo.")
        consultante = self._consultantes.obtener_por_usuario(usuario.id_usuario)
        empleado = self._empleados.obtener_por_usuario(usuario.id_usuario)
        nombres = (consultante or empleado).nombres if (consultante or empleado) else usuario.nombre_usuario
        with self._db.transaccion() as tx:
            self._usuarios.cambiar_rol(usuario.id_usuario, IDS_ROL[rol], tx=tx)
            self._usuarios.revocar_sesiones(usuario.id_usuario, tx=tx)
            if rol == "consultante" and consultante is None:
                self._consultantes.crear(usuario.id_usuario, nombres, tx=tx)
            elif rol != "consultante":
                if empleado is None:
                    self._empleados.crear(usuario.id_usuario, nombres, CARGO_POR_ROL[rol], tx=tx)
                else:
                    self._empleados.actualizar(empleado.id_empleado, {"cargo": CARGO_POR_ROL[rol]}, tx=tx)
            self._bitacora.registrar("usuario", usuario.id_usuario, "modificar", id_empleado,
                                     detalle=f"Rol {usuario.rol} -> {rol}", tx=tx)

    def bloquear(self, id_usuario: int, id_empleado: int = None):
        """Bloqueo indefinido hasta que el administrador lo desbloquee."""
        usuario = self._usuario(id_usuario)
        self._no_dejar_sin_admin(usuario)
        self._cambiar_estado(usuario, "bloqueado", "desactivar", id_empleado, "Bloqueado por el administrador")

    def desbloquear(self, id_usuario: int, id_empleado: int = None):
        usuario = self._usuario(id_usuario)
        self._cambiar_estado(usuario, "activo", "activar", id_empleado, "Desbloqueado")

    def activar(self, id_usuario: int, activo: bool, id_empleado: int = None):
        usuario = self._usuario(id_usuario)
        if not activo:
            self._no_dejar_sin_admin(usuario)
        self._cambiar_estado(usuario, "activo" if activo else "inactivo", "activar" if activo else "desactivar",
                             id_empleado, "Activado" if activo else "Inactivado")

    def restablecer_clave(self, id_usuario: int, clave_nueva: str, id_empleado: int = None):
        usuario = self._usuario(id_usuario)
        validar_clave(clave_nueva)
        with self._db.transaccion() as tx:
            self._usuarios.cambiar_hash(usuario.id_usuario, hashear_clave(clave_nueva), tx=tx)
            self._usuarios.revocar_sesiones(usuario.id_usuario, tx=tx)
            self._bitacora.registrar("usuario", usuario.id_usuario, "modificar", id_empleado,
                                     detalle="Contrasena restablecida por el administrador", tx=tx)

    # ----------------------------------------------------------- auditoria
    def auditoria(self, limite: int = 200) -> list:
        return self._bitacora.listar(max(1, min(int(limite), 5000)))

    # ----------------------------------------------------------- respaldos
    def respaldo_sql(self) -> str:
        """Script SQL con INSERT de las tablas de conocimiento y
        transaccionales. Incluye los hash de contrasena (nunca claves en claro).
        Las tablas de conocimiento usan ON CONFLICT DO UPDATE; el resto, DO NOTHING."""
        existentes = self._respaldo.tablas_existentes()
        lineas = [
            "-- Respaldo del Sistema Experto de Diagnostico de Fallas en Vehiculos",
            f"-- Generado: {datetime.now():%Y-%m-%d %H:%M:%S}",
            "-- Aplicar sobre una base con sql/01, 05 y 06 ya ejecutados.",
            "SET client_encoding = 'UTF8';",
            "BEGIN;",
        ]
        for tabla in ORDEN_RESPALDO:
            if tabla not in existentes:
                continue
            lineas.append(f"-- {tabla}")
            lineas.extend(self._respaldo.sentencias_insert(tabla, actualizar_si_existe=tabla in TABLAS_CONOCIMIENTO))
            lineas.extend(self._respaldo.sentencias_secuencias(tabla))
        lineas.append("COMMIT;")
        return "\n".join(lineas) + "\n"

    def respaldo_conocimiento_sql(self) -> str:
        lineas = ["-- Respaldo de la base de conocimiento", f"-- Generado: {datetime.now():%Y-%m-%d %H:%M:%S}",
                  "BEGIN;"]
        existentes = self._respaldo.tablas_existentes()
        for tabla in TABLAS_CONOCIMIENTO:
            if tabla not in existentes:
                continue
            lineas.append(f"-- {tabla}")
            lineas.extend(self._respaldo.sentencias_insert(tabla, actualizar_si_existe=True))
        lineas.append("COMMIT;")
        return "\n".join(lineas) + "\n"

    def restaurar_conocimiento(self, sql: str, id_empleado: int = None) -> int:
        """Aplica solo los INSERT de tablas de conocimiento de un respaldo
        generado por este sistema (upsert, no borra nada). Ignora las demas
        tablas y rechaza cualquier otra sentencia. Devuelve cuantas aplico."""
        sentencias = []
        for linea in (sql or "").splitlines():
            linea = linea.strip()
            if not linea or linea.startswith("--") or linea.upper() in ("BEGIN;", "COMMIT;") \
                    or linea.upper().startswith("SET CLIENT_ENCODING"):
                continue
            if linea.startswith("SELECT setval(") or (linea.startswith("INSERT INTO ")
                                                      and linea.split()[2] in ORDEN_RESPALDO
                                                      and linea.split()[2] not in TABLAS_CONOCIMIENTO):
                continue   # datos transaccionales: no se restauran desde la web
            sentencias.append(sentencia_restauracion(linea))
        if not sentencias:
            raise ErrorNegocio("El archivo no contiene datos de conocimiento para restaurar.")
        self._respaldo.ejecutar_parametrizadas(sentencias)
        self._bitacora.registrar("respaldo", None, "modificar", id_empleado,
                                 detalle=f"Restauracion de conocimiento: {len(sentencias)} sentencias")
        return len(sentencias)

    # ------------------------------------------------------------ internos
    def _usuario(self, id_usuario):
        u = self._usuarios.obtener(int(id_usuario))
        if u is None:
            raise ErrorNegocio("El usuario no existe.")
        return u

    def _contar_admins_activos(self) -> int:
        return sum(1 for u in self._usuarios.listar_detallado()
                   if u["id_rol"] == IDS_ROL["administrador"] and u["estado"] == "activo")

    def _no_dejar_sin_admin(self, usuario):
        if usuario.rol == "administrador" and usuario.estado == "activo" and self._contar_admins_activos() <= 1:
            raise ErrorNegocio("No se puede bloquear ni inactivar al unico administrador activo.")

    def _cambiar_estado(self, usuario, estado, accion, id_empleado, detalle):
        with self._db.transaccion() as tx:
            self._usuarios.cambiar_estado(usuario.id_usuario, estado, tx=tx)
            if estado != "activo":   # bloqueo manual o desactivacion: cierra las sesiones abiertas
                self._usuarios.revocar_sesiones(usuario.id_usuario, tx=tx)
            self._bitacora.registrar("usuario", usuario.id_usuario, accion, id_empleado,
                                     detalle=f"{usuario.nombre_usuario}: {detalle}", tx=tx)
