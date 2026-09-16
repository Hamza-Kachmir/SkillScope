import hashlib
import logging

from redis.asyncio import Redis
from redis.exceptions import RedisError

from .models import AnalysisRequest, AnalysisResponse

logger = logging.getLogger(__name__)
_redis: Redis | None = None


async def initialize_cache(redis_url: str) -> bool:
    global _redis
    if not redis_url:
        return False
    client = Redis.from_url(
        redis_url,
        decode_responses=True,
        socket_connect_timeout=2,
        socket_timeout=2,
    )
    try:
        await client.ping()
    except RedisError:
        await client.aclose()
        logger.warning("Redis indisponible, le cache des analyses est désactivé")
        return False
    _redis = client
    return True


async def close_cache() -> None:
    global _redis
    if _redis:
        await _redis.aclose()
        _redis = None


def cache_key(request: AnalysisRequest, model: str) -> str:
    source = "|".join(
        [
            request.query.casefold(),
            model,
            "v8-fixed-100",
        ]
    )
    digest = hashlib.sha256(source.encode("utf-8")).hexdigest()
    return f"skillscope:analysis:{digest}"


async def get_cached(key: str) -> AnalysisResponse | None:
    if not _redis:
        return None
    try:
        payload = await _redis.get(key)
    except RedisError:
        logger.warning("Lecture du cache Redis impossible")
        return None
    if not payload:
        return None
    try:
        result = AnalysisResponse.model_validate_json(payload)
    except ValueError:
        await _redis.delete(key)
        return None
    result.cached = True
    return result


async def set_cached(key: str, result: AnalysisResponse, ttl_seconds: int) -> None:
    if not _redis:
        return
    try:
        await _redis.set(key, result.model_dump_json(), ex=ttl_seconds)
    except RedisError:
        logger.warning("Écriture du cache Redis impossible")
