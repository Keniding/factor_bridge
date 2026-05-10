"""
Herramientas de validacion de identidad: RUC (SUNAT) y DNI (RENIEC).

Fuente primaria: tabla `documentos` en Supabase.
Si el documento no esta en la tabla se consulta apis.net.pe (requiere token)
y el resultado se persiste en Supabase para futuras consultas.
"""
from __future__ import annotations

import os
from datetime import datetime
from typing import Any

import httpx
from google.adk.tools import ToolContext

from ..db import get_conn


def _now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


def _is_valid_dni(doc: str) -> bool:
    return doc.isdigit() and len(doc) == 8


def _is_valid_ruc(doc: str) -> bool:
    return doc.isdigit() and len(doc) == 11 and doc[:2] in ("10", "15", "16", "17", "20")


def _db_lookup(numero: str) -> dict[str, Any] | None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT numero, tipo, nombre, estado, condicion, direccion, actividad, fuente "
                "FROM documentos WHERE numero = %s",
                (numero,),
            )
            row = cur.fetchone()
    if row is None:
        return None
    return {
        "numero": row[0], "tipo": row[1], "nombre": row[2],
        "estado": row[3], "condicion": row[4], "direccion": row[5],
        "actividad": row[6], "fuente": row[7],
    }


def _db_upsert(
    numero: str, tipo: str, nombre: str, fuente: str,
    estado: str | None = None, condicion: str | None = None,
    direccion: str | None = None, actividad: str | None = None,
) -> None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO documentos (numero, tipo, nombre, estado, condicion, direccion, actividad, fuente, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
                ON CONFLICT (numero) DO UPDATE SET
                    nombre = EXCLUDED.nombre,
                    estado = EXCLUDED.estado,
                    condicion = EXCLUDED.condicion,
                    direccion = EXCLUDED.direccion,
                    actividad = EXCLUDED.actividad,
                    fuente = EXCLUDED.fuente,
                    updated_at = NOW()
                """,
                (numero, tipo, nombre, estado, condicion, direccion, actividad, fuente),
            )


def validate_identity(document: str, tool_context: ToolContext) -> dict[str, Any]:
    """Valida un documento peruano (DNI de 8 digitos o RUC de 11 digitos)
    contra la base de datos Supabase (fuente primaria) o RENIEC/SUNAT via
    apis.net.pe si el documento aun no esta registrado.

    Usala como PRIMER paso antes de cualquier evaluacion crediticia.

    Args:
        document: numero de documento. DNI = 8 digitos. RUC = 11 digitos.

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
        "error": "Documento invalido. DNI debe tener 8 digitos numericos; "
                 "RUC debe tener 11 digitos comenzando en 10/15/16/17/20.",
        "documento": document,
        "timestamp": _now_iso(),
    }


def _validate_ruc(ruc: str, tool_context: ToolContext) -> dict[str, Any]:
    row = _db_lookup(ruc)

    if row is None:
        token = os.getenv("APIS_NET_PE_TOKEN")
        if not token:
            return {
                "status": "not_found",
                "tipo": "RUC",
                "documento": ruc,
                "mensaje": f"RUC {ruc} no encontrado en la base de datos. "
                           "Agregalo en Supabase tabla `documentos` o configura APIS_NET_PE_TOKEN.",
                "timestamp": _now_iso(),
            }
        try:
            r = httpx.get(
                "https://api.apis.net.pe/v2/sunat/ruc",
                params={"numero": ruc},
                headers={"Authorization": f"Bearer {token}"},
                timeout=10.0,
            )
            r.raise_for_status()
            data = r.json()
        except httpx.HTTPError as exc:
            return {
                "status": "error",
                "tipo": "RUC",
                "documento": ruc,
                "error": f"Error consultando SUNAT: {exc}",
                "timestamp": _now_iso(),
            }

        nombre = data.get("razonSocial", "")
        _db_upsert(
            numero=ruc, tipo="RUC", nombre=nombre,
            estado=data.get("estado"), condicion=data.get("condicion"),
            direccion=data.get("direccion"), actividad=data.get("ciiu"),
            fuente="apis.net.pe",
        )
        row = _db_lookup(ruc)

    identity_data = {
        "numeroDocumento": ruc,
        "razonSocial": row["nombre"],
        "estado": row["estado"],
        "condicion": row["condicion"],
        "direccion": row["direccion"],
        "actividad": row["actividad"],
    }
    tool_context.state[f"identity:{ruc}"] = identity_data

    return {
        "status": "ok",
        "tipo": "RUC",
        "documento": ruc,
        "razon_social": row["nombre"],
        "estado_sunat": row["estado"],
        "condicion_sunat": row["condicion"],
        "direccion": row["direccion"],
        "actividad": row["actividad"] or "No disponible",
        "fuente": row["fuente"],
        "timestamp": _now_iso(),
    }


def _validate_dni(dni: str, tool_context: ToolContext) -> dict[str, Any]:
    row = _db_lookup(dni)

    if row is None:
        token = os.getenv("APIS_NET_PE_TOKEN")
        if not token:
            return {
                "status": "not_found",
                "tipo": "DNI",
                "documento": dni,
                "mensaje": f"DNI {dni} no encontrado en la base de datos. "
                           "Agregalo en Supabase tabla `documentos` o configura APIS_NET_PE_TOKEN.",
                "timestamp": _now_iso(),
            }
        try:
            r = httpx.get(
                "https://api.apis.net.pe/v2/reniec/dni",
                params={"numero": dni},
                headers={"Authorization": f"Bearer {token}"},
                timeout=10.0,
            )
            r.raise_for_status()
            data = r.json()
        except httpx.HTTPError as exc:
            return {
                "status": "error",
                "tipo": "DNI",
                "documento": dni,
                "error": f"Error consultando RENIEC: {exc}",
                "timestamp": _now_iso(),
            }

        nombre = " ".join(filter(None, [
            data.get("nombres"),
            data.get("apellidoPaterno"),
            data.get("apellidoMaterno"),
        ]))
        _db_upsert(numero=dni, tipo="DNI", nombre=nombre, fuente="apis.net.pe")
        row = _db_lookup(dni)

    identity_data = {"numeroDocumento": dni, "nombreCompleto": row["nombre"]}
    tool_context.state[f"identity:{dni}"] = identity_data

    return {
        "status": "ok",
        "tipo": "DNI",
        "documento": dni,
        "nombre_completo": row["nombre"],
        "fuente": row["fuente"],
        "timestamp": _now_iso(),
    }