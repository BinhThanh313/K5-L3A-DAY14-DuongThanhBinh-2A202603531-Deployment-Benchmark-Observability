"""
Kết nối Redis dùng chung cho rate limiter và cost guard.
"""
import redis

from app.config import settings

# Tạo client lazy, không ping lúc import để app vẫn khởi động được khi Redis chưa sẵn sàng
r = redis.from_url(
    settings.redis_url,
    decode_responses=True,
    socket_connect_timeout=2,
    socket_timeout=2,
)


def redis_healthy() -> bool:
    """Ping Redis; lỗi kết nối -> False."""
    try:
        return bool(r.ping())
    except Exception:
        return False
