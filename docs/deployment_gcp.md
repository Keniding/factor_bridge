# Despliegue en GCP Cloud Run

Fecha inicial: 2026-05-09
Ultima actualizacion: 2026-05-10
Proyecto GCP: adk-devops-agent
Servicio: factor-bridge-agent
URL: https://factor-bridge-agent-197950168142.us-central1.run.app

---

## Infraestructura reutilizada

El proyecto GCP ya tenia toda la infraestructura creada por Terraform para
el agente `adk-devops-agent`. Para este segundo servicio no se necesito
Terraform adicional; solo Cloud Build y gcloud para secretos y permisos.

APIs habilitadas (pre-existentes via TF + cloudbuild.googleapis.com manual):
- run.googleapis.com
- artifactregistry.googleapis.com
- secretmanager.googleapis.com
- cloudbuild.googleapis.com

Artifact Registry: `us-central1-docker.pkg.dev/adk-devops-agent/docker/`

---

## Secrets en Secret Manager

Creados el 2026-05-09:

| Nombre | Descripcion |
|---|---|
| `OPENROUTER_API_KEY` | API key de OpenRouter (provider alternativo) |
| `HUGGINGFACE_API_KEY` | Token de Hugging Face (provider activo) |
| `POSTGRES_URL` | Cadena de conexion Supabase |

Actualizar un secret existente:
```bash
echo -n "nuevo_valor" | gcloud secrets versions add NOMBRE --data-file=- --project=adk-devops-agent
```

---

## IAM — permisos configurados

Cloud Build SA (`197950168142@cloudbuild.gserviceaccount.com`):
- `roles/run.admin` — desplegar servicios Cloud Run
- `roles/run.invoker` — setear politica de acceso publico
- `roles/secretmanager.secretAccessor` — leer secrets durante el build
- `roles/iam.serviceAccountUser` — impersonar Compute SA al deployar
- `roles/artifactregistry.writer` — pushear imagenes Docker

Compute SA (`197950168142-compute@developer.gserviceaccount.com`):
- `roles/secretmanager.secretAccessor` — leer secrets en runtime (Cloud Run)

Cloud Run service (`allUsers`):
- `roles/run.invoker` — acceso publico sin autenticacion

El permiso `allUsers` se aplico manualmente una vez tras el primer deploy
porque Cloud Build SA no tenia `roles/run.invoker` en ese momento. Con el
rol ya asignado, los deploys siguientes lo setean automaticamente.

---

## Pipeline Cloud Build (infra/cloudbuild.yaml)

Pasos del pipeline:
1. `build` — `docker build` con cache desde `:latest`
2. `push-sha` — push tagueado con `$SHORT_SHA`
3. `push-latest` — push del tag `:latest` (en paralelo con `push-sha`)
4. `deploy` — `gcloud run deploy` con secrets inyectados y env vars
5. `smoke-test` — curl a `/health`; falla si no retorna HTTP 200

Variables bash en el smoke-test usan `$$` para escapar la sustitucion de
Cloud Build (e.g. `$$SERVICE_URL` en lugar de `$SERVICE_URL`).

Configuracion de Cloud Run:
- Memory: 512Mi
- CPU: 1
- min-instances: 0 (escala a cero — costo idle = $0)
- max-instances: 3
- `MODEL_PROVIDER=huggingface`

---

## Historial de builds

| Build ID | Fecha | SHA | Resultado | Nota |
|---|---|---|---|---|
| b028c818 | 2026-05-09 | 022cbd8 | FAILURE | Smoke test 403 — permiso allUsers pendiente |
| 50c5c134 | 2026-05-09 | 022cbd8 | SUCCESS | Primera version funcional (HF Llama 8B) |
| b936eefc | 2026-05-10 | 99494af | SUCCESS | HF Qwen 7B + limpiador de respuesta + DB sin mocks |

---

## Problemas encontrados en el primer deploy

### $PROJECT_ID no se expande en substituciones de usuario

En `cloudbuild.yaml`, las substituciones definidas por el usuario
(`_VARIABLE`) no expanden otras substituciones built-in dentro de su valor.
Usar el project ID hardcodeado en `_REPO`:

```yaml
# Incorrecto
_IMAGE: gcr.io/$PROJECT_ID/...

# Correcto
_REPO: us-central1-docker.pkg.dev/adk-devops-agent/docker/factor-bridge-agent
```

### $COMMIT_SHA vacio en submit manual

`$COMMIT_SHA` solo se establece en builds disparados por trigger de git.
En `gcloud builds submit` manual es necesario pasar `SHORT_SHA` explicitamente:

```bash
gcloud builds submit --config=infra/cloudbuild.yaml \
  --substitutions=SHORT_SHA=$(git rev-parse --short HEAD) .
```

### Variables bash con $ en el smoke-test

Cloud Build interpreta `$VAR` en scripts bash como substituciones propias.
Para variables bash locales usar `$$VAR`:

```yaml
# Incorrecto
SERVICE_URL=$(gcloud run ...)

# Correcto
SERVICE_URL=$$(gcloud run ...)
```

### Smoke test HTTP 403 en primer deploy

Cloud Build SA no tenia `roles/run.invoker` para setear el acceso publico
de Cloud Run. Se aplico manualmente y se agrego el rol para futuros deploys:

```bash
gcloud run services add-iam-policy-binding factor-bridge-agent \
  --region=us-central1 --member=allUsers --role=roles/run.invoker \
  --project=adk-devops-agent

gcloud projects add-iam-policy-binding adk-devops-agent \
  --member="serviceAccount:197950168142@cloudbuild.gserviceaccount.com" \
  --role="roles/run.invoker" --condition=None
```

---

## Redeploy (flujo normal)

```bash
cd factor_bridge/
gcloud builds submit --config=infra/cloudbuild.yaml \
  --project=adk-devops-agent \
  --substitutions=SHORT_SHA=$(git rev-parse --short HEAD) .
```

Duracion tipica: 5-6 minutos. El smoke test pasa automaticamente.

Cambiar solo la variable de entorno sin rebuild (30 segundos):
```bash
gcloud run services update factor-bridge-agent \
  --region=us-central1 \
  --update-env-vars=MODEL_PROVIDER=openrouter \
  --project=adk-devops-agent
```

---

## Verificacion

```bash
# Health
curl https://factor-bridge-agent-197950168142.us-central1.run.app/health
# {"status":"healthy","agent":"factor_bridge","version":"0.1.0"}

# Swagger UI
# https://factor-bridge-agent-197950168142.us-central1.run.app/docs

# Consulta al agente
curl -X POST https://factor-bridge-agent-197950168142.us-central1.run.app/query \
  -H "Content-Type: application/json" \
  -d '{"message": "Valida el RUC 20512345678", "session_id": "test-001"}'
```

---

## Costo estimado

Con `min-instances=0` el servicio escala a cero sin trafico: costo idle = $0.

Free tier de Cloud Run: 2M requests/mes y 360K GB-segundos/mes.
Cloud Build: 120 min/dia gratis. Cada build tarda ~5-6 minutos.
Artifact Registry: primer GB gratis.

Para trafico de pruebas/desarrollo esporadico el costo mensual es $0.