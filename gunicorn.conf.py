# -*- coding: utf-8 -*-
"""Configuracion de gunicorn. gunicorn carga ./gunicorn.conf.py por defecto,
asi que se aplica tambien en Azure App Service (directorio /home/site/wwwroot).
Los argumentos del comando de arranque tienen prioridad sobre estos valores.

Comando recomendado en Azure (Configuracion > Comando de inicio):
    gunicorn --bind=0.0.0.0 --timeout 120 --workers 2 --threads 4 main:app
"""
import os

import gunicorn.http.wsgi

# H-04: no anunciar "Server: gunicorn" (gunicorn siempre envia la cabecera).
gunicorn.http.wsgi.SERVER = "web"

bind = "0.0.0.0:" + os.environ.get("PORT", "8000")
workers = int(os.environ.get("GUNICORN_WORKERS", "2"))
threads = int(os.environ.get("GUNICORN_THREADS", "4"))
timeout = 120
# X-Forwarded-For/Proto los interpreta la app con ProxyFix (1 salto, Azure);
# se deja forwarded_allow_ips con su valor por defecto.
# Limites de la linea de peticion y cabeceras (valores por defecto explicitos).
limit_request_line = 4094
limit_request_fields = 100
limit_request_field_size = 8190
