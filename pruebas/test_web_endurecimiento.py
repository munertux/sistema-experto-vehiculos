# -*- coding: utf-8 -*-
"""Endurecimiento previo al despliegue (auditoria H-01 a H-08). Sin base de datos."""
import os
import re

import pytest

from main import crear_app
from test_web import CLAVE, Auth, ingresar, servicios, token  # noqa: F401 (fixtures)
from app.web.autenticacion import _destino_seguro
from app.web.limitador import LimitadorVentana, normalizar_ip
from app.web.seguridad import POLITICA_CSP

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = {"TESTING": True, "SECRET_KEY": "prueba", "SESSION_COOKIE_SECURE": False}


def nueva_app(servicios, **config):
    return crear_app(config=dict(BASE, **config), servicios=servicios)


def post_login(cliente, usuario="consultante1", clave="mala1234", ip=None):
    cliente.get("/login")
    cabeceras = {"X-Forwarded-For": ip} if ip else {}
    return cliente.post("/login", data={"usuario": usuario, "clave": clave, "csrf_token": token(cliente)},
                        headers=cabeceras)


# ------------------------------------------------------- H-01 limite por IP
def test_limitador_ventana_deslizante():
    t = [1000.0]
    lim = LimitadorVentana(reloj=lambda: t[0])
    assert all(lim.consumir("k", 3, 60) for _ in range(3))
    assert not lim.consumir("k", 3, 60)
    t[0] += 30
    assert not lim.consumir("k", 3, 60)          # sigue dentro de la ventana
    t[0] += 31
    assert lim.consumir("k", 3, 60)              # los 3 primeros ya salieron
    assert lim.consumir("otra", 3, 60)           # claves independientes


def test_normalizar_ip_quita_puerto_de_azure():
    assert normalizar_ip("203.0.113.7:51234") == "203.0.113.7"
    assert normalizar_ip("[2001:db8::1]:443") == "2001:db8::1"
    assert normalizar_ip("2001:db8::1") == "2001:db8::1"
    assert normalizar_ip("") == "desconocida"


def test_login_limitado_por_ip_responde_429_en_espanol(servicios):
    cliente = nueva_app(servicios, LIMITE_LOGIN_IP=(3, 300)).test_client()
    for _ in range(3):
        assert post_login(cliente, ip="198.51.100.10").status_code == 401
    r = post_login(cliente, ip="198.51.100.10")
    assert r.status_code == 429
    html = r.get_data(as_text=True)
    assert "Demasiados intentos" in html and "Espere" in html
    assert int(r.headers["Retry-After"]) > 0
    # incluso con la clave correcta: el limite va antes de verificar credenciales
    assert post_login(cliente, clave=CLAVE, ip="198.51.100.10").status_code == 429
    # otra IP (X-Forwarded-For via ProxyFix) no queda afectada
    assert post_login(cliente, clave=CLAVE, ip="198.51.100.11").status_code == 302


def test_limite_ignora_el_puerto_en_x_forwarded_for(servicios):
    cliente = nueva_app(servicios, LIMITE_LOGIN_IP=(2, 300)).test_client()
    assert post_login(cliente, ip="198.51.100.20:40001").status_code == 401
    assert post_login(cliente, ip="198.51.100.20:40002").status_code == 401
    assert post_login(cliente, ip="198.51.100.20:40003").status_code == 429


def test_proxyfix_usa_solo_el_ultimo_salto(servicios):
    """Un X-Forwarded-For falsificado por el cliente no evade el limite:
    Azure agrega la IP real al final y ProxyFix(x_for=1) toma esa."""
    cliente = nueva_app(servicios, LIMITE_LOGIN_IP=(2, 300)).test_client()
    for falsa in ("1.1.1.1, 198.51.100.30", "2.2.2.2, 198.51.100.30"):
        assert post_login(cliente, ip=falsa).status_code == 401
    assert post_login(cliente, ip="3.3.3.3, 198.51.100.30").status_code == 429


def test_get_login_no_consume_cupo(servicios):
    cliente = nueva_app(servicios, LIMITE_LOGIN_IP=(1, 300)).test_client()
    for _ in range(5):
        assert cliente.get("/login").status_code == 200
    assert post_login(cliente, clave=CLAVE).status_code == 302


def test_cambio_de_clave_limitado_por_ip(servicios):
    cliente = nueva_app(servicios, LIMITE_CLAVE_IP=(2, 300)).test_client()
    ingresar(cliente, "consultante1")
    datos = {"clave_actual": "x", "clave_nueva": "a", "clave_confirmacion": "b"}
    for _ in range(2):
        assert cliente.post("/cuenta/clave", data=dict(datos, csrf_token=token(cliente))).status_code == 200
    assert cliente.post("/cuenta/clave", data=dict(datos, csrf_token=token(cliente))).status_code == 429


# --------------------------------------- H-06 fallos de la clave actual
def test_cambio_de_clave_corta_la_sesion_tras_cinco_fallos(servicios):
    cliente = nueva_app(servicios).test_client()
    ingresar(cliente, "consultante1")
    with cliente.session_transaction() as s:
        cookie_vieja = dict(s)
    malo = {"clave_actual": "equivocada1", "clave_nueva": "Nueva2026x", "clave_confirmacion": "Nueva2026x"}
    for _ in range(4):
        r = cliente.post("/cuenta/clave", data=dict(malo, csrf_token=token(cliente)))
        assert r.status_code == 200 and "actual no es correcta" in r.get_data(as_text=True)
    r = cliente.post("/cuenta/clave", data=dict(malo, csrf_token=token(cliente)))
    assert r.status_code == 302 and "/login" in r.headers["Location"]
    with cliente.session_transaction() as s:
        assert "id_usuario" not in s
    # reenviar una cookie anterior no reinicia el contador (vive en el servidor)
    with cliente.session_transaction() as s:
        s.update(cookie_vieja)
    bueno = {"clave_actual": CLAVE, "clave_nueva": "Nueva2026x", "clave_confirmacion": "Nueva2026x",
             "csrf_token": cookie_vieja["csrf"]}
    r = cliente.post("/cuenta/clave", data=bueno)
    assert r.status_code == 302 and "/login" in r.headers["Location"]


def test_cambio_de_clave_exitoso_reinicia_el_contador(servicios):
    cliente = nueva_app(servicios).test_client()
    ingresar(cliente, "consultante1")
    malo = {"clave_actual": "equivocada1", "clave_nueva": "Nueva2026x", "clave_confirmacion": "Nueva2026x"}
    bueno = dict(malo, clave_actual=CLAVE)
    for _ in range(4):
        cliente.post("/cuenta/clave", data=dict(malo, csrf_token=token(cliente)))
    assert cliente.post("/cuenta/clave", data=dict(bueno, csrf_token=token(cliente))).status_code == 302
    for _ in range(4):
        r = cliente.post("/cuenta/clave", data=dict(malo, csrf_token=token(cliente)))
        assert r.status_code == 200


# ------------------------------------------------------ H-02 open redirect
@pytest.mark.parametrize("destino", [
    "/\\evil.com", "/%5Cevil.com", "/%5cevil.com", "/%09/evil.com", "/\t/evil.com", "/%0d%0a/evil.com",
    "//evil.com", "///evil.com", "/%2F/evil.com", "/%252F/evil.com", "https://evil.com", "http:evil.com",
    "javascript:alert(1)", "evil.com", " /panel", "/\x00/evil.com", "/　/evil.com", "\\\\evil.com",
    "/login", "/logout", "", None, "/" + "a" * 600,
])
def test_destino_externo_rechazado(destino):
    assert _destino_seguro(destino) is None


@pytest.mark.parametrize("destino", ["/panel", "/consulta/500", "/historial?pagina=2", "/conocimiento/reglas#R10"])
def test_destino_interno_permitido(destino):
    assert _destino_seguro(destino) == destino


@pytest.mark.parametrize("destino", ["/\\evil.com", "/%09/evil.com", "//evil.com", "https://evil.com"])
def test_login_no_redirige_fuera(servicios, destino):
    cliente = nueva_app(servicios).test_client()
    cliente.get("/login")
    r = cliente.post("/login", query_string={"siguiente": destino},
                     data={"usuario": "consultante1", "clave": CLAVE, "csrf_token": token(cliente)})
    assert r.status_code == 302
    assert r.headers["Location"] == "/panel"


def test_login_respeta_destino_interno(servicios):
    cliente = nueva_app(servicios).test_client()
    cliente.get("/login")
    r = cliente.post("/login", query_string={"siguiente": "/historial"},
                     data={"usuario": "consultante1", "clave": CLAVE, "csrf_token": token(cliente)})
    assert r.headers["Location"] == "/historial"


# ------------------------------------------------------- H-03 SECRET_KEY
def test_sin_secret_key_no_arranca_en_produccion(monkeypatch, servicios):
    for var in ("SECRET_KEY", "FLASK_DEBUG", "SE_ENTORNO"):
        monkeypatch.delenv(var, raising=False)
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        crear_app(servicios=servicios)


@pytest.mark.parametrize("var,valor", [("FLASK_DEBUG", "1"), ("SE_ENTORNO", "desarrollo"), ("SE_ENTORNO", "pruebas")])
def test_clave_aleatoria_solo_en_entorno_explicito(monkeypatch, servicios, var, valor):
    for v in ("SECRET_KEY", "FLASK_DEBUG", "SE_ENTORNO"):
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setenv(var, valor)
    assert len(crear_app(servicios=servicios).config["SECRET_KEY"]) >= 32


def test_secret_key_de_entorno(monkeypatch, servicios):
    monkeypatch.delenv("SE_ENTORNO", raising=False)
    monkeypatch.delenv("FLASK_DEBUG", raising=False)
    monkeypatch.setenv("SECRET_KEY", "k" * 64)
    assert crear_app(servicios=servicios).config["SECRET_KEY"] == "k" * 64


# ------------------------------------------------------------ H-04 cabeceras
def test_cabeceras_csp_y_permisos(servicios):
    r = nueva_app(servicios).test_client().get("/login")
    csp = r.headers["Content-Security-Policy"]
    directivas = dict(d.strip().split(" ", 1) for d in csp.split(";"))
    assert "'unsafe-inline'" not in directivas["script-src"] and "'unsafe-eval'" not in directivas["script-src"]
    assert "https://cdnjs.cloudflare.com/ajax/libs/d3/7.9.0/" in directivas["script-src"]
    assert directivas["frame-ancestors"] == "'none'" and directivas["object-src"] == "'none'"
    assert directivas["default-src"] == "'self'" and directivas["form-action"] == "'self'"
    assert "camera=()" in r.headers["Permissions-Policy"]
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["Referrer-Policy"] == "same-origin"


def test_hsts_solo_bajo_https(servicios):
    cliente = nueva_app(servicios).test_client()
    assert "Strict-Transport-Security" not in cliente.get("/login").headers
    r = cliente.get("/login", headers={"X-Forwarded-Proto": "https"})   # Azure termina TLS
    assert r.headers["Strict-Transport-Security"] == "max-age=31536000; includeSubDomains"


def test_respuestas_con_sesion_no_se_cachean(servicios):
    cliente = nueva_app(servicios).test_client()
    ingresar(cliente, "consultante1")
    r = cliente.get("/panel")
    assert r.headers["Cache-Control"] == "no-store" and "Cookie" in r.headers["Vary"]


def _plantillas():
    for raiz, _, archivos in os.walk(os.path.join(RAIZ, "app", "templates")):
        for a in archivos:
            if a.endswith(".html"):
                ruta = os.path.join(raiz, a)
                with open(ruta, encoding="utf-8") as f:
                    yield os.path.relpath(ruta, RAIZ), f.read()


def test_plantillas_sin_javascript_inline():
    """La CSP no permite scripts inline: ni <script> con codigo ni on*=."""
    evento = re.compile(r"<[^>]*\son[a-z]+\s*=", re.I)
    script = re.compile(r"<script(?![^>]*\b(src|type=\"application/json\"))[^>]*>", re.I)
    for ruta, html in _plantillas():
        assert not evento.search(html), f"manejador inline en {ruta}"
        assert not script.search(html), f"<script> inline en {ruta}"
        assert "javascript:" not in html, ruta


def test_scripts_externos_solo_de_origenes_de_la_csp_y_con_sri():
    externos = re.compile(r"<script[^>]*src=\"(https?://[^\"]+)\"[^>]*>", re.I)
    for ruta, html in _plantillas():
        for m in externos.finditer(html):
            assert m.group(1).startswith("https://cdnjs.cloudflare.com/ajax/libs/d3/7.9.0/"), ruta
            assert 'integrity="sha512-' in m.group(0), f"script externo sin SRI en {ruta}"
            assert m.group(1).rsplit("/", 1)[0] + "/" in POLITICA_CSP


def test_gunicorn_conf_oculta_el_banner():
    import runpy
    import gunicorn.http.wsgi
    original = gunicorn.http.wsgi.SERVER
    try:
        conf = runpy.run_path(os.path.join(RAIZ, "gunicorn.conf.py"))
        assert gunicorn.http.wsgi.SERVER != "gunicorn"
        assert conf["workers"] >= 2 and conf["threads"] >= 2 and conf["timeout"] <= 120
    finally:
        gunicorn.http.wsgi.SERVER = original


# --------------------------------------------------- H-08 logout por POST
def test_logout_por_get_no_cierra_la_sesion(servicios):
    cliente = nueva_app(servicios).test_client()
    ingresar(cliente, "consultante1")
    r = cliente.get("/logout")
    assert r.status_code == 302
    with cliente.session_transaction() as s:
        assert s.get("id_usuario")
    cliente.post("/logout", data={"csrf_token": token(cliente)})
    with cliente.session_transaction() as s:
        assert "id_usuario" not in s


def test_logout_por_post_exige_csrf(servicios):
    cliente = nueva_app(servicios).test_client()
    ingresar(cliente, "consultante1")
    assert cliente.post("/logout").status_code == 400
    with cliente.session_transaction() as s:
        assert s.get("id_usuario")


# -------------------------------------------------------- H-07 dependencias
def test_requirements_fijados_y_sin_versiones_vulnerables():
    with open(os.path.join(RAIZ, "requirements.txt"), encoding="utf-8") as f:
        lineas = [l.split("#")[0].strip() for l in f if l.split("#")[0].strip()]
    versiones = {}
    for l in lineas:
        assert "==" in l, f"dependencia sin fijar: {l}"
        nombre, version = l.split("==")
        versiones[nombre.lower()] = tuple(int(x) for x in version.split("."))
    assert versiones["gunicorn"] >= (23, 0, 0)            # CVE-2024-6827
    assert versiones["werkzeug"] >= (3, 0, 6)             # CVE-2024-49767
    assert versiones["jinja2"] >= (3, 1, 6)               # CVE-2025-27516
    assert versiones["psycopg2-binary"] >= (2, 9, 10)
    assert versiones["flask"] >= (3, 1, 3)                # PYSEC-2026-2151


def test_head_login_responde_200(servicios):
    assert nueva_app(servicios).test_client().head("/login").status_code == 200
