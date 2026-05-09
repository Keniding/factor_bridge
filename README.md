# FactorBridge Agent

Agente intermediario bilateral para operaciones de **factoring** (compra-venta de facturas) construido sobre **Google Agent Development Kit (ADK) v1.32+** con metodología **ReAct**.

Conecta:
- **Cedentes** (vendedores de facturas que necesitan liquidez)
- **Factores** (compradores/inversionistas que asumen el riesgo)
- Evalúa la salud financiera del **Pagador** (deudor real, fuente de riesgo) usando fuentes peruanas (SUNAT, RENIEC, perfil crediticio).

---

## Stack

| Componente | Versión |
|---|---|
| Python | 3.10+ |
| google-adk | 1.32.0 (estable, May 2026) |
| Modelo orquestador | `gemini-2.5-pro` (razonamiento ReAct) |
| Modelo sub-agentes | `gemini-2.5-flash` (rápido, costo-eficiente) |

---

## Instalación

```bash
# 1. Clonar / copiar este directorio
cd factor_bridge

# 2. Crear venv
python -m venv .venv
source .venv/bin/activate   # macOS/Linux
# .venv\Scripts\activate    # Windows

# 3. Instalar dependencias
uv sync

# 4. Configurar variables de entorno
cp factor_bridge_agent/.env.example factor_bridge_agent/.env
# Edita .env y coloca tu GOOGLE_API_KEY de Google AI Studio
```

Obtén tu API key gratis en https://aistudio.google.com/app/apikey

---

## Levantar el agente

### Opción 1 — Web UI (recomendado para desarrollo)

```bash
adk web
```
Abre `http://localhost:8000` y selecciona `factor_bridge_agent`.
Verás trazas de razonamiento ReAct, llamadas a herramientas y estado de la sesión.

### Opción 2 — CLI

```bash
adk run factor_bridge_agent
```

### Opción 3 — Servidor API (FastAPI)

```bash
adk api_server factor_bridge_agent --port 8080
```

---

## Estructura del proyecto

```
factor_bridge/
├── README.md
├── pyproject.toml
└── factor_bridge_agent/
    ├── __init__.py            # expone root_agent (requerido por ADK)
    ├── agent.py               # Coordinator agent (root)
    ├── prompts.py             # System prompts ReAct
    ├── .env.example           # Plantilla de credenciales
    ├── tools/
    │   ├── __init__.py
    │   ├── identity_tools.py  # Validación SUNAT/RENIEC
    │   ├── credit_tools.py    # Salud financiera (SBS/Infocorp mock)
    │   ├── matching_tools.py  # Matching cedente↔factor
    │   └── platform_tools.py  # Usuarios registrados en la plataforma
    └── sub_agents/
        ├── __init__.py
        ├── credit_assessor.py # Especialista en evaluación crediticia
        └── matchmaker.py      # Especialista en matching de oportunidades
```

---

## Casos de uso de ejemplo

```
"Tengo una factura de S/ 50,000 a 60 días contra el RUC 20512345678. Quiero venderla."
"Soy inversionista con apetito conservador, ¿qué oportunidades hay en mi rango?"
"Evalúa la salud financiera del DNI 12345678 antes de comprar su factura."
"¿Cómo funciona el factoring? ¿Por qué importa el pagador y no el cedente?"
```

---

## Notas Web3 / siguientes pasos

Este agente está listo para integrarse con un layer on-chain (settlement con stablecoins, tokenización de facturas como NFTs, escrow). Ver `tools/platform_tools.py` donde `register_intent` puede emitir un evento on-chain en el futuro.
