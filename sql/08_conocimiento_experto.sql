-- 08_conocimiento_experto.sql
-- Conocimiento del motor experto: hechos intermedios, reglas compuestas
-- (con negacion), reglas intermedias encadenadas (R69 en adelante) y
-- evidencia de testigos del tablero y codigos OBD-II.
-- Requiere 07_motor_experto.sql. Idempotente: las reglas se identifican
-- por su codigo y solo se insertan si el codigo no existe; las condiciones
-- solo se asocian si la regla con ese codigo tiene la pregunta principal
-- esperada (no se mezclan con reglas creadas a mano con el mismo codigo).
-- Generado con un script; editar con cuidado.

SET client_encoding = 'UTF8';

-- ===================== HECHOS =====================
INSERT INTO hechos (codigo, descripcion) VALUES ('TENSION_BATERIA_BAJA', 'La bateria entrega tension insuficiente durante el arranque') ON CONFLICT (codigo) DO UPDATE SET descripcion = EXCLUDED.descripcion;
INSERT INTO hechos (codigo, descripcion) VALUES ('FALLA_CARGA', 'El sistema de carga (alternador, regulador o correa) no recarga la bateria') ON CONFLICT (codigo) DO UPDATE SET descripcion = EXCLUDED.descripcion;
INSERT INTO hechos (codigo, descripcion) VALUES ('MEZCLA_RICA', 'La combustion recibe exceso de combustible respecto al aire') ON CONFLICT (codigo) DO UPDATE SET descripcion = EXCLUDED.descripcion;
INSERT INTO hechos (codigo, descripcion) VALUES ('MEZCLA_POBRE', 'La combustion recibe exceso de aire o falta de combustible') ON CONFLICT (codigo) DO UPDATE SET descripcion = EXCLUDED.descripcion;
INSERT INTO hechos (codigo, descripcion) VALUES ('FALLA_ENCENDIDO', 'Combustion incompleta en uno o mas cilindros (misfire)') ON CONFLICT (codigo) DO UPDATE SET descripcion = EXCLUDED.descripcion;
INSERT INTO hechos (codigo, descripcion) VALUES ('PERDIDA_LUBRICACION', 'Presion o cantidad de aceite insuficiente para lubricar el motor') ON CONFLICT (codigo) DO UPDATE SET descripcion = EXCLUDED.descripcion;
INSERT INTO hechos (codigo, descripcion) VALUES ('SOBRECALENTAMIENTO', 'El motor trabaja por encima de su temperatura normal de operacion') ON CONFLICT (codigo) DO UPDATE SET descripcion = EXCLUDED.descripcion;
INSERT INTO hechos (codigo, descripcion) VALUES ('PERDIDA_PRESION_FRENO', 'El circuito hidraulico de frenos pierde presion') ON CONFLICT (codigo) DO UPDATE SET descripcion = EXCLUDED.descripcion;

-- ===================== REGLAS COMPUESTAS E INTERMEDIAS =====================
-- R69: SI P27 Y P26 ENTONCES hecho TENSION_BATERIA_BAJA
INSERT INTO reglas (id_regla, codigo, id_pregunta, id_hipotesis, id_area, nivel_atencion, gravedad, recomendacion, peso, version, activa, concluye_hecho)
SELECT (SELECT COALESCE(MAX(id_regla), 0) + 1 FROM reglas), 'R69', 27, NULL, 9, 'Revision proxima', 2, 'Regla intermedia: arranque lento con clic indica tension baja de bateria.', 0.90, 1, TRUE, 'TENSION_BATERIA_BAJA'
WHERE NOT EXISTS (SELECT 1 FROM reglas WHERE upper(codigo) = 'R69');
INSERT INTO regla_condicion (id_regla, orden, tipo, referencia, valor_esperado)
SELECT r.id_regla, v.orden, v.tipo, v.referencia, v.valor FROM reglas r, (VALUES (1, 'pregunta', '27', 'si'), (2, 'pregunta', '26', 'si')) AS v(orden, tipo, referencia, valor)
WHERE upper(r.codigo) = 'R69' AND r.id_pregunta = 27 ON CONFLICT (id_regla, orden) DO NOTHING;
-- R70: SI P29 Y hecho:TENSION_BATERIA_BAJA ENTONCES hecho FALLA_CARGA
INSERT INTO reglas (id_regla, codigo, id_pregunta, id_hipotesis, id_area, nivel_atencion, gravedad, recomendacion, peso, version, activa, concluye_hecho)
SELECT (SELECT COALESCE(MAX(id_regla), 0) + 1 FROM reglas), 'R70', 29, NULL, 9, 'Revision prioritaria', 3, 'Regla intermedia: tension baja y testigo de carga encendido indican que la bateria no se recarga.', 1.00, 1, TRUE, 'FALLA_CARGA'
WHERE NOT EXISTS (SELECT 1 FROM reglas WHERE upper(codigo) = 'R70');
INSERT INTO regla_condicion (id_regla, orden, tipo, referencia, valor_esperado)
SELECT r.id_regla, v.orden, v.tipo, v.referencia, v.valor FROM reglas r, (VALUES (1, 'pregunta', '29', 'si'), (2, 'hecho', 'TENSION_BATERIA_BAJA', 'si')) AS v(orden, tipo, referencia, valor)
WHERE upper(r.codigo) = 'R70' AND r.id_pregunta = 29 ON CONFLICT (id_regla, orden) DO NOTHING;
-- R71: SI P57 Y testigo:BATERIA ENTONCES hecho FALLA_CARGA
INSERT INTO reglas (id_regla, codigo, id_pregunta, id_hipotesis, id_area, nivel_atencion, gravedad, recomendacion, peso, version, activa, concluye_hecho)
SELECT (SELECT COALESCE(MAX(id_regla), 0) + 1 FROM reglas), 'R71', 57, NULL, 21, 'Revision prioritaria', 3, 'Regla intermedia: testigo de bateria y luces que parpadean indican tension de carga irregular.', 0.80, 1, TRUE, 'FALLA_CARGA'
WHERE NOT EXISTS (SELECT 1 FROM reglas WHERE upper(codigo) = 'R71');
INSERT INTO regla_condicion (id_regla, orden, tipo, referencia, valor_esperado)
SELECT r.id_regla, v.orden, v.tipo, v.referencia, v.valor FROM reglas r, (VALUES (1, 'pregunta', '57', 'si'), (2, 'testigo', 'BATERIA', 'si')) AS v(orden, tipo, referencia, valor)
WHERE upper(r.codigo) = 'R71' AND r.id_pregunta = 57 ON CONFLICT (id_regla, orden) DO NOTHING;
-- R72: SI hecho:FALLA_CARGA Y NO P79 ENTONCES H5
INSERT INTO reglas (id_regla, codigo, id_pregunta, id_hipotesis, id_area, nivel_atencion, gravedad, recomendacion, peso, version, activa, concluye_hecho)
SELECT (SELECT COALESCE(MAX(id_regla), 0) + 1 FROM reglas), 'R72', 79, 5, 23, 'Revision prioritaria', 3, 'Medir la tension de carga (13,8-14,7 V con el motor encendido); si la correa esta bien, revisar alternador y regulador.', 1.10, 1, TRUE, NULL
WHERE NOT EXISTS (SELECT 1 FROM reglas WHERE upper(codigo) = 'R72');
INSERT INTO regla_condicion (id_regla, orden, tipo, referencia, valor_esperado)
SELECT r.id_regla, v.orden, v.tipo, v.referencia, v.valor FROM reglas r, (VALUES (1, 'hecho', 'FALLA_CARGA', 'si'), (2, 'pregunta', '79', 'no')) AS v(orden, tipo, referencia, valor)
WHERE upper(r.codigo) = 'R72' AND r.id_pregunta = 79 ON CONFLICT (id_regla, orden) DO NOTHING;
-- R73: SI hecho:FALLA_CARGA Y P79 ENTONCES H55
INSERT INTO reglas (id_regla, codigo, id_pregunta, id_hipotesis, id_area, nivel_atencion, gravedad, recomendacion, peso, version, activa, concluye_hecho)
SELECT (SELECT COALESCE(MAX(id_regla), 0) + 1 FROM reglas), 'R73', 79, 55, 23, 'Revision proxima', 2, 'La correa patina y el alternador no gira a su regimen: revisar tension, desgaste y contaminacion de la correa de accesorios.', 1.00, 1, TRUE, NULL
WHERE NOT EXISTS (SELECT 1 FROM reglas WHERE upper(codigo) = 'R73');
INSERT INTO regla_condicion (id_regla, orden, tipo, referencia, valor_esperado)
SELECT r.id_regla, v.orden, v.tipo, v.referencia, v.valor FROM reglas r, (VALUES (1, 'hecho', 'FALLA_CARGA', 'si'), (2, 'pregunta', '79', 'si')) AS v(orden, tipo, referencia, valor)
WHERE upper(r.codigo) = 'R73' AND r.id_pregunta = 79 ON CONFLICT (id_regla, orden) DO NOTHING;
-- R74: SI hecho:TENSION_BATERIA_BAJA Y P58 Y NO P29 ENTONCES H34
INSERT INTO reglas (id_regla, codigo, id_pregunta, id_hipotesis, id_area, nivel_atencion, gravedad, recomendacion, peso, version, activa, concluye_hecho)
SELECT (SELECT COALESCE(MAX(id_regla), 0) + 1 FROM reglas), 'R74', 58, 34, 21, 'Revision proxima', 2, 'La carga funciona pero la bateria se descarga en reposo: medir consumo parasito y hacer prueba de capacidad a la bateria.', 1.00, 1, TRUE, NULL
WHERE NOT EXISTS (SELECT 1 FROM reglas WHERE upper(codigo) = 'R74');
INSERT INTO regla_condicion (id_regla, orden, tipo, referencia, valor_esperado)
SELECT r.id_regla, v.orden, v.tipo, v.referencia, v.valor FROM reglas r, (VALUES (1, 'hecho', 'TENSION_BATERIA_BAJA', 'si'), (2, 'pregunta', '58', 'si'), (3, 'pregunta', '29', 'no')) AS v(orden, tipo, referencia, valor)
WHERE upper(r.codigo) = 'R74' AND r.id_pregunta = 58 ON CONFLICT (id_regla, orden) DO NOTHING;
-- R75: SI P33 Y obd:P0172 ENTONCES hecho MEZCLA_RICA
INSERT INTO reglas (id_regla, codigo, id_pregunta, id_hipotesis, id_area, nivel_atencion, gravedad, recomendacion, peso, version, activa, concluye_hecho)
SELECT (SELECT COALESCE(MAX(id_regla), 0) + 1 FROM reglas), 'R75', 33, NULL, 8, 'Revision proxima', 2, 'Regla intermedia: humo negro con codigo de mezcla rica confirma exceso de combustible.', 1.00, 1, TRUE, 'MEZCLA_RICA'
WHERE NOT EXISTS (SELECT 1 FROM reglas WHERE upper(codigo) = 'R75');
INSERT INTO regla_condicion (id_regla, orden, tipo, referencia, valor_esperado)
SELECT r.id_regla, v.orden, v.tipo, v.referencia, v.valor FROM reglas r, (VALUES (1, 'pregunta', '33', 'si'), (2, 'obd', 'P0172', 'si')) AS v(orden, tipo, referencia, valor)
WHERE upper(r.codigo) = 'R75' AND r.id_pregunta = 33 ON CONFLICT (id_regla, orden) DO NOTHING;
-- R76: SI P33 Y P31 ENTONCES hecho MEZCLA_RICA
INSERT INTO reglas (id_regla, codigo, id_pregunta, id_hipotesis, id_area, nivel_atencion, gravedad, recomendacion, peso, version, activa, concluye_hecho)
SELECT (SELECT COALESCE(MAX(id_regla), 0) + 1 FROM reglas), 'R76', 33, NULL, 8, 'Revision proxima', 2, 'Regla intermedia: humo negro y ralenti inestable con consumo alto indican mezcla rica.', 0.80, 1, TRUE, 'MEZCLA_RICA'
WHERE NOT EXISTS (SELECT 1 FROM reglas WHERE upper(codigo) = 'R76');
INSERT INTO regla_condicion (id_regla, orden, tipo, referencia, valor_esperado)
SELECT r.id_regla, v.orden, v.tipo, v.referencia, v.valor FROM reglas r, (VALUES (1, 'pregunta', '33', 'si'), (2, 'pregunta', '31', 'si')) AS v(orden, tipo, referencia, valor)
WHERE upper(r.codigo) = 'R76' AND r.id_pregunta = 33 ON CONFLICT (id_regla, orden) DO NOTHING;
-- R77: SI hecho:MEZCLA_RICA Y P30 ENTONCES H6
INSERT INTO reglas (id_regla, codigo, id_pregunta, id_hipotesis, id_area, nivel_atencion, gravedad, recomendacion, peso, version, activa, concluye_hecho)
SELECT (SELECT COALESCE(MAX(id_regla), 0) + 1 FROM reglas), 'R77', 30, 6, 8, 'Atencion preventiva', 1, 'Mezcla rica con perdida de potencia: inspeccionar y reemplazar el filtro de aire.', 0.90, 1, TRUE, NULL
WHERE NOT EXISTS (SELECT 1 FROM reglas WHERE upper(codigo) = 'R77');
INSERT INTO regla_condicion (id_regla, orden, tipo, referencia, valor_esperado)
SELECT r.id_regla, v.orden, v.tipo, v.referencia, v.valor FROM reglas r, (VALUES (1, 'hecho', 'MEZCLA_RICA', 'si'), (2, 'pregunta', '30', 'si')) AS v(orden, tipo, referencia, valor)
WHERE upper(r.codigo) = 'R77' AND r.id_pregunta = 30 ON CONFLICT (id_regla, orden) DO NOTHING;
-- R78: SI hecho:MEZCLA_RICA Y P73 ENTONCES H49
INSERT INTO reglas (id_regla, codigo, id_pregunta, id_hipotesis, id_area, nivel_atencion, gravedad, recomendacion, peso, version, activa, concluye_hecho)
SELECT (SELECT COALESCE(MAX(id_regla), 0) + 1 FROM reglas), 'R78', 73, 49, 14, 'Revision proxima', 2, 'Mezcla rica con respuesta deficiente: revisar lecturas del sensor MAF/MAP con el escaner y limpiarlo o reemplazarlo.', 1.00, 1, TRUE, NULL
WHERE NOT EXISTS (SELECT 1 FROM reglas WHERE upper(codigo) = 'R78');
INSERT INTO regla_condicion (id_regla, orden, tipo, referencia, valor_esperado)
SELECT r.id_regla, v.orden, v.tipo, v.referencia, v.valor FROM reglas r, (VALUES (1, 'hecho', 'MEZCLA_RICA', 'si'), (2, 'pregunta', '73', 'si')) AS v(orden, tipo, referencia, valor)
WHERE upper(r.codigo) = 'R78' AND r.id_pregunta = 73 ON CONFLICT (id_regla, orden) DO NOTHING;
-- R79: SI hecho:MEZCLA_RICA Y NO P30 Y NO P73 ENTONCES H9
INSERT INTO reglas (id_regla, codigo, id_pregunta, id_hipotesis, id_area, nivel_atencion, gravedad, recomendacion, peso, version, activa, concluye_hecho)
SELECT (SELECT COALESCE(MAX(id_regla), 0) + 1 FROM reglas), 'R79', 30, 9, 8, 'Revision proxima', 2, 'Mezcla rica sin restriccion de aire ni falla de sensores: revisar inyectores (goteo) y regulador de presion.', 1.00, 1, TRUE, NULL
WHERE NOT EXISTS (SELECT 1 FROM reglas WHERE upper(codigo) = 'R79');
INSERT INTO regla_condicion (id_regla, orden, tipo, referencia, valor_esperado)
SELECT r.id_regla, v.orden, v.tipo, v.referencia, v.valor FROM reglas r, (VALUES (1, 'hecho', 'MEZCLA_RICA', 'si'), (2, 'pregunta', '30', 'no'), (3, 'pregunta', '73', 'no')) AS v(orden, tipo, referencia, valor)
WHERE upper(r.codigo) = 'R79' AND r.id_pregunta = 30 ON CONFLICT (id_regla, orden) DO NOTHING;
-- R80: SI P31 Y obd:P0171 ENTONCES hecho MEZCLA_POBRE
INSERT INTO reglas (id_regla, codigo, id_pregunta, id_hipotesis, id_area, nivel_atencion, gravedad, recomendacion, peso, version, activa, concluye_hecho)
SELECT (SELECT COALESCE(MAX(id_regla), 0) + 1 FROM reglas), 'R80', 31, NULL, 8, 'Revision proxima', 2, 'Regla intermedia: ralenti inestable con codigo de mezcla pobre.', 1.00, 1, TRUE, 'MEZCLA_POBRE'
WHERE NOT EXISTS (SELECT 1 FROM reglas WHERE upper(codigo) = 'R80');
INSERT INTO regla_condicion (id_regla, orden, tipo, referencia, valor_esperado)
SELECT r.id_regla, v.orden, v.tipo, v.referencia, v.valor FROM reglas r, (VALUES (1, 'pregunta', '31', 'si'), (2, 'obd', 'P0171', 'si')) AS v(orden, tipo, referencia, valor)
WHERE upper(r.codigo) = 'R80' AND r.id_pregunta = 31 ON CONFLICT (id_regla, orden) DO NOTHING;
-- R81: SI hecho:MEZCLA_POBRE Y P72 ENTONCES H48
INSERT INTO reglas (id_regla, codigo, id_pregunta, id_hipotesis, id_area, nivel_atencion, gravedad, recomendacion, peso, version, activa, concluye_hecho)
SELECT (SELECT COALESCE(MAX(id_regla), 0) + 1 FROM reglas), 'R81', 72, 48, 11, 'No debe seguir usandose', 4, 'Mezcla pobre con olor a combustible: fuga en lineas o deposito. No usar el vehiculo hasta reparar (riesgo de incendio).', 1.20, 1, TRUE, NULL
WHERE NOT EXISTS (SELECT 1 FROM reglas WHERE upper(codigo) = 'R81');
INSERT INTO regla_condicion (id_regla, orden, tipo, referencia, valor_esperado)
SELECT r.id_regla, v.orden, v.tipo, v.referencia, v.valor FROM reglas r, (VALUES (1, 'hecho', 'MEZCLA_POBRE', 'si'), (2, 'pregunta', '72', 'si')) AS v(orden, tipo, referencia, valor)
WHERE upper(r.codigo) = 'R81' AND r.id_pregunta = 72 ON CONFLICT (id_regla, orden) DO NOTHING;
-- R82: SI hecho:MEZCLA_POBRE Y P71 Y NO P72 ENTONCES H47
INSERT INTO reglas (id_regla, codigo, id_pregunta, id_hipotesis, id_area, nivel_atencion, gravedad, recomendacion, peso, version, activa, concluye_hecho)
SELECT (SELECT COALESCE(MAX(id_regla), 0) + 1 FROM reglas), 'R82', 71, 47, 11, 'Revision prioritaria', 3, 'Mezcla pobre con falta de potencia y sin fugas: medir presion de combustible y cambiar el filtro.', 1.10, 1, TRUE, NULL
WHERE NOT EXISTS (SELECT 1 FROM reglas WHERE upper(codigo) = 'R82');
INSERT INTO regla_condicion (id_regla, orden, tipo, referencia, valor_esperado)
SELECT r.id_regla, v.orden, v.tipo, v.referencia, v.valor FROM reglas r, (VALUES (1, 'hecho', 'MEZCLA_POBRE', 'si'), (2, 'pregunta', '71', 'si'), (3, 'pregunta', '72', 'no')) AS v(orden, tipo, referencia, valor)
WHERE upper(r.codigo) = 'R82' AND r.id_pregunta = 71 ON CONFLICT (id_regla, orden) DO NOTHING;
-- R83: SI hecho:MEZCLA_POBRE Y NO P71 ENTONCES H7
INSERT INTO reglas (id_regla, codigo, id_pregunta, id_hipotesis, id_area, nivel_atencion, gravedad, recomendacion, peso, version, activa, concluye_hecho)
SELECT (SELECT COALESCE(MAX(id_regla), 0) + 1 FROM reglas), 'R83', 71, 7, 11, 'Revision proxima', 2, 'Mezcla pobre solo al ralenti y sin problema de suministro: buscar fugas de vacio y limpiar el cuerpo de aceleracion.', 1.00, 1, TRUE, NULL
WHERE NOT EXISTS (SELECT 1 FROM reglas WHERE upper(codigo) = 'R83');
INSERT INTO regla_condicion (id_regla, orden, tipo, referencia, valor_esperado)
SELECT r.id_regla, v.orden, v.tipo, v.referencia, v.valor FROM reglas r, (VALUES (1, 'hecho', 'MEZCLA_POBRE', 'si'), (2, 'pregunta', '71', 'no')) AS v(orden, tipo, referencia, valor)
WHERE upper(r.codigo) = 'R83' AND r.id_pregunta = 71 ON CONFLICT (id_regla, orden) DO NOTHING;
-- R84: SI P34 Y obd:P030 ENTONCES hecho FALLA_ENCENDIDO
INSERT INTO reglas (id_regla, codigo, id_pregunta, id_hipotesis, id_area, nivel_atencion, gravedad, recomendacion, peso, version, activa, concluye_hecho)
SELECT (SELECT COALESCE(MAX(id_regla), 0) + 1 FROM reglas), 'R84', 34, NULL, 8, 'Revision prioritaria', 3, 'Regla intermedia: vibracion con codigo P030x confirma fallo de encendido.', 1.00, 1, TRUE, 'FALLA_ENCENDIDO'
WHERE NOT EXISTS (SELECT 1 FROM reglas WHERE upper(codigo) = 'R84');
INSERT INTO regla_condicion (id_regla, orden, tipo, referencia, valor_esperado)
SELECT r.id_regla, v.orden, v.tipo, v.referencia, v.valor FROM reglas r, (VALUES (1, 'pregunta', '34', 'si'), (2, 'obd', 'P030', 'si')) AS v(orden, tipo, referencia, valor)
WHERE upper(r.codigo) = 'R84' AND r.id_pregunta = 34 ON CONFLICT (id_regla, orden) DO NOTHING;
-- R85: SI P34 Y P39 ENTONCES hecho FALLA_ENCENDIDO
INSERT INTO reglas (id_regla, codigo, id_pregunta, id_hipotesis, id_area, nivel_atencion, gravedad, recomendacion, peso, version, activa, concluye_hecho)
SELECT (SELECT COALESCE(MAX(id_regla), 0) + 1 FROM reglas), 'R85', 34, NULL, 8, 'No debe seguir usandose', 4, 'Regla intermedia: vibracion con MIL parpadeante confirma fallo de encendido activo.', 1.00, 1, TRUE, 'FALLA_ENCENDIDO'
WHERE NOT EXISTS (SELECT 1 FROM reglas WHERE upper(codigo) = 'R85');
INSERT INTO regla_condicion (id_regla, orden, tipo, referencia, valor_esperado)
SELECT r.id_regla, v.orden, v.tipo, v.referencia, v.valor FROM reglas r, (VALUES (1, 'pregunta', '34', 'si'), (2, 'pregunta', '39', 'si')) AS v(orden, tipo, referencia, valor)
WHERE upper(r.codigo) = 'R85' AND r.id_pregunta = 34 ON CONFLICT (id_regla, orden) DO NOTHING;
-- R86: SI hecho:FALLA_ENCENDIDO Y P39 ENTONCES H15
INSERT INTO reglas (id_regla, codigo, id_pregunta, id_hipotesis, id_area, nivel_atencion, gravedad, recomendacion, peso, version, activa, concluye_hecho)
SELECT (SELECT COALESCE(MAX(id_regla), 0) + 1 FROM reglas), 'R86', 39, 15, 8, 'No debe seguir usandose', 4, 'Fallo de encendido con MIL parpadeante: detener el uso; el combustible sin quemar dana el catalizador.', 1.20, 1, TRUE, NULL
WHERE NOT EXISTS (SELECT 1 FROM reglas WHERE upper(codigo) = 'R86');
INSERT INTO regla_condicion (id_regla, orden, tipo, referencia, valor_esperado)
SELECT r.id_regla, v.orden, v.tipo, v.referencia, v.valor FROM reglas r, (VALUES (1, 'hecho', 'FALLA_ENCENDIDO', 'si'), (2, 'pregunta', '39', 'si')) AS v(orden, tipo, referencia, valor)
WHERE upper(r.codigo) = 'R86' AND r.id_pregunta = 39 ON CONFLICT (id_regla, orden) DO NOTHING;
-- R87: SI hecho:FALLA_ENCENDIDO Y NO P35 Y NO P36 ENTONCES H10
INSERT INTO reglas (id_regla, codigo, id_pregunta, id_hipotesis, id_area, nivel_atencion, gravedad, recomendacion, peso, version, activa, concluye_hecho)
SELECT (SELECT COALESCE(MAX(id_regla), 0) + 1 FROM reglas), 'R87', 35, 10, 8, 'Revision proxima', 2, 'Fallo de encendido sin golpeteo ni humo azul: intercambiar bobinas entre cilindros y revisar bujias.', 1.00, 1, TRUE, NULL
WHERE NOT EXISTS (SELECT 1 FROM reglas WHERE upper(codigo) = 'R87');
INSERT INTO regla_condicion (id_regla, orden, tipo, referencia, valor_esperado)
SELECT r.id_regla, v.orden, v.tipo, v.referencia, v.valor FROM reglas r, (VALUES (1, 'hecho', 'FALLA_ENCENDIDO', 'si'), (2, 'pregunta', '35', 'no'), (3, 'pregunta', '36', 'no')) AS v(orden, tipo, referencia, valor)
WHERE upper(r.codigo) = 'R87' AND r.id_pregunta = 35 ON CONFLICT (id_regla, orden) DO NOTHING;
-- R88: SI hecho:FALLA_ENCENDIDO Y P35 ENTONCES H11
INSERT INTO reglas (id_regla, codigo, id_pregunta, id_hipotesis, id_area, nivel_atencion, gravedad, recomendacion, peso, version, activa, concluye_hecho)
SELECT (SELECT COALESCE(MAX(id_regla), 0) + 1 FROM reglas), 'R88', 35, 11, 8, 'Revision prioritaria', 3, 'Fallo de encendido con golpeteo metalico: realizar prueba de compresion y de fugas de cilindro.', 1.10, 1, TRUE, NULL
WHERE NOT EXISTS (SELECT 1 FROM reglas WHERE upper(codigo) = 'R88');
INSERT INTO regla_condicion (id_regla, orden, tipo, referencia, valor_esperado)
SELECT r.id_regla, v.orden, v.tipo, v.referencia, v.valor FROM reglas r, (VALUES (1, 'hecho', 'FALLA_ENCENDIDO', 'si'), (2, 'pregunta', '35', 'si')) AS v(orden, tipo, referencia, valor)
WHERE upper(r.codigo) = 'R88' AND r.id_pregunta = 35 ON CONFLICT (id_regla, orden) DO NOTHING;
-- R89: SI P70 Y P69 ENTONCES hecho PERDIDA_LUBRICACION
INSERT INTO reglas (id_regla, codigo, id_pregunta, id_hipotesis, id_area, nivel_atencion, gravedad, recomendacion, peso, version, activa, concluye_hecho)
SELECT (SELECT COALESCE(MAX(id_regla), 0) + 1 FROM reglas), 'R89', 70, NULL, 7, 'No debe seguir usandose', 4, 'Regla intermedia: testigo de aceite encendido y nivel que baja.', 1.00, 1, TRUE, 'PERDIDA_LUBRICACION'
WHERE NOT EXISTS (SELECT 1 FROM reglas WHERE upper(codigo) = 'R89');
INSERT INTO regla_condicion (id_regla, orden, tipo, referencia, valor_esperado)
SELECT r.id_regla, v.orden, v.tipo, v.referencia, v.valor FROM reglas r, (VALUES (1, 'pregunta', '70', 'si'), (2, 'pregunta', '69', 'si')) AS v(orden, tipo, referencia, valor)
WHERE upper(r.codigo) = 'R89' AND r.id_pregunta = 70 ON CONFLICT (id_regla, orden) DO NOTHING;
-- R90: SI P40 Y testigo:ACEITE ENTONCES hecho PERDIDA_LUBRICACION
INSERT INTO reglas (id_regla, codigo, id_pregunta, id_hipotesis, id_area, nivel_atencion, gravedad, recomendacion, peso, version, activa, concluye_hecho)
SELECT (SELECT COALESCE(MAX(id_regla), 0) + 1 FROM reglas), 'R90', 40, NULL, 8, 'No debe seguir usandose', 4, 'Regla intermedia: ruido metalico con testigo de presion de aceite.', 1.00, 1, TRUE, 'PERDIDA_LUBRICACION'
WHERE NOT EXISTS (SELECT 1 FROM reglas WHERE upper(codigo) = 'R90');
INSERT INTO regla_condicion (id_regla, orden, tipo, referencia, valor_esperado)
SELECT r.id_regla, v.orden, v.tipo, v.referencia, v.valor FROM reglas r, (VALUES (1, 'pregunta', '40', 'si'), (2, 'testigo', 'ACEITE', 'si')) AS v(orden, tipo, referencia, valor)
WHERE upper(r.codigo) = 'R90' AND r.id_pregunta = 40 ON CONFLICT (id_regla, orden) DO NOTHING;
-- R91: SI hecho:PERDIDA_LUBRICACION Y P40 ENTONCES H16
INSERT INTO reglas (id_regla, codigo, id_pregunta, id_hipotesis, id_area, nivel_atencion, gravedad, recomendacion, peso, version, activa, concluye_hecho)
SELECT (SELECT COALESCE(MAX(id_regla), 0) + 1 FROM reglas), 'R91', 40, 16, 8, 'No debe seguir usandose', 4, 'Perdida de lubricacion con ruido metalico: apagar el motor de inmediato y verificar nivel y presion de aceite.', 1.20, 1, TRUE, NULL
WHERE NOT EXISTS (SELECT 1 FROM reglas WHERE upper(codigo) = 'R91');
INSERT INTO regla_condicion (id_regla, orden, tipo, referencia, valor_esperado)
SELECT r.id_regla, v.orden, v.tipo, v.referencia, v.valor FROM reglas r, (VALUES (1, 'hecho', 'PERDIDA_LUBRICACION', 'si'), (2, 'pregunta', '40', 'si')) AS v(orden, tipo, referencia, valor)
WHERE upper(r.codigo) = 'R91' AND r.id_pregunta = 40 ON CONFLICT (id_regla, orden) DO NOTHING;
-- R92: SI hecho:PERDIDA_LUBRICACION Y P69 ENTONCES H45
INSERT INTO reglas (id_regla, codigo, id_pregunta, id_hipotesis, id_area, nivel_atencion, gravedad, recomendacion, peso, version, activa, concluye_hecho)
SELECT (SELECT COALESCE(MAX(id_regla), 0) + 1 FROM reglas), 'R92', 69, 45, 7, 'Revision prioritaria', 3, 'Perdida de lubricacion por fuga externa: localizar la fuga (carter, retenes, juntas) y reponer aceite.', 1.10, 1, TRUE, NULL
WHERE NOT EXISTS (SELECT 1 FROM reglas WHERE upper(codigo) = 'R92');
INSERT INTO regla_condicion (id_regla, orden, tipo, referencia, valor_esperado)
SELECT r.id_regla, v.orden, v.tipo, v.referencia, v.valor FROM reglas r, (VALUES (1, 'hecho', 'PERDIDA_LUBRICACION', 'si'), (2, 'pregunta', '69', 'si')) AS v(orden, tipo, referencia, valor)
WHERE upper(r.codigo) = 'R92' AND r.id_pregunta = 69 ON CONFLICT (id_regla, orden) DO NOTHING;
-- R93: SI hecho:PERDIDA_LUBRICACION Y NO P69 Y NO P36 ENTONCES H46
INSERT INTO reglas (id_regla, codigo, id_pregunta, id_hipotesis, id_area, nivel_atencion, gravedad, recomendacion, peso, version, activa, concluye_hecho)
SELECT (SELECT COALESCE(MAX(id_regla), 0) + 1 FROM reglas), 'R93', 69, 46, 7, 'No debe seguir usandose', 4, 'Baja presion sin fuga ni consumo: medir presion con manometro; revisar bomba, chupador y filtro de aceite.', 1.20, 1, TRUE, NULL
WHERE NOT EXISTS (SELECT 1 FROM reglas WHERE upper(codigo) = 'R93');
INSERT INTO regla_condicion (id_regla, orden, tipo, referencia, valor_esperado)
SELECT r.id_regla, v.orden, v.tipo, v.referencia, v.valor FROM reglas r, (VALUES (1, 'hecho', 'PERDIDA_LUBRICACION', 'si'), (2, 'pregunta', '69', 'no'), (3, 'pregunta', '36', 'no')) AS v(orden, tipo, referencia, valor)
WHERE upper(r.codigo) = 'R93' AND r.id_pregunta = 69 ON CONFLICT (id_regla, orden) DO NOTHING;
-- R94: SI P36 Y NO P69 ENTONCES H12
INSERT INTO reglas (id_regla, codigo, id_pregunta, id_hipotesis, id_area, nivel_atencion, gravedad, recomendacion, peso, version, activa, concluye_hecho)
SELECT (SELECT COALESCE(MAX(id_regla), 0) + 1 FROM reglas), 'R94', 36, 12, 8, 'Revision prioritaria', 3, 'Humo azul sin fugas externas: el aceite se quema dentro del motor; prueba de compresion y revision de sellos de valvula.', 1.10, 1, TRUE, NULL
WHERE NOT EXISTS (SELECT 1 FROM reglas WHERE upper(codigo) = 'R94');
INSERT INTO regla_condicion (id_regla, orden, tipo, referencia, valor_esperado)
SELECT r.id_regla, v.orden, v.tipo, v.referencia, v.valor FROM reglas r, (VALUES (1, 'pregunta', '36', 'si'), (2, 'pregunta', '69', 'no')) AS v(orden, tipo, referencia, valor)
WHERE upper(r.codigo) = 'R94' AND r.id_pregunta = 36 ON CONFLICT (id_regla, orden) DO NOTHING;
-- R95: SI P41 Y testigo:TEMPERATURA ENTONCES hecho SOBRECALENTAMIENTO
INSERT INTO reglas (id_regla, codigo, id_pregunta, id_hipotesis, id_area, nivel_atencion, gravedad, recomendacion, peso, version, activa, concluye_hecho)
SELECT (SELECT COALESCE(MAX(id_regla), 0) + 1 FROM reglas), 'R95', 41, NULL, 8, 'No debe seguir usandose', 4, 'Regla intermedia: aguja al maximo con testigo de temperatura.', 1.00, 1, TRUE, 'SOBRECALENTAMIENTO'
WHERE NOT EXISTS (SELECT 1 FROM reglas WHERE upper(codigo) = 'R95');
INSERT INTO regla_condicion (id_regla, orden, tipo, referencia, valor_esperado)
SELECT r.id_regla, v.orden, v.tipo, v.referencia, v.valor FROM reglas r, (VALUES (1, 'pregunta', '41', 'si'), (2, 'testigo', 'TEMPERATURA', 'si')) AS v(orden, tipo, referencia, valor)
WHERE upper(r.codigo) = 'R95' AND r.id_pregunta = 41 ON CONFLICT (id_regla, orden) DO NOTHING;
-- R96: SI P42 Y P43 ENTONCES hecho SOBRECALENTAMIENTO
INSERT INTO reglas (id_regla, codigo, id_pregunta, id_hipotesis, id_area, nivel_atencion, gravedad, recomendacion, peso, version, activa, concluye_hecho)
SELECT (SELECT COALESCE(MAX(id_regla), 0) + 1 FROM reglas), 'R96', 42, NULL, 20, 'Revision prioritaria', 3, 'Regla intermedia: temperatura que sube y ventilador que no enciende.', 0.90, 1, TRUE, 'SOBRECALENTAMIENTO'
WHERE NOT EXISTS (SELECT 1 FROM reglas WHERE upper(codigo) = 'R96');
INSERT INTO regla_condicion (id_regla, orden, tipo, referencia, valor_esperado)
SELECT r.id_regla, v.orden, v.tipo, v.referencia, v.valor FROM reglas r, (VALUES (1, 'pregunta', '42', 'si'), (2, 'pregunta', '43', 'si')) AS v(orden, tipo, referencia, valor)
WHERE upper(r.codigo) = 'R96' AND r.id_pregunta = 42 ON CONFLICT (id_regla, orden) DO NOTHING;
-- R97: SI hecho:SOBRECALENTAMIENTO Y P43 ENTONCES H19
INSERT INTO reglas (id_regla, codigo, id_pregunta, id_hipotesis, id_area, nivel_atencion, gravedad, recomendacion, peso, version, activa, concluye_hecho)
SELECT (SELECT COALESCE(MAX(id_regla), 0) + 1 FROM reglas), 'R97', 43, 19, 20, 'Revision prioritaria', 3, 'Sobrecalentamiento con ventilador apagado: revisar fusible, rele, sensor de temperatura y motor del ventilador.', 1.10, 1, TRUE, NULL
WHERE NOT EXISTS (SELECT 1 FROM reglas WHERE upper(codigo) = 'R97');
INSERT INTO regla_condicion (id_regla, orden, tipo, referencia, valor_esperado)
SELECT r.id_regla, v.orden, v.tipo, v.referencia, v.valor FROM reglas r, (VALUES (1, 'hecho', 'SOBRECALENTAMIENTO', 'si'), (2, 'pregunta', '43', 'si')) AS v(orden, tipo, referencia, valor)
WHERE upper(r.codigo) = 'R97' AND r.id_pregunta = 43 ON CONFLICT (id_regla, orden) DO NOTHING;
-- R98: SI hecho:SOBRECALENTAMIENTO Y P42 Y NO P43 ENTONCES H18
INSERT INTO reglas (id_regla, codigo, id_pregunta, id_hipotesis, id_area, nivel_atencion, gravedad, recomendacion, peso, version, activa, concluye_hecho)
SELECT (SELECT COALESCE(MAX(id_regla), 0) + 1 FROM reglas), 'R98', 42, 18, 20, 'Revision prioritaria', 3, 'Sobrecalentamiento gradual con ventilador funcionando: revisar nivel de refrigerante, fugas y bomba de agua.', 1.10, 1, TRUE, NULL
WHERE NOT EXISTS (SELECT 1 FROM reglas WHERE upper(codigo) = 'R98');
INSERT INTO regla_condicion (id_regla, orden, tipo, referencia, valor_esperado)
SELECT r.id_regla, v.orden, v.tipo, v.referencia, v.valor FROM reglas r, (VALUES (1, 'hecho', 'SOBRECALENTAMIENTO', 'si'), (2, 'pregunta', '42', 'si'), (3, 'pregunta', '43', 'no')) AS v(orden, tipo, referencia, valor)
WHERE upper(r.codigo) = 'R98' AND r.id_pregunta = 42 ON CONFLICT (id_regla, orden) DO NOTHING;
-- R99: SI hecho:SOBRECALENTAMIENTO Y P67 ENTONCES H43
INSERT INTO reglas (id_regla, codigo, id_pregunta, id_hipotesis, id_area, nivel_atencion, gravedad, recomendacion, peso, version, activa, concluye_hecho)
SELECT (SELECT COALESCE(MAX(id_regla), 0) + 1 FROM reglas), 'R99', 67, 43, 13, 'Revision proxima', 2, 'Sobrecalentamiento sin calefaccion: termostato pegado cerrado o bolsa de aire; revisar termostato y purgar el circuito.', 1.00, 1, TRUE, NULL
WHERE NOT EXISTS (SELECT 1 FROM reglas WHERE upper(codigo) = 'R99');
INSERT INTO regla_condicion (id_regla, orden, tipo, referencia, valor_esperado)
SELECT r.id_regla, v.orden, v.tipo, v.referencia, v.valor FROM reglas r, (VALUES (1, 'hecho', 'SOBRECALENTAMIENTO', 'si'), (2, 'pregunta', '67', 'si')) AS v(orden, tipo, referencia, valor)
WHERE upper(r.codigo) = 'R99' AND r.id_pregunta = 67 ON CONFLICT (id_regla, orden) DO NOTHING;
-- R100: SI P44 Y testigo:FRENOS ENTONCES hecho PERDIDA_PRESION_FRENO
INSERT INTO reglas (id_regla, codigo, id_pregunta, id_hipotesis, id_area, nivel_atencion, gravedad, recomendacion, peso, version, activa, concluye_hecho)
SELECT (SELECT COALESCE(MAX(id_regla), 0) + 1 FROM reglas), 'R100', 44, NULL, 2, 'No debe seguir usandose', 4, 'Regla intermedia: pedal esponjoso con testigo de frenos encendido.', 1.00, 1, TRUE, 'PERDIDA_PRESION_FRENO'
WHERE NOT EXISTS (SELECT 1 FROM reglas WHERE upper(codigo) = 'R100');
INSERT INTO regla_condicion (id_regla, orden, tipo, referencia, valor_esperado)
SELECT r.id_regla, v.orden, v.tipo, v.referencia, v.valor FROM reglas r, (VALUES (1, 'pregunta', '44', 'si'), (2, 'testigo', 'FRENOS', 'si')) AS v(orden, tipo, referencia, valor)
WHERE upper(r.codigo) = 'R100' AND r.id_pregunta = 44 ON CONFLICT (id_regla, orden) DO NOTHING;
-- R101: SI hecho:PERDIDA_PRESION_FRENO Y P48 ENTONCES H24
INSERT INTO reglas (id_regla, codigo, id_pregunta, id_hipotesis, id_area, nivel_atencion, gravedad, recomendacion, peso, version, activa, concluye_hecho)
SELECT (SELECT COALESCE(MAX(id_regla), 0) + 1 FROM reglas), 'R101', 48, 24, 2, 'No debe seguir usandose', 4, 'Perdida de presion con desvio al frenar: un circuito de freno falla; no conducir hasta revisarlo.', 1.20, 1, TRUE, NULL
WHERE NOT EXISTS (SELECT 1 FROM reglas WHERE upper(codigo) = 'R101');
INSERT INTO regla_condicion (id_regla, orden, tipo, referencia, valor_esperado)
SELECT r.id_regla, v.orden, v.tipo, v.referencia, v.valor FROM reglas r, (VALUES (1, 'hecho', 'PERDIDA_PRESION_FRENO', 'si'), (2, 'pregunta', '48', 'si')) AS v(orden, tipo, referencia, valor)
WHERE upper(r.codigo) = 'R101' AND r.id_pregunta = 48 ON CONFLICT (id_regla, orden) DO NOTHING;
-- R102: SI hecho:PERDIDA_PRESION_FRENO Y NO P48 ENTONCES H20
INSERT INTO reglas (id_regla, codigo, id_pregunta, id_hipotesis, id_area, nivel_atencion, gravedad, recomendacion, peso, version, activa, concluye_hecho)
SELECT (SELECT COALESCE(MAX(id_regla), 0) + 1 FROM reglas), 'R102', 48, 20, 2, 'No debe seguir usandose', 4, 'Perdida de presion sin desvio: aire o fuga de liquido; revisar nivel, fugas y purgar el sistema antes de conducir.', 1.20, 1, TRUE, NULL
WHERE NOT EXISTS (SELECT 1 FROM reglas WHERE upper(codigo) = 'R102');
INSERT INTO regla_condicion (id_regla, orden, tipo, referencia, valor_esperado)
SELECT r.id_regla, v.orden, v.tipo, v.referencia, v.valor FROM reglas r, (VALUES (1, 'hecho', 'PERDIDA_PRESION_FRENO', 'si'), (2, 'pregunta', '48', 'no')) AS v(orden, tipo, referencia, valor)
WHERE upper(r.codigo) = 'R102' AND r.id_pregunta = 48 ON CONFLICT (id_regla, orden) DO NOTHING;
-- R103: SI P47 Y obd:C00 ENTONCES H23
INSERT INTO reglas (id_regla, codigo, id_pregunta, id_hipotesis, id_area, nivel_atencion, gravedad, recomendacion, peso, version, activa, concluye_hecho)
SELECT (SELECT COALESCE(MAX(id_regla), 0) + 1 FROM reglas), 'R103', 47, 23, 2, 'Revision prioritaria', 3, 'Testigo ABS con codigo de chasis C00xx: leer el codigo y revisar el sensor de rueda indicado y su cableado.', 1.10, 1, TRUE, NULL
WHERE NOT EXISTS (SELECT 1 FROM reglas WHERE upper(codigo) = 'R103');
INSERT INTO regla_condicion (id_regla, orden, tipo, referencia, valor_esperado)
SELECT r.id_regla, v.orden, v.tipo, v.referencia, v.valor FROM reglas r, (VALUES (1, 'pregunta', '47', 'si'), (2, 'obd', 'C00', 'si')) AS v(orden, tipo, referencia, valor)
WHERE upper(r.codigo) = 'R103' AND r.id_pregunta = 47 ON CONFLICT (id_regla, orden) DO NOTHING;
-- R104: SI P91 Y P47 ENTONCES H68
INSERT INTO reglas (id_regla, codigo, id_pregunta, id_hipotesis, id_area, nivel_atencion, gravedad, recomendacion, peso, version, activa, concluye_hecho)
SELECT (SELECT COALESCE(MAX(id_regla), 0) + 1 FROM reglas), 'R104', 91, 68, 3, 'Revision prioritaria', 3, 'ESP y ABS encendidos a la vez: el fallo comun esta en sensores de rueda o en el modulo ABS.', 1.10, 1, TRUE, NULL
WHERE NOT EXISTS (SELECT 1 FROM reglas WHERE upper(codigo) = 'R104');
INSERT INTO regla_condicion (id_regla, orden, tipo, referencia, valor_esperado)
SELECT r.id_regla, v.orden, v.tipo, v.referencia, v.valor FROM reglas r, (VALUES (1, 'pregunta', '91', 'si'), (2, 'pregunta', '47', 'si')) AS v(orden, tipo, referencia, valor)
WHERE upper(r.codigo) = 'R104' AND r.id_pregunta = 91 ON CONFLICT (id_regla, orden) DO NOTHING;
-- R105: SI P91 Y NO P47 ENTONCES H67
INSERT INTO reglas (id_regla, codigo, id_pregunta, id_hipotesis, id_area, nivel_atencion, gravedad, recomendacion, peso, version, activa, concluye_hecho)
SELECT (SELECT COALESCE(MAX(id_regla), 0) + 1 FROM reglas), 'R105', 91, 67, 3, 'Revision prioritaria', 3, 'ESP encendido sin testigo ABS: calibrar o revisar el sensor de angulo de direccion y el modulo de estabilidad.', 1.10, 1, TRUE, NULL
WHERE NOT EXISTS (SELECT 1 FROM reglas WHERE upper(codigo) = 'R105');
INSERT INTO regla_condicion (id_regla, orden, tipo, referencia, valor_esperado)
SELECT r.id_regla, v.orden, v.tipo, v.referencia, v.valor FROM reglas r, (VALUES (1, 'pregunta', '91', 'si'), (2, 'pregunta', '47', 'no')) AS v(orden, tipo, referencia, valor)
WHERE upper(r.codigo) = 'R105' AND r.id_pregunta = 91 ON CONFLICT (id_regla, orden) DO NOTHING;
-- R106: SI P68 Y obd:B00 ENTONCES H44
INSERT INTO reglas (id_regla, codigo, id_pregunta, id_hipotesis, id_area, nivel_atencion, gravedad, recomendacion, peso, version, activa, concluye_hecho)
SELECT (SELECT COALESCE(MAX(id_regla), 0) + 1 FROM reglas), 'R106', 68, 44, 24, 'No debe seguir usandose', 4, 'Testigo de airbag con codigo B00xx: el sistema puede no desplegarse; revisar el modulo SRS con escaner.', 1.20, 1, TRUE, NULL
WHERE NOT EXISTS (SELECT 1 FROM reglas WHERE upper(codigo) = 'R106');
INSERT INTO regla_condicion (id_regla, orden, tipo, referencia, valor_esperado)
SELECT r.id_regla, v.orden, v.tipo, v.referencia, v.valor FROM reglas r, (VALUES (1, 'pregunta', '68', 'si'), (2, 'obd', 'B00', 'si')) AS v(orden, tipo, referencia, valor)
WHERE upper(r.codigo) = 'R106' AND r.id_pregunta = 68 ON CONFLICT (id_regla, orden) DO NOTHING;
-- R107: SI P74 Y obd:P033 ENTONCES H50
INSERT INTO reglas (id_regla, codigo, id_pregunta, id_hipotesis, id_area, nivel_atencion, gravedad, recomendacion, peso, version, activa, concluye_hecho)
SELECT (SELECT COALESCE(MAX(id_regla), 0) + 1 FROM reglas), 'R107', 74, 50, 14, 'Revision prioritaria', 3, 'Apagado repentino con codigo P033x: revisar el sensor de posicion del ciguenal y su conector.', 1.10, 1, TRUE, NULL
WHERE NOT EXISTS (SELECT 1 FROM reglas WHERE upper(codigo) = 'R107');
INSERT INTO regla_condicion (id_regla, orden, tipo, referencia, valor_esperado)
SELECT r.id_regla, v.orden, v.tipo, v.referencia, v.valor FROM reglas r, (VALUES (1, 'pregunta', '74', 'si'), (2, 'obd', 'P033', 'si')) AS v(orden, tipo, referencia, valor)
WHERE upper(r.codigo) = 'R107' AND r.id_pregunta = 74 ON CONFLICT (id_regla, orden) DO NOTHING;
-- R108: SI P76 Y obd:P0016 ENTONCES H52
INSERT INTO reglas (id_regla, codigo, id_pregunta, id_hipotesis, id_area, nivel_atencion, gravedad, recomendacion, peso, version, activa, concluye_hecho)
SELECT (SELECT COALESCE(MAX(id_regla), 0) + 1 FROM reglas), 'R108', 76, 52, 18, 'No debe seguir usandose', 4, 'Motor que se apaga y no enciende con correlacion ciguenal/arbol (P0016): verificar puesta a punto antes de intentar arrancar.', 1.20, 1, TRUE, NULL
WHERE NOT EXISTS (SELECT 1 FROM reglas WHERE upper(codigo) = 'R108');
INSERT INTO regla_condicion (id_regla, orden, tipo, referencia, valor_esperado)
SELECT r.id_regla, v.orden, v.tipo, v.referencia, v.valor FROM reglas r, (VALUES (1, 'pregunta', '76', 'si'), (2, 'obd', 'P0016', 'si')) AS v(orden, tipo, referencia, valor)
WHERE upper(r.codigo) = 'R108' AND r.id_pregunta = 76 ON CONFLICT (id_regla, orden) DO NOTHING;
-- R109: SI P59 Y obd:U0 ENTONCES H35
INSERT INTO reglas (id_regla, codigo, id_pregunta, id_hipotesis, id_area, nivel_atencion, gravedad, recomendacion, peso, version, activa, concluye_hecho)
SELECT (SELECT COALESCE(MAX(id_regla), 0) + 1 FROM reglas), 'R109', 59, 35, 21, 'Revision prioritaria', 3, 'Fallas simultaneas con codigos U0xxx: perdida de comunicacion en la red CAN; revisar ECU/PCM, alimentacion y masas.', 1.10, 1, TRUE, NULL
WHERE NOT EXISTS (SELECT 1 FROM reglas WHERE upper(codigo) = 'R109');
INSERT INTO regla_condicion (id_regla, orden, tipo, referencia, valor_esperado)
SELECT r.id_regla, v.orden, v.tipo, v.referencia, v.valor FROM reglas r, (VALUES (1, 'pregunta', '59', 'si'), (2, 'obd', 'U0', 'si')) AS v(orden, tipo, referencia, valor)
WHERE upper(r.codigo) = 'R109' AND r.id_pregunta = 59 ON CONFLICT (id_regla, orden) DO NOTHING;
-- R110: SI P89 Y testigo:INMOVILIZADOR ENTONCES H65
INSERT INTO reglas (id_regla, codigo, id_pregunta, id_hipotesis, id_area, nivel_atencion, gravedad, recomendacion, peso, version, activa, concluye_hecho)
SELECT (SELECT COALESCE(MAX(id_regla), 0) + 1 FROM reglas), 'R110', 89, 65, 6, 'Revision proxima', 2, 'Motor gira sin arrancar con testigo del inmovilizador: probar con la llave de repuesto y reprogramar el transpondedor.', 1.00, 1, TRUE, NULL
WHERE NOT EXISTS (SELECT 1 FROM reglas WHERE upper(codigo) = 'R110');
INSERT INTO regla_condicion (id_regla, orden, tipo, referencia, valor_esperado)
SELECT r.id_regla, v.orden, v.tipo, v.referencia, v.valor FROM reglas r, (VALUES (1, 'pregunta', '89', 'si'), (2, 'testigo', 'INMOVILIZADOR', 'si')) AS v(orden, tipo, referencia, valor)
WHERE upper(r.codigo) = 'R110' AND r.id_pregunta = 89 ON CONFLICT (id_regla, orden) DO NOTHING;

-- ===================== TESTIGOS DEL TABLERO =====================
INSERT INTO testigo_hipotesis (testigo, id_hipotesis, peso) VALUES ('CHECK_ENGINE', 14, 0.60) ON CONFLICT (testigo, id_hipotesis) DO UPDATE SET peso = EXCLUDED.peso;
INSERT INTO testigo_hipotesis (testigo, id_hipotesis, peso) VALUES ('CHECK_ENGINE', 35, 0.30) ON CONFLICT (testigo, id_hipotesis) DO UPDATE SET peso = EXCLUDED.peso;
INSERT INTO testigo_hipotesis (testigo, id_hipotesis, peso) VALUES ('BATERIA', 5, 0.60) ON CONFLICT (testigo, id_hipotesis) DO UPDATE SET peso = EXCLUDED.peso;
INSERT INTO testigo_hipotesis (testigo, id_hipotesis, peso) VALUES ('BATERIA', 3, 0.40) ON CONFLICT (testigo, id_hipotesis) DO UPDATE SET peso = EXCLUDED.peso;
INSERT INTO testigo_hipotesis (testigo, id_hipotesis, peso) VALUES ('BATERIA', 55, 0.30) ON CONFLICT (testigo, id_hipotesis) DO UPDATE SET peso = EXCLUDED.peso;
INSERT INTO testigo_hipotesis (testigo, id_hipotesis, peso) VALUES ('ACEITE', 46, 0.60) ON CONFLICT (testigo, id_hipotesis) DO UPDATE SET peso = EXCLUDED.peso;
INSERT INTO testigo_hipotesis (testigo, id_hipotesis, peso) VALUES ('ACEITE', 16, 0.50) ON CONFLICT (testigo, id_hipotesis) DO UPDATE SET peso = EXCLUDED.peso;
INSERT INTO testigo_hipotesis (testigo, id_hipotesis, peso) VALUES ('ACEITE', 45, 0.30) ON CONFLICT (testigo, id_hipotesis) DO UPDATE SET peso = EXCLUDED.peso;
INSERT INTO testigo_hipotesis (testigo, id_hipotesis, peso) VALUES ('TEMPERATURA', 17, 0.60) ON CONFLICT (testigo, id_hipotesis) DO UPDATE SET peso = EXCLUDED.peso;
INSERT INTO testigo_hipotesis (testigo, id_hipotesis, peso) VALUES ('TEMPERATURA', 18, 0.50) ON CONFLICT (testigo, id_hipotesis) DO UPDATE SET peso = EXCLUDED.peso;
INSERT INTO testigo_hipotesis (testigo, id_hipotesis, peso) VALUES ('TEMPERATURA', 19, 0.40) ON CONFLICT (testigo, id_hipotesis) DO UPDATE SET peso = EXCLUDED.peso;
INSERT INTO testigo_hipotesis (testigo, id_hipotesis, peso) VALUES ('FRENOS', 20, 0.50) ON CONFLICT (testigo, id_hipotesis) DO UPDATE SET peso = EXCLUDED.peso;
INSERT INTO testigo_hipotesis (testigo, id_hipotesis, peso) VALUES ('FRENOS', 24, 0.30) ON CONFLICT (testigo, id_hipotesis) DO UPDATE SET peso = EXCLUDED.peso;
INSERT INTO testigo_hipotesis (testigo, id_hipotesis, peso) VALUES ('FRENOS', 59, 0.30) ON CONFLICT (testigo, id_hipotesis) DO UPDATE SET peso = EXCLUDED.peso;
INSERT INTO testigo_hipotesis (testigo, id_hipotesis, peso) VALUES ('ABS', 23, 0.60) ON CONFLICT (testigo, id_hipotesis) DO UPDATE SET peso = EXCLUDED.peso;
INSERT INTO testigo_hipotesis (testigo, id_hipotesis, peso) VALUES ('ABS', 68, 0.40) ON CONFLICT (testigo, id_hipotesis) DO UPDATE SET peso = EXCLUDED.peso;
INSERT INTO testigo_hipotesis (testigo, id_hipotesis, peso) VALUES ('AIRBAG', 44, 0.80) ON CONFLICT (testigo, id_hipotesis) DO UPDATE SET peso = EXCLUDED.peso;
INSERT INTO testigo_hipotesis (testigo, id_hipotesis, peso) VALUES ('ESP', 67, 0.60) ON CONFLICT (testigo, id_hipotesis) DO UPDATE SET peso = EXCLUDED.peso;
INSERT INTO testigo_hipotesis (testigo, id_hipotesis, peso) VALUES ('ESP', 68, 0.40) ON CONFLICT (testigo, id_hipotesis) DO UPDATE SET peso = EXCLUDED.peso;
INSERT INTO testigo_hipotesis (testigo, id_hipotesis, peso) VALUES ('TPMS', 38, 0.70) ON CONFLICT (testigo, id_hipotesis) DO UPDATE SET peso = EXCLUDED.peso;
INSERT INTO testigo_hipotesis (testigo, id_hipotesis, peso) VALUES ('EPS', 25, 0.70) ON CONFLICT (testigo, id_hipotesis) DO UPDATE SET peso = EXCLUDED.peso;
INSERT INTO testigo_hipotesis (testigo, id_hipotesis, peso) VALUES ('PRECALENTAMIENTO', 4, 0.40) ON CONFLICT (testigo, id_hipotesis) DO UPDATE SET peso = EXCLUDED.peso;
INSERT INTO testigo_hipotesis (testigo, id_hipotesis, peso) VALUES ('INMOVILIZADOR', 65, 0.80) ON CONFLICT (testigo, id_hipotesis) DO UPDATE SET peso = EXCLUDED.peso;

-- ===================== CODIGOS OBD-II =====================
INSERT INTO obd_hipotesis (prefijo, id_hipotesis, peso, descripcion) VALUES ('P030', 10, 0.60, 'P0300-P0309: fallo de encendido aleatorio o por cilindro') ON CONFLICT (prefijo, id_hipotesis) DO UPDATE SET peso = EXCLUDED.peso, descripcion = EXCLUDED.descripcion;
INSERT INTO obd_hipotesis (prefijo, id_hipotesis, peso, descripcion) VALUES ('P030', 15, 0.50, 'P0300-P0309: fallo de encendido aleatorio o por cilindro') ON CONFLICT (prefijo, id_hipotesis) DO UPDATE SET peso = EXCLUDED.peso, descripcion = EXCLUDED.descripcion;
INSERT INTO obd_hipotesis (prefijo, id_hipotesis, peso, descripcion) VALUES ('P017', 9, 0.40, 'P0170-P0175: correccion de mezcla fuera de rango') ON CONFLICT (prefijo, id_hipotesis) DO UPDATE SET peso = EXCLUDED.peso, descripcion = EXCLUDED.descripcion;
INSERT INTO obd_hipotesis (prefijo, id_hipotesis, peso, descripcion) VALUES ('P017', 49, 0.40, 'P0170-P0175: correccion de mezcla fuera de rango') ON CONFLICT (prefijo, id_hipotesis) DO UPDATE SET peso = EXCLUDED.peso, descripcion = EXCLUDED.descripcion;
INSERT INTO obd_hipotesis (prefijo, id_hipotesis, peso, descripcion) VALUES ('P0171', 7, 0.50, 'P0171: sistema demasiado pobre (banco 1)') ON CONFLICT (prefijo, id_hipotesis) DO UPDATE SET peso = EXCLUDED.peso, descripcion = EXCLUDED.descripcion;
INSERT INTO obd_hipotesis (prefijo, id_hipotesis, peso, descripcion) VALUES ('P0171', 47, 0.40, 'P0171: sistema demasiado pobre (banco 1)') ON CONFLICT (prefijo, id_hipotesis) DO UPDATE SET peso = EXCLUDED.peso, descripcion = EXCLUDED.descripcion;
INSERT INTO obd_hipotesis (prefijo, id_hipotesis, peso, descripcion) VALUES ('P0172', 9, 0.60, 'P0172: sistema demasiado rico (banco 1)') ON CONFLICT (prefijo, id_hipotesis) DO UPDATE SET peso = EXCLUDED.peso, descripcion = EXCLUDED.descripcion;
INSERT INTO obd_hipotesis (prefijo, id_hipotesis, peso, descripcion) VALUES ('P0172', 6, 0.30, 'P0172: sistema demasiado rico (banco 1)') ON CONFLICT (prefijo, id_hipotesis) DO UPDATE SET peso = EXCLUDED.peso, descripcion = EXCLUDED.descripcion;
INSERT INTO obd_hipotesis (prefijo, id_hipotesis, peso, descripcion) VALUES ('P010', 49, 0.60, 'P0100-P0109: circuito del sensor MAF o MAP') ON CONFLICT (prefijo, id_hipotesis) DO UPDATE SET peso = EXCLUDED.peso, descripcion = EXCLUDED.descripcion;
INSERT INTO obd_hipotesis (prefijo, id_hipotesis, peso, descripcion) VALUES ('P0562', 5, 0.60, 'P0562: tension del sistema baja') ON CONFLICT (prefijo, id_hipotesis) DO UPDATE SET peso = EXCLUDED.peso, descripcion = EXCLUDED.descripcion;
INSERT INTO obd_hipotesis (prefijo, id_hipotesis, peso, descripcion) VALUES ('P0562', 3, 0.40, 'P0562: tension del sistema baja') ON CONFLICT (prefijo, id_hipotesis) DO UPDATE SET peso = EXCLUDED.peso, descripcion = EXCLUDED.descripcion;
INSERT INTO obd_hipotesis (prefijo, id_hipotesis, peso, descripcion) VALUES ('P0620', 5, 0.70, 'P0620: circuito de control del generador (alternador)') ON CONFLICT (prefijo, id_hipotesis) DO UPDATE SET peso = EXCLUDED.peso, descripcion = EXCLUDED.descripcion;
INSERT INTO obd_hipotesis (prefijo, id_hipotesis, peso, descripcion) VALUES ('P052', 46, 0.70, 'P0520-P0524: sensor o circuito de presion de aceite') ON CONFLICT (prefijo, id_hipotesis) DO UPDATE SET peso = EXCLUDED.peso, descripcion = EXCLUDED.descripcion;
INSERT INTO obd_hipotesis (prefijo, id_hipotesis, peso, descripcion) VALUES ('P052', 16, 0.40, 'P0520-P0524: sensor o circuito de presion de aceite') ON CONFLICT (prefijo, id_hipotesis) DO UPDATE SET peso = EXCLUDED.peso, descripcion = EXCLUDED.descripcion;
INSERT INTO obd_hipotesis (prefijo, id_hipotesis, peso, descripcion) VALUES ('P021', 17, 0.60, 'P0217: condicion de sobretemperatura del motor') ON CONFLICT (prefijo, id_hipotesis) DO UPDATE SET peso = EXCLUDED.peso, descripcion = EXCLUDED.descripcion;
INSERT INTO obd_hipotesis (prefijo, id_hipotesis, peso, descripcion) VALUES ('P021', 18, 0.30, 'P0217: condicion de sobretemperatura del motor') ON CONFLICT (prefijo, id_hipotesis) DO UPDATE SET peso = EXCLUDED.peso, descripcion = EXCLUDED.descripcion;
INSERT INTO obd_hipotesis (prefijo, id_hipotesis, peso, descripcion) VALUES ('P011', 17, 0.30, 'P0115-P0119: circuito del sensor de temperatura del refrigerante') ON CONFLICT (prefijo, id_hipotesis) DO UPDATE SET peso = EXCLUDED.peso, descripcion = EXCLUDED.descripcion;
INSERT INTO obd_hipotesis (prefijo, id_hipotesis, peso, descripcion) VALUES ('P011', 19, 0.30, 'P0115-P0119: circuito del sensor de temperatura del refrigerante') ON CONFLICT (prefijo, id_hipotesis) DO UPDATE SET peso = EXCLUDED.peso, descripcion = EXCLUDED.descripcion;
INSERT INTO obd_hipotesis (prefijo, id_hipotesis, peso, descripcion) VALUES ('P0128', 43, 0.60, 'P0128: termostato por debajo de la temperatura de regulacion') ON CONFLICT (prefijo, id_hipotesis) DO UPDATE SET peso = EXCLUDED.peso, descripcion = EXCLUDED.descripcion;
INSERT INTO obd_hipotesis (prefijo, id_hipotesis, peso, descripcion) VALUES ('P033', 50, 0.70, 'P0335-P0339: sensor de posicion del ciguenal') ON CONFLICT (prefijo, id_hipotesis) DO UPDATE SET peso = EXCLUDED.peso, descripcion = EXCLUDED.descripcion;
INSERT INTO obd_hipotesis (prefijo, id_hipotesis, peso, descripcion) VALUES ('P034', 50, 0.40, 'P0340-P0349: sensor de posicion del arbol de levas') ON CONFLICT (prefijo, id_hipotesis) DO UPDATE SET peso = EXCLUDED.peso, descripcion = EXCLUDED.descripcion;
INSERT INTO obd_hipotesis (prefijo, id_hipotesis, peso, descripcion) VALUES ('P034', 52, 0.30, 'P0340-P0349: sensor de posicion del arbol de levas') ON CONFLICT (prefijo, id_hipotesis) DO UPDATE SET peso = EXCLUDED.peso, descripcion = EXCLUDED.descripcion;
INSERT INTO obd_hipotesis (prefijo, id_hipotesis, peso, descripcion) VALUES ('P0016', 52, 0.60, 'P0016-P0019: correlacion ciguenal / arbol de levas') ON CONFLICT (prefijo, id_hipotesis) DO UPDATE SET peso = EXCLUDED.peso, descripcion = EXCLUDED.descripcion;
INSERT INTO obd_hipotesis (prefijo, id_hipotesis, peso, descripcion) VALUES ('P0016', 51, 0.50, 'P0016-P0019: correlacion ciguenal / arbol de levas') ON CONFLICT (prefijo, id_hipotesis) DO UPDATE SET peso = EXCLUDED.peso, descripcion = EXCLUDED.descripcion;
INSERT INTO obd_hipotesis (prefijo, id_hipotesis, peso, descripcion) VALUES ('P042', 54, 0.70, 'P0420-P0430: eficiencia del catalizador bajo el umbral') ON CONFLICT (prefijo, id_hipotesis) DO UPDATE SET peso = EXCLUDED.peso, descripcion = EXCLUDED.descripcion;
INSERT INTO obd_hipotesis (prefijo, id_hipotesis, peso, descripcion) VALUES ('P044', 48, 0.40, 'P0440-P0449: sistema de control de emisiones evaporativas (fuga)') ON CONFLICT (prefijo, id_hipotesis) DO UPDATE SET peso = EXCLUDED.peso, descripcion = EXCLUDED.descripcion;
INSERT INTO obd_hipotesis (prefijo, id_hipotesis, peso, descripcion) VALUES ('P050', 63, 0.50, 'P0500-P0503: sensor de velocidad del vehiculo') ON CONFLICT (prefijo, id_hipotesis) DO UPDATE SET peso = EXCLUDED.peso, descripcion = EXCLUDED.descripcion;
INSERT INTO obd_hipotesis (prefijo, id_hipotesis, peso, descripcion) VALUES ('P07', 30, 0.50, 'P07xx: sistema de control de la transmision') ON CONFLICT (prefijo, id_hipotesis) DO UPDATE SET peso = EXCLUDED.peso, descripcion = EXCLUDED.descripcion;
INSERT INTO obd_hipotesis (prefijo, id_hipotesis, peso, descripcion) VALUES ('C00', 23, 0.60, 'C00xx: sistema ABS / sensores de rueda') ON CONFLICT (prefijo, id_hipotesis) DO UPDATE SET peso = EXCLUDED.peso, descripcion = EXCLUDED.descripcion;
INSERT INTO obd_hipotesis (prefijo, id_hipotesis, peso, descripcion) VALUES ('C00', 68, 0.40, 'C00xx: sistema ABS / sensores de rueda') ON CONFLICT (prefijo, id_hipotesis) DO UPDATE SET peso = EXCLUDED.peso, descripcion = EXCLUDED.descripcion;
INSERT INTO obd_hipotesis (prefijo, id_hipotesis, peso, descripcion) VALUES ('B00', 44, 0.70, 'B00xx: sistema de airbag (SRS)') ON CONFLICT (prefijo, id_hipotesis) DO UPDATE SET peso = EXCLUDED.peso, descripcion = EXCLUDED.descripcion;
INSERT INTO obd_hipotesis (prefijo, id_hipotesis, peso, descripcion) VALUES ('U0', 35, 0.60, 'U0xxx: perdida de comunicacion en la red de modulos') ON CONFLICT (prefijo, id_hipotesis) DO UPDATE SET peso = EXCLUDED.peso, descripcion = EXCLUDED.descripcion;
INSERT INTO obd_hipotesis (prefijo, id_hipotesis, peso, descripcion) VALUES ('U0', 68, 0.30, 'U0xxx: perdida de comunicacion en la red de modulos') ON CONFLICT (prefijo, id_hipotesis) DO UPDATE SET peso = EXCLUDED.peso, descripcion = EXCLUDED.descripcion;
