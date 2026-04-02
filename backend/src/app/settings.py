from functools import lru_cache
from pathlib import Path

try:
    from pydantic_settings import BaseSettings, SettingsConfigDict
except ImportError:  # pragma: no cover - placeholder until deps are installed
    BaseSettings = object
    SettingsConfigDict = dict


class Settings(BaseSettings):
    service_name: str = "trading-backend"
    environment: str = "development"
    version: str = "0.1.0"
    log_level: str = "INFO"

    cors_origins: str = "*"
    socketio_path: str = "/realtime"
    database_url: str = "postgresql+asyncpg://localhost/trading_backend"
    redis_url: str = "redis://localhost:6379/0"
    prompt_image_store_path: str = "backend/tmp/prompt_images"
    prompt_image_base_url: str = ""
    prompt_image_uploader: str = "filesystem"
    prompt_image_upload_concurrency: int = 4
    prompt_image_imgbb_api_key: str = ""
    prompt_image_imgbb_api_url: str = "https://api.imgbb.com/1/upload"
    prompt_image_freeimage_api_key: str = ""
    prompt_image_freeimage_api_url: str = "https://freeimage.host/api/1/upload"
    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: str = ""
    llm_model: str = "gpt-4o"
    llm_temperature: float = 0.7
    llm_max_tokens: int = 4096
    codex_cli_path: str = "codex"
    codex_cli_timeout_seconds: int = 180
    codex_temp_image_path: str = "backend/tmp/codex_images"
    codex_temp_image_ttl_minutes: int = 60
    codex_temp_image_sweep_interval_seconds: int = 600
    binance_http_timeout_seconds: float = 10.0
    binance_http_pool_timeout_seconds: float = 30.0
    binance_http_max_keepalive_connections: int = 20
    binance_http_max_connections: int = 100
    binance_max_requests_per_second: int = 5
    binance_max_concurrency: int = 2
    binance_retry_count: int = 2
    binance_retry_base_delay: float = 0.5
    binance_retry_max_delay: float = 4.0
    binance_retry_jitter: float = 0.3
    binance_rate_limit_backoff: float = 15.0
    dynamic_assets_oi_source: str = "nofx"
    local_timezone: str = "Asia/Shanghai"

    _env_path = Path(__file__).resolve().parents[3] / ".env"
    model_config = SettingsConfigDict(
        env_prefix="BACKEND_",
        env_file=str(_env_path),
        extra="ignore",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    # Keep this light for now; environment parsing can be expanded later.
    if BaseSettings is object:
        return Settings()  # type: ignore[call-arg]
    return Settings()
