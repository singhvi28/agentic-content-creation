from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    gemini_api_key: str = ""
    cursor_api_key: str = ""
    database_url: str = (
        "postgresql+asyncpg://postgres:postgres@localhost:5432/content_pipeline"
    )
    redis_url: str = "redis://localhost:6379"
    critic_score_threshold: float = 7.0
    gemini_model: str = "gemini-2.0-flash"
    gemini_critic_model: str = "gemini-2.0-flash"
    cursor_model: str = "composer-2.5"
    cursor_critic_model: str = "composer-2.5"
    cursor_cwd: str = "."
    # Secondary bandit update weight from automated critic (0–1 scale mapped to soft update)
    critic_reward_weight: float = 0.3
    max_revision_rounds: int = 2
    # When true, worker uses FakeLLMClient (no external LLM calls)
    use_fake_llm: bool = False
    # llm provider: auto | cursor | gemini | fake
    # auto prefers Cursor when CURSOR_API_KEY is set, else Gemini
    llm_provider: str = "auto"


@lru_cache
def get_settings() -> Settings:
    return Settings()
