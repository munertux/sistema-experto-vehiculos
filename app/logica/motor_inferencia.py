# -*- coding: utf-8 -*-
"""MotorInferencia: propaga evidencia, selecciona la siguiente pregunta,
contrasta ramas no examinadas y pondera las hipotesis lideres. Replica el
algoritmo descrito en "Estrategia de Inferencia" y "Diseno del Sistema de
Inferencia" del manual tecnico (paginas 43-51), sin contener ninguna
pregunta, regla o relacion sintoma-falla escrita en el codigo: todo se
consulta al RepositorioConocimiento (RNF-07).

Extension a sistema experto (se conserva intacto el algoritmo del manual):
  1. Reglas compuestas: SI c1 Y c2 Y NO c3 ENTONCES h (peso w). Cada
     condicion es una pregunta, un testigo, un codigo OBD o un hecho. La
     regla dispara cuando todas se cumplen; su evidencia es el minimo de
     las evidencias de sus condiciones (e = 2c - 1, o 1 - 2c si esta
     negada) y aporta puntaje(h) += w * e_min, como un granulo.
  2. Encadenamiento hacia adelante: las reglas intermedias concluyen
     hechos que otras reglas consumen; se itera hasta el punto fijo con
     refraccion (cada regla dispara una sola vez).
  3. Testigos y codigos OBD aportan evidencia al iniciar la atencion.
  4. Certeza acotada [0,1] por hipotesis (MYCIN) junto al puntaje.
  5. Explicacion: por_que(memoria, pregunta) y como(memoria, id_hipotesis).
"""
from app.logica.modelos import certeza_a_evidencia, ETIQUETAS_RESPUESTA, Granulo, HipotesisPonderada

SATISFECHA, PENDIENTE, BLOQUEADA = "satisfecha", "pendiente", "bloqueada"
UMBRAL_MINIMO_CERTEZA = 0.20



def _num(x) -> str:
    """Numero con coma decimal para los textos de explicacion."""
    return f"{float(x):g}".replace(".", ",")


def _dec(x) -> str:
    return f"{float(x):.2f}".replace(".", ",")

class MotorInferencia:
    def __init__(self, repo_conocimiento):
        self._repo = repo_conocimiento
        self._p = dict(repo_conocimiento.parametros())
        # certeza minima para presentar una hipotesis como diagnostico
        # (sql/09; si la base aun no lo tiene se usa 0,20)
        self._p.setdefault("umbral_minimo_certeza", UMBRAL_MINIMO_CERTEZA)

    @property
    def umbral_minimo(self) -> float:
        return float(self._p["umbral_minimo_certeza"])

    # ---------------------------------------------------------- iniciar
    def iniciar(self, id_area: int, memoria, testigos=None, codigos_obd=None):
        """Activa las hipotesis del area, aplica la evidencia de los
        testigos del tablero y de los codigos OBD, encadena y devuelve la
        pregunta de entrada del area."""
        for id_h in self._repo.ids_hipotesis_activas(id_area):
            memoria.activar_hipotesis(id_h)
        memoria.testigos = [str(t).upper() for t in (testigos or [])]
        memoria.codigos_obd = [str(c).upper() for c in (codigos_obd or [])]
        for f in self._repo.evidencia_testigos(memoria.testigos):
            granulo = Granulo(id_hipotesis=f["id_hipotesis"], peso=f["peso"])
            memoria.aplicar_evidencia(granulo, 1.0, None, origen="testigo",
                                      detalle={"codigo": "T:" + f["testigo"].upper(), "testigo": f["testigo"].upper()})
        for f in self._repo.evidencia_obd(memoria.codigos_obd):
            granulo = Granulo(id_hipotesis=f["id_hipotesis"], peso=f["peso"])
            memoria.aplicar_evidencia(granulo, 1.0, None, origen="obd",
                                      detalle={"codigo": "OBD:" + f["codigo"], "obd": f["codigo"],
                                               "prefijo": f["prefijo"], "descripcion": f["descripcion"]})
        self.encadenar(memoria)
        entrada = self._repo.pregunta_de_entrada_del_area(id_area)
        memoria.motivo = {"tipo": "entrada", "id_area": id_area,
                          "id_pregunta": entrada.id_pregunta if entrada else None}
        return entrada

    # ------------------------------------------------------- propagar
    def procesar_respuesta(self, memoria, pregunta, respuesta_clave: str, certeza: float):
        memoria.registrar_respuesta(pregunta.id_pregunta, respuesta_clave, certeza)
        evidencia = certeza_a_evidencia(certeza)
        if pregunta.es_entrada:
            granulos = self._repo.granulos_del_area(pregunta.id_area, self._p["peso_entrada"])
        else:
            granulos = self._repo.granulos_de_pregunta(pregunta.id_pregunta)
        detalle = {"id_pregunta": pregunta.id_pregunta, "respuesta": respuesta_clave}
        for granulo in granulos:
            memoria.aplicar_evidencia(granulo, evidencia, pregunta.id_area, detalle=detalle)
        self.encadenar(memoria)
        return granulos

    # -------------------------------------------- encadenamiento adelante
    def encadenar(self, memoria) -> list:
        """Dispara reglas compuestas e intermedias hasta el punto fijo.
        Refraccion: una regla disparada no vuelve a disparar. Devuelve los
        ids disparados en esta llamada, en orden."""
        reglas = self._repo.reglas_compuestas()
        if not reglas:
            return []
        productoras = self._productoras(reglas)
        disparadas = []
        cambio = True
        while cambio:
            cambio = False
            for regla in reglas:
                if regla["id_regla"] in memoria.disparadas:
                    continue
                estado, e_min, premisas = self._evaluar(regla, memoria, productoras)
                if estado != SATISFECHA:
                    continue
                self._disparar(regla, e_min, premisas, memoria)
                disparadas.append(regla["id_regla"])
                cambio = True
        return disparadas

    def _disparar(self, regla, e_min, premisas, memoria):
        detalle = {"codigo": regla["codigo"], "premisas": premisas,
                   "soporte": self._soporte(regla, memoria)}
        if regla["concluye_hecho"]:
            fuerza = min(1.0, e_min * regla["peso"])
            memoria.disparadas[regla["id_regla"]] = ("F", regla["concluye_hecho"])
            memoria.establecer_hecho(regla["concluye_hecho"], fuerza, regla["id_regla"], detalle)
            return
        id_h = regla["id_hipotesis"]
        detalle.update(nivel_atencion=regla["nivel_atencion"], gravedad=regla["gravedad"],
                       recomendacion=regla["recomendacion"])
        memoria.disparadas[regla["id_regla"]] = ("H", id_h)
        granulo = Granulo(id_hipotesis=id_h, peso=regla["peso"], id_regla=regla["id_regla"],
                          nivel_atencion=regla["nivel_atencion"], gravedad=regla["gravedad"],
                          recomendacion=regla["recomendacion"])
        memoria.aplicar_evidencia(granulo, e_min, regla["id_area"], origen="compuesta", detalle=detalle)
        # la traza (reglas_activadas) incluye la cadena de reglas intermedias que la sostienen
        for id_r in self._cadena_intermedia(detalle["soporte"], memoria):
            if id_r not in memoria.traza[id_h]:
                memoria.traza[id_h].append(id_r)

    @staticmethod
    def _soporte(regla, memoria) -> list:
        """Reglas intermedias que establecieron los hechos usados (nivel inmediato)."""
        ids = []
        for c in regla["condiciones"]:
            if c["tipo"] == "hecho" and c["valor_esperado"] == "si":
                ids.extend(memoria.origen_hechos.get(c["referencia"], []))
        return ids

    @staticmethod
    def _cadena_intermedia(ids, memoria) -> list:
        """Cierre transitivo de las reglas intermedias de soporte (orden de disparo)."""
        salida, pendientes = [], list(ids)
        soporte_de = {e["id_regla"]: e.get("soporte", []) for e in memoria.eventos if e["tipo"] == "intermedia"}
        while pendientes:
            id_r = pendientes.pop(0)
            if id_r in salida:
                continue
            salida.append(id_r)
            pendientes.extend(soporte_de.get(id_r, []))
        return salida

    @staticmethod
    def _productoras(reglas) -> dict:
        productoras = {}
        for r in reglas:
            if r["concluye_hecho"]:
                productoras.setdefault(r["concluye_hecho"], []).append(r)
        return productoras

    def _evaluar(self, regla, memoria, productoras, visitados=None):
        """(estado, e_min, premisas). estado: satisfecha | pendiente | bloqueada."""
        premisas, evidencias, estados = [], [], []
        for c in regla["condiciones"]:
            estado, e = self._evaluar_condicion(c, memoria, productoras, visitados)
            premisas.append({"tipo": c["tipo"], "referencia": c["referencia"],
                             "valor_esperado": c["valor_esperado"], "estado": estado,
                             "evidencia": None if e is None else round(e, 4)})
            estados.append(estado)
            if e is not None:
                evidencias.append(e)
        if BLOQUEADA in estados:
            return BLOQUEADA, None, premisas
        if PENDIENTE in estados or not estados:
            return PENDIENTE, None, premisas
        return SATISFECHA, min(evidencias), premisas

    def _evaluar_condicion(self, c, memoria, productoras, visitados):
        tipo, ref, afirmada = c["tipo"], c["referencia"], c["valor_esperado"] != "no"
        if tipo == "pregunta":
            id_p = int(ref)
            if id_p not in memoria.certezas:
                return PENDIENTE, None
            certeza = memoria.certezas[id_p]
            e = (2 * certeza - 1) if afirmada else (1 - 2 * certeza)
            return (SATISFECHA, e) if e > 0 else (BLOQUEADA, e)
        if tipo == "testigo":
            presente = ref.upper() in memoria.testigos
            return (SATISFECHA, 1.0) if presente == afirmada else (BLOQUEADA, -1.0)
        if tipo == "obd":
            presente = any(cod.startswith(ref.upper()) for cod in memoria.codigos_obd)
            return (SATISFECHA, 1.0) if presente == afirmada else (BLOQUEADA, -1.0)
        if tipo == "hecho":
            fuerza = memoria.hechos.get(ref, 0.0)
            if fuerza > 0:
                return (SATISFECHA, fuerza) if afirmada else (BLOQUEADA, -fuerza)
            if self._hecho_refutado(ref, memoria, productoras, visitados):
                # negacion por fallo, solo cuando ya ninguna regla puede concluir el hecho
                return (BLOQUEADA, None) if afirmada else (SATISFECHA, 1.0)
            return PENDIENTE, None
        return BLOQUEADA, None

    def _hecho_refutado(self, codigo, memoria, productoras, visitados=None) -> bool:
        visitados = set(visitados or ()) | {codigo}
        for r in productoras.get(codigo, []):
            if r["id_regla"] in memoria.disparadas:
                return False
            if any(c["tipo"] == "hecho" and c["referencia"] in visitados for c in r["condiciones"]):
                continue   # ciclo: no puede sostener el hecho
            estado, _, _ = self._evaluar(r, memoria, productoras, visitados)
            if estado != BLOQUEADA:
                return False
        return True

    # ------------------------------------------------------- seleccionar
    def siguiente_pregunta(self, memoria, id_area_inicial: int):
        """Escoge la hipotesis con mas evidencia y formula la primera
        pregunta especifica que apunte a ella y no haya sido respondida.
        Primero las de sus granulos directos (manual) y luego las premisas
        pendientes de sus reglas compuestas, incluidas las de las reglas
        intermedias que concluyen los hechos que esas reglas necesitan
        (encadenamiento hacia atras para elegir la pregunta). Si no hay,
        intenta con la siguiente hipotesis del ranking. Si ninguna
        hipotesis activa tiene preguntas pendientes, se evalua contraste
        con otra area (ver _pregunta_de_contraste)."""
        reglas = None
        descartadas = self._areas_descartadas(memoria, id_area_inicial)
        for id_h, _puntaje in memoria.ranking():
            for pregunta in self._repo.preguntas_que_apuntan_a(id_h):
                if pregunta.id_area in descartadas:
                    continue
                if not memoria.fue_respondida(pregunta.id_pregunta):
                    memoria.motivo = {"tipo": "directa", "id_hipotesis": id_h, "id_pregunta": pregunta.id_pregunta}
                    return pregunta
            if reglas is None:
                reglas = self._repo.reglas_compuestas()
                productoras = self._productoras(reglas)
            for regla in reglas:
                if regla["id_hipotesis"] != id_h or regla["id_regla"] in memoria.disparadas:
                    continue
                hallada = self._pregunta_pendiente(regla, memoria, productoras, [])
                if hallada:
                    id_p, cadena = hallada
                    pregunta = self._repo.pregunta(id_p)
                    if pregunta is None or pregunta.id_area in descartadas:
                        continue
                    memoria.motivo = {"tipo": "compuesta", "id_hipotesis": id_h, "id_pregunta": id_p,
                                      "id_regla": regla["id_regla"], "cadena": cadena}
                    return pregunta
        return self._pregunta_de_contraste(memoria, id_area_inicial)

    def _areas_descartadas(self, memoria, id_area_inicial: int) -> set:
        """Areas distintas de la inicial cuya pregunta de entrada (abierta
        por contraste) el consultante nego (certeza < 0,5): en el arbol del
        manual la rama 'No' de la entrada no desciende a sus preguntas
        especificas. El area inicial se recorre siempre (la eligio el
        consultante)."""
        descartadas = set()
        for id_p, certeza in memoria.certezas.items():
            if certeza >= 0.5:
                continue
            pregunta = self._repo.pregunta(id_p)
            if pregunta is not None and pregunta.es_entrada and pregunta.id_area != id_area_inicial:
                descartadas.add(pregunta.id_area)
        return descartadas

    def _pregunta_pendiente(self, regla, memoria, productoras, cadena, visitados=frozenset()):
        """Primera pregunta sin responder que ayudaria a disparar la regla
        (None si la regla ya esta bloqueada). Devuelve (id_pregunta, cadena
        de ids de reglas intermedias recorridas)."""
        estado, _, _ = self._evaluar(regla, memoria, productoras)
        if estado != PENDIENTE:
            return None
        for c in regla["condiciones"]:
            if c["tipo"] == "pregunta" and int(c["referencia"]) not in memoria.certezas:
                return int(c["referencia"]), cadena
            if c["tipo"] == "hecho" and memoria.hechos.get(c["referencia"], 0.0) <= 0:
                if c["referencia"] in visitados:
                    continue
                for prod in productoras.get(c["referencia"], []):
                    if prod["id_regla"] in memoria.disparadas:
                        continue
                    hallada = self._pregunta_pendiente(prod, memoria, productoras, cadena + [prod["id_regla"]],
                                                       visitados | {c["referencia"]})
                    if hallada:
                        return hallada
        return None

    def _pregunta_de_contraste(self, memoria, id_area_inicial: int):
        if memoria.contrastes_usados >= self._p["max_contrastes"]:
            return None
        if len(memoria.preguntas_respondidas) < 3:
            return None
        id_area_dom, proporcion = memoria.area_dominante()
        if proporcion < self._p["umbral_dominancia"]:
            return None
        areas_ya_exploradas = {
            self._repo.pregunta(pid).id_area for pid in memoria.preguntas_respondidas
        }
        candidatas = self._repo.riesgo_por_area(areas_ya_exploradas)
        for id_area in candidatas:
            pregunta = self._repo.pregunta_de_entrada_del_area(id_area)
            if pregunta and not memoria.fue_respondida(pregunta.id_pregunta):
                memoria.contrastes_usados += 1
                for id_h in self._repo.ids_hipotesis_activas(id_area):
                    memoria.activar_hipotesis(id_h)
                memoria.motivo = {"tipo": "contraste", "id_area": id_area, "id_area_dominante": id_area_dom,
                                  "proporcion": round(proporcion, 4), "id_pregunta": pregunta.id_pregunta}
                return pregunta
        return None

    # -------------------------------------------------------- evaluar parada
    def sintoma_confirmado(self, memoria, id_hipotesis: int) -> bool:
        """El sintoma especifico de la hipotesis fue afirmado (granulo
        directo) o una regla compuesta que la concluye ya disparo."""
        if any(c == ("H", id_hipotesis) for c in memoria.disparadas.values()):
            return True
        for pregunta in self._repo.preguntas_que_apuntan_a(id_hipotesis):
            if memoria.respuestas.get(pregunta.id_pregunta) in ("si", "probablemente_si"):
                return True
        return False

    def debe_detenerse(self, memoria) -> bool:
        if len(memoria.preguntas_respondidas) >= self._p["max_preguntas"]:
            return True
        ranking = memoria.ranking()
        if not ranking:
            return False
        id_lider, puntaje_lider = ranking[0]
        total = sum(p for _, p in ranking) or 1e-9
        probabilidad_lider = puntaje_lider / total
        if probabilidad_lider < self._p["umbral_confianza"]:
            return False
        # el sintoma especifico de la hipotesis lider debe haber sido afirmado
        return self.sintoma_confirmado(memoria, id_lider)

    # -------------------------------------------------------- ponderar
    def diagnostico(self, memoria, n: int = None):
        """Hipotesis que se presentan como diagnostico: solo las que tienen
        evidencia positiva suficiente (certeza >= umbral_minimo_certeza).
        Lista vacia = "sin falla identificada"."""
        return self.hipotesis_ponderadas(memoria, n, minimo_certeza=self.umbral_minimo)

    def hipotesis_ponderadas(self, memoria, n: int = None, minimo_certeza: float = None):
        n = int(self._p["num_hipotesis"]) if n is None else int(n)
        ranking = memoria.ranking()
        if minimo_certeza is not None:
            ranking = [(h, p) for h, p in ranking if memoria.certeza(h) >= minimo_certeza - 1e-9]
        mejores = {}

        def mejor(id_h):
            if id_h not in mejores:
                mejores[id_h] = self._mejor_regla(memoria, id_h)
            return mejores[id_h]

        def clave_orden(item):
            id_h, puntaje = item
            m = mejor(id_h)
            gravedad = m["gravedad"] if m else 0
            return (-puntaje, -gravedad)

        ranking = sorted(ranking, key=clave_orden)[:n]
        total = sum(p for _, p in ranking) or 1e-9

        resultado = []
        for posicion, (id_h, puntaje) in enumerate(ranking, start=1):
            hip = self._repo.hipotesis(id_h)
            m = mejor(id_h)
            resultado.append(
                HipotesisPonderada(
                    hipotesis=hip,
                    puntaje=puntaje,
                    probabilidad=puntaje / total,
                    posicion=posicion,
                    id_area=0,
                    nivel_atencion=m["nivel_atencion"] if m else "Sin informacion",
                    recomendacion=m["recomendacion"] if m else "",
                    sintoma_confirmado=self.sintoma_confirmado(memoria, id_h),
                    reglas_activadas=memoria.traza.get(id_h, []),
                    certeza=memoria.certeza(id_h),
                    reglas_compuestas=[r for r, c in memoria.disparadas.items() if c == ("H", id_h)],
                )
            )
        return resultado

    def _mejor_regla(self, memoria, id_h):
        """Regla simple de mayor gravedad (manual); si disparo una regla
        compuesta de gravedad igual o mayor, su recomendacion (mas
        especifica) la reemplaza."""
        mejor = self._repo.mejor_regla_de_hipotesis(id_h)
        for e in memoria.eventos:
            if e["tipo"] == "compuesta" and e["id_hipotesis"] == id_h:
                g = e.get("gravedad", 0)
                if mejor is None or g >= mejor["gravedad"]:
                    mejor = {"codigo": e["codigo"], "nivel_atencion": e["nivel_atencion"], "gravedad": g,
                             "recomendacion": e["recomendacion"]}
        return mejor

    # ======================================================== explicacion
    def por_que(self, memoria, pregunta) -> str:
        """Por que se formula esta pregunta (texto para el consultante)."""
        if pregunta is None:
            return ""
        motivo = memoria.motivo if memoria.motivo and memoria.motivo.get("id_pregunta") == pregunta.id_pregunta \
            else self._motivo_de(memoria, pregunta)
        tipo = motivo.get("tipo")
        if tipo == "entrada" or (pregunta.es_entrada and tipo != "contraste"):
            area = self._repo.area(pregunta.id_area)
            n = len(self._repo.ids_hipotesis_activas(pregunta.id_area))
            texto = (f"Le pregunto esto para abrir el area {area.nombre if area else pregunta.id_area}: "
                     f"la respuesta reparte evidencia (peso {_num(self._p['peso_entrada'])}) entre sus {n} "
                     "hipotesis de falla.")
            lider = self._lider(memoria)
            if lider and lider[2] > 0:
                texto += (f" Con los testigos y codigos OBD registrados, la hipotesis líder es "
                          f"'{lider[1]}' (certeza {lider[2] * 100:.0f} %).")
            return texto
        if tipo == "contraste":
            dominante = self._repo.area(motivo.get("id_area_dominante")) if motivo.get("id_area_dominante") else None
            area = self._repo.area(pregunta.id_area)
            return (f"Pregunta de contraste: la evidencia se concentra en el area "
                    f"{dominante.nombre if dominante else '?'} ({motivo.get('proporcion', 0) * 100:.0f} %), "
                    f"asi que reviso el area {area.nombre if area else pregunta.id_area}, de mayor riesgo, "
                    "antes de concluir.")
        id_h = motivo.get("id_hipotesis")
        if id_h is None:
            return "Le pregunto esto para completar la evidencia antes de concluir."
        hip = self._repo.hipotesis(id_h)
        nombre = hip.nombre if hip else str(id_h)
        ranking = memoria.ranking()
        posicion = next((i for i, (h, _) in enumerate(ranking, start=1) if h == id_h), None)
        total = sum(p for _, p in ranking) or 1e-9
        prob = memoria.puntajes.get(id_h, 0.0) / total * 100
        papel = "la hipotesis líder" if posicion == 1 else f"la hipotesis en evaluacion (puesto {posicion})"
        inicio = (f"Le pregunto esto porque {papel} es '{nombre}' "
                  f"(certeza {memoria.certeza(id_h) * 100:.0f} %, probabilidad relativa {prob:.0f} %)")
        if tipo == "directa":
            regla = self._repo.regla_de(pregunta.id_pregunta, id_h)
            codigo = regla["codigo"] if regla else "?"
            peso = float(regla["peso"]) if regla else 1.0
            return (f"{inicio} y la regla {codigo} la confirmaria si responde que si: "
                    f"SI P{pregunta.id_pregunta} '{pregunta.enunciado}' ENTONCES '{nombre}' (peso {_num(peso)}).")
        reglas = {r["id_regla"]: r for r in self._repo.reglas_compuestas()}
        regla = reglas.get(motivo.get("id_regla"))
        if regla is None:
            return inicio + "."
        productoras = self._productoras(reglas.values())
        _, _, premisas = self._evaluar(regla, memoria, productoras)
        texto = (f"{inicio} y la regla {regla['codigo']} la confirmaria si se cumple: "
                 f"SI {self._premisas_texto(premisas)} (peso {_num(regla['peso'])}).")
        for id_r in motivo.get("cadena") or []:
            inter = reglas.get(id_r)
            if inter:
                _, _, prem = self._evaluar(inter, memoria, productoras)
                texto += (f" La respuesta alimenta la regla intermedia {inter['codigo']}, que concluye el hecho "
                          f"{inter['concluye_hecho']} si se cumple: {self._premisas_texto(prem)}.")
        return texto

    def _motivo_de(self, memoria, pregunta) -> dict:
        """Reconstruye el motivo cuando la pregunta no fue la ultima elegida."""
        if pregunta.es_entrada:
            return {"tipo": "entrada", "id_pregunta": pregunta.id_pregunta}
        reglas = self._repo.reglas_compuestas()
        productoras = self._productoras(reglas)
        for id_h, _ in memoria.ranking():
            if any(p.id_pregunta == pregunta.id_pregunta for p in self._repo.preguntas_que_apuntan_a(id_h)):
                return {"tipo": "directa", "id_hipotesis": id_h, "id_pregunta": pregunta.id_pregunta}
            for regla in reglas:
                if regla["id_hipotesis"] != id_h:
                    continue
                hallada = self._pregunta_pendiente(regla, memoria, productoras, [])
                if hallada and hallada[0] == pregunta.id_pregunta:
                    return {"tipo": "compuesta", "id_hipotesis": id_h, "id_pregunta": pregunta.id_pregunta,
                            "id_regla": regla["id_regla"], "cadena": hallada[1]}
        return {"tipo": "otra", "id_pregunta": pregunta.id_pregunta}

    def _lider(self, memoria):
        ranking = memoria.ranking()
        if not ranking:
            return None
        id_h = ranking[0][0]
        hip = self._repo.hipotesis(id_h)
        return id_h, hip.nombre if hip else str(id_h), memoria.certeza(id_h)

    def _premisa_texto(self, p) -> str:
        neg = "NO " if p["valor_esperado"] == "no" else ""
        ref = p["referencia"]
        if p["tipo"] == "pregunta":
            preg = self._repo.pregunta(int(ref))
            base = f"{neg}P{ref} '{preg.enunciado if preg else ''}'"
        elif p["tipo"] == "testigo":
            base = f"{neg}testigo {ref} encendido"
        elif p["tipo"] == "obd":
            base = f"{neg}codigo OBD {ref}xx"
        else:
            descripcion = self._repo.hechos().get(ref, "")
            base = f"{neg}hecho {ref}" + (f" ({descripcion})" if descripcion else "")
        estado = p.get("estado")
        if estado:
            base += f" [{estado}]"
        return base

    def _premisas_texto(self, premisas) -> str:
        return " Y ".join(self._premisa_texto(p) for p in premisas)

    def como(self, memoria, id_hipotesis: int) -> list:
        """Cadena de razonamiento que sostiene la hipotesis: lista de pasos
        en orden de inferencia. Cada paso es un dict con codigo, tipo
        (testigo | obd | directa | intermedia | compuesta), conclusion,
        premisas (textos), evidencia, peso, aporte (al puntaje), certeza
        (de la hipotesis tras el paso), hechos (codigos usados) y texto."""
        hip = self._repo.hipotesis(id_hipotesis)
        nombre = hip.nombre if hip else str(id_hipotesis)
        eventos = [e for e in memoria.eventos if e.get("id_hipotesis") == id_hipotesis and e["tipo"] != "rama"]
        intermedias = {e["id_regla"]: e for e in memoria.eventos if e["tipo"] == "intermedia"}
        ids_directas = [e["id_regla"] for e in eventos if e["tipo"] == "directa" and e.get("id_regla")]
        codigos = self._repo.codigos_de_reglas(ids_directas) if ids_directas else {}
        pasos, incluidas = [], set()

        def paso_intermedio(id_r):
            if id_r in incluidas or id_r not in intermedias:
                return
            incluidas.add(id_r)
            e = intermedias[id_r]
            for previo in e.get("soporte", []):
                paso_intermedio(previo)
            premisas = [self._premisa_texto(dict(p, estado=None)) for p in e.get("premisas", [])]
            pasos.append({
                "codigo": e.get("codigo"), "tipo": "intermedia", "conclusion": f"Hecho {e['hecho']}",
                "premisas": premisas, "evidencia": e["evidencia"], "peso": None, "aporte": None,
                "certeza": e.get("fuerza_hecho"),
                "hechos": [p["referencia"] for p in e.get("premisas", []) if p["tipo"] == "hecho"],
                "texto": f"{e.get('codigo')}: SI {' Y '.join(premisas)} ENTONCES hecho {e['hecho']} "
                         f"(fuerza {_dec(e.get('fuerza_hecho', 0))})",
            })

        for e in eventos:
            signo = "+" if e["incremento"] >= 0 else ""
            if e["tipo"] in ("testigo", "obd"):
                if e["tipo"] == "testigo":
                    premisas = [f"testigo {e['testigo']} encendido"]
                else:
                    premisas = [f"codigo OBD {e['obd']}" + (f" ({e['descripcion']})" if e.get("descripcion") else "")]
                pasos.append({
                    "codigo": e["codigo"], "tipo": e["tipo"], "conclusion": nombre, "premisas": premisas,
                    "evidencia": e["evidencia"], "peso": e["peso"], "aporte": e["incremento"],
                    "certeza": e["certeza"], "hechos": [],
                    "texto": f"{e['codigo']}: {premisas[0]} -> '{nombre}' (peso {_num(e['peso'])}, "
                             f"aporte {signo}{_dec(e['incremento'])})",
                })
            elif e["tipo"] == "directa":
                codigo = codigos.get(e["id_regla"], str(e["id_regla"]))
                preg = self._repo.pregunta(e["id_pregunta"]) if e.get("id_pregunta") else None
                etiqueta = ETIQUETAS_RESPUESTA.get(e.get("respuesta"), e.get("respuesta"))
                premisas = [f"P{e.get('id_pregunta')} '{preg.enunciado if preg else ''}' = {etiqueta}"]
                pasos.append({
                    "codigo": codigo, "tipo": "directa", "conclusion": nombre, "premisas": premisas,
                    "evidencia": e["evidencia"], "peso": e["peso"], "aporte": e["incremento"],
                    "certeza": e["certeza"], "hechos": [],
                    "texto": f"{codigo}: SI {premisas[0]} ENTONCES '{nombre}' (evidencia {_dec(e['evidencia'])} "
                             f"x peso {_num(e['peso'])} = {signo}{_dec(e['incremento'])})",
                })
            elif e["tipo"] == "compuesta":
                for id_r in e.get("soporte", []):
                    paso_intermedio(id_r)
                premisas = [self._premisa_texto(dict(p, estado=None)) for p in e.get("premisas", [])]
                pasos.append({
                    "codigo": e["codigo"], "tipo": "compuesta", "conclusion": nombre, "premisas": premisas,
                    "evidencia": e["evidencia"], "peso": e["peso"], "aporte": e["incremento"],
                    "certeza": e["certeza"],
                    "hechos": [p["referencia"] for p in e.get("premisas", []) if p["tipo"] == "hecho"],
                    "nivel_atencion": e.get("nivel_atencion"), "gravedad": e.get("gravedad"),
                    "recomendacion": e.get("recomendacion"),
                    "texto": f"{e['codigo']}: SI {' Y '.join(premisas)} ENTONCES '{nombre}' (evidencia mínima "
                             f"{_dec(e['evidencia'])} x peso {_num(e['peso'])} = +{_dec(e['incremento'])})",
                })
        return pasos
