from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    openrouter_api_key: str = ""
    openrouter_model: str = "openrouter/auto"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openfda_base_url: str = "https://api.fda.gov"
    rxnorm_base_url: str = "https://rxnav.nlm.nih.gov/REST"
    log_level: str = "INFO"
    # User accounts (symptom search is gated behind login).
    database_path: str = "medicine_search.db"
    # Signs the session cookie. MUST be overridden in production via SESSION_SECRET.
    session_secret: str = "dev-insecure-change-me"
    # Per-client (IP) request caps per minute. Symptom search calls a paid LLM, so
    # it's stricter than the name lookup.
    name_rate_limit_per_minute: int = 60
    symptom_rate_limit_per_minute: int = 15


settings = Settings()
