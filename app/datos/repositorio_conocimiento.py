# -*- coding: utf-8 -*-
"""RepositorioConocimiento: consultas granulares a la base de conocimiento
(Tabla 20 del manual). El motor de inferencia nunca ejecuta SQL directo;
siempre pasa por aqui, y esta clase nunca conoce reglas de negocio.

Motor experto (sql/07 y 08): las consultas "simples" del manual solo
consideran reglas sin condiciones en regla_condicion (granulos directos);
las reglas compuestas e intermedias se leen con reglas_compuestas(). Si la
base aun no tiene las tablas de 07, todo se comporta como antes."""
import time

from app.logica.modelos import Area, Pregunta, Hipotesis, Granulo

# Filtro SQL de regla simple (granulo directo del manual); "r" es el alias de reglas.
_SIMPLE_EXPERTO = ("r.id_hipotesis IS NOT NULL AND NOT EXISTS "
                   "(SELECT 1 FROM regla_condicion c WHERE c.id_regla = r.id_regla)")


class RepositorioConocimiento:
    def __init__(self, conexion):
        self._db = conexion
        self._experto = False
        self._revisado = -1e9

    # ------------------------------------------------------ motor experto
    def tiene_motor_experto(self) -> bool:
        """True si la base ya tiene las tablas de sql/07 (se recuerda solo el si)."""
        # el "no" se vuelve a comprobar cada 60 s (por si se aplica 07 con la app en marcha)
        if not self._experto and time.monotonic() - self._revisado > 60:
            fila = self._db.consultar("SELECT to_regclass('regla_condicion') IS NOT NULL "
                                      "AND to_regclass('obd_hipotesis') IS NOT NULL AS ok")
            self._experto = bool(fila and fila[0]["ok"])
            self._revisado = time.monotonic()
        return self._experto

    def _simple(self) -> str:
        return _SIMPLE_EXPERTO if self.tiene_motor_experto() else "TRUE"

    def parametros(self) -> dict:
        filas = self._db.consultar("SELECT clave, valor FROM parametros_inferencia")
        return {f["clave"]: float(f["valor"]) for f in filas}

    def areas(self):
        filas = self._db.consultar("SELECT id_area, nombre, descripcion FROM areas ORDER BY id_area")
        return [Area(**f) for f in filas]

    def ids_hipotesis_activas(self, id_area: int):
        filas = self._db.consultar(
            "SELECT DISTINCT r.id_hipotesis FROM reglas r WHERE r.id_area = %s AND r.activa = TRUE "
            f"AND {self._simple()} ORDER BY r.id_hipotesis",
            (id_area,),
        )
        return [f["id_hipotesis"] for f in filas]

    def pregunta_de_entrada_del_area(self, id_area: int):
        fila = self._db.consultar(
            "SELECT id_pregunta, id_area, enunciado, sintoma_evaluado, es_entrada "
            "FROM preguntas WHERE id_area = %s AND es_entrada = TRUE AND activa = TRUE LIMIT 1",
            (id_area,),
        )
        return Pregunta(**fila[0]) if fila else None

    def pregunta(self, id_pregunta: int):
        fila = self._db.consultar(
            "SELECT id_pregunta, id_area, enunciado, sintoma_evaluado, es_entrada "
            "FROM preguntas WHERE id_pregunta = %s",
            (id_pregunta,),
        )
        return Pregunta(**fila[0]) if fila else None

    def granulos_del_area(self, id_area: int, peso_entrada: float):
        """Granulo de rama: reparte peso_entrada entre todas las hipotesis
        del area (pagina 43-44 del manual)."""
        filas = self._db.consultar(
            "SELECT DISTINCT r.id_hipotesis FROM reglas r WHERE r.id_area = %s AND r.activa = TRUE "
            f"AND {self._simple()} ORDER BY r.id_hipotesis",
            (id_area,),
        )
        return [Granulo(id_hipotesis=f["id_hipotesis"], peso=peso_entrada) for f in filas]

    def granulos_de_pregunta(self, id_pregunta: int):
        """Granulo directo: las reglas de la pregunta respondida, con su
        hipotesis y su peso (1.0 por defecto)."""
        filas = self._db.consultar(
            "SELECT r.id_regla, r.id_hipotesis, r.peso, r.nivel_atencion, r.gravedad, r.recomendacion "
            f"FROM reglas r WHERE r.id_pregunta = %s AND r.activa = TRUE AND {self._simple()} ORDER BY r.id_regla",
            (id_pregunta,),
        )
        return [
            Granulo(
                id_hipotesis=f["id_hipotesis"],
                peso=float(f["peso"]),
                id_regla=f["id_regla"],
                nivel_atencion=f["nivel_atencion"],
                gravedad=f["gravedad"],
                recomendacion=f["recomendacion"],
            )
            for f in filas
        ]

    def preguntas_que_apuntan_a(self, id_hipotesis: int):
        filas = self._db.consultar(
            "SELECT p.id_pregunta, p.id_area, p.enunciado, p.sintoma_evaluado, p.es_entrada "
            "FROM preguntas p JOIN reglas r ON r.id_pregunta = p.id_pregunta "
            f"WHERE r.id_hipotesis = %s AND r.activa = TRUE AND p.activa = TRUE AND {self._simple()} "
            "ORDER BY r.id_regla",
            (id_hipotesis,),
        )
        return [Pregunta(**f) for f in filas]

    def riesgo_por_area(self, ids_area_excluidas):
        excluidas = tuple(ids_area_excluidas) or (-1,)
        filas = self._db.consultar(
            "SELECT r.id_area, MAX(r.gravedad) AS gravedad_max FROM reglas r "
            f"WHERE r.activa = TRUE AND r.id_area NOT IN %s AND {self._simple()} "
            "GROUP BY r.id_area ORDER BY gravedad_max DESC, r.id_area",
            (excluidas,),
        )
        return [f["id_area"] for f in filas]

    def hipotesis(self, id_hipotesis: int):
        fila = self._db.consultar(
            "SELECT id_hipotesis, nombre, descripcion FROM hipotesis WHERE id_hipotesis = %s",
            (id_hipotesis,),
        )
        return Hipotesis(**fila[0]) if fila else None

    def regla_de(self, id_pregunta: int, id_hipotesis: int):
        filas = self._db.consultar(
            "SELECT r.id_regla, r.codigo, r.nivel_atencion, r.gravedad, r.recomendacion, r.peso FROM reglas r "
            f"WHERE r.id_pregunta = %s AND r.id_hipotesis = %s AND r.activa = TRUE AND {self._simple()} "
            "ORDER BY r.id_regla LIMIT 1",
            (id_pregunta, id_hipotesis),
        )
        return filas[0] if filas else None

    def mejor_regla_de_hipotesis(self, id_hipotesis: int):
        """Nivel de atencion y recomendacion de mayor gravedad entre las
        reglas que sustentan la hipotesis (para el resultado final)."""
        filas = self._db.consultar(
            "SELECT r.codigo, r.nivel_atencion, r.gravedad, r.recomendacion FROM reglas r "
            f"WHERE r.id_hipotesis = %s AND r.activa = TRUE AND {self._simple()} "
            "ORDER BY r.gravedad DESC, r.id_regla LIMIT 1",
            (id_hipotesis,),
        )
        return filas[0] if filas else None

    def codigos_de_reglas(self, ids_regla) -> dict:
        """{id_regla: codigo} (la traza del motor guarda ids de regla)."""
        ids = tuple(int(i) for i in ids_regla)
        if not ids:
            return {}
        filas = self._db.consultar("SELECT id_regla, codigo FROM reglas WHERE id_regla IN %s", (ids,))
        return {f["id_regla"]: f["codigo"] for f in filas}

    def area(self, id_area: int):
        fila = self._db.consultar("SELECT id_area, nombre, descripcion FROM areas WHERE id_area = %s", (id_area,))
        return Area(**fila[0]) if fila else None

    def conteos(self):
        filas = self._db.consultar(
            "SELECT 'Areas' AS conocimiento, COUNT(*) AS cantidad FROM areas "
            "UNION ALL SELECT 'Preguntas', COUNT(*) FROM preguntas "
            "UNION ALL SELECT 'Hipotesis', COUNT(*) FROM hipotesis "
            "UNION ALL SELECT 'Reglas', COUNT(*) FROM reglas"
        )
        return filas

    # ------------------------------------------------- conocimiento experto
    def reglas_compuestas(self) -> list:
        """Reglas activas con premisas en regla_condicion (finales e
        intermedias), con sus condiciones en orden. [] sin sql/07."""
        if not self.tiene_motor_experto():
            return []
        filas = self._db.consultar(
            "SELECT r.id_regla, r.codigo, r.id_pregunta, r.id_hipotesis, r.concluye_hecho, r.id_area, "
            "r.nivel_atencion, r.gravedad, r.recomendacion, r.peso, "
            "c.orden, c.tipo, c.referencia, c.valor_esperado "
            "FROM reglas r JOIN regla_condicion c ON c.id_regla = r.id_regla "
            "WHERE r.activa = TRUE ORDER BY r.id_regla, c.orden")
        reglas = {}
        for f in filas:
            regla = reglas.get(f["id_regla"])
            if regla is None:
                regla = reglas[f["id_regla"]] = {
                    k: f[k] for k in ("id_regla", "codigo", "id_pregunta", "id_hipotesis", "concluye_hecho",
                                      "id_area", "nivel_atencion", "gravedad", "recomendacion")}
                regla["peso"] = float(f["peso"])
                regla["condiciones"] = []
            regla["condiciones"].append({"tipo": f["tipo"], "referencia": str(f["referencia"]).strip(),
                                         "valor_esperado": f["valor_esperado"]})
        return [r for r in reglas.values() if r["id_hipotesis"] is not None or r["concluye_hecho"]]

    def hechos(self) -> dict:
        """{codigo: descripcion} de los hechos intermedios."""
        if not self.tiene_motor_experto():
            return {}
        return {f["codigo"]: f["descripcion"] for f in
                self._db.consultar("SELECT codigo, descripcion FROM hechos ORDER BY codigo")}

    def evidencia_testigos(self, testigos) -> list:
        """Filas (testigo, id_hipotesis, peso) de los testigos encendidos."""
        codigos = sorted({str(t).upper() for t in testigos or []})
        if not codigos or not self.tiene_motor_experto():
            return []
        filas = self._db.consultar(
            "SELECT t.testigo, t.id_hipotesis, t.peso FROM testigo_hipotesis t "
            "JOIN hipotesis h ON h.id_hipotesis = t.id_hipotesis "
            "WHERE upper(t.testigo) = ANY(%s) ORDER BY t.testigo, t.id_hipotesis", (codigos,))
        return [dict(f, peso=float(f["peso"])) for f in filas]

    def evidencia_obd(self, codigos_obd) -> list:
        """Por cada codigo y cada hipotesis, la fila del prefijo mas largo
        que lo cubre: (codigo, prefijo, id_hipotesis, peso, descripcion)."""
        codigos = sorted({str(c).upper() for c in codigos_obd or []})
        if not codigos or not self.tiene_motor_experto():
            return []
        filas = self._db.consultar(
            "SELECT DISTINCT ON (c.codigo, o.id_hipotesis) c.codigo, o.prefijo, o.id_hipotesis, o.peso, "
            "o.descripcion FROM unnest(%s::text[]) AS c(codigo) "
            "JOIN obd_hipotesis o ON c.codigo LIKE upper(o.prefijo) || '%%' "
            "ORDER BY c.codigo, o.id_hipotesis, length(o.prefijo) DESC", (codigos,))
        return [dict(f, peso=float(f["peso"])) for f in filas]

    def base_conocimiento(self) -> dict:
        """Volcado completo (JSON) de la base de conocimiento para la API."""
        experto = self.tiene_motor_experto()
        areas = self._db.consultar("SELECT id_area, nombre, descripcion FROM areas ORDER BY id_area")
        preguntas = self._db.consultar(
            "SELECT id_pregunta, id_area, enunciado, sintoma_evaluado, es_entrada, activa "
            "FROM preguntas ORDER BY id_pregunta")
        hipotesis = self._db.consultar("SELECT id_hipotesis, nombre, descripcion FROM hipotesis ORDER BY id_hipotesis")
        extra = ", r.concluye_hecho" if experto else ", NULL AS concluye_hecho"
        reglas = self._db.consultar(
            "SELECT r.id_regla, r.codigo, r.id_pregunta, r.id_hipotesis, r.id_area, r.nivel_atencion, "
            f"r.gravedad, r.recomendacion, r.peso, r.version, r.activa{extra} FROM reglas r ORDER BY r.id_regla")
        condiciones = {}
        if experto:
            for c in self._db.consultar("SELECT id_regla, orden, tipo, referencia, valor_esperado "
                                        "FROM regla_condicion ORDER BY id_regla, orden"):
                condiciones.setdefault(c["id_regla"], []).append(
                    {"orden": c["orden"], "tipo": c["tipo"], "referencia": c["referencia"],
                     "valor_esperado": c["valor_esperado"]})
        for r in reglas:
            r["peso"] = float(r["peso"])
            r["condiciones"] = condiciones.get(r["id_regla"], [])
            r["tipo"] = ("intermedia" if r["concluye_hecho"] else "compuesta") if r["condiciones"] else "simple"
        salida = {
            "areas": areas, "preguntas": preguntas, "hipotesis": hipotesis, "reglas": reglas,
            "hechos": [{"codigo": k, "descripcion": v} for k, v in self.hechos().items()],
            "testigos": [], "obd": [], "parametros": self.parametros(),
        }
        if experto:
            salida["testigos"] = [dict(f, peso=float(f["peso"])) for f in self._db.consultar(
                "SELECT testigo, id_hipotesis, peso FROM testigo_hipotesis ORDER BY testigo, id_hipotesis")]
            salida["obd"] = [dict(f, peso=float(f["peso"])) for f in self._db.consultar(
                "SELECT prefijo, id_hipotesis, peso, descripcion FROM obd_hipotesis ORDER BY prefijo, id_hipotesis")]
        return salida
