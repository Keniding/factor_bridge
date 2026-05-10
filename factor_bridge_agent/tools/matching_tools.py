"""
Herramientas de matching: empareja facturas (cedentes) con factores
compatibles segun apetito de riesgo, ticket y plazo.
Fuente de datos: tabla `factores` en Supabase.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from google.adk.tools import ToolContext

from ..db import get_conn


_APETITO_BANDAS = {
    "conservador": {"VERDE"},
    "balanceado": {"VERDE", "AMARILLO"},
    "agresivo": {"VERDE", "AMARILLO", "ROJO"},
}


def _now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


def _load_factores() -> list[dict[str, Any]]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, nombre, apetito_riesgo,
                       ticket_min_pen, ticket_max_pen, plazo_max_dias,
                       tasa_mensual_min, tasa_mensual_max, sectores
                FROM factores
                WHERE activo = TRUE
                ORDER BY id
                """
            )
            rows = cur.fetchall()
    return [
        {
            "id": r[0],
            "nombre": r[1],
            "apetito_riesgo": r[2],
            "ticket_min_pen": float(r[3]),
            "ticket_max_pen": float(r[4]),
            "plazo_max_dias": r[5],
            "tasa_mensual_min": float(r[6]),
            "tasa_mensual_max": float(r[7]),
            "sectores": list(r[8]),
        }
        for r in rows
    ]


def match_invoice_to_factors(
    invoice_amount_pen: float,
    term_days: int,
    pagador_document: str,
    sector: str | None,
    tool_context: ToolContext,
) -> dict[str, Any]:
    """Encuentra factores compatibles con una factura especifica.

    Empareja la banda de riesgo del PAGADOR (debe haber sido evaluado
    previamente con get_credit_profile) con el apetito de cada factor,
    ademas de verificar ticket y plazo. Lee factores desde Supabase.

    Args:
        invoice_amount_pen: monto de la factura en soles (PEN).
        term_days: plazo en dias hasta el vencimiento.
        pagador_document: DNI/RUC del pagador (ya evaluado en sesion).
        sector: sector economico del cedente. Puede ser None.

    Returns:
        dict con la lista ordenada de factores compatibles y un racional.
    """
    pagador_credit = tool_context.state.get(f"credit:{pagador_document}")

    if not pagador_credit:
        return {
            "status": "error",
            "error": (
                f"Pagador {pagador_document} no evaluado en esta sesion. "
                "Ejecuta primero validate_identity y get_credit_profile."
            ),
            "timestamp": _now_iso(),
        }

    band = pagador_credit["banda_riesgo"]
    sector_norm = (sector or "").lower().strip()

    try:
        factores = _load_factores()
    except Exception as exc:
        return {
            "status": "error",
            "error": f"Error consultando factores en Supabase: {exc}",
            "timestamp": _now_iso(),
        }

    matches: list[dict[str, Any]] = []
    for f in factores:
        if band not in _APETITO_BANDAS[f["apetito_riesgo"]]:
            continue
        if not (f["ticket_min_pen"] <= invoice_amount_pen <= f["ticket_max_pen"]):
            continue
        if term_days > f["plazo_max_dias"]:
            continue
        if sector_norm and "cualquiera" not in f["sectores"] and sector_norm not in f["sectores"]:
            continue

        score = 100
        if band == "AMARILLO" and f["apetito_riesgo"] == "balanceado":
            score -= 10
        if band == "ROJO":
            score -= 30
        score -= max(0, (term_days - 60) // 10)

        tasa_mensual = (f["tasa_mensual_min"] + f["tasa_mensual_max"]) / 2
        if band == "AMARILLO":
            tasa_mensual = f["tasa_mensual_max"]
        elif band == "ROJO":
            tasa_mensual = f["tasa_mensual_max"] * 1.2

        descuento_pct = tasa_mensual * (term_days / 30)
        monto_neto = round(invoice_amount_pen * (1 - descuento_pct / 100), 2)

        matches.append({
            "factor_id": f["id"],
            "nombre": f["nombre"],
            "apetito_riesgo": f["apetito_riesgo"],
            "tasa_mensual_estimada_pct": round(tasa_mensual, 2),
            "descuento_total_pct": round(descuento_pct, 2),
            "monto_neto_estimado_pen": monto_neto,
            "score_compatibilidad": max(0, min(100, score)),
        })

    matches.sort(key=lambda m: (-m["score_compatibilidad"], -m["monto_neto_estimado_pen"]))

    return {
        "status": "ok",
        "fuente": "supabase",
        "pagador": pagador_document,
        "banda_riesgo_pagador": band,
        "monto_factura_pen": invoice_amount_pen,
        "plazo_dias": term_days,
        "sector": sector_norm or "no_especificado",
        "total_matches": len(matches),
        "matches": matches[:5],
        "timestamp": _now_iso(),
        "racional_general": (
            f"Pagador en banda {band}. Se filtraron {len(matches)} factores "
            f"compatibles ordenados por score de compatibilidad."
        ),
    }
