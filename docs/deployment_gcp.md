# Despliegue en GCP Cloud Run

Fecha: 2026-05-09
Proyecto GCP: adk-devops-agent
Servicio: factor-bridge-agent
URL: https://factor-bridge-agent-197950168142.us-central1.run.app

## Infraestructura reutilizada

El proyecto GCP ya tenia toda la infraestructura creada por Terraform para el agente
adk-devops-agent (APIs habilitadas, Artifact Registry, Compute SA). Para este segundo
servicio no se necesito Terraform; solo Cloud Build y gcloud para los permisos.

APIs habilitadas (pre-existentes via TF):
- run.googleapis.com
- artifactregistry.googleapis.com
- secretmanager.googleapis.com
- cloudbuild.googleapis.com (habilitada manualmente para este servicio)

Artifact Registry: us-central1-docker.pkg.dev/adk-devops-agent/docker/

## Secrets en Secret Manager

Tres secrets creados (2026-05-09):

| Nombre               | Descripcion                         |
|----------------------|-------------------------------------|
| OPENROUTER_API_KEY   | API key de OpenRouter               |
| HUGGINGFACE_API_KEY  | Token de Hugging Face               |
| POSTGRES_URL         | Cadena de conexion Supabase         |

Crear/actualizar un secret:
```bash
echo -n "valor" | gcloud secrets create NOMBRE_SECRET --data-file=- --project=adk-devops-agent
# Si ya existe, usar versions add:
echo -n "valor" | gcloud secrets versions add NOMBRE_SECRET --data-file=- --project=adk-devops-agent
```

## IAM — permisos configurados

Cloud Build SA (197950168142@cloudbuild.gserviceaccount.com):
- roles/run.admin — desplegar servicios Cloud Run
- roles/run.invoker — setear politica de acceso publico
- roles/secretmanager.secretAccessor — leer secrets en build
- roles/iam.serviceAccountUser — impersonar Compute SA al deployar
- roles/artifactregistry.writer — pushear imagenes Docker

Compute SA (197950168142-compute@developer.gserviceaccount.com):
- roles/secretmanager.secretAccessor — leer secrets en runtime

Cloud Run service (allUsers):
- roles/run.invoker — acceso publico sin autenticacion

## Pipeline Cloud Build (infra/cloudbuild.yaml)

Pasos del pipeline:
1. build — docker build con cache desde :latest
2. push-sha — push de la imagen tagueada con SHORT_SHA
3. push-latest — push del tag :latest (en paralelo con push-sha)
4. deploy — gcloud run deploy con secrets y env vars
5. smoke-test — curl a /health; falla si no retorna 200

Configuracion de Cloud Run:
- Memory: 512Mi
- CPU: 1
- min-instances: 0 (escala a cero — sin costo idle)
- max-instances: 3
- MODEL_PROVIDER: huggingface (Llama 3.1 8B via HF Serverless Inference)

## Primer despliegue

```bash
cd factor_bridge/
gcloud builds submit --config=infra/cloudbuild.yaml \
  --project=adk-devops-agent \
  --substitutions=SHORT_SHA=$(git rev-parse --short HEAD) .
```

Build ID: b028c818-ab52-4877-981d-a1cd23803db8
Revision desplegada: factor-bridge-agent-00001-rzz
Imagen: us-central1-docker.pkg.dev/adk-devops-agent/docker/factor-bridge-agent:022cbd8

Problemas encontrados y solucion:
- Variable $PROJECT_ID no se expande dentro de substituciones de usuario en cloudbuild.yaml.
  Solucion: hardcodear el project ID en _REPO.
- $COMMIT_SHA vacio en submit manual. Solucion: usar $SHORT_SHA pasado via --substitutions.
- Smoke test fallaba con HTTP 403 porque Cloud Build SA no tenia permiso para setear
  allUsers en Cloud Run. Solucion: aplicar el binding manualmente con
  gcloud run services add-iam-policy-binding y agregar roles/run.invoker a la Cloud Build SA
  para futuros deploys.

## Redeploy (flujo normal)

```bash
gcloud builds submit --config=infra/cloudbuild.yaml \
  --project=adk-devops-agent \
  --substitutions=SHORT_SHA=$(git rev-parse --short HEAD) .
```

El smoke test pasa automaticamente desde el segundo deploy (roles ya configurados).

## Verificacion

```bash
# Health
curl https://factor-bridge-agent-197950168142.us-central1.run.app/health
# {"status":"healthy","agent":"factor_bridge","version":"0.1.0"}

# Raiz
curl https://factor-bridge-agent-197950168142.us-central1.run.app/
# {"message":"FactorBridge Agent esta corriendo","docs":"/docs","health":"/health","query":"POST /query"}

# Swagger UI
# https://factor-bridge-agent-197950168142.us-central1.run.app/docs

# Consulta al agente
curl -X POST https://factor-bridge-agent-197950168142.us-central1.run.app/query \
  -H "Content-Type: application/json" \
  -d '{"message": "Valida el RUC 20512345678", "session_id": "test-001"}'
```

## Costo estimado

Con min-instances=0 el servicio escala a cero sin trafico: costo idle = $0.
Free tier de Cloud Run cubre 2M requests/mes y 360K GB-segundos/mes.
Cloud Build: 120 minutos/dia gratis; cada build tarda ~5 minutos.
Artifact Registry: primer GB gratis, luego $0.10/GB/mes.