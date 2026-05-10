"""
API REST que expone FactorBridge como servicio HTTP.
Disenada para correr en Google Cloud Run.
"""
from __future__ import annotations

import os
import re

from fastapi import FastAPI, HTTPException
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai.types import Content, Part
from pydantic import BaseModel

from factor_bridge_agent.agent import root_agent

AGENT_NAME = "factor_bridge"
AGENT_VERSION = "0.1.0"

app = FastAPI(
    title="FactorBridge Agent",
    description="Agente intermediario bilateral de factoring para Peru — powered by Google ADK",
    version=AGENT_VERSION,
)

session_service = InMemorySessionService()
runner = Runner(
    agent=root_agent,
    app_name=AGENT_NAME,
    session_service=session_service,
)

# Patron para detectar razonamiento interno de modelos tipo ReAct
_COT_LINE = re.compile(
    r"^\s*(Thought|Action|Observation|Reflection|Final Answer)\s*:",
    re.IGNORECASE,
)
_HAS_CJK = re.compile(r"[一-鿿぀-ゟ゠-ヿ]")


def _clean_response(text: str) -> str:
    """Elimina trazas de cadena de pensamiento (CoT/ReAct) del output del modelo.

    Algunos modelos menores mezclan su razonamiento interno en la respuesta.
    Extrae solo el bloque 'Final Answer' si existe, o filtra lineas de CoT.
    """
    # Prioridad: extraer bloque "Final Answer: ..." si existe
    fa_match = re.search(
        r"(?:Final Answer|FinalAnswer)\s*:\s*(.+)",
        text,
        re.IGNORECASE | re.DOTALL,
    )
    if fa_match:
        return fa_match.group(1).strip()

    # Fallback: eliminar lineas que son traza de CoT o tienen caracteres CJK
    clean_lines = []
    for line in text.splitlines():
        if _COT_LINE.match(line):
            continue
        if _HAS_CJK.search(line):
            continue
        clean_lines.append(line)

    return "\n".join(clean_lines).strip()


class QueryRequest(BaseModel):
    message: str
    session_id: str = "default-session"
    user_id: str = "demo-user"


class QueryResponse(BaseModel):
    response: str
    agent: str
    version: str


@app.get("/health")
async def health_check():
    """Endpoint de salud — usado por Cloud Run para readiness checks."""
    return {"status": "healthy", "agent": AGENT_NAME, "version": AGENT_VERSION}


@app.post("/query", response_model=QueryResponse)
async def query_agent(request: QueryRequest):
    """Envia un mensaje al agente FactorBridge y retorna su respuesta."""
    try:
        await session_service.create_session(
            app_name=AGENT_NAME,
            user_id=request.user_id,
            session_id=request.session_id,
        )
    except Exception:
        pass

    user_message = Content(role="user", parts=[Part(text=request.message)])

    raw_response = ""
    async for event in runner.run_async(
        user_id=request.user_id,
        session_id=request.session_id,
        new_message=user_message,
    ):
        if event.is_final_response() and event.content:
            for part in event.content.parts or []:
                if part.text:
                    raw_response += part.text

    if not raw_response:
        raise HTTPException(status_code=500, detail="El agente no genero respuesta")

    final_response = _clean_response(raw_response)
    if not final_response:
        final_response = raw_response

    return QueryResponse(response=final_response, agent=AGENT_NAME, version=AGENT_VERSION)


@app.get("/")
async def root():
    return {
        "message": "FactorBridge Agent esta corriendo",
        "docs": "/docs",
        "health": "/health",
        "query": "POST /query",
    }


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8080"))
    uvicorn.run("api.main:app", host="0.0.0.0", port=port, reload=False)