from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "SkillScope API"
    frontend_origin: str = "http://localhost:5173"
    ft_client_id: str = ""
    ft_client_secret: str = ""
    google_cloud_project: str = ""
    google_cloud_location: str = "global"
    google_credentials: str = ""
    gemini_model: str = "gemini-3.1-flash-lite"
    gemini_batch_size: int = 20
    gemini_concurrency: int = 5
    redis_url: str = ""
    cache_ttl_seconds: int = 2_592_000

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def live_mode(self) -> bool:
        return bool(self.ft_client_id and self.ft_client_secret)

    @property
    def vertex_ai_configured(self) -> bool:
        return bool(self.google_cloud_project)


@lru_cache
def get_settings() -> Settings:
    return Settings()
