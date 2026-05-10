# Integracion Supabase / PostgreSQL

Fecha: 2026-05-10
Proyecto Supabase: wzavnbatuhdbsrqrjaws (pool AWS us-west-1)
Tablas activas: 5

---

## Conexion

La cadena de conexion se almacena en Secret Manager como `POSTGRES_URL` y
se inyecta en Cloud Run via `--set-secrets`. En desarrollo local va en
`factor_bridge_agent/.env`.

Formato:
```
postgresql://postgres.{proyecto}:{password}@{host}.pooler.supabase.com:5432/postgres
```

El modulo `factor_bridge_agent/db.py` gestiona un pool psycopg2 de 1-5
conexiones que se inicializa de forma perezosa al primer uso:

```python
_pool = pool.SimpleConnectionPool(1, 5, dsn=os.environ["POSTGRES_URL"])
```

`POSTGRES_URL` es obligatorio. Sin el, el agente no arranca.

---

## Schema

Definicion completa en `factor_bridge_agent/schema.sql`.
Ejecutar una sola vez en el proyecto Supabase (idempotente por `IF NOT EXISTS`
y `ON CONFLICT DO NOTHING`).

### factores

Compradores de facturas registrados en la plataforma.

| Columna | Tipo | Descripcion |
|---|---|---|
| id | TEXT PK | Identificador (FAC-001, FAC-002, ...) |
| nombre | TEXT | Razon social del fondo/empresa |
| apetito_riesgo | TEXT | conservador / balanceado / agresivo |
| ticket_min_pen | NUMERIC | Monto minimo de factura en soles |
| ticket_max_pen | NUMERIC | Monto maximo de factura en soles |
| plazo_max_dias | INTEGER | Plazo maximo aceptado en dias |
| tasa_mensual_min | NUMERIC | Tasa mensual minima (%) |
| tasa_mensual_max | NUMERIC | Tasa mensual maxima (%) |
| sectores | TEXT[] | Sectores que acepta. "cualquiera" = sin filtro |
| activo | BOOLEAN | FALSE excluye al factor del matching |
| created_at | TIMESTAMPTZ | |

Registros actuales: 4 (FAC-001 a FAC-004)

### cedentes

Empresas que venden facturas en la plataforma.

| Columna | Tipo | Descripcion |
|---|---|---|
| id | TEXT PK | Identificador (CED-001, CED-002, ...) |
| razon_social | TEXT | |
| ruc | TEXT UNIQUE | RUC de 11 digitos |
| sector | TEXT | Sector economico |
| facturas_publicadas | INTEGER | Contador historico |
| activo | BOOLEAN | |
| created_at | TIMESTAMPTZ | |

Registros actuales: 2 (CED-001, CED-002)

### documentos

Identidades validadas (RUC via SUNAT, DNI via RENIEC).

| Columna | Tipo | Descripcion |
|---|---|---|
| numero | TEXT PK | Numero de documento |
| tipo | TEXT | RUC o DNI |
| nombre | TEXT | Razon social (RUC) o nombre completo (DNI) |
| estado | TEXT | ACTIVO / INACTIVO (solo RUC) |
| condicion | TEXT | HABIDO / NO HABIDO (solo RUC) |
| direccion | TEXT | (solo RUC) |
| actividad | TEXT | CIIU / giro declarado (solo RUC) |
| fuente | TEXT | seed / apis.net.pe / manual |
| updated_at | TIMESTAMPTZ | Ultima actualizacion |

Registros actuales: 6 (4 RUC + 2 DNI)

Flujo de `validate_identity`:
1. Busca el documento en esta tabla
2. Si no existe y `APIS_NET_PE_TOKEN` esta configurado, consulta SUNAT/RENIEC
   y persiste el resultado con `fuente = 'apis.net.pe'`
3. Si no existe y no hay token, retorna `status: not_found` con instruccion
   de agregar el documento manualmente

Agregar un documento manualmente:
```sql
INSERT INTO documentos (numero, tipo, nombre, estado, condicion, direccion, actividad, fuente)
VALUES ('20123456789', 'RUC', 'EMPRESA EJEMPLO S.A.C.', 'ACTIVO', 'HABIDO',
        'AV. EJEMPLO 123, LIMA', 'Comercio', 'manual');
```

### credit_scores

Perfiles crediticios de pagadores.

| Columna | Tipo | Descripcion |
|---|---|---|
| numero | TEXT PK | DNI o RUC del pagador |
| score | INTEGER | 300 a 850 |
| banda_riesgo | TEXT | VERDE / AMARILLO / ROJO |
| morosidad_activa | BOOLEAN | |
| lista_negra_sbs | BOOLEAN | |
| sunat_no_habido | BOOLEAN | |
| deuda_pen | NUMERIC | Deuda estimada en soles |
| dias_mora | INTEGER | Promedio de dias de mora |
| fuente | TEXT | seed / manual / buro-externo |
| updated_at | TIMESTAMPTZ | |

Registros actuales: 6

Si un pagador no tiene perfil en esta tabla, `get_credit_profile` calcula
un score determinista via SHA-256 del numero de documento (rango 300-850).
Esto es solo para desarrollo; en produccion se debe integrar Equifax, Sentinel
o SBS y persistir el resultado con `fuente = 'buro-externo'`.

Agregar o actualizar un score manualmente:
```sql
INSERT INTO credit_scores (numero, score, banda_riesgo, morosidad_activa, lista_negra_sbs, sunat_no_habido, deuda_pen, dias_mora, fuente)
VALUES ('20987654321', 750, 'VERDE', FALSE, FALSE, FALSE, 0, 0, 'manual')
ON CONFLICT (numero) DO UPDATE SET
    score = EXCLUDED.score,
    banda_riesgo = EXCLUDED.banda_riesgo,
    updated_at = NOW();
```

### intenciones

Registro de operaciones iniciadas (vender / comprar factura).

| Columna | Tipo | Descripcion |
|---|---|---|
| intent_id | TEXT PK | Generado por el agente (INT-XXXXXXXX) |
| actor_role | TEXT | cedente o factor |
| actor_document | TEXT | RUC o DNI del actor |
| payload | TEXT | JSON con detalles de la operacion |
| status | TEXT | pending_match (unico valor actual) |
| created_at | TIMESTAMPTZ | |

Cada llamada exitosa a `register_intent` escribe una fila aqui.

---

## Flujo de datos por herramienta

```
validate_identity(document)
  └─ SELECT FROM documentos WHERE numero = ?
     ├─ Encontrado → retorna datos, escribe tool_context.state["identity:{doc}"]
     └─ No encontrado → consulta apis.net.pe (si token) → INSERT INTO documentos

get_credit_profile(document)
  └─ Lee tool_context.state["identity:{doc}"]  ← requiere validate_identity previo
     └─ SELECT FROM credit_scores WHERE numero = ?
        ├─ Encontrado → retorna perfil
        └─ No encontrado → calcula score determinista (solo dev)
        └─ Escribe tool_context.state["credit:{doc}"]

match_invoice_to_factors(amount, days, pagador, sector)
  └─ Lee tool_context.state["credit:{pagador}"]  ← requiere get_credit_profile previo
     └─ SELECT FROM factores WHERE activo = TRUE
        └─ Filtra por banda_riesgo, ticket, plazo, sector
        └─ Retorna lista ordenada por score de compatibilidad

query_platform_users(role, apetito, sector)
  └─ role="factor"   → SELECT FROM factores WHERE activo = TRUE [+ filtros]
     role="cedente"  → SELECT FROM cedentes WHERE activo = TRUE [+ filtros]

register_intent(role, document, payload_json)
  └─ INSERT INTO intenciones (intent_id, actor_role, actor_document, payload, ...)
```

---

## Agregar datos de produccion

Para un nuevo factor real:
```sql
INSERT INTO factores (id, nombre, apetito_riesgo, ticket_min_pen, ticket_max_pen,
                      plazo_max_dias, tasa_mensual_min, tasa_mensual_max, sectores)
VALUES ('FAC-005', 'Nuevo Fondo Capital S.A.', 'balanceado',
        10000, 300000, 90, 1.7, 2.8, ARRAY['comercio', 'servicios']);
```

Para deshabilitar un factor sin borrarlo:
```sql
UPDATE factores SET activo = FALSE WHERE id = 'FAC-003';
```

Para actualizar un score cuando llega respuesta de un buro real:
```sql
INSERT INTO credit_scores (numero, score, banda_riesgo, morosidad_activa,
                           lista_negra_sbs, sunat_no_habido, deuda_pen, dias_mora, fuente)
VALUES ('20111222333', 800, 'VERDE', FALSE, FALSE, FALSE, 0, 0, 'equifax')
ON CONFLICT (numero) DO UPDATE SET
    score = EXCLUDED.score, banda_riesgo = EXCLUDED.banda_riesgo,
    fuente = EXCLUDED.fuente, updated_at = NOW();
```

---

## Re-ejecutar el schema (sin perder datos)

```bash
uv run python -c "
from factor_bridge_agent.db import get_conn
with open('factor_bridge_agent/schema.sql') as f: sql = f.read()
with get_conn() as conn:
    with conn.cursor() as cur: cur.execute(sql)
print('Done')
"
```

El script es idempotente: `CREATE TABLE IF NOT EXISTS` no falla si la tabla
ya existe y `ON CONFLICT DO NOTHING` no duplica filas seed.
