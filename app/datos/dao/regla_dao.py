# -*- coding: utf-8 -*-
from app.datos.dao.base_dao import BaseDAO
from app.logica.entidades import Regla

_COLUMNAS = ("id_regla, codigo, id_pregunta, id_hipotesis, id_area, nivel_atencion, gravedad, "
             "recomendacion, peso, version, activa")


def _regla(f) -> Regla:
    f = dict(f)
    f["peso"] = float(f["peso"])
    return Regla(**f)


# Regla simple = granulo directo del manual (sin premisas en regla_condicion, sql/07).
_SIMPLE = ("id_hipotesis IS NOT NULL AND NOT EXISTS "
           "(SELECT 1 FROM regla_condicion c WHERE c.id_regla = reglas.id_regla)")


class ReglaDAO(BaseDAO):
    _experto = False

    def tiene_motor_experto(self, tx=None) -> bool:
        if not self._experto:
            self._experto = bool(self._escalar("SELECT to_regclass('regla_condicion') IS NOT NULL", tx=tx))
        return self._experto

    def _simple(self, tx=None) -> str:
        return _SIMPLE if self.tiene_motor_experto(tx) else "TRUE"

    def es_compuesta(self, id_regla: int, tx=None) -> bool:
        """True si la regla tiene premisas en regla_condicion (compuesta o intermedia)."""
        if not self.tiene_motor_experto(tx):
            return False
        return self._fila("SELECT 1 FROM regla_condicion WHERE id_regla = %s LIMIT 1", (id_regla,), tx) is not None

    def condiciones(self, id_regla: int, tx=None) -> list:
        if not self.tiene_motor_experto(tx):
            return []
        return self._filas("SELECT orden, tipo, referencia, valor_esperado FROM regla_condicion "
                           "WHERE id_regla = %s ORDER BY orden", (id_regla,), tx)

    def condiciones_invalidas(self, tx=None) -> list:
        """Premisas de reglas activas que apuntan a preguntas inexistentes o
        inactivas, o a hechos que ninguna regla activa concluye."""
        if not self.tiene_motor_experto(tx):
            return []
        return self._filas(
            "SELECT r.id_regla, r.codigo, c.tipo, c.referencia FROM regla_condicion c "
            "JOIN reglas r ON r.id_regla = c.id_regla WHERE r.activa AND ("
            " (c.tipo = 'pregunta' AND NOT EXISTS (SELECT 1 FROM preguntas p WHERE p.activa "
            "   AND p.id_pregunta::text = c.referencia))"
            " OR (c.tipo = 'hecho' AND NOT EXISTS (SELECT 1 FROM reglas r2 WHERE r2.activa "
            "   AND r2.concluye_hecho = c.referencia))) ORDER BY r.id_regla, c.orden", tx=tx)
    def obtener(self, id_regla: int, tx=None):
        f = self._fila(f"SELECT {_COLUMNAS} FROM reglas WHERE id_regla = %s", (id_regla,), tx)
        return _regla(f) if f else None

    def obtener_por_codigo(self, codigo: str, tx=None):
        f = self._fila(f"SELECT {_COLUMNAS} FROM reglas WHERE upper(codigo) = upper(%s)", (codigo,), tx)
        return _regla(f) if f else None

    def obtener_detalle(self, id_regla: int, tx=None):
        filas = self._listar_detalle("WHERE r.id_regla = %s", (id_regla,), tx)
        return filas[0] if filas else None

    def listar(self, id_area: int = None, tx=None) -> list:
        """Reglas con enunciado de la pregunta, nombre de hipotesis y area (dict)."""
        if id_area is None:
            return self._listar_detalle("", (), tx)
        return self._listar_detalle("WHERE r.id_area = %s", (id_area,), tx)

    def _listar_detalle(self, where: str, parametros: tuple, tx) -> list:
        filas = self._filas(
            "SELECT r.id_regla, r.codigo, r.id_pregunta, p.enunciado, p.activa AS pregunta_activa, "
            "r.id_hipotesis, h.nombre AS hipotesis, r.id_area, a.nombre AS area, r.nivel_atencion, "
            "r.gravedad, r.recomendacion, r.peso, r.version, r.activa "
            "FROM reglas r JOIN preguntas p ON p.id_pregunta = r.id_pregunta "
            "LEFT JOIN hipotesis h ON h.id_hipotesis = r.id_hipotesis JOIN areas a ON a.id_area = r.id_area "
            f"{where} ORDER BY r.id_regla", parametros, tx)
        compuestas = {}
        if filas and self.tiene_motor_experto(tx):
            for c in self._filas("SELECT c.id_regla, c.tipo, c.referencia, c.valor_esperado, r.concluye_hecho "
                                 "FROM regla_condicion c JOIN reglas r ON r.id_regla = c.id_regla "
                                 "ORDER BY c.id_regla, c.orden", tx=tx):
                compuestas.setdefault(c["id_regla"], []).append(c)
        for f in filas:
            f["peso"] = float(f["peso"])
            conds = compuestas.get(f["id_regla"], [])
            f["condiciones"] = [{k: c[k] for k in ("tipo", "referencia", "valor_esperado")} for c in conds]
            f["concluye_hecho"] = conds[0]["concluye_hecho"] if conds else None
            if f["hipotesis"] is None and f["concluye_hecho"]:
                f["hipotesis"] = "Hecho intermedio: " + f["concluye_hecho"]
            if conds:   # la columna "SI (pregunta)" muestra la premisa completa
                f["enunciado"] = " Y ".join(
                    ("NO " if c["valor_esperado"] == "no" else "")
                    + (f"P{c['referencia']}" if c["tipo"] == "pregunta" else f"{c['tipo']} {c['referencia']}")
                    for c in conds) + " | " + (f["enunciado"] or "")
        return filas

    def listar_por_hipotesis(self, id_hipotesis: int, tx=None) -> list:
        return [_regla(f) for f in self._filas(
            f"SELECT {_COLUMNAS} FROM reglas WHERE id_hipotesis = %s ORDER BY id_regla", (id_hipotesis,), tx)]

    def codigos(self, ids_regla, tx=None) -> dict:
        """{id_regla: codigo} para una lista de ids."""
        ids = tuple(int(i) for i in ids_regla)
        if not ids:
            return {}
        return {f["id_regla"]: f["codigo"] for f in self._filas(
            "SELECT id_regla, codigo FROM reglas WHERE id_regla IN %s", (ids,), tx)}

    def existe_activa(self, id_pregunta: int, id_hipotesis: int, excluir_id: int = None, tx=None) -> bool:
        return self._fila(
            "SELECT 1 FROM reglas WHERE id_pregunta = %s AND id_hipotesis = %s AND activa AND id_regla <> %s "
            f"AND {self._simple(tx)}",
            (id_pregunta, id_hipotesis, excluir_id or -1), tx) is not None

    def existe_codigo(self, codigo: str, excluir_id: int = None, tx=None) -> bool:
        return self._fila("SELECT 1 FROM reglas WHERE upper(codigo) = upper(%s) AND id_regla <> %s",
                          (codigo, excluir_id or -1), tx) is not None

    def siguiente_codigo(self, tx=None) -> str:
        return self._escalar(
            "SELECT 'R' || lpad((COALESCE(MAX(substring(codigo FROM 2)::int), 0) + 1)::text, 2, '0') "
            "FROM reglas WHERE codigo ~ '^R[0-9]+$'", tx=tx)

    def crear(self, datos: dict, tx=None) -> int:
        codigo = datos.get("codigo") or self.siguiente_codigo(tx)
        f = self._retornando(
            "INSERT INTO reglas (id_regla, codigo, id_pregunta, id_hipotesis, id_area, nivel_atencion, "
            "gravedad, recomendacion, peso, version, activa) "
            "SELECT COALESCE(MAX(id_regla), 0) + 1, %s, %s, %s, %s, %s, %s, %s, %s, 1, %s FROM reglas "
            "RETURNING id_regla",
            (codigo, datos["id_pregunta"], datos["id_hipotesis"], datos["id_area"], datos["nivel_atencion"],
             datos["gravedad"], datos["recomendacion"], datos.get("peso", 1.0), bool(datos.get("activa", True))), tx)
        return f["id_regla"]

    def actualizar(self, id_regla: int, datos: dict, tx=None) -> int:
        """Actualiza los campos dados y sube la version de la regla."""
        sets, valores = self._set_dinamico(
            datos, ("codigo", "id_pregunta", "id_hipotesis", "id_area", "nivel_atencion", "gravedad",
                    "recomendacion", "peso"))
        if not sets:
            return 0
        return self._ejecutar(f"UPDATE reglas SET {sets}, version = version + 1 WHERE id_regla = %s",
                              valores + (id_regla,), tx)

    def cambiar_activa(self, id_regla: int, activa: bool, tx=None) -> int:
        return self._ejecutar("UPDATE reglas SET activa = %s WHERE id_regla = %s", (activa, id_regla), tx)

    def activas_con_pregunta_inactiva(self, tx=None) -> list:
        return self._filas(
            "SELECT r.id_regla, r.codigo, r.id_pregunta FROM reglas r JOIN preguntas p ON p.id_pregunta = r.id_pregunta "
            "WHERE r.activa AND NOT p.activa ORDER BY r.id_regla", tx=tx)

    def activas_sobre_pregunta_de_entrada(self, tx=None) -> list:
        return self._filas(
            "SELECT r.id_regla, r.codigo, r.id_pregunta FROM reglas r JOIN preguntas p ON p.id_pregunta = r.id_pregunta "
            "WHERE r.activa AND p.es_entrada ORDER BY r.id_regla", tx=tx)

    def duplicadas(self, tx=None) -> list:
        """Pares pregunta-hipotesis con mas de una regla activa."""
        return self._filas(
            "SELECT id_pregunta, id_hipotesis, array_agg(codigo ORDER BY codigo) AS codigos "
            f"FROM reglas WHERE activa AND {self._simple(tx)} GROUP BY id_pregunta, id_hipotesis HAVING COUNT(*) > 1 "
            "ORDER BY id_pregunta", tx=tx)

    def area_distinta_a_pregunta(self, tx=None) -> list:
        return self._filas(
            "SELECT r.id_regla, r.codigo FROM reglas r JOIN preguntas p ON p.id_pregunta = r.id_pregunta "
            "WHERE r.id_area <> p.id_area ORDER BY r.id_regla", tx=tx)

    def contar(self, solo_activas: bool = False, tx=None) -> int:
        sql = "SELECT COUNT(*) FROM reglas" + (" WHERE activa" if solo_activas else "")
        return int(self._escalar(sql, tx=tx))
