-- 07_motor_experto.sql
-- Extension del motor de inferencia a sistema experto con reglas
-- compuestas (premisas conjuntivas con negacion), encadenamiento hacia
-- adelante por hechos intermedios y evidencia de testigos del tablero y
-- codigos OBD-II.
--
-- ADITIVO e idempotente: CREATE TABLE IF NOT EXISTS, ADD COLUMN IF NOT
-- EXISTS y restricciones agregadas solo si no existen. No contiene DROP
-- de tablas ni borra datos. Una regla sin filas en regla_condicion se
-- comporta exactamente como antes (granulo directo por su id_pregunta).

SET client_encoding = 'UTF8';

-- ===================== HECHOS INTERMEDIOS =====================
CREATE TABLE IF NOT EXISTS hechos (
    codigo      VARCHAR(40) PRIMARY KEY,           -- FALLA_CARGA, MEZCLA_RICA, ...
    descripcion TEXT NOT NULL
);

-- ===================== REGLAS (columnas nuevas) =====================
-- Regla intermedia: concluye un hecho y no una hipotesis.
ALTER TABLE reglas ADD COLUMN IF NOT EXISTS concluye_hecho VARCHAR(40) NULL;
ALTER TABLE reglas ALTER COLUMN id_hipotesis DROP NOT NULL;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                   WHERE conname = 'fk_reglas_hecho' AND conrelid = 'reglas'::regclass) THEN
        ALTER TABLE reglas ADD CONSTRAINT fk_reglas_hecho
            FOREIGN KEY (concluye_hecho) REFERENCES hechos(codigo);
    END IF;
    -- toda regla concluye algo: una hipotesis (final) o un hecho (intermedia), no ambos
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                   WHERE conname = 'ck_reglas_conclusion' AND conrelid = 'reglas'::regclass) THEN
        ALTER TABLE reglas ADD CONSTRAINT ck_reglas_conclusion
            CHECK ((id_hipotesis IS NOT NULL) <> (concluye_hecho IS NOT NULL));
    END IF;
END
$$;

-- ===================== PREMISAS DE LAS REGLAS COMPUESTAS =====================
-- Conjuncion de condiciones. tipo:
--   pregunta -> referencia = id_pregunta (texto), se evalua con la certeza de la respuesta
--   testigo  -> referencia = codigo del testigo (BATERIA, ACEITE, ...)
--   obd      -> referencia = prefijo del codigo OBD-II (P030, C00, U0, ...)
--   hecho    -> referencia = hechos.codigo concluido por otra regla
-- valor_esperado 'no' expresa la negacion (SI ... Y NO P13 ...).
CREATE TABLE IF NOT EXISTS regla_condicion (
    id_regla       INTEGER NOT NULL REFERENCES reglas(id_regla) ON DELETE CASCADE,
    orden          SMALLINT NOT NULL,
    tipo           VARCHAR(10) NOT NULL CHECK (tipo IN ('pregunta', 'testigo', 'obd', 'hecho')),
    referencia     VARCHAR(40) NOT NULL,
    valor_esperado VARCHAR(2) NOT NULL DEFAULT 'si' CHECK (valor_esperado IN ('si', 'no')),
    PRIMARY KEY (id_regla, orden)
);
CREATE INDEX IF NOT EXISTS idx_regla_condicion_ref ON regla_condicion(tipo, referencia);

-- ===================== EVIDENCIA DEL TABLERO Y DEL ESCANER =====================
CREATE TABLE IF NOT EXISTS testigo_hipotesis (
    testigo      VARCHAR(30) NOT NULL,             -- codigo corto del testigo (BATERIA, ABS, ...)
    id_hipotesis INTEGER NOT NULL REFERENCES hipotesis(id_hipotesis),
    peso         NUMERIC(4,2) NOT NULL CHECK (peso > 0 AND peso <= 2),
    PRIMARY KEY (testigo, id_hipotesis)
);

CREATE TABLE IF NOT EXISTS obd_hipotesis (
    prefijo      VARCHAR(5) NOT NULL,              -- P030, P0562, C00, U0 ...
    id_hipotesis INTEGER NOT NULL REFERENCES hipotesis(id_hipotesis),
    peso         NUMERIC(4,2) NOT NULL CHECK (peso > 0 AND peso <= 2),
    descripcion  TEXT,
    PRIMARY KEY (prefijo, id_hipotesis)
);

-- ===================== DIAGNOSTICO (columnas nuevas) =====================
-- certeza acotada [0,1] (MYCIN) y explicacion "como" en JSON.
ALTER TABLE atencion_diagnostico ADD COLUMN IF NOT EXISTS certeza NUMERIC(5,4) NULL;
ALTER TABLE atencion_diagnostico ADD COLUMN IF NOT EXISTS explicacion TEXT NULL;
