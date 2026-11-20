# -*- coding: utf-8 -*-
"""Genera el árbol de decisión REAL del sistema experto recorriendo el
motor de inferencia (no duplica su lógica).

Cada nodo es la pregunta que el motor formula en ese estado; cada rama es
la respuesta del usuario (Sí / No; "Probablemente sí" y "Probablemente
no" se agrupan con su lado y "No sé" no se ramifica porque no aporta
evidencia); cada hoja es el diagnóstico que el motor entrega cuando se
detiene (criterio de parada, sin más preguntas o límite de preguntas).

Adaptadores del motor (se elige automáticamente):
  - AdaptadorSimular: usa ServicioDiagnostico.simular(id_area, testigos,
    obd, respuestas) cuando ese método existe (rama master con B1).
  - AdaptadorMotor: usa directamente MotorInferencia + MemoriaTrabajo
    sobre el RepositorioConocimiento real, con caché en memoria de cada
    consulta (mismo SQL, mismos resultados, sin ir a la BD en cada paso).
    Reproduce exactamente el ciclo de ServicioDiagnostico.responder().

Uso:
    DATABASE_URL=postgresql://postgres:test@localhost:55432/se_arbol?sslmode=disable \
        .venv/bin/python scripts/generar_arbol_decision.py [--profundidad 6] [--salida ruta.json]
        [--adaptador auto|simular|motor] [--standalone exportes/arbol_standalone.html]
"""
import argparse
import datetime as _dt
import json
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if RAIZ not in sys.path:
    sys.path.insert(0, RAIZ)

from app.datos.conexion import Conexion  # noqa: E402
from app.datos.repositorio_conocimiento import RepositorioConocimiento  # noqa: E402
from app.logica.memoria_trabajo import MemoriaTrabajo  # noqa: E402
from app.logica.modelos import ESCALA_CERTEZA  # noqa: E402
from app.logica.motor_inferencia import MotorInferencia  # noqa: E402
from app.web.presentacion import clase_nivel, tildes as _tildes  # noqa: E402  (solo presentación)

DSN_LOCAL = "postgresql://postgres:test@localhost:55432/se_arbol?sslmode=disable"
SALIDA = os.path.join(RAIZ, "app", "static", "arbol_datos.json")
VERSION = 2
PROFUNDIDAD_MAX = 6
# Respuesta canónica con la que se calcula cada rama. Las intermedias
# ("probablemente_si" / "probablemente_no") van por el mismo lado.
RAMAS = (("si", "si"), ("no", "no"))

MOTIVOS = {
    "confianza": "Parada: la hipótesis líder supera el umbral de confianza y su síntoma fue afirmado",
    "max_preguntas": "Parada: se alcanzó el máximo de preguntas",
    "sin_preguntas": "Parada: no quedan preguntas pendientes ni contrastes posibles",
    "profundidad": "Corte de visualización: el motor seguiría preguntando",
    "parada": "Parada del motor",
}


def tx(texto):
    """Texto para mostrar con ortografía restituida (la BD no trae tildes);
    los identificadores no cambian."""
    import re
    return re.sub(r"\bno esta\b", "no está", _tildes(texto))


# ======================================================================
# Repositorio con caché (mismo RepositorioConocimiento, cada consulta una vez)
# ======================================================================
class RepositorioCacheado:
    """Envuelve el RepositorioConocimiento real y memoriza cada llamada
    por (método, argumentos). Las respuestas son idénticas a las de la BD
    porque se obtienen con el mismo SQL; solo se evita repetirlo."""

    def __init__(self, repo):
        self._repo = repo
        self._cache = {}

    @staticmethod
    def _clave(args):
        return tuple(frozenset(a) if isinstance(a, (set, list, tuple)) else a for a in args)

    def __getattr__(self, nombre):
        objetivo = getattr(self._repo, nombre)
        if not callable(objetivo):
            return objetivo

        def envoltura(*args):
            clave = (nombre, self._clave(args))
            if clave not in self._cache:
                self._cache[clave] = objetivo(*args)
            return self._cache[clave]

        return envoltura


def _pregunta_a_dict(p):
    if p is None:
        return None
    if isinstance(p, dict):
        return {
            "id_pregunta": p.get("id_pregunta"),
            "id_area": p.get("id_area"),
            "enunciado": p.get("enunciado") or p.get("texto", ""),
            "sintoma_evaluado": p.get("sintoma_evaluado") or p.get("sintoma") or p.get("enunciado", ""),
            "es_entrada": bool(p.get("es_entrada")),
        }
    return {
        "id_pregunta": p.id_pregunta,
        "id_area": p.id_area,
        "enunciado": p.enunciado,
        "sintoma_evaluado": p.sintoma_evaluado,
        "es_entrada": bool(p.es_entrada),
    }


# ======================================================================
# Adaptadores
# ======================================================================
class AdaptadorMotor:
    """Ciclo idéntico a ServicioDiagnostico.iniciar/responder, sin BD
    transaccional: iniciar -> (procesar_respuesta -> debe_detenerse? ->
    siguiente_pregunta)*."""

    nombre = "motor"

    def __init__(self, conexion):
        self.repo = RepositorioCacheado(RepositorioConocimiento(conexion))
        self.motor = MotorInferencia(self.repo)

    def areas(self):
        return [(a.id_area, a.nombre) for a in self.repo.areas()]

    def pregunta(self, id_pregunta):
        return _pregunta_a_dict(self.repo.pregunta(id_pregunta))

    def paso(self, id_area, respuestas):
        """respuestas: lista ordenada [(id_pregunta, clave)].
        Devuelve {"siguiente": dict|None, "hipotesis": [...], "motivo": str|None}."""
        memoria = MemoriaTrabajo(self.motor._p["puntaje_base"])
        pendiente = self.motor.iniciar(id_area, memoria)
        if not respuestas:
            return {"siguiente": _pregunta_a_dict(pendiente), "hipotesis": [], "motivo": None}
        motivo = None
        for i, (id_pregunta, clave) in enumerate(respuestas):
            if pendiente is None or pendiente.id_pregunta != id_pregunta:
                raise ValueError(f"Camino inválido en el paso {i}: el motor preguntaría "
                                 f"{getattr(pendiente, 'id_pregunta', None)}, no {id_pregunta}")
            self.motor.procesar_respuesta(memoria, pendiente, clave, ESCALA_CERTEZA[clave])
            if self.motor.debe_detenerse(memoria):
                pendiente = None
                maximo = len(memoria.preguntas_respondidas) >= self.motor._p["max_preguntas"]
                motivo = "max_preguntas" if maximo else "confianza"
            else:
                pendiente = self.motor.siguiente_pregunta(memoria, id_area)
                motivo = "sin_preguntas" if pendiente is None else None
            if pendiente is None and i < len(respuestas) - 1:
                raise ValueError("Camino inválido: el motor ya se había detenido")
        # ranking ponderado del estado (diagnóstico final si pendiente es None)
        hipotesis = []
        resultados = self.motor.hipotesis_ponderadas(memoria)
        ids = {i for hp in resultados for i in hp.reglas_activadas}
        codigos = self.repo.codigos_de_reglas(sorted(ids)) if ids else {}
        for hp in resultados:
            reglas = []
            for i in hp.reglas_activadas:
                c = codigos.get(i, str(i))
                if c not in reglas:
                    reglas.append(c)
            hipotesis.append({
                "id_hipotesis": hp.hipotesis.id_hipotesis,
                "nombre": hp.hipotesis.nombre,
                "puntaje": round(hp.puntaje, 4),
                "probabilidad": round(hp.probabilidad * 100, 1),
                "nivel_atencion": hp.nivel_atencion,
                "recomendacion": hp.recomendacion,
                "sintoma_confirmado": hp.sintoma_confirmado,
                "reglas_activadas": reglas,
            })
        return {"siguiente": _pregunta_a_dict(pendiente), "hipotesis": hipotesis, "motivo": motivo}


class AdaptadorSimular:
    """Usa ServicioDiagnostico.simular(id_area, testigos, obd, respuestas)
    -> {"siguiente": pregunta|None, "hipotesis": [...]} (contrato de B1)."""

    nombre = "simular"

    def __init__(self, conexion, testigos=None, obd=None):
        from app.logica.servicio_diagnostico import ServicioDiagnostico
        self.servicio = ServicioDiagnostico(conexion)
        self.repo = RepositorioCacheado(RepositorioConocimiento(conexion))
        self.testigos = testigos or []
        self.obd = obd or []

    def areas(self):
        return [(a.id_area, a.nombre) for a in self.repo.areas()]

    def pregunta(self, id_pregunta):
        return _pregunta_a_dict(self.repo.pregunta(id_pregunta))

    def paso(self, id_area, respuestas):
        r = self.servicio.simular(id_area, self.testigos, self.obd, dict(respuestas))
        siguiente = _pregunta_a_dict(r.get("siguiente"))
        hipotesis = [_hipotesis_normalizada(h) for h in (r.get("hipotesis") or [])]
        motivo = r.get("motivo") or ("parada" if siguiente is None and respuestas else None)
        return {"siguiente": siguiente, "hipotesis": hipotesis, "motivo": motivo}


def _hipotesis_normalizada(h):
    if not isinstance(h, dict):  # HipotesisPonderada
        return {
            "id_hipotesis": h.hipotesis.id_hipotesis, "nombre": h.hipotesis.nombre,
            "puntaje": round(h.puntaje, 4), "probabilidad": round(h.probabilidad * 100, 1),
            "nivel_atencion": h.nivel_atencion, "recomendacion": h.recomendacion,
            "sintoma_confirmado": h.sintoma_confirmado,
            "reglas_activadas": [str(x) for x in h.reglas_activadas],
        }
    prob = h.get("probabilidad", h.get("certeza", 0)) or 0
    if prob <= 1 and "probabilidad" not in h:
        prob *= 100
    return {
        "id_hipotesis": h.get("id_hipotesis"),
        "nombre": h.get("nombre", ""),
        "puntaje": h.get("puntaje"),
        "probabilidad": round(float(prob), 1),
        "nivel_atencion": h.get("nivel_atencion", "Sin informacion"),
        "recomendacion": h.get("recomendacion", ""),
        "sintoma_confirmado": bool(h.get("sintoma_confirmado")),
        "reglas_activadas": [str(x) for x in (h.get("reglas_activadas") or [])],
    }


def crear_adaptador(conexion, tipo="auto"):
    if tipo in ("auto", "simular"):
        from app.logica.servicio_diagnostico import ServicioDiagnostico
        if hasattr(ServicioDiagnostico, "simular"):
            return AdaptadorSimular(conexion)
        if tipo == "simular":
            raise RuntimeError("ServicioDiagnostico.simular() no existe en esta rama")
    return AdaptadorMotor(conexion)


# ======================================================================
# Construcción del árbol
# ======================================================================
def _hoja(resultado, motivo, camino):
    hipotesis = resultado["hipotesis"]
    lider = hipotesis[0] if hipotesis else None
    con_evidencia = bool(lider and (lider.get("puntaje") or 0) > 0)
    return {
        "tipo": "diagnostico",
        "motivo": motivo,
        "motivo_texto": MOTIVOS.get(motivo, MOTIVOS["parada"]),
        "con_evidencia": con_evidencia,
        "hipotesis": tx(lider["nombre"]) if lider else "Sin hipótesis",
        "id_hipotesis": lider["id_hipotesis"] if lider else None,
        "probabilidad": lider["probabilidad"] if lider else 0.0,
        "certeza": round((lider["probabilidad"] if lider else 0.0) / 100, 3),
        "nivel_atencion": tx(lider["nivel_atencion"]) if lider else "Sin información",
        "nivel": clase_nivel(lider["nivel_atencion"]).replace("nivel-", "") if lider else "sin-informacion",
        "recomendacion": tx(lider["recomendacion"]) if lider else "",
        "sintoma_confirmado": bool(lider and lider.get("sintoma_confirmado")),
        "reglas": lider["reglas_activadas"] if lider else [],
        "alternativas": [
            {"hipotesis": tx(h["nombre"]), "probabilidad": h["probabilidad"], "nivel_atencion": tx(h["nivel_atencion"])}
            for h in hipotesis[1:3] if (h.get("puntaje") or 0) > 0
        ],
        "camino": [[pid, r] for pid, r in camino],
        "profundidad": len(camino),
        "caminos": 1,
    }


def construir_area(adaptador, id_area, profundidad_max=PROFUNDIDAD_MAX):
    """Expande en profundidad Sí/No desde la pregunta de entrada hasta que
    el motor se detiene o se alcanza profundidad_max."""
    memo = {}  # estado (conjunto de respuestas) -> resultado del motor

    def consultar(camino):
        clave = frozenset(camino)
        if clave not in memo:
            memo[clave] = adaptador.paso(id_area, list(camino))
        return memo[clave]

    def expandir(camino):
        resultado = consultar(camino)
        siguiente = resultado["siguiente"]
        if siguiente is None:
            return _hoja(resultado, resultado.get("motivo") or "parada", camino)
        if len(camino) >= profundidad_max:
            hoja = _hoja(resultado, "profundidad", camino)
            hoja["siguiente_pregunta"] = tx(siguiente["sintoma_evaluado"])
            return hoja
        nodo = {
            "tipo": "pregunta",
            "id_pregunta": siguiente["id_pregunta"],
            "id_area": siguiente["id_area"],
            "texto": tx(siguiente["enunciado"]),
            "sintoma": tx(siguiente["sintoma_evaluado"]),
            "es_entrada": siguiente["es_entrada"],
            "contraste": siguiente["id_area"] != id_area,
            "profundidad": len(camino),
            "hijos": [],
        }
        for rama, clave in RAMAS:
            hijo = expandir(camino + ((siguiente["id_pregunta"], clave),))
            nodo["hijos"].append({"rama": rama, "nodo": hijo})
        nodo["caminos"] = sum(h["nodo"]["caminos"] for h in nodo["hijos"])
        return nodo

    return expandir(tuple())


# ======================================================================
# Estadísticas
# ======================================================================
def estadisticas(raiz):
    preguntas, hojas, profundidades, hipotesis, cortes, contrastes = 0, 0, [], set(), 0, 0
    pila = [raiz]
    while pila:
        n = pila.pop()
        if n["tipo"] == "pregunta":
            preguntas += 1
            contrastes += 1 if n.get("contraste") else 0
            pila.extend(h["nodo"] for h in n["hijos"])
        else:
            hojas += 1
            profundidades.append(n["profundidad"])
            if n["con_evidencia"]:
                hipotesis.add(n["hipotesis"])
            cortes += 1 if n["motivo"] == "profundidad" else 0
    return {
        "nodos": preguntas + hojas,
        "preguntas": preguntas,
        "hojas": hojas,
        "profundidad_media": round(sum(profundidades) / len(profundidades), 2) if profundidades else 0,
        "profundidad_max": max(profundidades) if profundidades else 0,
        "hipotesis_distintas": len(hipotesis),
        "hojas_por_corte": cortes,
        "nodos_contraste": contrastes,
    }


def generar(adaptador, profundidad_max=PROFUNDIDAD_MAX):
    areas = []
    for id_area, nombre in adaptador.areas():
        raiz = construir_area(adaptador, id_area, profundidad_max)
        areas.append({"id": id_area, "nombre": tx(nombre), "raiz": raiz, "estadisticas": estadisticas(raiz)})
    totales = {
        k: sum(a["estadisticas"][k] for a in areas)
        for k in ("nodos", "preguntas", "hojas", "hojas_por_corte")
    }
    return {
        "version": VERSION,
        "generado": _dt.datetime.now().isoformat(timespec="seconds"),
        "adaptador": adaptador.nombre,
        "profundidad_max": profundidad_max,
        "ramas": {
            "si": "Sí / Probablemente sí",
            "no": "No / Probablemente no",
            "nota": "Cada rama se calcula con la respuesta categórica (Sí = 1.0, No = 0.0). "
                    "\"No sé\" no aporta evidencia (e = 0) y no se ramifica.",
        },
        "totales": totales,
        "areas": areas,
    }


def incrustar_standalone(datos, ruta_html):
    """Página única con datos, JS y CSS incrustados (D3 por cdnjs)."""
    estatico = os.path.join(RAIZ, "app", "static")
    with open(os.path.join(estatico, "arbol.css"), encoding="utf-8") as f:
        css = f.read()
    with open(os.path.join(estatico, "arbol.js"), encoding="utf-8") as f:
        js = f.read()
    datos_js = json.dumps(datos, ensure_ascii=False).replace("</", "<\\/")
    html = PLANTILLA_STANDALONE.replace("/*CSS*/", css).replace("/*DATOS*/", datos_js).replace("/*JS*/", js)
    os.makedirs(os.path.dirname(ruta_html), exist_ok=True)
    with open(ruta_html, "w", encoding="utf-8") as f:
        f.write(html)


PLANTILLA_STANDALONE = """<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Árbol de decisión</title>
<style>/*CSS*/</style>
</head>
<body class="arbol-pagina">
<header class="arbol-cabecera">
  <h1>Árbol de decisión del motor de inferencia</h1>
  <p>Sistema experto de diagnóstico de fallas en vehículos · UMB. Cada nodo es una pregunta que el motor formula; cada rama, una respuesta; cada hoja, el diagnóstico donde el motor se detiene.</p>
</header>
<main id="arbol"></main>
<script>window.ARBOL_DATOS = /*DATOS*/;</script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/d3/7.9.0/d3.min.js"></script>
<script>/*JS*/</script>
</body>
</html>
"""


def main():
    parser = argparse.ArgumentParser(description="Genera el árbol de decisión recorriendo el motor real.")
    parser.add_argument("--dsn", default=os.environ.get("DATABASE_URL", DSN_LOCAL))
    parser.add_argument("--profundidad", type=int, default=PROFUNDIDAD_MAX)
    parser.add_argument("--salida", default=SALIDA)
    parser.add_argument("--adaptador", choices=("auto", "simular", "motor"), default="auto")
    parser.add_argument("--standalone", default=None, help="Ruta de un HTML autónomo a generar")
    args = parser.parse_args()
    if "azure" in args.dsn.lower():
        sys.exit("Por seguridad este script no se ejecuta contra la BD de Azure.")

    adaptador = crear_adaptador(Conexion(args.dsn), args.adaptador)
    datos = generar(adaptador, args.profundidad)
    with open(args.salida, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, separators=(",", ":"))
    print(f"Adaptador: {adaptador.nombre} · profundidad máx {args.profundidad}")
    print(f"{'Área':40s} {'nodos':>6} {'preg':>5} {'hojas':>6} {'prof.media':>10} {'máx':>4} {'cortes':>6}")
    for a in datos["areas"]:
        e = a["estadisticas"]
        print(f"{a['nombre'][:40]:40s} {e['nodos']:6d} {e['preguntas']:5d} {e['hojas']:6d} "
              f"{e['profundidad_media']:10.2f} {e['profundidad_max']:4d} {e['hojas_por_corte']:6d}")
    print("Totales:", datos["totales"])
    print("Escrito:", os.path.relpath(args.salida, RAIZ))
    if args.standalone:
        incrustar_standalone(datos, args.standalone)
        print("Standalone:", args.standalone)


if __name__ == "__main__":
    main()
