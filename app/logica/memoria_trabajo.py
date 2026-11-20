# -*- coding: utf-8 -*-
"""Memoria de trabajo de la atencion en curso (logica/memoria_trabajo.py).
Guarda los puntajes acumulados por hipotesis, la traza de reglas activadas
y las respuestas ya registradas, tal como lo describe el Diagrama de Caja
Negra (Figura 20) y el Diagrama de Flujo de Datos nivel 1 (Figura 22).

Ampliacion del motor experto:
  - certezas de las respuestas, testigos y codigos OBD de la atencion;
  - hechos intermedios concluidos (encadenamiento hacia adelante) y las
    reglas compuestas ya disparadas (refraccion: cada una dispara una vez);
  - certeza acotada [0,1] por hipotesis al estilo MYCIN: MB (creencia) y
    MD (descreencia) se combinan con c <- c + e(1 - c); certeza = MB - MD;
  - traza enriquecida (eventos) para explicar el "como" y el "por que".
Todo se reconstruye reproduciendo las respuestas guardadas, por lo que no
hace falta persistir la memoria (ver ServicioDiagnostico._reconstruir).
"""
from app.logica.modelos import ESCALA_CERTEZA

# Peso maximo de un granulo (el CRUD admite 0 < peso <= 2). Un granulo
# aporta a la certeza e_mycin = |peso * e| / PESO_MAXIMO, en [0, 1]: solo
# una regla de peso maximo con respuesta "Si" da certeza total por si sola.
PESO_MAXIMO = 2.0


def combinar_mycin(c: float, e: float) -> float:
    """c <- c + e(1 - c), con e en [0, 1]. Resultado siempre en [0, 1]."""
    e = min(1.0, max(0.0, e))
    return c + e * (1.0 - c)


class MemoriaTrabajo:
    def __init__(self, puntaje_base: float):
        self._puntaje_base = puntaje_base
        self.puntajes = {}          # id_hipotesis -> puntaje acumulado
        self.traza = {}             # id_hipotesis -> lista de ids de regla activados
        self.respuestas = {}        # id_pregunta -> respuesta (texto)
        self.preguntas_respondidas = []   # orden de preguntas respondidas
        self.evidencia_por_area = {}      # id_area -> suma de |evidencia| acumulada
        self.contrastes_usados = 0
        # --- motor experto
        self.certezas = {}          # id_pregunta -> certeza c de la respuesta
        self.testigos = []          # codigos de testigos encendidos (BATERIA, ABS, ...)
        self.codigos_obd = []       # codigos OBD-II leidos (P0300, ...)
        self.hechos = {}            # codigo de hecho -> fuerza (0, 1]
        self.origen_hechos = {}     # codigo de hecho -> [id_regla intermedia]
        self.disparadas = {}        # id_regla compuesta -> ("H", id_h) | ("F", codigo)
        self.mb = {}                # id_hipotesis -> creencia acumulada [0,1]
        self.md = {}                # id_hipotesis -> descreencia acumulada [0,1]
        self.eventos = []           # traza enriquecida (dicts serializables)
        self.motivo = None          # por que se formula la pregunta pendiente

    def activar_hipotesis(self, id_hipotesis: int):
        if id_hipotesis not in self.puntajes:
            self.puntajes[id_hipotesis] = self._puntaje_base
            self.traza[id_hipotesis] = []

    def registrar_respuesta(self, id_pregunta: int, respuesta: str, certeza: float = None):
        self.respuestas[id_pregunta] = respuesta
        self.preguntas_respondidas.append(id_pregunta)
        self.certezas[id_pregunta] = float(ESCALA_CERTEZA.get(respuesta, 0.5) if certeza is None else certeza)

    def fue_respondida(self, id_pregunta: int) -> bool:
        return id_pregunta in self.respuestas

    def aplicar_evidencia(self, granulo, evidencia: float, id_area: int, origen: str = None, detalle: dict = None):
        """puntaje(h) <- max(0, puntaje(h) + peso(g) * e)  (formula pagina 44).

        Ademas actualiza la certeza MYCIN de la hipotesis con
        |peso * e| / PESO_MAXIMO (salvo el granulo de rama de la pregunta de entrada,
        que no es evidencia especifica de ninguna falla) y deja un evento
        en la traza enriquecida. origen: rama | directa | compuesta |
        testigo | obd (por defecto directa si el granulo tiene regla)."""
        origen = origen or ("directa" if granulo.id_regla is not None else "rama")
        self.activar_hipotesis(granulo.id_hipotesis)
        incremento = granulo.peso * evidencia
        nuevo = self.puntajes[granulo.id_hipotesis] + incremento
        self.puntajes[granulo.id_hipotesis] = max(0.0, nuevo)
        if granulo.id_regla is not None and incremento > 0:
            self.traza[granulo.id_hipotesis].append(granulo.id_regla)
        if id_area is not None:
            self.evidencia_por_area[id_area] = self.evidencia_por_area.get(id_area, 0.0) + abs(incremento)
        if origen != "rama" and incremento != 0:
            id_h = granulo.id_hipotesis
            aporte = abs(incremento) / PESO_MAXIMO
            if incremento > 0:
                self.mb[id_h] = combinar_mycin(self.mb.get(id_h, 0.0), aporte)
            else:
                self.md[id_h] = combinar_mycin(self.md.get(id_h, 0.0), aporte)
        evento = {"tipo": origen, "id_hipotesis": granulo.id_hipotesis, "id_regla": granulo.id_regla,
                  "evidencia": round(evidencia, 4), "peso": round(float(granulo.peso), 4),
                  "incremento": round(incremento, 4),
                  "certeza": round(self.certeza(granulo.id_hipotesis), 4),
                  "n_respuestas": len(self.preguntas_respondidas)}
        evento.update(detalle or {})
        self.eventos.append(evento)

    def establecer_hecho(self, codigo: str, fuerza: float, id_regla: int, detalle: dict = None):
        """Concluye (o refuerza, combinando al estilo MYCIN) un hecho intermedio."""
        self.hechos[codigo] = combinar_mycin(self.hechos.get(codigo, 0.0), fuerza)
        self.origen_hechos.setdefault(codigo, []).append(id_regla)
        evento = {"tipo": "intermedia", "hecho": codigo, "id_regla": id_regla, "id_hipotesis": None,
                  "evidencia": round(fuerza, 4), "fuerza_hecho": round(self.hechos[codigo], 4),
                  "n_respuestas": len(self.preguntas_respondidas)}
        evento.update(detalle or {})
        self.eventos.append(evento)

    def certeza(self, id_hipotesis: int) -> float:
        """Certeza acotada [0,1]: creencia menos descreencia (MYCIN), minimo 0."""
        return max(0.0, self.mb.get(id_hipotesis, 0.0) - self.md.get(id_hipotesis, 0.0))

    def ranking(self):
        """Lista (id_hipotesis, puntaje) ordenada de mayor a menor puntaje."""
        return sorted(self.puntajes.items(), key=lambda kv: kv[1], reverse=True)

    def total_evidencia(self) -> float:
        return sum(self.evidencia_por_area.values()) or 1e-9

    def area_dominante(self):
        """Area que concentra la mayor proporcion de evidencia y esa proporcion."""
        if not self.evidencia_por_area:
            return None, 0.0
        id_area, valor = max(self.evidencia_por_area.items(), key=lambda kv: kv[1])
        return id_area, valor / self.total_evidencia()
