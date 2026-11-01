import json
import logging
from typing import Any
from redis import Redis
from redis.exceptions import RedisError
from app.core.config import settings

logger = logging.getLogger(__name__)


class CacheClient:
    def __init__(
        self,
        redis_url: str | None = None,
        timeout: float = 1.0,
    ) -> None:
        self._url = redis_url or settings.redis_url
        self._client = Redis.from_url(
            self._url,
            decode_responses=True,
            socket_connect_timeout=timeout,
            socket_timeout=timeout,
        )

    def ping(self) -> bool:
        try:
            return bool(self._client.ping())
        except RedisError as exc:
            logger.warning("Redis ping failed, operating in degraded mode: %s", exc)
            return False

    def get(self, key: str) -> Any | None:
        try:
            raw = self._client.get(key)
            if raw is None:
                return None
            return json.loads(raw)
        except (RedisError, ValueError, TypeError) as exc:
            logger.warning("Redis get failed for key '%s': %s", key, exc)
            return None

    def set(self, key: str, value: Any, ttl_seconds: int = 60) -> bool:
        try:
            payload = json.dumps(value)
            return bool(self._client.set(key, payload, ex=ttl_seconds))
        except RedisError as exc:
            logger.warning("Redis set failed for key '%s': %s", key, exc)
            return False

    def invalidate_prefix(self, prefix: str) -> bool:
        try:
            keys = list(self._client.scan_iter(match=f"{prefix}*"))
            if keys:
                self._client.delete(*keys)
            return True
        except RedisError as exc:
            logger.warning(
                "Redis invalidate_prefix failed for prefix '%s': %s", prefix, exc
            )
            return False


cache_client = CacheClient()


def get_cache_client() -> CacheClient:
    return cache_client
