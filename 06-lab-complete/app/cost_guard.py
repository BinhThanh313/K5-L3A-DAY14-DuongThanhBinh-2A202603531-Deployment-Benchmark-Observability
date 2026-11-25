"""
Cost guard (tiêu chí 8) — theo dõi chi phí LLM trong Redis.
"""
from datetime import date

from fastapi import HTTPException

from app.config import settings
from app.redis_client import r

# Giá USD / 1K tokens (tham khảo gpt-4o-mini)
PRICE_INPUT_PER_1K = 0.00015
PRICE_OUTPUT_PER_1K = 0.0006


def _cost_key() -> str:
    return f"cost:{date.today().isoformat()}"


def check_budget() -> None:
    """Gọi TRƯỚC khi gọi LLM. Hết budget -> raise HTTPException(status_code=402)."""
    key = _cost_key()
    current = float(r.get(key) or 0.0)
    if current >= settings.daily_budget_usd:
        raise HTTPException(status_code=402, detail="Daily budget exceeded")


def record_cost(input_tokens: int, output_tokens: int) -> float:
    """Gọi SAU khi gọi LLM. Cộng chi phí của request vào tổng, trả về chi phí request."""
    cost = (
        (input_tokens / 1000.0) * PRICE_INPUT_PER_1K
        + (output_tokens / 1000.0) * PRICE_OUTPUT_PER_1K
    )
    key = _cost_key()
    r.incrbyfloat(key, cost)
    r.expire(key, 86400)
    return cost
