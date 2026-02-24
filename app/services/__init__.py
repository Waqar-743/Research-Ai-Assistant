"""Services package initialization."""

# Avoid eager import of research_service to prevent circular imports
# (search_tools → redis_cache → services → research_service → orchestrator → base_agent)
from app.services.redis_cache import RedisCache, get_redis

__all__ = ["RedisCache", "get_redis"]
