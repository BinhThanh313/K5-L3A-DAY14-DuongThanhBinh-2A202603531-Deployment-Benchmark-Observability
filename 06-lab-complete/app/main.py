"""
Production AI Agent — Part 6 Final Project
"""
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import json
import logging
import signal
import sys
import time
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field

from app.auth import verify_api_key
from app.config import settings
from app.cost_guard import check_budget, record_cost
from app.rate_limiter import check_rate_limit
from app.redis_client import redis_healthy
from utils.mock_llm import ask as llm_ask


class JsonFormatter(logging.Formatter):
    """Format mọi dòng log thành một JSON object hợp lệ."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "lvl": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        extra = getattr(record, "extra_data", None)
        if isinstance(extra, dict):
            payload.update(extra)
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


logger = logging.getLogger("app")
logger.setLevel(logging.INFO)
logger.propagate = False
if not logger.handlers:
    _handler = logging.StreamHandler(sys.stdout)
    _handler.setFormatter(JsonFormatter())
    logger.addHandler(_handler)


_previous_sigterm = signal.getsignal(signal.SIGTERM)


def _on_sigterm(signum, frame):
    logger.info("sigterm_received", extra={"extra_data": {"event": "sigterm"}})
    if callable(_previous_sigterm):
        _previous_sigterm(signum, frame)


signal.signal(signal.SIGTERM, _on_sigterm)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    logger.info(
        "app_startup",
        extra={
            "extra_data": {
                "event": "startup",
                "environment": settings.environment,
                "port": settings.port,
            }
        },
    )
    yield
    logger.info("app_shutdown", extra={"extra_data": {"event": "shutdown"}})


app = FastAPI(title="Production AI Agent", lifespan=lifespan)


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    user_id: Optional[str] = None


@app.get("/health")
def health():
    """Liveness probe — luôn trả 200 khi process còn chạy."""
    return {"status": "ok"}


@app.get("/ready")
def ready():
    """Readiness probe — 200 khi Redis kết nối được, 503 khi mất kết nối."""
    if not redis_healthy():
        raise HTTPException(status_code=503, detail="Redis unavailable")
    return {"status": "ready"}


@app.post("/ask")
def ask(body: AskRequest, api_key: str = Depends(verify_api_key)):
    start = time.perf_counter()
    check_rate_limit(api_key)
    check_budget()

    answer = llm_ask(body.question)

    input_tokens = max(1, len(body.question.split()))
    output_tokens = max(1, len(answer.split()))
    cost_usd = record_cost(input_tokens, output_tokens)
    elapsed_ms = round((time.perf_counter() - start) * 1000, 2)

    logger.info(
        "ask_completed",
        extra={
            "extra_data": {
                "event": "request",
                "path": "/ask",
                "status": 200,
                "ms": elapsed_ms,
                "cost_usd": round(cost_usd, 6),
            }
        },
    )
    return {
        "question": body.question,
        "answer": answer,
        "user_id": body.user_id,
    }
