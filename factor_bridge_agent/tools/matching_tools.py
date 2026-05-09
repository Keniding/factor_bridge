"""
Herramientas de matching: empareja facturas (cedentes) con factores
compatibles según apetito de riesgo, ticket y plazo.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from google.adk.tools import ToolContext


# --------------------------------------------------------------------- mocks
# Base de factores registrados en la plataforma (en producción: BD/SQL/on-chain)
_MOCK_FACTORES: list[dict[str, Any]] = [
    {
        "id": "FAC-001",
        "nombre": "Capital Andino SAC",
        "apetito_riesgo": "conservador",  # solo VERDE
        "ticket_min_pen": 10_000,
        "ticket_max_pen": 200_000,
        "plazo_max_dias": 90,
        "tasa_mensual_min": 1.5,
        "tasa_mensual_max": 2.2,
        "sectores": ["comercio", "servicios"],
    },
    {
        "id": "FAC-002",
        "nombre": "Liquidez Pacífico Fondo Privado",
        "apetito_riesgo": "balanceado",  # VERDE y AMARILLO
        "ticket_min_pen": 5_000,
        "ticket_max_pen": 500_000,
        "plazo_max_dias": 120,
        "tasa_mensual_min": 1.8,
        "tasa_mensual_max": 3.0,
        "sectores": ["comercio", "industria", "construccion"],
    },
    {
        "id": "FAC-003",
        "nombre": "RiesgoPlus Crypto Factor",
        "apetito_riesgo": "agresivo",  # VERDE, AMARILLO y ROJO
        "ticket_min_pen": 1_000,
        "ticket_max_pen": 100_000,
        "plazo_max_dias": 180,
        "tasa_mensual_min": 2.5,
        "tasa_mensual_max": 5.0,
        "sectores": ["cualquiera"],
    },
    {
        "id": "FAC-004",
        "nombre": "Inversiones del Sur EIRL",
        "apetito_riesgo": "balanceado",
        "ticket_min_pen": 20_000,
        "ticket_max_pen": 1_000_000,
        "plazo_max_dias": 90,
        "tasa_mensual_min": 1.6,
        "tasa_mensual_max": 2.5,
        "sectores": ["industria", "servicios"],
    },
]

_APETITO_BANDAS = {
    "conservador": {"VERDE"},
    "balanceado": {"VERDE", "AMARILLO"},
    "agresivo": {"VERDE", "AMARILLO", "ROJO"},
}


def _now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


def match_invoice_to_factors(
    invoice_amount_pen: float,
    term_days: int,
    pagador_document: str,
    sector: str | None,
    tool_context: ToolContext,
) -> dict[str, Any]:
    """Encuentra factores compatibles con una factura específica.

    Empareja la banda de riesgo del PAGADOR (debe haber sido evaluado
    previamente con get_credit_profile) con el apetito de cada factor,
    además de verificar ticket y plazo.

    Args:
        invoice_amount_pen: monto de la factura en soles (PEN).
        term_days: plazo en días hasta el vencimiento.
        pagador_document: DNI/RUC del pagador (ya evaluado en sesión).
        sector: sector económico del cedente (ej. "comercio", "industria",
                "servicios"). Puede ser None.

    Returns:
        dict con la lista ordenada de factores compatibles y un racional.
    """
    pagador_credit = tool_context.state.get(f"credit:{pagador_document}")

    if not pagador_credit:
        return {
            "status": "error",
            "error": (
                f"Pagador {pagador_document} no evaluado en esta sesión. "
                "Ejecuta primero validate_identity y get_credit_profile."
            ),
            "timestamp": _now_iso(),
        }

    band = pagador_credit["banda_riesgo"]
    sector_norm = (sector or "").lower().strip()

    matches: list[dict[str, Any]] = []
    for f in _MOCK_FACTORES:
        # Filtro 1: apetito vs banda
        if band not in _APETITO_BANDAS[f["apetito_riesgo"]]:
            continue
        # Filtro 2: ticket
        if not (f["ticket_min_pen"] <= invoice_amount_pen <= f["ticket_max_pen"]):
            continue
        # Filtro 3: plazo
        if term_days > f["plazo_max_dias"]:
            continue
        # Filtro 4: sector
        if sector_norm and "cualquiera" not in f["sectores"] and sector_norm not in f["sectores"]:
            continue

        # Score de compatibilidad (0-100)
        score = 100
        if band == "AMARILLO" and f["apetito_riesgo"] == "balanceado":
            score -= 10
        if band == "ROJO":
            score -= 30
        # Premia plazos cortos
        score -= max(0, (term_days - 60) // 10)

        # Cálculo de descuento (tasa mensual promedio)
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
