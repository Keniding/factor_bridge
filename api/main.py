"""
API REST que expone FactorBridge como servicio HTTP.
Disenada para correr en Google Cloud Run.
"""
from __future__ import annotations

import os

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

    final_response = ""
    async for event in runner.run_async(
        user_id=request.user_id,
        session_id=request.session_id,
        new_message=user_message,
    ):
        if event.is_final_response() and event.content:
            for part in event.content.parts or []:
                if part.text:
                    final_response += part.text

    if not final_response:
        raise HTTPException(status_code=500, detail="El agente no genero respuesta")

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
