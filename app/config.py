"""
Configuration management for the Research Assistant.
Loads environment variables and provides settings for all components.
"""

from pydantic_settings import BaseSettings
from pydantic import Field
from typing import List, Optional
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # FastAPI Configuration
    app_name: str = "Multi-Agent Research Assistant"
    app_version: str = "1.0.0"
    debug: bool = Field(default=False, alias="FASTAPI_DEBUG")
    host: str = Field(default="0.0.0.0", alias="FASTAPI_HOST")
    port: int = Field(default=8000, alias="FASTAPI_PORT")
    workers: int = Field(default=4, alias="FASTAPI_WORKERS")
    
    # MongoDB Configuration
    mongodb_url: str = Field(
        default="mongodb://localhost:27017",
        alias="MONGODB_URL"
    )
    mongodb_database: str = Field(
        default="research_assistant_db",
        alias="MONGODB_DATABASE"
    )
    
    # Redis Cache (optional)
    redis_url: Optional[str] = Field(default=None, alias="REDIS_URL")
    cache_ttl: int = Field(default=86400, alias="CACHE_TTL")  # 24 hours
    
    # Sentry Error Tracking
    sentry_dsn: Optional[str] = Field(default=None, alias="SENTRY_DSN")
    
    # LLM Configuration (OpenRouter)
    openrouter_api_key: str = Field(default="", alias="OPENROUTER_API_KEY")
    openrouter_base_url: str = Field(
        default="https://openrouter.ai/api/v1",
        alias="OPENROUTER_BASE_URL"
    )
    
    # Model selections for different agents
    researcher_model: str = Field(default="deepseek/deepseek-chat", alias="RESEARCHER_MODEL")
    analyst_model: str = Field(default="anthropic/claude-3.5-sonnet", alias="ANALYST_MODEL")
    fact_checker_model: str = Field(default="openai/gpt-4o", alias="FACT_CHECKER_MODEL")
    report_generator_model: str = Field(default="deepseek/deepseek-chat", alias="REPORT_GENERATOR_MODEL")
    
    # External APIs
    serpapi_key: Optional[str] = Field(default=None, alias="SERPAPI_KEY")
    google_api_key: Optional[str] = Field(default=None, alias="GOOGLE_API_KEY")
    google_search_engine_id: Optional[str] = Field(default=None, alias="GOOGLE_SEARCH_ENGINE_ID")
    newsapi_key: Optional[str] = Field(default=None, alias="NEWSAPI_KEY")
    
    # API Base URLs
    arxiv_api_base: str = Field(
        default="http://export.arxiv.org/api/query",
        alias="ARXIV_API_BASE"
    )
    pubmed_api_base: str = Field(
        default="https://eutils.ncbi.nlm.nih.gov/entrez/eutils",
        alias="PUBMED_API_BASE"
    )
    wikipedia_api_base: str = Field(
        default="https://en.wikipedia.org/api/rest_v1",
        alias="WIKIPEDIA_API_BASE"
    )
    
    # Security
    secret_key: str = Field(
        default="change-this-in-production-use-strong-key",
        alias="SECRET_KEY"
    )
    algorithm: str = Field(default="HS256", alias="ALGORITHM")
    access_token_expire_minutes: int = Field(
        default=30,
        alias="ACCESS_TOKEN_EXPIRE_MINUTES"
    )
    
    # CORS
    allowed_origins: List[str] = Field(
        default=["*"],  # Allow all origins in development
        alias="ALLOWED_ORIGINS"
    )
    
    # Logging
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    log_file: str = Field(default="logs/app.log", alias="LOG_FILE")
    
    # Research Settings
    max_sources_default: int = Field(default=300, alias="MAX_SOURCES_DEFAULT")
    agent_timeout: int = Field(default=120, alias="AGENT_TIMEOUT")  # 2 minutes
    max_retries: int = Field(default=3, alias="MAX_RETRIES")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


# Export settings instance
settings = get_settings()
