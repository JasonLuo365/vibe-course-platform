from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="VIBE_", env_file=".env", extra="ignore")

    data_dir: str = "data"
    database_url: str = "sqlite:///data/app.db"
    session_secret: str = "dev-secret-change-me"
    session_cookie: str = "vibe_session"
    min_client_version: str = "0.1.0"
    supported_manifest_versions: list[str] = ["1"]
    default_max_package_mb: int = 50
    max_file_mb: int = 10
    max_files: int = 5000
    max_uncompressed_mb: int = 250
    max_compression_ratio: float = 100.0
    rate_limit_per_minute: int = 60

    # LLM / worker settings
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = "deepseek-chat"
    worker_enabled: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()
