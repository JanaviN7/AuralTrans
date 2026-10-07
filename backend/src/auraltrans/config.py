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
    llm_timeout_s: float = 120.0
    # Insights are generated in chunks of this many characters of transcript.
    llm_chunk_chars: int = 24000
    # Ask puts the whole transcript in the prompt (no retrieval yet), so it has a hard size limit.
    llm_context_chars: int = 60000
    # Product pipeline: which Whisper model the worker loads, and where it runs.
    asr_model: str = "small"
    asr_device: str = "cpu"
    asr_compute_type: str = "int8"
    max_upload_mb: int = 500
    worker_poll_s: float = 1.0
    worker_heartbeat_s: float = 20.0
    job_stale_after_s: float = 120.0
    # Eval audio and caches live outside the repo (and outside OneDrive).
    eval_data_dir: Path = Path.home() / "auraltrans-data"


    @property
    def llm_configured(self) -> bool:
        return bool(self.llm_base_url and self.llm_model)


settings = Settings()
