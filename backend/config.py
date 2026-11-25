"""Application settings loaded from .env and environment variables."""

from functools import lru_cache
from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration for the backend server and external adapters."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Backend Server
    app_host: str = "127.0.0.1"
    app_port: int = 8000
    cors_origins: str = "http://localhost:3000"
    database_path: str = "./data/exam_grader.db"
    storage_dir: str = "./data/uploads"

    # Preprocessing & Local PII Anonymization (Rule 4)
    pdf_render_dpi: int = Field(default=200, ge=72, le=600)
    skip_cover_page: bool = True
    auto_split_spreads: bool = True
    header_mask_pct: float = Field(default=0.0, ge=0.0, le=0.4)

    # Modal.com Serverless GPU OCR
    modal_ocr_vlm_url: str = ""
    modal_ocr_baseline_url: str = ""
    modal_api_key: str = ""
    mock_modal: bool = True
    modal_gpu_name: str = "L40S"
    modal_gpu_rate_per_hr: float = Field(default=1.95, ge=0.0)
    modal_credit_limit_usd: float = Field(default=30.0, gt=0.0)
    modal_baseline_spent_usd: float = Field(default=1.65, ge=0.0)

    # Variable AI Grader Provider (Phase 4)
    grader_provider: str = "gemini"
    grader_model: str = "gemini-3-flash-preview"
    grader_base_url: str = ""
    gemini_api_key: str = ""
    gemini_min_delay_sec: float = Field(default=1.5, ge=0.0)
    mock_gemini: bool = True

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @property
    def db_path(self) -> Path:
        return Path(self.database_path)

    @property
    def upload_dir(self) -> Path:
        return Path(self.storage_dir)

    def ensure_dirs(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.upload_dir.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached settings instance."""
    settings = Settings()
    settings.ensure_dirs()
    return settings
