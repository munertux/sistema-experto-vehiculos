# -*- coding: utf-8 -*-
"""Exporta SVG y PNG (2x) del árbol de decisión de varias áreas usando
Playwright sobre exportes/arbol_standalone.html.

Uso: python scripts/exportar_arbol.py [id_area ...]   (por defecto 9 2 8)
Requiere playwright + chromium (p. ej. el .venv de se-vehiculos-video)."""
import base64
import os
import sys
import unicodedata

from playwright.sync_api import sync_playwright

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXPORTES = os.path.join(RAIZ, "exportes")
HTML = os.path.join(EXPORTES, "arbol_standalone.html")


def nombre_archivo(nombre):
    base = unicodedata.normalize("NFD", nombre).encode("ascii", "ignore").decode().lower()
    return "arbol_" + "".join(c if c.isalnum() else "_" for c in base).strip("_")


def main():
    areas = [int(a) for a in sys.argv[1:]] or [9, 2, 8]
    with sync_playwright() as p:
        nav = p.chromium.launch()
        pagina = nav.new_page(viewport={"width": 1920, "height": 1080}, color_scheme="light")
        pagina.goto("file://" + HTML)
        pagina.wait_for_function("window.ArbolDecision && window.ArbolDecision.area")
        for id_area in areas:
            pagina.evaluate(f"ArbolDecision.modoExportacion({id_area})")
            pagina.wait_for_timeout(800)
            nombre = pagina.evaluate("ArbolDecision.area.nombre")
            base = os.path.join(EXPORTES, nombre_archivo(nombre))
            svg = pagina.evaluate("ArbolDecision.exportarSVG().svg")
            with open(base + ".svg", "w", encoding="utf-8") as f:
                f.write(svg)
            datos = pagina.evaluate("ArbolDecision.exportarPNG(2)")
            with open(base + ".png", "wb") as f:
                f.write(base64.b64decode(datos.split(",", 1)[1]))
            print("Exportado:", os.path.relpath(base, RAIZ), "(.svg/.png)")
        nav.close()


if __name__ == "__main__":
    main()
