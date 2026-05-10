"""
Herramientas de plataforma: consulta de usuarios registrados y registro
de intenciones (compra/venta).
Fuente de datos: tablas `cedentes`, `factores` e `intenciones` en Supabase.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from google.adk.tools import ToolContext

from ..db import get_conn


def _now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


def _load_cedentes(sector: str | None) -> list[dict[str, Any]]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            if sector:
                cur.execute(
                    "SELECT id, razon_social, ruc, sector, facturas_publicadas "
                    "FROM cedentes WHERE activo = TRUE AND sector = %s ORDER BY id",
                    (sector.lower(),),
                )
            else:
                cur.execute(
                    "SELECT id, razon_social, ruc, sector, facturas_publicadas "
                    "FROM cedentes WHERE activo = TRUE ORDER BY id"
                )
            rows = cur.fetchall()
    return [
        {"id": r[0], "razon_social": r[1], "ruc": r[2], "sector": r[3], "facturas_publicadas": r[4]}
        for r in rows
    ]


def _load_factores(apetito_riesgo: str | None, sector: str | None) -> list[dict[str, Any]]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            params: list[Any] = []
            where = ["activo = TRUE"]
            if apetito_riesgo:
                where.append("apetito_riesgo = %s")
                params.append(apetito_riesgo.lower())
            if sector:
                where.append("(%s = ANY(sectores) OR 'cualquiera' = ANY(sectores))")
                params.append(sector.lower())
            sql = (
                "SELECT id, nombre, apetito_riesgo, ticket_min_pen, ticket_max_pen, "
                "plazo_max_dias, sectores FROM factores WHERE "
                + " AND ".join(where)
                + " ORDER BY id"
            )
            cur.execute(sql, params)
            rows = cur.fetchall()
    return [
        {
            "id": r[0], "nombre": r[1], "apetito_riesgo": r[2],
            "ticket_min_pen": float(r[3]), "ticket_max_pen": float(r[4]),
            "plazo_max_dias": r[5], "sectores": list(r[6]),
        }
        for r in rows
    ]


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
        sector: filtro opcional por sector economico.

    Returns:
        dict con la lista de usuarios coincidentes.
    """
    role = role.lower().strip()

    try:
        if role == "factor":
            results = _load_factores(apetito_riesgo, sector)
            return {"status": "ok", "fuente": "supabase", "role": "factor",
                    "total": len(results), "users": results, "timestamp": _now_iso()}

        if role == "cedente":
            results = _load_cedentes(sector)
            return {"status": "ok", "fuente": "supabase", "role": "cedente",
                    "total": len(results), "users": results, "timestamp": _now_iso()}

    except Exception as exc:
        return {"status": "error", "error": f"DB error: {exc}", "timestamp": _now_iso()}

    return {"status": "error", "error": f"Role invalido: '{role}'. Usa 'cedente' o 'factor'.",
            "timestamp": _now_iso()}


def register_intent(
    actor_role: str,
    actor_document: str,
    payload_json: str,
    tool_context: ToolContext,
) -> dict[str, Any]:
    """Registra una intencion de operacion (vender/comprar factura).

    Args:
        actor_role: "cedente" o "factor".
        actor_document: RUC o DNI del actor que emite la intencion.
        payload_json: JSON-string con detalles (monto, plazo, pagador, etc.)

    Returns:
        dict con el id de la intencion registrada y un timestamp.
    """
    intent_id = f"INT-{uuid.uuid4().hex[:8].upper()}"

    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO intenciones (intent_id, actor_role, actor_document, payload, status, created_at) "
                    "VALUES (%s, %s, %s, %s, 'pending_match', NOW())",
                    (intent_id, actor_role, actor_document, payload_json),
                )
    except Exception as exc:
        return {"status": "error", "error": f"Error registrando intencion: {exc}", "timestamp": _now_iso()}

    record = {
        "intent_id": intent_id,
        "actor_role": actor_role,
        "actor_document": actor_document,
        "payload": payload_json,
        "status": "pending_match",
    }
    tool_context.state[f"intent:{intent_id}"] = record

    return {
        "status": "ok",
        "fuente": "supabase",
        "intent_id": intent_id,
        "message": "Intencion registrada. Sera procesada por el motor de matching.",
        "timestamp": _now_iso(),
    }