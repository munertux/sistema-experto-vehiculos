# -*- coding: utf-8 -*-
"""Seguridad de la capa web: sesion con expiracion por inactividad,
control de acceso por rol, proteccion CSRF, limite de peticiones por IP
y cabeceras HTTP (HSTS, CSP...)."""
import hmac
import secrets
import time
from datetime import timedelta
from functools import wraps

from flask import (abort, current_app, flash, jsonify, redirect, render_template,
                   request, session, url_for)
from werkzeug.middleware.proxy_fix import ProxyFix

from app.web.limitador import LimitadorVentana, normalizar_ip

MINUTOS_INACTIVIDAD = 15
ROLES = ("consultante", "ingeniero", "administrador")
NOMBRE_ROL = {
    "consultante": "Consultante",
    "ingeniero": "Ingeniero del conocimiento",
    "administrador": "Administrador",
}
# Panel de inicio de cada rol (destino de "/").
PANEL_ROL = {
    "consultante": "consultante.panel",
    "ingeniero": "conocimiento.resumen",
    "administrador": "administracion.usuarios",
}
METODOS_INSEGUROS = {"POST", "PUT", "PATCH", "DELETE"}
CLAVES_SESION = ("id_usuario", "nombre_usuario", "rol", "nombres",
                 "id_consultante", "id_empleado")

# Limites por IP (maximo de POST, ventana en segundos). Se pueden
# sobrescribir con app.config (pruebas).
LIMITES_POR_DEFECTO = {
    "LIMITE_LOGIN_IP": (20, 300),         # 20 intentos de ingreso cada 5 min por IP
    "LIMITE_CLAVE_IP": (10, 300),         # 10 cambios de clave cada 5 min por IP
    "LIMITE_CLAVE_USUARIO": (5, 900),     # 5 fallos de la clave actual cada 15 min por usuario
}
ENDPOINTS_LIMITADOS = {
    "autenticacion.login": "LIMITE_LOGIN_IP",
    "autenticacion.cambiar_clave": "LIMITE_CLAVE_IP",
}
CDN_D3 = "https://cdnjs.cloudflare.com/ajax/libs/d3/7.9.0/"
# Sin 'unsafe-inline' en scripts: todo el JS esta en app/static. Los estilos
# admiten 'unsafe-inline' por los atributos style= de las plantillas.
POLITICA_CSP = "; ".join([
    "default-src 'self'",
    f"script-src 'self' {CDN_D3}",
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data: blob:",
    "font-src 'self'",
    "connect-src 'self'",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
])
POLITICA_PERMISOS = ("camera=(), microphone=(), geolocation=(), payment=(), usb=(), "
                     "magnetometer=(), gyroscope=(), accelerometer=()")


def ip_cliente():
    """IP real del cliente (ProxyFix ya tomo X-Forwarded-For de Azure)."""
    return normalizar_ip(request.remote_addr)


def limitador():
    return current_app.extensions["se_limitador"]


def limite(nombre):
    return current_app.config.get(nombre) or LIMITES_POR_DEFECTO[nombre]


def respuesta_429(segundos):
    minutos = max(1, -(-int(segundos) // 60))
    resp = current_app.make_response((render_template(
        "error.html", codigo=429, titulo="Demasiados intentos",
        mensaje=f"Se hicieron demasiados intentos desde su conexión. "
                f"Espere {minutos} minuto(s) e inténtelo de nuevo."), 429))
    resp.headers["Retry-After"] = str(int(segundos))
    return resp


def _es_api():
    return request.path.startswith("/api/")


def autenticado():
    return bool(session.get("id_usuario")) and session.get("rol") in ROLES


def iniciar_sesion(datos):
    """Guarda en la sesion exactamente el diccionario del contrato."""
    session.clear()
    for clave in CLAVES_SESION:
        session[clave] = datos.get(clave)
    session.permanent = True
    session["ultimo_uso"] = int(time.time())
    session["csrf"] = secrets.token_urlsafe(32)


def token_csrf():
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(32)
    return session["csrf"]


def _no_autenticado():
    if _es_api():
        return jsonify({"error": "No autenticado"}), 401
    return redirect(url_for("autenticacion.login", siguiente=request.full_path.rstrip("?")))


def login_requerido(f):
    @wraps(f)
    def envoltura(*args, **kwargs):
        if not autenticado():
            return _no_autenticado()
        return f(*args, **kwargs)
    return envoltura


def rol_requerido(*roles):
    """Permite la vista solo a los roles indicados (403 para los demas)."""
    def decorador(f):
        @wraps(f)
        def envoltura(*args, **kwargs):
            if not autenticado():
                return _no_autenticado()
            if session.get("rol") not in roles:
                if _es_api():
                    return jsonify({"error": "No autorizado para este rol"}), 403
                abort(403)
            return f(*args, **kwargs)
        return envoltura
    return decorador


def instalar(app):
    """Registra en la aplicacion los ganchos de seguridad."""
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(minutes=MINUTOS_INACTIVIDAD)
    app.config["SESSION_REFRESH_EACH_REQUEST"] = True
    # Azure App Service antepone exactamente un proxy (X-Forwarded-For y
    # X-Forwarded-Proto). PROXY_SALTOS=0 lo desactiva (servidor expuesto directo).
    saltos = int(app.config.get("PROXY_SALTOS", 1))
    if saltos > 0:
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=saltos, x_proto=saltos)
    app.extensions["se_limitador"] = LimitadorVentana()

    @app.before_request
    def limitar_por_ip():
        """H-01: limite de POST por IP en el ingreso y el cambio de clave.
        Va antes de cualquier consulta a la base de datos."""
        if request.method != "POST" or app.config.get("LIMITADOR_DESACTIVADO"):
            return None
        nombre = ENDPOINTS_LIMITADOS.get(request.endpoint)
        if not nombre:
            return None
        maximo, ventana = limite(nombre)
        clave = (nombre, ip_cliente())
        if not limitador().consumir(clave, maximo, ventana):
            app.logger.warning("Limite %s excedido desde %s", nombre, clave[1])
            return respuesta_429(limitador().segundos_restantes(clave, ventana))
        return None

    @app.before_request
    def controlar_inactividad():
        if request.endpoint == "static" or not session.get("id_usuario"):
            return None
        ahora = int(time.time())
        ultimo = session.get("ultimo_uso", 0)
        if ahora - ultimo > MINUTOS_INACTIVIDAD * 60:
            session.clear()
            if _es_api():
                return jsonify({"error": "La sesión expiró por inactividad"}), 401
            flash("Su sesión expiró por inactividad. Ingrese de nuevo.", "info")
            return redirect(url_for("autenticacion.login"))
        session["ultimo_uso"] = ahora
        session.permanent = True
        return None

    @app.before_request
    def revalidar_usuario():
        """Corta la sesion si un administrador bloqueo, desactivo, elimino,
        cambio de rol o restablecio la clave del usuario desde que inicio
        sesion (no por el bloqueo automatico de intentos fallidos)."""
        if request.endpoint == "static" or not session.get("id_usuario"):
            return None
        from app.web.servicios import servicio
        svc = servicio("autenticacion")
        vigente = getattr(svc, "sesion_vigente", None)
        if vigente is None:   # dobles de prueba antiguos sin el metodo
            return None
        if "version_sesion" not in session:   # sesiones abiertas antes de esta version
            version = getattr(svc, "version_sesion", None)
            session["version_sesion"] = version(session["id_usuario"]) if version else None
        if vigente(session.get("id_usuario"), session.get("rol"), session.get("version_sesion")):
            return None
        session.clear()
        if request.endpoint in ("autenticacion.login", "autenticacion.logout"):
            return None
        if _es_api():
            return jsonify({"error": "La sesión ya no es válida. Ingrese de nuevo."}), 401
        flash("Su sesión ya no es válida (usuario bloqueado, inactivo o con otro rol). Ingrese de nuevo.", "info")
        return redirect(url_for("autenticacion.login"))

    @app.before_request
    def verificar_csrf():
        if request.method not in METODOS_INSEGUROS or app.config.get("CSRF_DESACTIVADO"):
            return None
        esperado = session.get("csrf")
        recibido = request.headers.get("X-CSRF-Token") or request.form.get("csrf_token")
        if not esperado or not recibido or not hmac.compare_digest(str(esperado), str(recibido)):
            if _es_api():
                return jsonify({"error": "Token CSRF inválido o ausente"}), 400
            if request.endpoint == "autenticacion.login":
                flash("El formulario caducó. Intente ingresar de nuevo.", "error")
                return redirect(url_for("autenticacion.login"))
            return render_template("error.html", codigo=400,
                                   titulo="Solicitud no válida",
                                   mensaje="El formulario caducó o no es válido. "
                                           "Vuelva a la página anterior, recárguela e inténtelo de nuevo."), 400
        return None

    @app.after_request
    def cabeceras_seguridad(resp):
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["Referrer-Policy"] = "same-origin"
        resp.headers["Content-Security-Policy"] = POLITICA_CSP
        resp.headers["Permissions-Policy"] = POLITICA_PERMISOS
        resp.headers["Cross-Origin-Opener-Policy"] = "same-origin"
        if request.is_secure:
            resp.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        if session.get("id_usuario") and request.endpoint != "static":
            resp.headers["Cache-Control"] = "no-store"
            resp.vary.add("Cookie")
        return resp

    @app.context_processor
    def contexto_seguridad():
        return {
            "csrf_token": token_csrf,
            "usuario_actual": {
                "nombre_usuario": session.get("nombre_usuario"),
                "nombres": session.get("nombres"),
                "rol": session.get("rol"),
                "nombre_rol": NOMBRE_ROL.get(session.get("rol"), ""),
            } if autenticado() else None,
        }
