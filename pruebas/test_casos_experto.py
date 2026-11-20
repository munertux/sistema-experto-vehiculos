# -*- coding: utf-8 -*-
"""Batería de casos de prueba del sistema experto (validación del
conocimiento y del motor de inferencia de extremo a extremo).

Cada caso describe a un consultante real: el área que elige, los testigos
del tablero encendidos, los códigos OBD-II leídos y lo que responde a cada
pregunta que el motor le formula (por id de pregunta; las que no figuran se
responden con `defecto`, normalmente "No"). El caso se ejecuta con
ServicioDiagnostico.simular() —el mismo ciclo iniciar/responder/finalizar de
la consulta real, sin escribir en la base transaccional— y se verifican:

  - la hipótesis líder esperada (o "sin falla identificada");
  - la certeza del líder dentro de [certeza_min, certeza_max];
  - el nivel de atención del líder;
  - el número máximo de preguntas formuladas;
  - las reglas que deben (y las que no deben) aparecer en su «¿cómo?»;
  - que el «¿por qué?» de la primera pregunta (o de alguna, cuando el
    líder solo aparece tras responder) mencione la hipótesis líder.

Las preguntas citadas (ids de sql/02_conocimiento.sql):
  9 Arranque · 25 sin ruido ni luces · 26 clic rápido · 27 arranque lento ·
  29 testigo de batería con motor en marcha · 79 chirrido de correa ·
  6 Antirrobo · 89 gira pero no arranca con testigo de inmovilizador ·
  8 Motor · 31 ralentí inestable · 33 humo negro · 34 misfire con vibración ·
  35 golpeteo metálico · 36 humo azul · 38 Check Engine fijo · 39 Check Engine
  parpadeante · 40 testigo de aceite con ruido metálico · 41 aguja de
  temperatura al máximo · 69 baja el nivel de aceite y hay manchas ·
  7 Lubricación · 70 testigo de presión de aceite encendido ·
  20 Temperatura · 42 temperatura sube gradualmente · 43 electroventilador no
  enciende · 2 Frenos · 44 pedal esponjoso · 46 chirrido al frenar · 47 testigo
  ABS · 19 Dirección · 49 dureza al girar · 22 Suspensión · 60 golpe seco en
  baches · 10 Transmisión · 53 embrague patina · 21 Eléctrico · 59 Check
  Engine con fallas en varios sistemas · 11 Combustible · 72 olor a
  combustible · 17 Escape · 77 olor de gases en la cabina · 24 Seguridad
  pasiva · 68 testigo de airbag · 3 Estabilidad · 91 testigo ESP encendido.

Se ejecuta sobre el esquema aislado se_pruebas_experto (sql 01, 02, 05-09).
scripts/informe_casos.py reutiliza CASOS y ejecutar_caso() para generar
informe_casos.md.
"""
from dataclasses import dataclass, field

import pytest

from apoyo_bd import conexion_experto  # noqa: F401 (fixture)
from app.logica import servicio_diagnostico as modulo_diag
from app.logica.errores import ErrorNegocio
from app.logica.servicio_diagnostico import MENSAJE_SIN_FALLA, ServicioDiagnostico
from app.web.presentacion import tildes

SIN_FALLA = None   # lider esperado cuando ninguna hipotesis alcanza la certeza minima


@dataclass
class Caso:
    nombre: str
    area: int
    respuestas: dict                    # {id_pregunta: clave}; el resto -> defecto
    lider: int = SIN_FALLA              # id_hipotesis esperado (None = sin falla)
    certeza_min: float = 0.0
    certeza_max: float = 1.0
    nivel: str = ""                     # prefijo del nivel de atencion (con tildes)
    max_preguntas: int = 15
    reglas: tuple = ()                  # deben aparecer en como() del lider (en este orden relativo)
    reglas_ausentes: tuple = ()         # no deben aparecer en como() del lider
    testigos: tuple = ()
    obd: tuple = ()
    defecto: str = "no"
    por_que_primera: bool = False       # el por_que de la 1.a pregunta ya nombra al lider
    descripcion: str = ""
    extra: dict = field(default_factory=dict)


CASOS = [
    # ------------------------------------------------------------ arranque
    Caso("Arranque: batería descargada (sin ruido ni luces)", 9, {9: "si", 25: "si"},
         lider=1, certeza_min=0.45, certeza_max=0.55, nivel="Revisión próxima", max_preguntas=4,
         reglas=("R01",)),
    Caso("Arranque: bornes sulfatados (clic rápido)", 9, {9: "si", 26: "si"},
         lider=2, certeza_min=0.45, certeza_max=0.55, nivel="Revisión próxima", max_preguntas=4,
         reglas=("R02",)),
    Caso("Arranque: alternador por testigo BATERIA + P0562 (R69→R70→R72)", 9,
         {9: "si", 27: "si", 26: "si", 29: "si"}, testigos=("BATERIA",), obd=("P0562",),
         lider=5, certeza_min=0.85, nivel="Revisión prioritaria", max_preguntas=10,
         reglas=("T:BATERIA", "OBD:P0562", "R05", "R69", "R70", "R72"), por_que_primera=True),
    Caso("Antirrobo: inmovilizador (testigo + gira sin arrancar)", 6, {6: "si", 89: "si"},
         testigos=("INMOVILIZADOR",), lider=65, certeza_min=0.8, nivel="Revisión próxima", max_preguntas=3,
         reglas=("T:INMOVILIZADOR", "R65", "R110"), por_que_primera=True),
    # --------------------------------------------------------------- motor
    Caso("Motor: misfire con CHECK_ENGINE + P0300 (bujías/bobinas)", 8, {8: "si", 34: "si"},
         testigos=("CHECK_ENGINE",), obd=("P0300",), lider=10, certeza_min=0.75,
         nivel="Revisión próxima", max_preguntas=10, reglas=("OBD:P0300", "R10", "R84", "R87")),
    Caso("Motor: misfire severo con Check Engine parpadeante + P0301", 8, {8: "si", 34: "si", 39: "si"},
         testigos=("CHECK_ENGINE",), obd=("P0301",), lider=15, certeza_min=0.8,
         nivel="No debe seguir usándose", max_preguntas=15, reglas=("R84", "R85", "R86")),
    Caso("Motor: mezcla rica (humo negro + ralentí inestable + P0172)", 8, {8: "si", 33: "si", 31: "si"},
         obd=("P0172",), lider=9, certeza_min=0.75, nivel="Revisión próxima", max_preguntas=12,
         reglas=("OBD:P0172", "R75", "R79"), por_que_primera=True),
    Caso("Motor: humo azul sin fugas de aceite → consumo interno (R94)", 8, {8: "si", 36: "si", 69: "no"},
         lider=12, certeza_min=0.75, nivel="Revisión prioritaria", max_preguntas=10, reglas=("R12", "R94")),
    # ---------------------------------------------------------- lubricacion
    Caso("Lubricación: testigo ACEITE + ruido metálico (R90→R91)", 8, {8: "si", 40: "si"},
         testigos=("ACEITE",), lider=16, certeza_min=0.8, nivel="No debe seguir usándose", max_preguntas=9,
         reglas=("T:ACEITE", "R16", "R90", "R91")),
    Caso("Lubricación: presión de aceite con testigo encendido", 7, {7: "si", 70: "si"},
         testigos=("ACEITE",), lider=46, certeza_min=0.65, nivel="No debe seguir usándose", max_preguntas=3,
         reglas=("T:ACEITE", "R46"), por_que_primera=True),
    # ---------------------------------------------------------- temperatura
    Caso("Temperatura: sobrecalentamiento encadenado (R95→R111)", 8, {8: "si", 41: "si"},
         testigos=("TEMPERATURA",), lider=17, certeza_min=0.8, nivel="No debe seguir usándose", max_preguntas=11,
         reglas=("T:TEMPERATURA", "R17", "R95", "R111"), por_que_primera=True),
    Caso("Temperatura: electroventilador que no enciende", 20, {20: "si", 42: "no", 43: "si"},
         testigos=("TEMPERATURA",), lider=19, certeza_min=0.6, nivel="Revisión prioritaria", max_preguntas=4,
         reglas=("T:TEMPERATURA", "R19")),
    # --------------------------------------------------------------- frenos
    Caso("Frenos: testigo ABS + C0035 (sensor de rueda)", 2, {2: "si", 47: "si"},
         testigos=("ABS",), obd=("C0035",), lider=23, certeza_min=0.85, nivel="Revisión prioritaria",
         max_preguntas=3, reglas=("T:ABS", "OBD:C0035", "R23", "R103"), por_que_primera=True),
    Caso("Frenos: pastillas desgastadas (chirrido al frenar)", 2, {2: "si", 46: "si"},
         lider=22, certeza_min=0.45, certeza_max=0.55, nivel="Revisión próxima", max_preguntas=5, reglas=("R22",)),
    Caso("Frenos: pedal esponjoso con testigo FRENOS (R100→R102)", 2, {2: "si", 44: "si"},
         testigos=("FRENOS",), lider=20, certeza_min=0.8, nivel="No debe seguir usándose", max_preguntas=4,
         reglas=("T:FRENOS", "R20", "R100", "R102"), por_que_primera=True),
    # ---------------------------------------------------- otras areas
    Caso("Dirección: dureza al girar con testigo EPS", 19, {19: "si", 49: "si"},
         testigos=("EPS",), lider=25, certeza_min=0.6, nivel="Revisión próxima", max_preguntas=3,
         reglas=("T:EPS", "R25"), por_que_primera=True),
    Caso("Suspensión: golpe seco en baches", 22, {22: "si", 60: "si"},
         lider=36, certeza_min=0.45, certeza_max=0.55, nivel="Revisión próxima", max_preguntas=3, reglas=("R36",)),
    Caso("Transmisión: embrague que patina", 10, {10: "si", 53: "si"},
         lider=29, certeza_min=0.45, certeza_max=0.55, nivel="Revisión próxima", max_preguntas=4, reglas=("R29",)),
    Caso("Eléctrico: ECU con CHECK_ENGINE + U0100", 21, {21: "si", 59: "si"},
         testigos=("CHECK_ENGINE",), obd=("U0100",), lider=35, certeza_min=0.85, nivel="Revisión prioritaria",
         max_preguntas=3, reglas=("T:CHECK_ENGINE", "OBD:U0100", "R35", "R109")),
    Caso("Combustible: olor a combustible y líquido cerca del tanque", 11, {11: "si", 72: "si"},
         lider=48, certeza_min=0.55, nivel="No debe seguir usándose", max_preguntas=4, reglas=("R48",)),
    Caso("Escape: olor de gases dentro de la cabina", 17, {17: "si", 77: "si"},
         lider=53, certeza_min=0.55, nivel="No debe seguir usándose", max_preguntas=3, reglas=("R53",)),
    Caso("Seguridad pasiva: testigo AIRBAG + B0001", 24, {24: "si", 68: "si"},
         testigos=("AIRBAG",), obd=("B0001",), lider=44, certeza_min=0.9, nivel="No debe seguir usándose",
         max_preguntas=3, reglas=("T:AIRBAG", "OBD:B0001", "R44", "R106"), por_que_primera=True),
    Caso("Estabilidad: testigo ESP encendido durante la conducción", 3, {3: "si", 91: "si"},
         testigos=("ESP",), lider=67, certeza_min=0.6, nivel="Revisión prioritaria", max_preguntas=3,
         reglas=("T:ESP", "R67"), por_que_primera=True),
    # ------------------------------------------------- negacion y parciales
    # mismo consultante que el caso del alternador, pero con chirrido de correa
    # (P79 = Si): la condicion negada "NO P79" bloquea R72, la certeza del
    # alternador baja de ~0,89 a ~0,78 y la correa (R73) entra al top 3.
    Caso("Negación: chirrido de correa bloquea R72 (alternador) y dispara R73 (correa)", 9,
         {9: "si", 27: "si", 26: "si", 29: "si", 79: "si"}, testigos=("BATERIA",), obd=("P0562",),
         lider=5, certeza_min=0.7, certeza_max=0.82, nivel="Revisión prioritaria", max_preguntas=10,
         reglas=("T:BATERIA", "OBD:P0562", "R05"), reglas_ausentes=("R72",), por_que_primera=True,
         extra={"en_top3_con_regla": (55, "R73")}),
    Caso("Parcial: 'Probablemente sí' al clic rápido", 9, {9: "si", 26: "probablemente_si"},
         lider=2, certeza_min=0.2, certeza_max=0.3, nivel="Revisión próxima", max_preguntas=5, reglas=("R02",)),
    Caso("Parcial: 'No sé' y 'Probablemente sí' (arranque lento)", 9,
         {9: "si", 25: "no_se", 26: "no_se", 27: "probablemente_si"},
         lider=3, certeza_min=0.2, certeza_max=0.3, nivel="Revisión próxima", max_preguntas=7, reglas=("R03",)),
    # --------------------------------------------------------- sin falla
    Caso("Sin falla: todo 'No' en Arranque", 9, {}, max_preguntas=9),
    Caso("Sin falla: todo 'No' en Frenos", 2, {}, max_preguntas=9),
    Caso("Sin falla: entrada 'Sí' y todo 'Probablemente no'", 9, {9: "si"}, defecto="probablemente_no",
         max_preguntas=9),
    Caso("Sin falla: testigo BATERIA desmentido por las respuestas", 9, {}, testigos=("BATERIA",), max_preguntas=11),
    # --------------------------------------------------------- testigo
    Caso("Testigo sin síntomas: Check Engine fijo y nada más", 8, {38: "si"}, testigos=("CHECK_ENGINE",),
         lider=14, certeza_min=0.6, nivel="Revisión próxima", max_preguntas=4,
         reglas=("T:CHECK_ENGINE", "R14"), por_que_primera=True),
]


# ======================================================================
# Ejecucion de un caso
# ======================================================================
def ejecutar_caso(servicio, caso):
    """Conduce la consulta como lo haria el consultante y devuelve un
    resumen: {"resultado": dict de simular(), "preguntas": [(id, clave,
    por_que)], "lider": dict | None, "como": [codigos del lider]}."""
    dadas, preguntas = {}, []
    resultado = None
    for _ in range(40):
        resultado = servicio.simular(caso.area, list(caso.testigos), list(caso.obd), dadas)
        siguiente = resultado["siguiente"]
        if siguiente is None:
            break
        clave = caso.respuestas.get(siguiente["id_pregunta"], caso.defecto)
        preguntas.append((siguiente["id_pregunta"], clave, siguiente.get("por_que", "")))
        dadas[siguiente["id_pregunta"]] = clave
    hipotesis = resultado["hipotesis"]
    lider = hipotesis[0] if hipotesis else None
    return {"resultado": resultado, "preguntas": preguntas, "lider": lider,
            "como": [p["codigo"] for p in (lider["como"] if lider else [])]}


def verificar_caso(caso, salida) -> list:
    """Lista de incumplimientos (vacia = el caso pasa)."""
    fallas = []
    r, lider, preguntas = salida["resultado"], salida["lider"], salida["preguntas"]
    if not r["detenido"]:
        fallas.append("el motor no concluyo")
    if len(preguntas) > caso.max_preguntas:
        fallas.append(f"{len(preguntas)} preguntas > {caso.max_preguntas}")
    if caso.lider is SIN_FALLA:
        if lider is not None:
            fallas.append(f"esperaba sin falla y el lider es H{lider['id_hipotesis']} (certeza {lider['certeza']})")
        if not r["sin_resultado"] or r["resultado_estado"] != "sin_resultado" or r["mensaje"] != MENSAJE_SIN_FALLA:
            fallas.append("el cierre no se marca como sin_resultado")
        if any(h["advertencia"] for h in r["hipotesis"]):
            fallas.append("aviso rojo sin evidencia")
        return fallas
    if lider is None:
        return fallas + ["sin falla identificada, esperaba H%d" % caso.lider]
    if lider["id_hipotesis"] != caso.lider:
        fallas.append(f"lider H{lider['id_hipotesis']} ({lider['nombre']}), esperaba H{caso.lider}")
    if not caso.certeza_min - 1e-9 <= lider["certeza"] <= caso.certeza_max + 1e-9:
        fallas.append(f"certeza {lider['certeza']} fuera de [{caso.certeza_min}, {caso.certeza_max}]")
    if caso.nivel and not tildes(lider["nivel_atencion"]).startswith(caso.nivel):
        fallas.append(f"nivel {tildes(lider['nivel_atencion'])!r}, esperaba {caso.nivel!r}")
    if lider["advertencia"] != tildes(lider["nivel_atencion"]).startswith("No debe seguir usándose"):
        fallas.append("advertencia incoherente con el nivel")
    como = salida["como"]
    faltan = [c for c in caso.reglas if c not in como]
    if faltan:
        fallas.append(f"faltan en como(): {faltan} (hay {como})")
    elif [como.index(c) for c in caso.reglas] != sorted(como.index(c) for c in caso.reglas):
        # orden de inferencia: testigos/OBD, reglas directas y la cadena intermedia -> compuesta
        fallas.append(f"el orden de inferencia no es {list(caso.reglas)}: {como}")
    presentes = [c for c in caso.reglas_ausentes if c in como]
    if presentes:
        fallas.append(f"no deberian estar en como(): {presentes}")
    nombre = lider["nombre"]
    if caso.por_que_primera and nombre not in preguntas[0][2]:
        fallas.append(f"el por_que de la primera pregunta no menciona al lider: {preguntas[0][2][:160]}")
    if not any(nombre in pq for _, _, pq in preguntas):
        fallas.append("ningun por_que menciona al lider")
    if lider["certeza"] < 0.2 or any(h["certeza"] < 0.2 for h in r["hipotesis"]):
        fallas.append("se presenta una hipotesis por debajo de la certeza minima")
    return fallas


@pytest.fixture(scope="module")
def servicio(conexion_experto):
    modulo_diag._SESIONES.clear()
    yield ServicioDiagnostico(conexion_experto)
    modulo_diag._SESIONES.clear()


def test_la_bateria_tiene_al_menos_veinte_casos():
    assert len(CASOS) >= 20
    assert len({c.nombre for c in CASOS}) == len(CASOS)


@pytest.mark.parametrize("caso", CASOS, ids=[c.nombre for c in CASOS])
def test_caso(servicio, caso):
    salida = ejecutar_caso(servicio, caso)
    assert verificar_caso(caso, salida) == []
    if "en_top3_con_regla" in caso.extra:
        id_h, codigo = caso.extra["en_top3_con_regla"]
        otra = next(h for h in salida["resultado"]["hipotesis"][:3] if h["id_hipotesis"] == id_h)
        assert codigo in [p["codigo"] for p in otra["como"]]


# ======================================================================
# Robustez y validaciones de entrada
# ======================================================================
def test_obd_invalido_se_rechaza(servicio):
    for malo in ("XYZ", "P03", "P03000", "Q0300", "P0G00"):
        with pytest.raises(ErrorNegocio, match="OBD"):
            servicio.iniciar(8, codigos_obd=malo)
        with pytest.raises(ErrorNegocio, match="OBD"):
            servicio.simular(8, None, [malo], {})
    assert servicio.normalizar_obd("p0300; c0035 P0300") == ["P0300", "C0035"]


def test_responder_dos_veces_la_misma_pregunta_no_duplica_evidencia(servicio):
    id_at, p = servicio.iniciar(9)
    r1 = servicio.responder(id_at, p["id_pregunta"], "si")
    r2 = servicio.responder(id_at, p["id_pregunta"], "si")       # doble clic / reintento
    assert r2["estado"] == "en_curso"
    assert r2["pregunta"]["id_pregunta"] == r1["pregunta"]["id_pregunta"]
    assert [(h["id_hipotesis"], h["puntaje"]) for h in r2["hipotesis_en_curso"]] == \
        [(h["id_hipotesis"], h["puntaje"]) for h in r1["hipotesis_en_curso"]]
    modulo_diag._SESIONES.clear()                                 # la reconstruccion coincide
    r3 = ServicioDiagnostico(servicio._repo_a.conexion).estado(id_at)
    assert [(h["id_hipotesis"], h["puntaje"]) for h in r3["hipotesis_en_curso"]] == \
        [(h["id_hipotesis"], h["puntaje"]) for h in r1["hipotesis_en_curso"]]
    # una pregunta que no es la pendiente se rechaza
    with pytest.raises(ErrorNegocio, match="no corresponde"):
        servicio.responder(id_at, 89, "si")


def test_dos_workers_reconstruyen_la_memoria_y_dan_el_mismo_diagnostico(servicio, conexion_experto):
    """Worker A y worker B atienden respuestas alternas de la misma
    atencion: cada uno debe reconstruir la memoria que el otro avanzo y el
    diagnostico final debe ser el de una sola memoria (simular)."""
    caso = next(c for c in CASOS if c.lider == 5)
    worker_a, worker_b = ServicioDiagnostico(conexion_experto), ServicioDiagnostico(conexion_experto)
    memorias = {"a": {}, "b": {}}
    id_at, p = worker_a.iniciar(caso.area, testigos=["Bateria o sistema de carga"], codigos_obd="P0562")
    memorias["a"] = dict(modulo_diag._SESIONES)
    turno, r = "b", None
    while True:
        modulo_diag._SESIONES.clear()
        modulo_diag._SESIONES.update(memorias[turno])             # cada worker con su memoria local
        worker = worker_a if turno == "a" else worker_b
        r = worker.responder(id_at, p["id_pregunta"], caso.respuestas.get(p["id_pregunta"], caso.defecto))
        memorias[turno] = dict(modulo_diag._SESIONES)
        if r["estado"] == "finalizado":
            break
        p = r["pregunta"]
        turno = "a" if turno == "b" else "b"
    esperado = ejecutar_caso(servicio, caso)["resultado"]["hipotesis"]
    assert [(h["id_hipotesis"], h["puntaje"], h["certeza"]) for h in r["resultado"]] == \
        [(h["id_hipotesis"], h["puntaje"], h["certeza"]) for h in esperado]


def test_todo_no_cierra_sin_falla_en_la_atencion_real(servicio, conexion_experto):
    """P1 en la consulta real: no se guarda diagnostico, el cierre es
    distinguible y el detalle no muestra el aviso de 'no debe seguir usandose'."""
    from app.logica.servicio_historial import ServicioHistorial
    id_at, p = servicio.iniciar(2)
    while True:
        r = servicio.responder(id_at, p["id_pregunta"], "no")
        if r["estado"] == "finalizado":
            break
        p = r["pregunta"]
    assert r["resultado"] == [] and r["sin_resultado"] and r["resultado_estado"] == "sin_resultado"
    assert r["mensaje"] == MENSAJE_SIN_FALLA and r["hipotesis_en_curso"] == []
    assert servicio.finalizar(id_at) == []
    estado = servicio.estado(id_at)
    assert estado["estado"] == "finalizado" and estado["sin_resultado"]
    d = ServicioHistorial(conexion_experto).detalle_sin_restriccion(id_at)
    assert d["sin_resultado"] and d["hipotesis"] == [] and not d["advertencia"]
    with pytest.raises(ErrorNegocio):
        servicio.confirmar_falla(id_at, 59)


def test_contraste_negado_no_desciende_al_area(servicio):
    """P3: si el consultante niega la pregunta de entrada de un area de
    contraste, el motor no formula las preguntas especificas de esa area."""
    salida = ejecutar_caso(servicio, Caso("todo no", 9, {}))
    ids = [pid for pid, _, _ in salida["preguntas"]]
    assert 5 in ids                                   # contraste: estacionamiento (mayor riesgo)
    assert 83 not in ids and 84 not in ids            # ... negado: no se baja a sus preguntas
    assert sum(1 for pid in ids if servicio._repo_c.pregunta(pid).id_area != 9) <= 2   # max_contrastes
