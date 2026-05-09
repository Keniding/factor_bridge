"""
Herramientas de plataforma: consulta de usuarios registrados y registro
de intenciones (compra/venta).

En producción, estas funciones se conectarían a la BD de la plataforma o
a un contrato inteligente Web3. Aquí están en memoria para desarrollo.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from google.adk.tools import ToolContext


# --------------------------------------------------------------------- mocks
_MOCK_CEDENTES: list[dict[str, Any]] = [
    {
        "id": "CED-001",
        "razon_social": "Textiles La Joya SAC",
        "ruc": "20512345678",
        "sector": "industria",
        "facturas_publicadas": 3,
    },
    {
        "id": "CED-002",
        "razon_social": "Servicios Logísticos Andinos EIRL",
        "ruc": "20445566778",
        "sector": "servicios",
        "facturas_publicadas": 1,
    },
]

_INTENTS_LOG: list[dict[str, Any]] = []


def _now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


def query_platform_users(
    role: str,
    apetito_riesgo: str | None,
    sector: str | None,
    tool_context: ToolContext,
) -> dict[str, Any]:
    """Lista usuarios registrados en la plataforma FactorBridge.

    Args:
        role: "cedente" o "factor".
        apetito_riesgo: solo aplica a factores. Valores: "conservador",
            "balanceado", "agresivo". None = todos.
        sector: filtro opcional por sector económico.

    Returns:
        dict con la lista de usuarios coincidentes.
    """
    role = role.lower().strip()

    if role == "factor":
        from .matching_tools import _MOCK_FACTORES  # import local para evitar ciclos

        results = list(_MOCK_FACTORES)
        if apetito_riesgo:
            results = [f for f in results if f["apetito_riesgo"] == apetito_riesgo.lower()]
        if sector:
            sec = sector.lower()
            results = [f for f in results
                       if "cualquiera" in f["sectores"] or sec in f["sectores"]]
        return {
            "status": "ok",
            "role": "factor",
            "total": len(results),
            "users": results,
            "timestamp": _now_iso(),
        }

    if role == "cedente":
        results = list(_MOCK_CEDENTES)
        if sector:
            sec = sector.lower()
            results = [c for c in results if c["sector"] == sec]
        return {
            "status": "ok",
            "role": "cedente",
            "total": len(results),
            "users": results,
            "timestamp": _now_iso(),
        }

    return {
        "status": "error",
        "error": f"Role inválido: '{role}'. Usa 'cedente' o 'factor'.",
        "timestamp": _now_iso(),
    }


def register_intent(
    actor_role: str,
    actor_document: str,
    payload_json: str,
    tool_context: ToolContext,
) -> dict[str, Any]:
    """Registra una intención de operación (vender/comprar factura) en la
    plataforma. En producción esto puede emitir un evento on-chain.

    Args:
        actor_role: "cedente" o "factor".
        actor_document: RUC o DNI del actor que emite la intención.
        payload_json: JSON-string con detalles (monto, plazo, pagador, etc.)

    Returns:
        dict con el id de la intención registrada y un timestamp.
    """
    intent_id = f"INT-{uuid.uuid4().hex[:8].upper()}"
    record = {
        "intent_id": intent_id,
        "actor_role": actor_role,
        "actor_document": actor_document,
        "payload": payload_json,
        "status": "pending_match",
        "created_at": _now_iso(),
    }
    _INTENTS_LOG.append(record)
    tool_context.state[f"intent:{intent_id}"] = record
    return {
        "status": "ok",
        "intent_id": intent_id,
        "message": "Intención registrada. Será procesada por el motor de matching.",
        "timestamp": _now_iso(),
    }
