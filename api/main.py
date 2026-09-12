from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes.triage import router as triage_router
from utils.logging_config import setup_logging

setup_logging()

app = FastAPI(
    title="SRE Incident Triage Agent API",
    description="High-performance, deterministic SRE Incident Triage engine using Polars pre-processing, Lyzr ADK/Groq, and Pydantic governance guardrails.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(triage_router)


@app.get("/health", tags=["health"])
async def health_check():
    return {"status": "ok", "service": "sre-triage-agent"}
