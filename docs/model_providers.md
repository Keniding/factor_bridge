# Estrategia de modelos LLM

Fecha: 2026-05-10
Estado: produccion activa con Hugging Face / Qwen 2.5 7B

---

## Configuracion activa

| Variable | Valor |
|---|---|
| `MODEL_PROVIDER` | `huggingface` |
| Modelo | `Qwen/Qwen2.5-7B-Instruct` |
| Provider LiteLLM | `huggingface/Qwen/Qwen2.5-7B-Instruct` |
| Endpoint | HF Serverless Inference API (gratuito) |
| Token | `HUGGINGFACE_API_KEY` en Secret Manager |

Para cambiar de proveedor basta con actualizar `MODEL_PROVIDER` en Cloud Run
o en `factor_bridge_agent/.env` para desarrollo local. No se requiere ningun
otro cambio en el codigo.

---

## Providers disponibles

| `MODEL_PROVIDER` | Modelo | Tool calling | Rate limit | Costo |
|---|---|---|---|---|
| `huggingface` | Qwen/Qwen2.5-7B-Instruct | Funcional | Sin limite practico | $0 |
| `huggingface_llama` | meta-llama/Llama-3.1-8B-Instruct | No confiable | Sin limite | $0 |
| `openrouter` | llama-3.3-70b-instruct:free | Correcto | 200 req/dia | $0 |
| `openrouter_claude` | anthropic/claude-sonnet-4.6 | Correcto | Alto | Pago |

---

## Investigacion y decision

### Por que no Llama 8B en HF

El modelo `meta-llama/Llama-3.1-8B-Instruct` via la API de HF devuelve el
tool call como texto plano en lugar de ejecutarlo via el protocolo OpenAI:

```json
{
  "response": "{\"type\": \"function\", \"name\": \"validate_identity\", \"parameters\": {\"document\": \"20512345678\"}}"
}
```

El LLM genera la estructura JSON del tool call dentro del campo `content`
del mensaje, pero ADK solo ejecuta herramientas cuando el modelo devuelve
un `tool_calls` estructurado en la respuesta de la API. Un modelo de 8B
no distingue estos dos modos con suficiente consistencia.

### Por que no el endpoint OpenAI-compatible de HF

HF expone un endpoint OpenAI-compatible (`/v1/chat/completions`) pero solo
en cuentas HF Pro ($9/mes) o en Inference Endpoints dedicados. El tier
gratuito de Serverless Inference retorna HTTP 404 para esa ruta.

Se probaron dos URLs sin exito:
- `https://api-inference.huggingface.co/v1/chat/completions`
- `https://api-inference.huggingface.co/models/{model}/v1/chat/completions`

### Por que no OpenRouter free (Llama 70B)

El modelo `meta-llama/llama-3.3-70b-instruct:free` en OpenRouter ejecuta
tool calls correctamente, pero el proveedor Venice que lo sirve esta
saturado de forma sistematica. En pruebas locales, todos los intentos
retornaron HTTP 429 incluyendo los 8 reintentos con backoff:

```
[FactorBridge] 429 rate limit — reintentando en 17s (intento 1/8)
[FactorBridge] 429 rate limit — reintentando en 30s (intento 2/8)
...
[FactorBridge] 429 rate limit — reintentando en 15s (intento 8/8)
→ Internal Server Error
```

En produccion con trafico esporadico (usuario a usuario, no pruebas en
rafaga) OpenRouter funciona. Pero la confiabilidad no es garantizable
sin credito en la cuenta.

### Qwen 2.5 7B via HF nativo — decision final

`Qwen/Qwen2.5-7B-Instruct` con el provider `huggingface/` de LiteLLM:
- Ejecuta herramientas correctamente (las llama via el mecanismo interno de ADK)
- Sin rate limits practicos en el tier gratuito
- Los datos retornan desde Supabase (no mock)

El unico problema es que el modelo mezcla su razonamiento interno (cadena
de pensamiento tipo ReAct) en la respuesta final. Esto se resuelve en
`api/main.py` con un limpiador de respuesta.

---

## Limpiador de respuesta (api/main.py)

```python
def _clean_response(text: str) -> str:
    # Prioridad: extraer bloque "Final Answer: ..." si existe
    fa_match = re.search(r"(?:Final Answer|FinalAnswer)\s*:\s*(.+)", text, re.DOTALL)
    if fa_match:
        return fa_match.group(1).strip()

    # Fallback: eliminar lineas de CoT y caracteres CJK (chino del modelo)
    clean_lines = [
        line for line in text.splitlines()
        if not _COT_LINE.match(line) and not _HAS_CJK.search(line)
    ]
    return "\n".join(clean_lines).strip()
```

Patrones filtrados: `Thought:`, `Action:`, `Observation:`, `Reflection:`,
`Final Answer:` (como prefijo, se extrae el contenido), caracteres Unicode
bloque CJK (chino/japones/coreano que el modelo usa para razonamiento interno).

---

## Retry con backoff (factor_bridge_agent/__init__.py)

Aplica para todos los providers. Parchea `LiteLLMClient.acompletion` de ADK
para que los reintentos por 429 usen `asyncio.sleep` real con el valor del
header `Retry-After` del servidor:

```python
async def _acompletion_with_backoff(self, model, messages, tools, **kwargs):
    kwargs.pop("num_retries", None)
    for attempt in range(_MAX_RETRIES + 1):
        try:
            return await _litellm_acompletion(model=model, messages=messages, tools=tools, **kwargs)
        except litellm.RateLimitError as exc:
            match = re.search(r'"retry_after_seconds":\s*(\d+)', str(exc))
            wait = int(match.group(1)) + 2 if match else _FALLBACK_WAIT * (2 ** attempt)
            await asyncio.sleep(wait)
```

Razon del patch: LiteLLM en modo async no respeta el header `Retry-After`,
sus reintentos internos ocurren en menos de 1 segundo y todos fallan. El
patch garantiza esperas reales entre intentos.

---

## Cambiar de proveedor

### Desarrollo local

Editar `factor_bridge_agent/.env`:
```
MODEL_PROVIDER=openrouter   # o huggingface, openrouter_claude
```

### Produccion (Cloud Run)

Opcion 1 — redeploy via Cloud Build:
```bash
# Editar infra/cloudbuild.yaml: --set-env-vars=MODEL_PROVIDER=openrouter
gcloud builds submit --config=infra/cloudbuild.yaml --project=adk-devops-agent --substitutions=SHORT_SHA=$(git rev-parse --short HEAD) .
```

Opcion 2 — actualizar solo la variable de entorno (sin rebuild de imagen):
```bash
gcloud run services update factor-bridge-agent \
  --region=us-central1 \
  --update-env-vars=MODEL_PROVIDER=openrouter \
  --project=adk-devops-agent
```

La opcion 2 tarda ~30 segundos y no requiere nuevo build de Docker.

---

## Agregar un nuevo provider

1. Agregar entrada a `_HF_MODELS` o agregar rama `if provider == "nuevo"` en
   `factor_bridge_agent/model_config.py`
2. Agregar la API key correspondiente a Secret Manager y al paso `deploy` de
   `infra/cloudbuild.yaml`
3. Probar local con `MODEL_PROVIDER=nuevo` en `.env`
