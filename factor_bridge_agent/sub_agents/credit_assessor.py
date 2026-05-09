"""
Credit Assessor Sub-Agent — Especialista en evaluación crediticia.

Trabaja con DNI/RUC peruanos, valida identidad y entrega un perfil
consolidado con banda de riesgo (VERDE/AMARILLO/ROJO).
"""
from google.adk.agents import LlmAgent

from ..prompts import CREDIT_ASSESSOR_INSTRUCTION
from ..tools.identity_tools import validate_identity
from ..tools.credit_tools import get_credit_profile, quick_risk_band


credit_assessor_agent = LlmAgent(
    name="credit_assessor",
    model="gemini-2.5-flash",
    description=(
        "Especialista en evaluación crediticia de pagadores peruanos. "
        "Dado un DNI o RUC, valida identidad (RENIEC/SUNAT) y devuelve un "
        "perfil consolidado con score y banda de riesgo VERDE/AMARILLO/ROJO. "
        "Úsalo cuando la consulta principal sea de scoring o due diligence "
        "de un pagador."
    ),
    instruction=CREDIT_ASSESSOR_INSTRUCTION,
    tools=[
        validate_identity,
        get_credit_profile,
        quick_risk_band,
    ],
)
