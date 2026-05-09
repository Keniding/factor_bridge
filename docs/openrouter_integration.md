# Integracion OpenRouter — Claude Sonnet 4.6

Fecha de prueba: 2026-05-09
Entorno: Google ADK 1.33.0 + LiteLLM via `google-adk[extensions]`

---

## Modelo activo

| Parametro | Valor |
|---|---|
| Proveedor | OpenRouter |
| Modelo | `anthropic/claude-sonnet-4.6` |
| ID interno de OpenRouter | `anthropic/claude-4.6-sonnet-20260217` |
| Configuracion en ADK | `LiteLlm(model="openrouter/anthropic/claude-sonnet-4.6")` |
| Variable de entorno | `OPENROUTER_API_KEY` |

---

## Por que Claude Sonnet 4.6

`claude-3.5-sonnet` no tiene endpoints activos en esta cuenta de OpenRouter.
Los modelos Anthropic disponibles al 2026-05-09 son:

```
anthropic/claude-3-haiku
anthropic/claude-3.5-haiku
anthropic/claude-3.7-sonnet
anthropic/claude-3.7-sonnet:thinking
anthropic/claude-haiku-4.5
anthropic/claude-opus-4
anthropic/claude-opus-4.1
anthropic/claude-opus-4.5
anthropic/claude-opus-4.6
anthropic/claude-opus-4.6-fast
anthropic/claude-opus-4.7
anthropic/claude-sonnet-4
anthropic/claude-sonnet-4.5
anthropic/claude-sonnet-4.6
```

`claude-sonnet-4.6` es el Sonnet mas reciente disponible, equivalente generacional
al que se buscaba originalmente y con mejor desempeno en razonamiento estructurado.

---

## Arquitectura de la integracion

Google ADK conecta con OpenRouter a traves de la clase `LiteLlm` del paquete
`google-adk[extensions]`, que a su vez usa la libreria `litellm` internamente.
El flujo de una llamada es:

```
ADK Agent  -->  LiteLlm  -->  litellm.completion()  -->  OpenRouter API  -->  Anthropic
```

No se requiere ningun SDK de Anthropic por separado.

---

## Resultados de la prueba de conectividad

Ejecutada el 2026-05-09 directamente contra la API de OpenRouter.

### Caso 1 — Definicion de factoring

**Pregunta:** Explica en dos oraciones que es el factoring y por que importa el pagador.

**Respuesta:**

El factoring es una operacion financiera en la que una empresa vende sus facturas
por cobrar a una entidad financiera (factor) a cambio de liquidez inmediata, sin
esperar el vencimiento del plazo de pago.

El pagador es la figura clave porque es quien finalmente cancelara la factura,
por lo que su solidez crediticia y comportamiento de pago determinan la viabilidad
y el costo de la operacion.

**Metricas:** 4.79 s | 61 prompt tokens | 111 completion tokens | 172 total

---

### Caso 2 — Evaluacion de factura cedente

**Pregunta:** Tengo una factura de S/ 50,000 a 60 dias contra RUC 20512345678. Como evaluo si conviene venderla?

**Respuesta (extracto):**

El modelo estructuro correctamente los pasos de due diligence:
- Verificacion de la factura (conformidad, registro SUNAT, ausencia de cargas)
- Evaluacion del deudor por RUC (estado ACTIVO/HABIDO, historial de pagos)
- Calculo del costo efectivo de la operacion

**Metricas:** 5.25 s | 79 prompt tokens | 250 completion tokens | 329 total

---

### Caso 3 — Lista de verificacion para factor conservador

**Pregunta:** Soy un fondo con apetito conservador, ticket minimo S/ 10,000. Que debo revisar antes de comprar una factura?

**Respuesta (extracto):**

El modelo identifico correctamente los cuatro ejes de revision:
- Solidez del deudor (centrales de riesgo SBS, Equifax, Experian)
- Conformidad y validez de la factura en SUNAT
- Concentracion de cartera (limite por deudor)
- Condiciones del contrato de cesion

**Metricas:** 6.03 s | 77 prompt tokens | 250 completion tokens | 327 total

---

### Caso 4 — Explicacion del riesgo sobre el pagador

**Pregunta:** Por que el riesgo real en una operacion de factoring recae sobre el pagador y no sobre el cedente?

**Respuesta (extracto):**

El modelo explico tres razones estructurales correctas:
1. La obligacion de pago pertenece al deudor; el cedente ya cumplio entregando el bien/servicio.
2. Al comprar la factura, el factor se convierte en el nuevo acreedor y absorbe el riesgo de impago.
3. En factoring sin recurso (modalidad estandar en Peru), el cedente no responde si el pagador incumple.

**Metricas:** 5.85 s | 67 prompt tokens | 250 completion tokens | 317 total

---

## Resumen de metricas

| Caso | Tiempo (s) | Tokens totales |
|---|---|---|
| Definicion | 4.79 | 172 |
| Cedente | 5.25 | 329 |
| Factor conservador | 6.03 | 327 |
| Riesgo sobre pagador | 5.85 | 317 |
| **Promedio** | **5.48** | **286** |

Latencia promedio: 5.5 segundos. Dentro del rango esperado para respuestas de
hasta 250 tokens via OpenRouter con modelo Sonnet.

---

## Modelo activo y manejo de rate limits

Modelo configurado: `meta-llama/llama-3.3-70b-instruct:free` (sin costo).

Este modelo es servido por el proveedor Venice en OpenRouter y tiene rate limits
agresivos en cuentas sin saldo. Para manejar esto, `factor_bridge_agent/__init__.py`
parchea `LiteLLMClient.acompletion` con retry real usando `asyncio.sleep`:

```python
# __init__.py
async def _acompletion_with_backoff(self, model, messages, tools, **kwargs):
    kwargs.pop("num_retries", None)  # desactiva reintentos inmediatos de litellm
    for attempt in range(8 + 1):
        try:
            return await _litellm_acompletion(model=model, messages=messages, tools=tools, **kwargs)
        except litellm.RateLimitError as exc:
            # Lee el Retry-After real del header de OpenRouter
            match = re.search(r'"retry_after_seconds":\s*(\d+)', str(exc))
            wait = int(match.group(1)) + 2 if match else 15 * (2 ** attempt)
            await asyncio.sleep(wait)  # espera real, no inmediata

LiteLLMClient.acompletion = _acompletion_with_backoff
```

Razon por la que litellm.num_retries no funciona para este caso:
`LiteLLMClient.acompletion` en Google ADK llama `litellm.acompletion()` directamente,
y los reintentos internos de LiteLLM en modo async no respetan el header Retry-After,
por lo que los 6 reintentos ocurren en menos de 1 segundo y todos fallan.

El patch garantiza que cada reintento espera el tiempo exacto indicado por el servidor
(tipicamente 5-30 segundos por reintento).

Limitacion conocida: si el proveedor Venice esta saturado de forma sostenida, incluso
8 reintentos pueden agotar el limite. En ese caso la solucion es agregar credito a
la cuenta en openrouter.ai/credits para desbloquear Claude Sonnet 4.6.

Para cambiar de vuelta a Claude Sonnet 4.6 una vez con credito, modificar los tres
agentes reemplazando `meta-llama/llama-3.3-70b-instruct:free` por `claude-sonnet-4.6`.

---

## Notas de implementacion

- El `BuiltInPlanner` con `ThinkingConfig` (exclusivo de Gemini 2.5) fue removido
  al migrar. Claude Sonnet 4.6 razona via chain-of-thought nativo sin configuracion adicional.
- Los tres agentes del sistema (root, credit_assessor, matchmaker) usan el mismo
  modelo `claude-sonnet-4.6`. Si se desea diferenciar costo/velocidad, los sub-agentes
  pueden cambiarse a `claude-haiku-4.5` sin modificar el coordinador.
- La variable `OPENROUTER_API_KEY` debe estar en `factor_bridge_agent/.env` y nunca
  en el historial de git (el archivo `.env` ya esta en `.gitignore` por convencion ADK).
