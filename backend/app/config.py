from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_env: Literal["development", "staging", "production"] = "development"

    # Database
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/interview_copilot"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # LLM
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    primary_llm_provider: Literal["anthropic", "openai"] = "anthropic"
    primary_model: str = "claude-sonnet-4-6"          # guidance generation
    fast_model: str = "claude-haiku-4-5-20251001"     # question detection + followup analysis
    fallback_model: str = "gpt-4o"

    # Vector store
    vector_store_type: Literal["chroma", "pinecone"] = "chroma"
    chroma_persist_dir: str = "./chroma_db"
    pinecone_api_key: str = ""
    pinecone_env: str = ""
    pinecone_index: str = "interview-copilot"

    # Speech
    whisper_model: str = "whisper-1"
    transcription_backend: Literal["api", "local"] = "api"

    # Storage
    upload_dir: str = "./uploads"
    max_upload_size_mb: int = 50

    # CORS — companion app opens from localhost on any port
    cors_origins: list[str] = [
        "http://localhost:3000",
        "http://localhost:3001",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "null",   # file:// origin when companion is opened locally
    ]

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors(cls, v: str | list[str]) -> list[str]:
        if isinstance(v, str):
            return json.loads(v)
        return v

    @property
    def upload_path(self) -> Path:
        path = Path(self.upload_dir)
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


settings = Settings()
