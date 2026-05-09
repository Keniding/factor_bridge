"""
Herramientas de validación de identidad: RUC (SUNAT) y DNI (RENIEC).

Usa apis.net.pe / decolecta.com si hay token. Caso contrario retorna mocks
para que el agente pueda probarse sin credenciales externas.
"""
from __future__ import annotations

import os
from datetime import datetime
from typing import Any

import httpx
from google.adk.tools import ToolContext


# --------------------------------------------------------------------- helpers
def _now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


def _is_valid_dni(doc: str) -> bool:
    return doc.isdigit() and len(doc) == 8


def _is_valid_ruc(doc: str) -> bool:
    return doc.isdigit() and len(doc) == 11 and doc[:2] in ("10", "15", "16", "17", "20")


# --------------------------------------------------------------------- mocks
_MOCK_RUC_DB: dict[str, dict[str, Any]] = {
    "20512345678": {
        "razon_social": "DISTRIBUIDORA SAN MARTIN S.A.C.",
        "estado": "ACTIVO",
        "condicion": "HABIDO",
        "direccion": "AV. JAVIER PRADO ESTE 1234, SAN ISIDRO, LIMA",
        "actividad": "Comercio al por mayor",
    },
    "20601030013": {
        "razon_social": "REXTIE S.A.C.",
        "estado": "ACTIVO",
        "condicion": "HABIDO",
        "direccion": "AV. LARCO 345, MIRAFLORES, LIMA",
        "actividad": "Servicios financieros",
    },
    "20999999999": {
        "razon_social": "EMPRESA MOROSA S.A.",
        "estado": "ACTIVO",
        "condicion": "NO HABIDO",
        "direccion": "DESCONOCIDA",
        "actividad": "No declarada",
    },
}

_MOCK_DNI_DB: dict[str, dict[str, Any]] = {
    "12345678": {
        "nombres": "JUAN ALBERTO",
        "apellido_paterno": "PEREZ",
        "apellido_materno": "GARCIA",
    },
    "87654321": {
        "nombres": "MARIA DEL CARMEN",
        "apellido_paterno": "RODRIGUEZ",
        "apellido_materno": "LOPEZ",
    },
}


# --------------------------------------------------------------------- tools
def validate_identity(document: str, tool_context: ToolContext) -> dict[str, Any]:
    """Valida un documento peruano (DNI de 8 dígitos o RUC de 11 dígitos)
    contra fuentes oficiales (RENIEC para DNI, SUNAT para RUC).

    Úsala como PRIMER paso antes de cualquier evaluación crediticia.

    Args:
        document: número de documento. DNI = 8 dígitos. RUC = 11 dígitos.

    Returns:
        dict con status, tipo de documento (DNI/RUC), datos identitarios,
        estado tributario (solo RUC) y timestamp de la consulta.
    """
    document = document.strip()

    if _is_valid_dni(document):
        return _validate_dni(document, tool_context)
    if _is_valid_ruc(document):
        return _validate_ruc(document, tool_context)

    return {
        "status": "error",
        "error": "Documento inválido. DNI debe tener 8 dígitos numéricos; "
                 "RUC debe tener 11 dígitos comenzando en 10/15/16/17/20.",
        "documento": document,
        "timestamp": _now_iso(),
    }


def _validate_ruc(ruc: str, tool_context: ToolContext) -> dict[str, Any]:
    token = os.getenv("APIS_NET_PE_TOKEN")
    source = "MOCK"
    data: dict[str, Any] | None = None

    if token:
        try:
            r = httpx.get(
                "https://api.apis.net.pe/v2/sunat/ruc",
                params={"numero": ruc},
                headers={"Authorization": f"Bearer {token}"},
                timeout=10.0,
            )
            if r.status_code == 200:
                data = r.json()
                source = "apis.net.pe (SUNAT)"
        except httpx.HTTPError:
            data = None

    if data is None:
        mock = _MOCK_RUC_DB.get(ruc)
        if mock is None:
            return {
                "status": "not_found",
                "documento": ruc,
                "tipo": "RUC",
                "mensaje": f"RUC {ruc} no encontrado en padrón consultado.",
                "fuente": source,
                "timestamp": _now_iso(),
            }
        data = {
            "numeroDocumento": ruc,
            "razonSocial": mock["razon_social"],
            "estado": mock["estado"],
            "condicion": mock["condicion"],
            "direccion": mock["direccion"],
            "actividad": mock["actividad"],
        }

    # Persistimos en estado de sesión para uso por otros tools/sub-agents
    tool_context.state[f"identity:{ruc}"] = data

    return {
        "status": "ok",
        "tipo": "RUC",
        "documento": ruc,
        "razon_social": data.get("razonSocial") or data.get("razon_social"),
        "estado_sunat": data.get("estado"),
        "condicion_sunat": data.get("condicion"),
        "direccion": data.get("direccion"),
        "actividad": data.get("actividad", "No disponible"),
        "fuente": source,
        "timestamp": _now_iso(),
    }


def _validate_dni(dni: str, tool_context: ToolContext) -> dict[str, Any]:
    token = os.getenv("APIS_NET_PE_TOKEN")
    source = "MOCK"
    data: dict[str, Any] | None = None

    if token:
        try:
            r = httpx.get(
                "https://api.apis.net.pe/v2/reniec/dni",
                params={"numero": dni},
                headers={"Authorization": f"Bearer {token}"},
                timeout=10.0,
            )
            if r.status_code == 200:
                data = r.json()
                source = "apis.net.pe (RENIEC)"
        except httpx.HTTPError:
            data = None

    if data is None:
        mock = _MOCK_DNI_DB.get(dni)
        if mock is None:
            return {
                "status": "not_found",
                "documento": dni,
                "tipo": "DNI",
                "mensaje": f"DNI {dni} no encontrado.",
                "fuente": source,
                "timestamp": _now_iso(),
            }
        data = {
            "numeroDocumento": dni,
            **mock,
        }

    nombre_completo = " ".join(filter(None, [
        data.get("nombres"),
        data.get("apellidoPaterno") or data.get("apellido_paterno"),
        data.get("apellidoMaterno") or data.get("apellido_materno"),
    ]))

    tool_context.state[f"identity:{dni}"] = data

    return {
        "status": "ok",
        "tipo": "DNI",
        "documento": dni,
        "nombre_completo": nombre_completo,
        "fuente": source,
        "timestamp": _now_iso(),
    }
