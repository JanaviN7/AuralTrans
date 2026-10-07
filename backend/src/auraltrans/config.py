from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://auraltrans:auraltrans@localhost:5432/auraltrans"
    storage_backend: str = "local"
    storage_path: str = "./data"
    hf_token: str = ""
    llm_provider: str = "openai_compat"
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = ""
    # Eval audio and caches live outside the repo (and outside OneDrive).
    eval_data_dir: Path = Path.home() / "auraltrans-data"


settings = Settings()
