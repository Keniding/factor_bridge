# Integracion de modelos LLM externos — Historial y estado

Fecha inicial: 2026-05-09
Ultima actualizacion: 2026-05-10

> El provider activo en produccion es Hugging Face (Qwen 2.5 7B).
> Ver `docs/model_providers.md` para la decision completa y comparativa.

---

## Arquitectura de conexion LLM

Google ADK conecta con cualquier provider externo a traves de `LiteLlm`,
clase incluida en `google-adk[extensions]` (que instala `litellm`).

```
ADK Agent  -->  LiteLlm  -->  litellm.acompletion()  -->  Provider API
```

La seleccion de provider ocurre en `factor_bridge_agent/model_config.py`
en funcion de la variable de entorno `MODEL_PROVIDER`.

---

## Primera prueba — OpenRouter con Claude Sonnet 4.6

Fecha: 2026-05-09
Resultado: exitoso para conversacion, fallido por credito insuficiente en tool calling

### Configuracion

```
MODEL_PROVIDER=openrouter_claude
OPENROUTER_API_KEY=sk-or-v1-...
```

Modelo: `openrouter/anthropic/claude-sonnet-4.6`

### Resultados de prueba de conectividad

| Caso | Tiempo (s) | Tokens |
|---|---|---|
| Definicion de factoring | 4.79 | 172 |
| Evaluacion cedente | 5.25 | 329 |
| Factor conservador | 6.03 | 327 |
| Riesgo sobre pagador | 5.85 | 317 |
| Promedio | 5.48 | 286 |

### Error encontrado

Al ejecutar el agente completo con herramientas, ADK solicita `max_tokens=65536`
por defecto. Con solo 2340 tokens de credito en la cuenta, OpenRouter rechaza
la solicitud con HTTP 402:

```
You requested up to 65536 tokens, but can only afford 2340.
```

Solucion: agregar credito en openrouter.ai/credits o usar un modelo gratuito.

---

## Segunda prueba — OpenRouter con Llama 3.3 70B (gratuito)

Fecha: 2026-05-09
Resultado: tool calling correcto, pero rate limits severos del proveedor Venice

### Configuracion

```
MODEL_PROVIDER=openrouter
```

Modelo: `openrouter/meta-llama/llama-3.3-70b-instruct:free`

### Problema de rate limits

El modelo gratuito es servido por el proveedor Venice en OpenRouter y tiene
rate limits agresivos. Incluso con retry backoff de 8 intentos esperando el
`Retry-After` del servidor (17-30 segundos por intento), todos los reintentos
retornan 429.

```
[FactorBridge] 429 rate limit — reintentando en 17s (intento 1/8)
[FactorBridge] 429 rate limit — reintentando en 30s (intento 2/8)
[FactorBridge] 429 rate limit — reintentando en 30s (intento 3/8)
... (hasta intento 8)
→ Internal Server Error
```

Este comportamiento ocurre cuando se hacen multiples solicitudes en sesion
de pruebas rapidas. En produccion con trafico esporadico (un usuario real
por vez) OpenRouter funciona correctamente.

### Por que litellm.num_retries no funciona

`LiteLLMClient.acompletion` en ADK llama `litellm.acompletion()` directamente
y los reintentos internos de LiteLLM en modo async no respetan el header
`Retry-After`, ejecutando los 6 reintentos en menos de 1 segundo.

El patch en `factor_bridge_agent/__init__.py` sobreescribe `acompletion` con
una version que usa `asyncio.sleep(wait)` con el valor real del header.

---

## Tercera prueba — Hugging Face Llama 3.1 8B

Fecha: 2026-05-09
Resultado: sin rate limits, pero sin tool calling funcional

### Problema

El modelo 8B no usa el protocolo de tool calling de la API. En lugar de
retornar un `tool_calls` estructurado en la respuesta, devuelve el JSON
del tool call como texto en el campo `content`:

```json
{
  "response": "{\"type\": \"function\", \"name\": \"validate_identity\", ...}"
}
```

ADK no reconoce esto como una llamada de herramienta y lo trata como
respuesta final de texto.

---

## Decision final — Hugging Face Qwen 2.5 7B

Fecha: 2026-05-10
Estado: activo en produccion

`Qwen/Qwen2.5-7B-Instruct` via el provider `huggingface/` de LiteLLM:
- Ejecuta herramientas correctamente via el mecanismo interno de ADK
- Sin rate limits practicos (HF Serverless Inference gratuito)
- Mezcla razonamiento interno (CoT) en la respuesta → resuelto con limpiador

El limpiador en `api/main.py` extrae la respuesta limpia eliminando lineas
de cadena de pensamiento (`Thought:`, `Action:`, `Observation:`, caracteres
CJK del razonamiento en chino del modelo).

Ver `docs/model_providers.md` para la tabla comparativa completa.
