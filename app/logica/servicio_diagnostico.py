# -*- coding: utf-8 -*-
"""ServicioDiagnostico: caso de uso CU-03 "Consultar al sistema experto"
(RF03). Abre la atencion, conduce el ciclo de preguntas sucesivas y
cierra el diagnostico. Es la unica clase que la capa de presentacion
conoce de la logica de negocio para la consulta.

Se construye con una Conexion (ServicioDiagnostico(conexion)) o, por
compatibilidad, con los dos repositorios de siempre
(ServicioDiagnostico(repo_conocimiento, repo_atencion))."""
import re
import time
import unicodedata

from app.datos.dao.vehiculo_dao import VehiculoDAO
from app.datos.repositorio_atencion import RepositorioAtencion
from app.datos.repositorio_conocimiento import RepositorioConocimiento
from app.logica.entidades import lista_texto
from app.logica.errores import ErrorNegocio
from app.logica.memoria_trabajo import MemoriaTrabajo
from app.logica.modelos import ESCALA_CERTEZA, ETIQUETAS_RESPUESTA
from app.logica.motor_inferencia import MotorInferencia

# Memoria de trabajo en curso por atencion (equivalente al almacen D2 del DFD).
# Si se pierde (reinicio del servidor u otro worker) se reconstruye
# reproduciendo las respuestas guardadas en atencion_respuesta.
_SESIONES = {}

PATRON_OBD = re.compile(r"^[PCBU][0-9A-F]{4}$")

TESTIGOS_TABLERO = (
    "Check engine (falla del motor)",
    "Bateria o sistema de carga",
    "Presion de aceite",
    "Temperatura del refrigerante",
    "Frenos o freno de estacionamiento",
    "ABS",
    "Airbag",
    "Control de estabilidad o traccion (ESP/TCS)",
    "Presion de neumaticos (TPMS)",
    "Direccion asistida (EPS)",
    "Precalentamiento de bujias (diesel)",
    "Inmovilizador o antirrobo",
    "Nivel bajo de combustible",
)

# Codigo corto de cada testigo (testigo_hipotesis.testigo en sql/08). La
# interfaz sigue enviando las etiquetas; tambien se aceptan los codigos.
CODIGOS_TESTIGO = {
    "Check engine (falla del motor)": "CHECK_ENGINE",
    "Bateria o sistema de carga": "BATERIA",
    "Presion de aceite": "ACEITE",
    "Temperatura del refrigerante": "TEMPERATURA",
    "Frenos o freno de estacionamiento": "FRENOS",
    "ABS": "ABS",
    "Airbag": "AIRBAG",
    "Control de estabilidad o traccion (ESP/TCS)": "ESP",
    "Presion de neumaticos (TPMS)": "TPMS",
    "Direccion asistida (EPS)": "EPS",
    "Precalentamiento de bujias (diesel)": "PRECALENTAMIENTO",
    "Inmovilizador o antirrobo": "INMOVILIZADOR",
    "Nivel bajo de combustible": "COMBUSTIBLE",
}


def _sin_tildes(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", str(texto)) if unicodedata.category(c) != "Mn")


_TESTIGO_POR_CLAVE = {}
for _etiqueta, _codigo in CODIGOS_TESTIGO.items():
    _TESTIGO_POR_CLAVE[_sin_tildes(_etiqueta).strip().lower()] = _codigo
    _TESTIGO_POR_CLAVE[_codigo.lower()] = _codigo


class _RepoEnCache:
    """Envoltorio de solo lectura del RepositorioConocimiento que memoriza
    las consultas durante unos segundos. Lo usa simular(), que recorre el
    motor muchas veces seguidas (generacion del arbol de decision)."""

    def __init__(self, repo, segundos: float = 60.0):
        self._repo = repo
        self._segundos = segundos
        self._cache = {}
        self._desde = time.monotonic()

    def __getattr__(self, nombre):
        metodo = getattr(self._repo, nombre)
        if not callable(metodo):
            return metodo

        def envoltura(*args):
            if time.monotonic() - self._desde > self._segundos:
                self._cache.clear()
                self._desde = time.monotonic()
            clave = (nombre,) + tuple(tuple(a) if isinstance(a, (list, set)) else a for a in args)
            if clave not in self._cache:
                self._cache[clave] = metodo(*args)
            return self._cache[clave]
        return envoltura


class ServicioDiagnostico:
    def __init__(self, conexion_o_repo, repo_atencion=None):
        if repo_atencion is None:
            conexion = conexion_o_repo
            self._repo_c = RepositorioConocimiento(conexion)
            self._repo_a = RepositorioAtencion(conexion)
        else:
            self._repo_c = conexion_o_repo
            self._repo_a = repo_atencion
        self._vehiculos = VehiculoDAO(self._repo_a.conexion)
        self._motor = MotorInferencia(self._repo_c)
        self._motor_simulacion = None

    # ------------------------------------------------------------ catalogos
    def areas(self):
        return self._repo_c.areas()

    @staticmethod
    def testigos_disponibles() -> list:
        return list(TESTIGOS_TABLERO)

    @staticmethod
    def codigos_testigos(testigos) -> list:
        """Etiquetas o codigos de testigos -> codigos cortos (BATERIA, ABS...).
        Ignora mayusculas y tildes; los desconocidos se descartan."""
        salida = []
        for t in lista_texto(testigos):
            codigo = _TESTIGO_POR_CLAVE.get(_sin_tildes(t).strip().lower())
            if codigo and codigo not in salida:
                salida.append(codigo)
        return salida

    # --------------------------------------------------------------- ciclo
    def iniciar(self, id_area: int, id_vehiculo: int = None, testigos=None, codigos_obd=None,
                id_consultante: int = None):
        """Abre la atencion. `testigos` y `codigos_obd` pueden ser lista o
        texto separado por comas. Si se da id_consultante, el vehiculo debe
        ser suyo. Devuelve (id_atencion, pregunta)."""
        area = self._repo_c.area(int(id_area))
        if area is None:
            raise ErrorNegocio("El area seleccionada no existe.")
        if id_vehiculo:
            vehiculo = self._vehiculos.obtener(int(id_vehiculo))
            if vehiculo is None or not vehiculo.activo:
                raise ErrorNegocio("El vehiculo seleccionado no existe o esta inactivo.")
            if id_consultante is not None and vehiculo.id_consultante != int(id_consultante):
                raise ErrorNegocio("El vehiculo seleccionado no pertenece al consultante.")
            id_consultante = vehiculo.id_consultante
        testigos_txt = ", ".join(lista_texto(testigos)) or None
        obd_txt = ", ".join(self.normalizar_obd(codigos_obd)) or None

        memoria = MemoriaTrabajo(self._motor._p["puntaje_base"])
        pregunta = self._motor.iniciar(area.id_area, memoria, self.codigos_testigos(testigos_txt),
                                       lista_texto(obd_txt))
        if pregunta is None:
            raise ErrorNegocio("El area no tiene una pregunta de entrada activa.")
        id_atencion = self._repo_a.abrir(area.id_area, id_vehiculo=id_vehiculo or None, testigos=testigos_txt,
                                         codigos_obd=obd_txt, id_consultante=id_consultante)
        _SESIONES[id_atencion] = {"memoria": memoria, "id_area": area.id_area, "orden": 0, "pendiente": pregunta}
        return id_atencion, self._serializar_pregunta(pregunta, memoria)

    def responder(self, id_atencion: int, id_pregunta: int, respuesta_clave: str):
        sesion = self._sesion(id_atencion)
        if respuesta_clave not in ESCALA_CERTEZA:
            raise ErrorNegocio("Respuesta no valida.")
        pregunta = self._repo_c.pregunta(id_pregunta)
        if pregunta is None:
            raise ErrorNegocio("Pregunta no valida.")

        certeza = ESCALA_CERTEZA[respuesta_clave]
        memoria = sesion["memoria"]
        self._motor.procesar_respuesta(memoria, pregunta, respuesta_clave, certeza)
        sesion["orden"] += 1
        self._repo_a.guardar_respuesta(id_atencion, id_pregunta, respuesta_clave, certeza, sesion["orden"])

        if self._motor.debe_detenerse(memoria):
            return self._respuesta_final(id_atencion)

        siguiente = self._motor.siguiente_pregunta(memoria, sesion["id_area"])
        if siguiente is None:
            return self._respuesta_final(id_atencion)
        sesion["pendiente"] = siguiente
        return {"estado": "en_curso", "pregunta": self._serializar_pregunta(siguiente, memoria),
                "hipotesis_en_curso": self._en_curso(memoria)}

    def _respuesta_final(self, id_atencion: int) -> dict:
        resultado = self.finalizar(id_atencion)
        return {"estado": "finalizado", "resultado": resultado, "hipotesis_en_curso": self._top(resultado)}

    @staticmethod
    def _top(resultado) -> list:
        claves = ("id_hipotesis", "nombre", "puntaje", "probabilidad", "certeza", "nivel_atencion", "posicion")
        return [{k: h.get(k) for k in claves} for h in (resultado or [])[:5]]

    def _en_curso(self, memoria, motor=None) -> list:
        """Top 5 provisional: id_hipotesis, nombre, puntaje, probabilidad
        (% entre las 5), certeza [0,1], nivel_atencion y posicion."""
        motor = motor or self._motor
        return [{"id_hipotesis": hp.hipotesis.id_hipotesis, "nombre": hp.hipotesis.nombre,
                 "puntaje": round(hp.puntaje, 4), "probabilidad": round(hp.probabilidad * 100, 1),
                 "certeza": round(hp.certeza, 4), "nivel_atencion": hp.nivel_atencion, "posicion": hp.posicion}
                for hp in motor.hipotesis_ponderadas(memoria, 5)]

    def hipotesis_en_curso(self, id_atencion: int) -> list:
        """Top 5 provisional (o final, si la atencion ya se cerro)."""
        atencion = self._repo_a.obtener(id_atencion)
        if atencion is None:
            raise ErrorNegocio("La atencion no existe.")
        if atencion.estado != "en_curso":
            return self._top(self.resultado_guardado(id_atencion))
        return self._en_curso(self._sesion(id_atencion)["memoria"])

    def finalizar(self, id_atencion: int):
        """Pondera las hipotesis, guarda el diagnostico (con reglas
        activadas) y cierra la atencion. Si ya estaba cerrada, devuelve el
        diagnostico guardado."""
        atencion = self._repo_a.obtener(id_atencion)
        if atencion is None:
            raise ErrorNegocio("La atencion no existe.")
        if atencion.estado != "en_curso":
            _SESIONES.pop(id_atencion, None)
            return self.resultado_guardado(id_atencion)
        sesion = self._sesion(id_atencion)
        memoria = sesion["memoria"]
        resultados = self._motor.hipotesis_ponderadas(memoria)
        por_hipotesis = self._codigos_por_hipotesis(resultados)
        explicaciones = {hp.hipotesis.id_hipotesis: self._motor.como(memoria, hp.hipotesis.id_hipotesis)
                         for hp in resultados}
        self._repo_a.guardar_diagnostico(id_atencion, resultados, por_hipotesis, explicaciones=explicaciones)
        _SESIONES.pop(id_atencion, None)
        return [self._serializar_hipotesis(hp, por_hipotesis[hp.hipotesis.id_hipotesis],
                                           explicaciones[hp.hipotesis.id_hipotesis]) for hp in resultados]

    def _codigos_por_hipotesis(self, resultados) -> dict:
        ids_regla = {i for hp in resultados for i in hp.reglas_activadas}
        codigos = self._repo_c.codigos_de_reglas(ids_regla)
        return {
            hp.hipotesis.id_hipotesis: self._sin_repetir([codigos.get(i, str(i)) for i in hp.reglas_activadas])
            for hp in resultados
        }

    # ------------------------------------------------------------ simular
    def simular(self, id_area: int, testigos=None, obd=None, respuestas: dict = None) -> dict:
        """Recorre el motor real sin tocar la base transaccional (funcion
        pura y determinista): inicia el area con los testigos y codigos OBD
        y responde, en el orden en que el motor las formula, las preguntas
        que esten en `respuestas` ({id_pregunta: clave}). Se detiene en la
        primera pregunta formulada que no tenga respuesta o cuando el motor
        decide parar.

        Devuelve {"siguiente": pregunta serializada | None,
                  "hipotesis": [hipotesis serializadas, top 5],
                  "detenido": bool (el motor concluyo),
                  "camino": [{"id_pregunta", "respuesta"}] respondidas en orden}."""
        area = self._repo_c.area(int(id_area))
        if area is None:
            raise ErrorNegocio("El area seleccionada no existe.")
        respuestas = {int(k): v for k, v in (respuestas or {}).items()}
        for clave in respuestas.values():
            if clave not in ESCALA_CERTEZA:
                raise ErrorNegocio(f"Respuesta no valida: {clave}.")
        motor = self._motor_de_simulacion()
        memoria = MemoriaTrabajo(motor._p["puntaje_base"])
        pregunta = motor.iniciar(area.id_area, memoria, self.codigos_testigos(testigos), self.normalizar_obd(obd))
        camino, detenido = [], False
        limite = int(motor._p["max_preguntas"]) + int(motor._p["max_contrastes"]) + 5
        while pregunta is not None and pregunta.id_pregunta in respuestas and len(camino) < limite:
            clave = respuestas[pregunta.id_pregunta]
            motor.procesar_respuesta(memoria, pregunta, clave, ESCALA_CERTEZA[clave])
            camino.append({"id_pregunta": pregunta.id_pregunta, "respuesta": clave})
            if motor.debe_detenerse(memoria):
                pregunta, detenido = None, True
                break
            pregunta = motor.siguiente_pregunta(memoria, area.id_area)
            if pregunta is None:
                detenido = True
        resultados = motor.hipotesis_ponderadas(memoria)
        ids_regla = {i for hp in resultados for i in hp.reglas_activadas}
        codigos = motor._repo.codigos_de_reglas(ids_regla)
        hipotesis = [self._serializar_hipotesis(
            hp, self._sin_repetir([codigos.get(i, str(i)) for i in hp.reglas_activadas]),
            motor.como(memoria, hp.hipotesis.id_hipotesis)) for hp in resultados]
        return {"siguiente": self._serializar_pregunta(pregunta, memoria, motor), "hipotesis": hipotesis,
                "detenido": detenido, "camino": camino}

    def _motor_de_simulacion(self):
        if self._motor_simulacion is None:
            self._motor_simulacion = MotorInferencia(_RepoEnCache(self._repo_c))
        return self._motor_simulacion

    def confirmar_falla(self, id_atencion: int, id_hipotesis: int, observacion: str = None):
        diagnostico = self._repo_a.diagnostico(id_atencion)
        if not diagnostico:
            raise ErrorNegocio("La atencion no tiene un diagnostico finalizado.")
        if int(id_hipotesis) not in {d["id_hipotesis"] for d in diagnostico}:
            raise ErrorNegocio("La hipotesis no hace parte del diagnostico de esta atencion.")
        observacion = (observacion or "").strip()[:1000] or None
        self._repo_a.confirmar_falla(id_atencion, int(id_hipotesis), observacion)

    # ------------------------------------------------------------ consultas
    def pertenece(self, id_atencion: int, id_consultante: int) -> bool:
        """True si la atencion es del consultante (para validar en la web)."""
        duenio = self._repo_a.propietario(id_atencion)
        return duenio is not None and int(duenio) == int(id_consultante)

    def estado(self, id_atencion: int) -> dict:
        """Estado actual de la atencion; si esta en curso incluye la
        pregunta pendiente (para retomar la consulta tras recargar)."""
        atencion = self._repo_a.obtener(id_atencion)
        if atencion is None:
            raise ErrorNegocio("La atencion no existe.")
        if atencion.estado != "en_curso":
            return {"estado": "finalizado", "resultado": self.resultado_guardado(id_atencion)}
        sesion = self._sesion(id_atencion)
        return {"estado": "en_curso", "pregunta": self._serializar_pregunta(sesion.get("pendiente"), sesion["memoria"]),
                "hipotesis_en_curso": self._en_curso(sesion["memoria"])}

    def resultado_guardado(self, id_atencion: int) -> list:
        """Diagnostico persistido, con el mismo formato de finalizar()."""
        respuestas = {r["id_pregunta"]: r["respuesta"] for r in self._repo_a.respuestas(id_atencion)}
        salida = []
        for d in self._repo_a.diagnostico(id_atencion):
            mejor = self._repo_c.mejor_regla_de_hipotesis(d["id_hipotesis"])
            pasos = d.get("explicacion") or []
            for paso in pasos:   # la recomendacion de una regla compuesta disparada es mas especifica
                if paso.get("tipo") == "compuesta" and paso.get("nivel_atencion"):
                    if mejor is None or paso.get("gravedad", 0) >= mejor["gravedad"]:
                        mejor = {"nivel_atencion": paso["nivel_atencion"], "gravedad": paso.get("gravedad", 0),
                                 "recomendacion": paso.get("recomendacion", "")}
            nivel = mejor["nivel_atencion"] if mejor else "Sin informacion"
            sintoma = any(respuestas.get(p.id_pregunta) in ("si", "probablemente_si")
                          for p in self._repo_c.preguntas_que_apuntan_a(d["id_hipotesis"])) or \
                any(p.get("tipo") == "compuesta" for p in pasos)
            salida.append({
                "id_hipotesis": d["id_hipotesis"],
                "nombre": d["nombre"],
                "descripcion": d["descripcion"],
                "puntaje": round(d["puntaje"], 4),
                "probabilidad": round(d["probabilidad"] * 100, 1),
                "posicion": d["posicion"],
                "nivel_atencion": nivel,
                "recomendacion": mejor["recomendacion"] if mejor else "",
                "sintoma_confirmado": sintoma,
                "advertencia": nivel.startswith("No debe seguir usandose"),
                "reglas_activadas": lista_texto(d["reglas_activadas"]),
                "falla_confirmada": bool(d["falla_confirmada"]),
                "observacion": d["observacion"],
                "certeza": d.get("certeza") if d.get("certeza") is not None else 0.0,
                "como": pasos,
            })
        return salida

    @staticmethod
    def normalizar_obd(codigos) -> list:
        """Valida codigos OBD-II (P0300, C1234, B0001, U0100)."""
        salida = []
        for c in lista_texto(codigos.replace(";", ",").replace(" ", ",") if isinstance(codigos, str) else codigos):
            c = c.upper()
            if not PATRON_OBD.match(c):
                raise ErrorNegocio(f"Codigo OBD no valido: {c}. Use el formato P0300, C1234, B0001 o U0100.")
            if c not in salida:
                salida.append(c)
        return salida

    # ------------------------------------------------------------ internos
    def _sesion(self, id_atencion: int) -> dict:
        sesion = _SESIONES.get(id_atencion)
        if sesion is None:
            sesion = self._reconstruir(id_atencion)
            if sesion is None:
                raise ErrorNegocio("La atencion no existe o ya fue cerrada.")
            _SESIONES[id_atencion] = sesion
        return sesion

    def _reconstruir(self, id_atencion: int):
        """Reproduce las respuestas guardadas para recuperar la memoria de trabajo."""
        atencion = self._repo_a.obtener(id_atencion)
        if atencion is None or atencion.estado != "en_curso":
            return None
        memoria = MemoriaTrabajo(self._motor._p["puntaje_base"])
        pendiente = self._motor.iniciar(atencion.id_area, memoria, self.codigos_testigos(atencion.testigos_tablero),
                                        lista_texto(atencion.codigos_obd))
        respuestas = self._repo_a.respuestas(id_atencion)
        for r in respuestas:
            pregunta = self._repo_c.pregunta(r["id_pregunta"])
            self._motor.procesar_respuesta(memoria, pregunta, r["respuesta"], r["certeza"])
            # replica la seleccion (puede consumir un contraste, igual que en vivo)
            pendiente = self._motor.siguiente_pregunta(memoria, atencion.id_area)
        return {"memoria": memoria, "id_area": atencion.id_area, "orden": len(respuestas), "pendiente": pendiente}

    @staticmethod
    def _sin_repetir(lista) -> list:
        vistos = []
        for x in lista:
            if x not in vistos:
                vistos.append(x)
        return vistos

    def _serializar_pregunta(self, pregunta, memoria=None, motor=None):
        if pregunta is None:
            return None
        salida = {
            "id_pregunta": pregunta.id_pregunta,
            "id_area": pregunta.id_area,
            "enunciado": pregunta.enunciado,
            "es_entrada": pregunta.es_entrada,
            "opciones": [{"clave": k, "etiqueta": v} for k, v in ETIQUETAS_RESPUESTA.items()],
        }
        if memoria is not None:
            salida["por_que"] = (motor or self._motor).por_que(memoria, pregunta)
        return salida

    @staticmethod
    def _serializar_hipotesis(hp, codigos=None, como=None):
        return {
            "id_hipotesis": hp.hipotesis.id_hipotesis,
            "nombre": hp.hipotesis.nombre,
            "descripcion": hp.hipotesis.descripcion,
            "puntaje": round(hp.puntaje, 4),
            "probabilidad": round(hp.probabilidad * 100, 1),
            "posicion": hp.posicion,
            "nivel_atencion": hp.nivel_atencion,
            "recomendacion": hp.recomendacion,
            "sintoma_confirmado": hp.sintoma_confirmado,
            "advertencia": hp.nivel_atencion.startswith("No debe seguir usandose"),
            "reglas_activadas": list(codigos or []),
            "certeza": round(getattr(hp, "certeza", 0.0), 4),
            "como": list(como or []),
        }
