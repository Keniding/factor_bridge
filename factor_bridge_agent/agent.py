"""
FactorBridge — Root Agent (Coordinator).

Agente intermediario bilateral de factoring para Perú.
Construido sobre Google ADK 1.32+ con metodología ReAct.

Para levantarlo:
    adk web                        # UI de desarrollo en localhost:8000
    adk run factor_bridge_agent    # CLI interactiva
    adk api_server factor_bridge_agent  # FastAPI REST
"""
from google.adk.agents import LlmAgent

from .model_config import get_model
from .prompts import ROOT_AGENT_INSTRUCTION
from .sub_agents.credit_assessor import credit_assessor_agent
from .sub_agents.matchmaker import matchmaker_agent

# Tools que el coordinador puede invocar directamente (queries simples)
from .tools.identity_tools import validate_identity
from .tools.credit_tools import get_credit_profile, quick_risk_band
from .tools.matching_tools import match_invoice_to_factors
from .tools.platform_tools import query_platform_users, register_intent


# ---------------------------------------------------------------------
# ROOT AGENT — Coordinador (modelo seleccionado por MODEL_PROVIDER)
# ---------------------------------------------------------------------
root_agent = LlmAgent(
    name="factor_bridge",
    model=get_model(),
    description=(
        "FactorBridge — agente intermediario bilateral de factoring. "
        "Conecta cedentes (vendedores de facturas) con factores (compradores) "
        "evaluando la salud financiera del pagador, fuente principal de riesgo. "
        "Opera en Perú con datos de SUNAT, RENIEC y burós crediticios."
    ),
    instruction=ROOT_AGENT_INSTRUCTION,

    # Sub-agentes a los que puede transferir control
    sub_agents=[
        credit_assessor_agent,
        matchmaker_agent,
    ],

    # Tools que el coordinador puede ejecutar sin delegar
    tools=[
        validate_identity,
        get_credit_profile,
        quick_risk_band,
        match_invoice_to_factors,
        query_platform_users,
        register_intent,
    ],
)
