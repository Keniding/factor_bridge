-- FactorBridge — Schema Supabase/PostgreSQL
-- Ejecutar una sola vez en el proyecto Supabase.
-- Incluye datos seed equivalentes a los mocks de desarrollo.

-- -----------------------------------------------------------------------
-- Factores (compradores de facturas)
-- -----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS factores (
    id               TEXT        PRIMARY KEY,
    nombre           TEXT        NOT NULL,
    apetito_riesgo   TEXT        NOT NULL CHECK (apetito_riesgo IN ('conservador', 'balanceado', 'agresivo')),
    ticket_min_pen   NUMERIC     NOT NULL,
    ticket_max_pen   NUMERIC     NOT NULL,
    plazo_max_dias   INTEGER     NOT NULL,
    tasa_mensual_min NUMERIC     NOT NULL,
    tasa_mensual_max NUMERIC     NOT NULL,
    sectores         TEXT[]      NOT NULL,
    activo           BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- -----------------------------------------------------------------------
-- Cedentes (vendedores de facturas)
-- -----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS cedentes (
    id                   TEXT        PRIMARY KEY,
    razon_social         TEXT        NOT NULL,
    ruc                  TEXT        UNIQUE NOT NULL,
    sector               TEXT        NOT NULL,
    facturas_publicadas  INTEGER     NOT NULL DEFAULT 0,
    activo               BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- -----------------------------------------------------------------------
-- Intenciones de operacion (vender / comprar factura)
-- -----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS intenciones (
    intent_id       TEXT        PRIMARY KEY,
    actor_role      TEXT        NOT NULL CHECK (actor_role IN ('cedente', 'factor')),
    actor_document  TEXT        NOT NULL,
    payload         TEXT        NOT NULL,
    status          TEXT        NOT NULL DEFAULT 'pending_match',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- -----------------------------------------------------------------------
-- Seed — factores
-- -----------------------------------------------------------------------
INSERT INTO factores (id, nombre, apetito_riesgo, ticket_min_pen, ticket_max_pen, plazo_max_dias, tasa_mensual_min, tasa_mensual_max, sectores)
VALUES
    ('FAC-001', 'Capital Andino SAC',             'conservador', 10000,  200000,  90,  1.5, 2.2, ARRAY['comercio','servicios']),
    ('FAC-002', 'Liquidez Pacifico Fondo Privado', 'balanceado',  5000,   500000,  120, 1.8, 3.0, ARRAY['comercio','industria','construccion']),
    ('FAC-003', 'RiesgoPlus Crypto Factor',        'agresivo',    1000,   100000,  180, 2.5, 5.0, ARRAY['cualquiera']),
    ('FAC-004', 'Inversiones del Sur EIRL',        'balanceado',  20000,  1000000, 90,  1.6, 2.5, ARRAY['industria','servicios'])
ON CONFLICT (id) DO NOTHING;

-- -----------------------------------------------------------------------
-- Seed — cedentes
-- -----------------------------------------------------------------------
INSERT INTO cedentes (id, razon_social, ruc, sector, facturas_publicadas)
VALUES
    ('CED-001', 'Textiles La Joya SAC',              '20512345678', 'industria', 3),
    ('CED-002', 'Servicios Logisticos Andinos EIRL', '20445566778', 'servicios', 1)
ON CONFLICT (id) DO NOTHING;

-- -----------------------------------------------------------------------
-- Documentos validados (RUC y DNI consultados a SUNAT/RENIEC o cargados)
-- La columna payload almacena el JSON completo de la respuesta oficial.
-- -----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS documentos (
    numero      TEXT        PRIMARY KEY,
    tipo        TEXT        NOT NULL CHECK (tipo IN ('RUC', 'DNI')),
    nombre      TEXT        NOT NULL,
    estado      TEXT,
    condicion   TEXT,
    direccion   TEXT,
    actividad   TEXT,
    fuente      TEXT        NOT NULL DEFAULT 'manual',
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- -----------------------------------------------------------------------
-- Seed — documentos RUC (equivalente a los mocks de identity_tools.py)
-- -----------------------------------------------------------------------
INSERT INTO documentos (numero, tipo, nombre, estado, condicion, direccion, actividad, fuente)
VALUES
    ('20512345678', 'RUC', 'DISTRIBUIDORA SAN MARTIN S.A.C.',     'ACTIVO', 'HABIDO',    'AV. JAVIER PRADO ESTE 1234, SAN ISIDRO, LIMA', 'Comercio al por mayor',   'seed'),
    ('20601030013', 'RUC', 'REXTIE S.A.C.',                       'ACTIVO', 'HABIDO',    'AV. LARCO 345, MIRAFLORES, LIMA',               'Servicios financieros',   'seed'),
    ('20999999999', 'RUC', 'EMPRESA MOROSA S.A.',                  'ACTIVO', 'NO HABIDO', 'DESCONOCIDA',                                   'No declarada',            'seed'),
    ('20445566778', 'RUC', 'SERVICIOS LOGISTICOS ANDINOS EIRL',   'ACTIVO', 'HABIDO',    'JR. LOS PINOS 456, SURCO, LIMA',               'Transporte y logistica',  'seed')
ON CONFLICT (numero) DO NOTHING;

-- -----------------------------------------------------------------------
-- Seed — documentos DNI
-- -----------------------------------------------------------------------
INSERT INTO documentos (numero, tipo, nombre, fuente)
VALUES
    ('12345678', 'DNI', 'JUAN ALBERTO PEREZ GARCIA',        'seed'),
    ('87654321', 'DNI', 'MARIA DEL CARMEN RODRIGUEZ LOPEZ', 'seed')
ON CONFLICT (numero) DO NOTHING;

-- -----------------------------------------------------------------------
-- Perfiles crediticios precargados (equivalente a scoring SBS/Infocorp)
-- score: 300-850  |  banda: VERDE / AMARILLO / ROJO
-- -----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS credit_scores (
    numero           TEXT        PRIMARY KEY,
    score            INTEGER     NOT NULL CHECK (score BETWEEN 300 AND 850),
    banda_riesgo     TEXT        NOT NULL CHECK (banda_riesgo IN ('VERDE', 'AMARILLO', 'ROJO')),
    morosidad_activa BOOLEAN     NOT NULL DEFAULT FALSE,
    lista_negra_sbs  BOOLEAN     NOT NULL DEFAULT FALSE,
    sunat_no_habido  BOOLEAN     NOT NULL DEFAULT FALSE,
    deuda_pen        NUMERIC     NOT NULL DEFAULT 0,
    dias_mora        INTEGER     NOT NULL DEFAULT 0,
    fuente           TEXT        NOT NULL DEFAULT 'manual',
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- -----------------------------------------------------------------------
-- Seed — perfiles crediticios (RUC conocidos)
-- -----------------------------------------------------------------------
INSERT INTO credit_scores (numero, score, banda_riesgo, morosidad_activa, lista_negra_sbs, sunat_no_habido, deuda_pen, dias_mora, fuente)
VALUES
    ('20512345678', 780, 'VERDE',    FALSE, FALSE, FALSE,     0,     0, 'seed'),
    ('20601030013', 720, 'VERDE',    FALSE, FALSE, FALSE,     0,     0, 'seed'),
    ('20999999999', 480, 'ROJO',     TRUE,  FALSE, TRUE,  4625.0,   37, 'seed'),
    ('20445566778', 650, 'AMARILLO', TRUE,  FALSE, FALSE, 2500.0,   20, 'seed'),
    ('12345678',    810, 'VERDE',    FALSE, FALSE, FALSE,     0,     0, 'seed'),
    ('87654321',    540, 'ROJO',     TRUE,  FALSE, FALSE, 3875.0,   31, 'seed')
ON CONFLICT (numero) DO NOTHING;
