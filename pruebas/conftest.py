# -*- coding: utf-8 -*-
"""Configuracion comun de pytest: entorno de pruebas explicito.

main.py crea ``app`` al importarse y exige SECRET_KEY fuera de pruebas o
desarrollo (H-03); aqui se declara el entorno de pruebas para que la
importacion no falle sin la variable."""
import os
import sys

os.environ.setdefault("SE_ENTORNO", "pruebas")
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if RAIZ not in sys.path:
    sys.path.insert(0, RAIZ)
