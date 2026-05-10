"""
Herramientas de evaluacion crediticia (scoring tipo SBS / Infocorp / Sentinel).

Fuente primaria: tabla `credit_scores` en Supabase.
Para documentos sin perfil precargado se calcula un score determinista
(desarrollo) hasta que se integre un buro real.
"""
from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any

from google.adk.tools import ToolContext

from ..db import get_conn


def _now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


def _db_lookup_score(numero: str) -> dict[str, Any] | None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT score, banda_riesgo, morosidad_activa, lista_negra_sbs, "
                "sunat_no_habido, deuda_pen, dias_mora, fuente "
                "FROM credit_scores WHERE numero = %s",
                (numero,),
            )
            row = cur.fetchone()
    if row is None:
        return None
    return {
        "score": row[0], "banda_riesgo": row[1], "morosidad_activa": row[2],
        "lista_negra_sbs": row[3], "sunat_no_habido": row[4],
        "deuda_pen": float(row[5]), "dias_mora": row[6], "fuente": row[7],
    }


def _computed_score(document: str, sunat_no_habido: bool) -> dict[str, Any]:
    """Score determinista para documentos sin perfil en DB (solo desarrollo)."""
    h = int(hashlib.sha256(document.encode()).hexdigest(), 16)
    score = 300 + (h % 551)
    blacklist = document.endswith("9")
    morosidad = score < 600 or blacklist

    if blacklist or sunat_no_habido or score < 550:
        banda = "ROJO"
    elif score < 700:
        banda = "AMARILLO"
    else:
        banda = "VERDE"

    return {
        "score": score, "banda_riesgo": banda,
        "morosidad_activa": morosidad, "lista_negra_sbs": blacklist,
        "sunat_no_habido": sunat_no_habido,
        "deuda_pen": round((850 - score) * 12.5, 2) if morosidad else 0.0,
        "dias_mora": (850 - score) // 10 if morosidad else 0,
        "fuente": "algoritmo-determinista",
    }


def get_credit_profile(document: str, tool_context: ToolContext) -> dict[str, Any]:
    """Obtiene el perfil crediticio consolidado de un DNI o RUC peruano.

    Consulta la tabla credit_scores en Supabase. Si el documento no tiene
    perfil precargado calcula un score determinista (solo para desarrollo).

    Usala SOLO despues de validate_identity.

    Args:
        document: DNI (8 digitos) o RUC (11 digitos) ya validado.

    Returns:
        dict con score, banda de riesgo, morosidad, fuente y timestamp.
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

    try:
        cs = _db_lookup_score(document)
    except Exception as exc:
        return {
            "status": "error",
            "error": f"Error consultando credit_scores en Supabase: {exc}",
            "documento": document,
            "timestamp": _now_iso(),
        }

    if cs is None:
        cs = _computed_score(document, sunat_no_habido)

    profile = {
        "status": "ok",
        "fuente": cs["fuente"],
        "documento": document,
        "score": cs["score"],
        "morosidad_activa": cs["morosidad_activa"],
        "lista_negra_sbs": cs["lista_negra_sbs"],
        "sunat_no_habido": cs["sunat_no_habido"],
        "banda_riesgo": cs["banda_riesgo"],
        "deuda_estimada_pen": cs["deuda_pen"],
        "dias_mora_promedio": cs["dias_mora"],
        "timestamp": _now_iso(),
    }

    tool_context.state[f"credit:{document}"] = profile
    return profile


def quick_risk_band(document: str, tool_context: ToolContext) -> dict[str, Any]:
    """Atajo: devuelve solo la banda de riesgo si ya se evaluo al pagador
    en esta sesion, o ejecuta la evaluacion completa.

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
        "mensaje": "Aun no se evaluo al pagador. Llama a get_credit_profile.",
    }