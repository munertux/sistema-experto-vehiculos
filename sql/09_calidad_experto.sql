-- 09_calidad_experto.sql
-- Ajustes de calidad del motor experto (rama qa). ADITIVO e idempotente:
-- se puede aplicar varias veces sobre una base con 01, 02, 05-08.
--
-- 1) umbral_minimo_certeza: certeza [0,1] minima para presentar una
--    hipotesis como diagnostico. Con 0,20 una sola respuesta "Probablemente
--    si" a un sintoma especifico (peso 1,0 -> 0,25) ya cuenta; una
--    hipotesis que solo recibio respuestas "No" (certeza 0) no se presenta
--    y la consulta cierra como "sin falla identificada".
SET client_encoding = 'UTF8';

INSERT INTO parametros_inferencia (clave, valor) VALUES ('umbral_minimo_certeza', 0.20)
ON CONFLICT (clave) DO NOTHING;

-- 2) R111: SI hecho SOBRECALENTAMIENTO ENTONCES 'Falla en el sistema de
--    refrigeracion' (H17). Motivo (bateria de casos, caso "sobrecalentamiento
--    con encadenamiento"): el hecho intermedio SOBRECALENTAMIENTO (R95: aguja
--    al maximo + testigo de temperatura; R96: temperatura que sube + ventilador
--    que no enciende) solo alimentaba hipotesis del area Temperatura (R97/R98)
--    y del area Climatizacion (R99); la hipotesis general H17, que es la
--    conclusion directa de un sobrecalentamiento confirmado por dos fuentes,
--    no lo consumia y el encadenamiento no aparecia en el "como" del lider.
--    Peso 1,00 y nivel "No debe seguir usandose" (igual que R17). Misma
--    convencion de 08: se identifica por codigo y la condicion solo se asocia
--    si la regla tiene la pregunta principal esperada (P41).
INSERT INTO reglas (id_regla, codigo, id_pregunta, id_hipotesis, id_area, nivel_atencion, gravedad, recomendacion, peso, version, activa, concluye_hecho)
SELECT (SELECT COALESCE(MAX(id_regla), 0) + 1 FROM reglas), 'R111', 41, 17, 8, 'No debe seguir usandose', 4,
       'Sobrecalentamiento confirmado: detenga el motor, deje enfriar sin abrir la tapa del radiador y revise nivel de refrigerante, termostato, bomba de agua y electroventilador antes de volver a conducir.',
       1.00, 1, TRUE, NULL
WHERE NOT EXISTS (SELECT 1 FROM reglas WHERE upper(codigo) = 'R111');
INSERT INTO regla_condicion (id_regla, orden, tipo, referencia, valor_esperado)
SELECT r.id_regla, v.orden, v.tipo, v.referencia, v.valor FROM reglas r,
       (VALUES (1, 'hecho', 'SOBRECALENTAMIENTO', 'si')) AS v(orden, tipo, referencia, valor)
WHERE upper(r.codigo) = 'R111' AND r.id_pregunta = 41 ON CONFLICT (id_regla, orden) DO NOTHING;
