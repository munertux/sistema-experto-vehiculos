# -*- coding: utf-8 -*-
"""Ejecuta la batería de casos del sistema experto (pruebas/test_casos_experto.py)
contra el motor real y genera informe_casos.md con una tabla por caso:
entradas, hipótesis líder, certeza, nivel de atención, preguntas, reglas
del «¿cómo?» y OK/FALLA. Útil para el video y el documento.

Uso:
    DATABASE_URL=postgresql://postgres:test@localhost:55432/se_qa?sslmode=disable \\
        .venv/bin/python scripts/informe_casos.py [--dsn ...] [--salida informe_casos.md]

La base debe tener aplicados sql/01, 02, 05, 06, 07, 08 y 09. Solo lee el
conocimiento (simular() no escribe en la base transaccional).
"""
import argparse
import datetime as _dt
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for ruta in (RAIZ, os.path.join(RAIZ, "pruebas")):
    if ruta not in sys.path:
        sys.path.insert(0, ruta)

from app.datos.conexion import Conexion, _dsn_desde_env  # noqa: E402
from app.datos.entorno import cargar_env  # noqa: E402
from app.logica.modelos import ETIQUETAS_RESPUESTA  # noqa: E402
from app.logica.servicio_diagnostico import ServicioDiagnostico  # noqa: E402
from app.web.presentacion import tildes  # noqa: E402
from test_casos_experto import CASOS, SIN_FALLA, ejecutar_caso, verificar_caso  # noqa: E402

SALIDA = os.path.join(RAIZ, "informe_casos.md")


def _celda(texto) -> str:
    return str(texto).replace("|", "\\|").replace("\n", " ")


def _entradas(servicio, caso) -> str:
    area = servicio.areas()
    nombre_area = next((a.nombre for a in area if a.id_area == caso.area), str(caso.area))
    partes = [f"Área: {tildes(nombre_area)}"]
    if caso.testigos:
        partes.append("Testigos: " + ", ".join(caso.testigos))
    if caso.obd:
        partes.append("OBD: " + ", ".join(caso.obd))
    resp = ", ".join(f"P{p}={tildes(ETIQUETAS_RESPUESTA[c])}" for p, c in caso.respuestas.items())
    partes.append(f"Respuestas: {resp or '—'}; resto: {tildes(ETIQUETAS_RESPUESTA[caso.defecto])}")
    return "<br>".join(partes)


def generar(servicio):
    filas, fallidos = [], []
    for i, caso in enumerate(CASOS, start=1):
        salida = ejecutar_caso(servicio, caso)
        fallas = verificar_caso(caso, salida)
        lider = salida["lider"]
        if lider:
            texto_lider = f"H{lider['id_hipotesis']} {tildes(lider['nombre'])}"
            certeza = f"{lider['certeza']:.2f}".replace(".", ",")
            nivel = tildes(lider["nivel_atencion"])
        else:
            texto_lider, certeza, nivel = "Sin falla identificada", "—", "—"
        esperado = "sin falla" if caso.lider is SIN_FALLA else f"H{caso.lider}"
        camino = " → ".join(f"P{p}:{tildes(ETIQUETAS_RESPUESTA[c])}" for p, c, _ in salida["preguntas"])
        filas.append({
            "n": i, "caso": caso.nombre, "entradas": _entradas(servicio, caso), "lider": texto_lider,
            "esperado": esperado, "certeza": certeza, "nivel": nivel, "preguntas": len(salida["preguntas"]),
            "max": caso.max_preguntas, "reglas": ", ".join(salida["como"]) or "—", "camino": camino,
            "ok": not fallas, "fallas": fallas,
        })
        if fallas:
            fallidos.append((caso.nombre, fallas))
    return filas, fallidos


def escribir(filas, fallidos, ruta, umbral):
    ok = sum(1 for f in filas if f["ok"])
    lineas = [
        "# Batería de casos del sistema experto",
        "",
        f"Generado: {_dt.datetime.now().isoformat(timespec='seconds')} · "
        f"casos: {len(filas)} · OK: {ok} · FALLA: {len(filas) - ok} · "
        f"umbral mínimo de certeza: {umbral:.2f}".replace(".", ",", 1),
        "",
        "Cada caso se ejecuta con `ServicioDiagnostico.simular()` (el mismo ciclo de la consulta real). "
        "Las preguntas no listadas en *Respuestas* se contestan con el valor de *resto*. "
        "Fuente: `pruebas/test_casos_experto.py`; regenerar con `scripts/informe_casos.py`.",
        "",
        "| # | Caso | Entradas | Líder (esperado) | Certeza | Nivel de atención | Preguntas (máx.) | Reglas en «¿cómo?» | Resultado |",
        "|---|------|----------|------------------|---------|-------------------|------------------|--------------------|-----------|",
    ]
    for f in filas:
        lineas.append("| " + " | ".join(_celda(x) for x in (
            f["n"], f["caso"], f["entradas"], f"{f['lider']} ({f['esperado']})", f["certeza"], f["nivel"],
            f"{f['preguntas']} ({f['max']})", f["reglas"], "OK" if f["ok"] else "FALLA")) + " |")
    lineas += ["", "## Camino de preguntas por caso", ""]
    for f in filas:
        lineas.append(f"{f['n']}. **{f['caso']}**: {f['camino'] or '—'}")
    if fallidos:
        lineas += ["", "## Fallas", ""]
        for nombre, fallas in fallidos:
            lineas.append(f"- **{nombre}**: " + "; ".join(fallas))
    lineas.append("")
    with open(ruta, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lineas))


def main():
    parser = argparse.ArgumentParser(description="Ejecuta la batería de casos y genera informe_casos.md.")
    parser.add_argument("--dsn", default=None, help="Cadena de conexión (por defecto DATABASE_URL)")
    parser.add_argument("--salida", default=SALIDA)
    args = parser.parse_args()
    cargar_env()
    dsn = args.dsn or _dsn_desde_env()
    if "azure" in dsn.lower():
        sys.exit("Por seguridad este script no se ejecuta contra la BD de Azure.")
    servicio = ServicioDiagnostico(Conexion(dsn))
    filas, fallidos = generar(servicio)
    escribir(filas, fallidos, args.salida, servicio.umbral_minimo_certeza)
    ok = sum(1 for f in filas if f["ok"])
    print(f"Casos: {len(filas)} · OK: {ok} · FALLA: {len(filas) - ok}")
    print("Escrito:", os.path.relpath(args.salida, RAIZ))
    sys.exit(1 if fallidos else 0)


if __name__ == "__main__":
    main()
