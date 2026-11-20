-- 10_parada_por_certeza.sql
-- Criterio de parada adicional: detener cuando la hipotesis con mayor certeza
-- supera umbral_certeza_parada y aventaja a la segunda en margen_certeza_parada.
-- Idempotente.
INSERT INTO parametros_inferencia (clave, valor) VALUES ('umbral_certeza_parada', 0.85)
    ON CONFLICT (clave) DO NOTHING;
INSERT INTO parametros_inferencia (clave, valor) VALUES ('margen_certeza_parada', 0.30)
    ON CONFLICT (clave) DO NOTHING;
