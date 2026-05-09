"""
Matchmaker Sub-Agent — Especialista en emparejar cedentes con factores.

Dado el perfil de una factura (monto, plazo, pagador) o el perfil de un
factor (apetito, ticket), encuentra contrapartes compatibles.
"""
from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm

from ..prompts import MATCHMAKER_INSTRUCTION
from ..tools.matching_tools import match_invoice_to_factors
from ..tools.platform_tools import query_platform_users
from ..tools.credit_tools import quick_risk_band


matchmaker_agent = LlmAgent(
    name="matchmaker",
    model=LiteLlm(model="openrouter/meta-llama/llama-3.3-70b-instruct:free", num_retries=6),
    description=(
        "Especialista en emparejar cedentes (vendedores de facturas) con "
        "factores (compradores) compatibles, respetando apetito de riesgo, "
        "ticket, plazo y sector. Úsalo cuando la consulta principal sea de "
        "búsqueda/matching de contrapartes."
    ),
    instruction=MATCHMAKER_INSTRUCTION,
    tools=[
        match_invoice_to_factors,
        query_platform_users,
        quick_risk_band,
    ],
)
