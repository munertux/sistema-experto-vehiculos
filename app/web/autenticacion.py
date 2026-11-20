# -*- coding: utf-8 -*-
"""Blueprint de autenticacion: ingreso, salida y cambio de contrasena."""
from urllib.parse import unquote, urlsplit

from flask import (Blueprint, current_app, flash, redirect, render_template,
                   request, session, url_for)

from app.web.seguridad import (PANEL_ROL, autenticado, iniciar_sesion, limitador,
                               limite, login_requerido)
from app.web.servicios import ERRORES_USUARIO, mensaje, servicio

bp = Blueprint("autenticacion", __name__)
LONGITUD_MAX_DESTINO = 512


def _destino_seguro(siguiente):
    """H-02: solo rutas relativas internas ("/algo"), para evitar
    redirecciones abiertas. Se rechaza ademas cualquier valor que, tras
    decodificar %XX, contenga barra invertida, caracteres de control,
    espacios o no ASCII (los navegadores los eliminan o los tratan como "/":
    ``/\\evil.com``, ``/%09/evil.com``, ``/%5Cevil.com``)."""
    if not siguiente or not isinstance(siguiente, str) or len(siguiente) > LONGITUD_MAX_DESTINO:
        return None
    candidatos = [siguiente]
    actual = siguiente
    for _ in range(3):                         # doble o triple codificacion
        decodificado = unquote(actual)
        if decodificado == actual:
            break
        candidatos.append(decodificado)
        actual = decodificado
    for c in candidatos:
        # solo ASCII visible (0x21-0x7E), sin "\\": fuera tabuladores, saltos,
        # espacios, NUL, caracteres Unicode de control o de ancho completo
        if "\\" in c or any(not ("!" <= ch <= "~") for ch in c):
            return None
        if not c.startswith("/") or c.startswith("//"):
            return None
        partes = urlsplit(c)
        if partes.scheme or partes.netloc:
            return None
    if siguiente.startswith(("/login", "/logout")):
        return None
    return siguiente


@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method != "POST":                  # GET y HEAD
        if autenticado():
            return redirect(url_for(PANEL_ROL[session["rol"]]))
        return render_template("login.html", error=None, usuario="")

    nombre_usuario = (request.form.get("usuario") or "").strip()
    clave = request.form.get("clave") or ""
    if not nombre_usuario or not clave:
        return render_template("login.html", error="Ingrese el usuario y la contraseña.",
                               usuario=nombre_usuario), 400
    try:
        datos = servicio("autenticacion").autenticar(nombre_usuario, clave)
    except ERRORES_USUARIO as exc:
        return render_template("login.html", error=mensaje(exc), usuario=nombre_usuario), 401
    iniciar_sesion(datos)
    version = getattr(servicio("autenticacion"), "version_sesion", None)
    if version is not None:
        session["version_sesion"] = version(datos["id_usuario"])
    destino = _destino_seguro(request.args.get("siguiente"))
    return redirect(destino or url_for(PANEL_ROL[session["rol"]]))


@bp.route("/logout", methods=["GET", "POST"])
def logout():
    # H-08: solo POST (con CSRF) cierra la sesion; un GET desde otro sitio
    # (<img src=".../logout">) ya no puede cerrarla.
    if request.method == "GET":
        return redirect(url_for("autenticacion.login"))
    session.clear()
    flash("Sesión cerrada correctamente.", "info")
    return redirect(url_for("autenticacion.login"))


@bp.route("/cuenta/clave", methods=["GET", "POST"])
@login_requerido
def cambiar_clave():
    if request.method == "POST":
        actual = request.form.get("clave_actual") or ""
        nueva = request.form.get("clave_nueva") or ""
        confirmacion = request.form.get("clave_confirmacion") or ""
        # H-06: tope de fallos por usuario (en el servidor, no en la cookie,
        # para que reenviar una cookie vieja no reinicie el contador).
        maximo, ventana = limite("LIMITE_CLAVE_USUARIO")
        clave_lim = ("fallos_clave", session["id_usuario"])
        if not current_app.config.get("LIMITADOR_DESACTIVADO") and \
                limitador().excedido(clave_lim, maximo, ventana):
            return _demasiados_fallos_clave()
        if nueva != confirmacion:
            flash("La confirmación no coincide con la contraseña nueva.", "error")
        else:
            try:
                servicio("autenticacion").cambiar_clave(session["id_usuario"], actual, nueva)
                limitador().reiniciar(clave_lim)
                flash("La contraseña se cambió correctamente.", "exito")
                return redirect(url_for("inicio"))
            except ERRORES_USUARIO as exc:
                limitador().registrar(clave_lim, ventana)
                if not current_app.config.get("LIMITADOR_DESACTIVADO") and \
                        limitador().excedido(clave_lim, maximo, ventana):
                    return _demasiados_fallos_clave()
                flash(mensaje(exc), "error")
    return render_template("cuenta_clave.html")


def _demasiados_fallos_clave():
    current_app.logger.warning("Cambio de clave: demasiados fallos para el usuario %s",
                               session.get("id_usuario"))
    session.clear()
    flash("Demasiados intentos fallidos al cambiar la contraseña. Ingrese de nuevo "
          "o espere unos minutos.", "error")
    return redirect(url_for("autenticacion.login"))
