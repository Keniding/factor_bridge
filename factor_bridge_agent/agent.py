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
from google.adk.planners import BuiltInPlanner
from google.genai import types

from .prompts import ROOT_AGENT_INSTRUCTION
from .sub_agents.credit_assessor import credit_assessor_agent
from .sub_agents.matchmaker import matchmaker_agent

# Tools que el coordinador puede invocar directamente (queries simples)
from .tools.identity_tools import validate_identity
from .tools.credit_tools import get_credit_profile, quick_risk_band
from .tools.matching_tools import match_invoice_to_factors
from .tools.platform_tools import query_platform_users, register_intent


# ---------------------------------------------------------------------
# ROOT AGENT — Coordinador con razonamiento ReAct (thinking habilitado)
# ---------------------------------------------------------------------
root_agent = LlmAgent(
    name="factor_bridge",
    model="gemini-2.5-pro",
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

    # Planner ReAct: habilita el "thinking" nativo de Gemini 2.5 para que
    # el modelo razone explícitamente Thought→Action→Observation→Reflection
    # antes de cada decisión. include_thoughts=True permite ver el
    # razonamiento en la UI de adk web (clave para auditoría fintech).
    planner=BuiltInPlanner(
        thinking_config=types.ThinkingConfig(
            include_thoughts=True,
            thinking_budget=4096,
        ),
    ),
)
