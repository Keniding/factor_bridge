# FactorBridge Agent

Agente intermediario bilateral para operaciones de **factoring** (compra-venta de facturas) construido sobre **Google Agent Development Kit (ADK) v1.33+** con metodologia **ReAct**.

Conecta:
- **Cedentes** (vendedores de facturas que necesitan liquidez)
- **Factores** (compradores/inversionistas que asumen el riesgo)
- Evalua la salud financiera del **Pagador** (deudor real, fuente de riesgo) usando fuentes peruanas (SUNAT, RENIEC, perfil crediticio).

---

## Stack

| Componente | Version |
|---|---|
| Python | 3.10+ |
| google-adk | 1.33.0 (con extensions para LiteLLM) |
| Enrutador de modelos | OpenRouter (openrouter.ai) |
| Modelo orquestador | `anthropic/claude-sonnet-4.6` |
| Modelo sub-agentes | `anthropic/claude-sonnet-4.6` |

---

## Instalacion

```bash
# 1. Clonar / copiar este directorio
cd factor_bridge

# 2. Crear venv e instalar dependencias
python -m venv .venv
source .venv/bin/activate   # macOS/Linux
# .venv\Scripts\activate    # Windows

uv sync

# 3. Configurar variables de entorno
cp factor_bridge_agent/.env.example factor_bridge_agent/.env
# Edita .env y coloca tu OPENROUTER_API_KEY
```

Obtén tu API key en https://openrouter.ai/keys

---

## Levantar el agente

### Opcion 1 — Web UI (recomendado para desarrollo)

```bash
adk web
```
Abre `http://localhost:8000` y selecciona `factor_bridge_agent`.
Veras trazas de herramientas, estado de sesion y el razonamiento del modelo.

### Opcion 2 — CLI

```bash
adk run factor_bridge_agent
```

### Opcion 3 — Servidor API (FastAPI)

```bash
adk api_server factor_bridge_agent --port 8080
```

---

## Estructura del proyecto

```
factor_bridge/
├── README.md
├── pyproject.toml
├── docs/
│   └── openrouter_integration.md   # Prueba de conectividad y metricas
└── factor_bridge_agent/
    ├── __init__.py            # expone root_agent (requerido por ADK)
    ├── agent.py               # Coordinator agent (root)
    ├── prompts.py             # System prompts ReAct
    ├── .env.example           # Plantilla de credenciales
    ├── tools/
    │   ├── __init__.py
    │   ├── identity_tools.py  # Validacion SUNAT/RENIEC
    │   ├── credit_tools.py    # Salud financiera (SBS/Infocorp mock)
    │   ├── matching_tools.py  # Matching cedente-factor
    │   └── platform_tools.py  # Usuarios registrados en la plataforma
    └── sub_agents/
        ├── __init__.py
        ├── credit_assessor.py # Especialista en evaluacion crediticia
        └── matchmaker.py      # Especialista en matching de oportunidades
```

---

## Casos de uso de ejemplo

```
"Tengo una factura de S/ 50,000 a 60 dias contra el RUC 20512345678. Quiero venderla."
"Soy inversionista con apetito conservador, que oportunidades hay en mi rango?"
"Evalua la salud financiera del DNI 12345678 antes de comprar su factura."
"Como funciona el factoring? Por que importa el pagador y no el cedente?"
```

---

## Fallback automatico

Si la cuenta de OpenRouter no tiene credito (error 402), el agente cambia
automaticamente al modelo gratuito `meta-llama/llama-3.3-70b-instruct:free`
sin reiniciar ni modificar codigo. El fallback esta configurado en
`factor_bridge_agent/__init__.py` via `litellm.fallbacks`.

Para agregar credito: https://openrouter.ai/credits

---

## Cambio de modelo

El proyecto comenzo con Gemini 2.5 Pro/Flash y fue migrado a Claude Sonnet 4.6 via OpenRouter
para mayor flexibilidad de proveedor. Ver `docs/openrouter_integration.md` para la prueba
completa de conectividad y metricas de la migracion.

Si se desea volver a Gemini, reemplazar en cada agente:

```python
# Antes (Gemini)
model="gemini-2.5-pro"

# Ahora (OpenRouter)
from google.adk.models.lite_llm import LiteLlm
model=LiteLlm(model="openrouter/anthropic/claude-sonnet-4.6")
```

---

## Notas Web3 / siguientes pasos

Este agente esta listo para integrarse con un layer on-chain (settlement con stablecoins,
tokenizacion de facturas como NFTs, escrow). Ver `tools/platform_tools.py` donde
`register_intent` puede emitir un evento on-chain en el futuro.