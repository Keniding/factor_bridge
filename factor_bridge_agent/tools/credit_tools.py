"""
Herramientas de evaluación crediticia (scoring tipo SBS / Infocorp / Sentinel).

NOTA: Las APIs reales de SBS e Infocorp son de pago y requieren convenios.
Este módulo provee un perfil simulado realista para desarrollo, con
ganchos claros para enchufar el proveedor real más adelante.
"""
from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any

from google.adk.tools import ToolContext


def _now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


def _deterministic_score(document: str) -> int:
    """Genera un score determinista entre 300 y 850 a partir del documento.
    Usa SHA-256 para que el mismo documento siempre devuelva el mismo score
    durante el desarrollo."""
    h = int(hashlib.sha256(document.encode()).hexdigest(), 16)
    return 300 + (h % 551)  # rango 300..850


def _classify_band(score: int, sunat_no_habido: bool, blacklist: bool) -> str:
    if blacklist or sunat_no_habido or score < 550:
        return "ROJO"
    if score < 700:
        return "AMARILLO"
    return "VERDE"


def get_credit_profile(document: str, tool_context: ToolContext) -> dict[str, Any]:
    """Obtiene el perfil crediticio consolidado de un DNI o RUC peruano.

    Consulta (mock para desarrollo) burós tipo SBS, Infocorp y Sentinel,
    y devuelve un score 300-850, indicadores de morosidad activa, lista
    negra, y banda de riesgo (VERDE/AMARILLO/ROJO).

    Úsala SOLO después de `validate_identity`.

    Args:
        document: DNI (8 dígitos) o RUC (11 dígitos) ya validado.

    Returns:
        dict con score, banda de riesgo, morosidad, fuentes y timestamp.
    """
    document = document.strip()
    identity = tool_context.state.get(f"identity:{document}")

    if not identity:
        return {
            "status": "error",
            "error": "Documento no validado previamente. "
                     "Llama primero a validate_identity.",
            "documento": document,
            "timestamp": _now_iso(),
        }

    sunat_condicion = (identity.get("condicion") or "").upper()
    sunat_no_habido = sunat_condicion == "NO HABIDO"

    score = _deterministic_score(document)

    # Heurística mock: documentos terminados en 9 → blacklist
    blacklist = document.endswith("9")
    morosidad_activa = score < 600 or blacklist

    band = _classify_band(score, sunat_no_habido, blacklist)

    profile = {
        "status": "ok",
        "documento": document,
        "score": score,
        "score_provider": "InfocorpMock v1",
        "morosidad_activa": morosidad_activa,
        "lista_negra_sbs": blacklist,
        "sunat_no_habido": sunat_no_habido,
        "banda_riesgo": band,
        "deuda_estimada_pen": round((850 - score) * 12.5, 2) if morosidad_activa else 0.0,
        "dias_mora_promedio": (850 - score) // 10 if morosidad_activa else 0,
        "fuentes_consultadas": ["SUNAT", "InfocorpMock", "SBS-blacklist-mock"],
        "timestamp": _now_iso(),
        "disclaimer": (
            "Datos de scoring son simulados con fines de desarrollo. "
            "En producción reemplazar con integración Equifax/Sentinel/SBS."
        ),
    }

    # Guardamos perfil en sesión para que el matchmaker lo lea sin re-consultar
    tool_context.state[f"credit:{document}"] = profile
    return profile


def quick_risk_band(document: str, tool_context: ToolContext) -> dict[str, Any]:
    """Atajo: devuelve solo la banda de riesgo (VERDE/AMARILLO/ROJO) si ya
    se evaluó al pagador en esta sesión, o ejecuta la evaluación completa.

    Args:
        document: DNI o RUC del pagador.

    Returns:
        dict con la banda y el score.
    """
    cached = tool_context.state.get(f"credit:{document}")
    if cached:
        return {
            "status": "cached",
            "documento": document,
            "banda_riesgo": cached["banda_riesgo"],
            "score": cached["score"],
            "timestamp": cached["timestamp"],
        }
    return {
        "status": "not_evaluated",
        "documento": document,
        "mensaje": "Aún no se evaluó al pagador. Llama a get_credit_profile.",
    }
