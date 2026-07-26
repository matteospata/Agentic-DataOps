from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, Field, field_validator


class Settings(BaseModel):
    environment: str = Field(default="local", alias="AGENTIC_ENV")
    data_dir: Path = Field(default=Path("./data"), alias="AGENTIC_DATA_DIR")
    knowledge_base_dir: Path = Field(default=Path("./data/knowledge_base"), alias="AGENTIC_KB_DIR")
    database_path: Path = Field(default=Path("./data/agentic_dataops.db"), alias="AGENTIC_DB_PATH")
    log_level: str = Field(default="INFO", alias="AGENTIC_LOG_LEVEL")
    agent_provider: str = Field(default="heuristic", alias="AGENTIC_AGENT_PROVIDER")
    llm_model: str = Field(default="gpt-4o-mini", alias="AGENTIC_LLM_MODEL")
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    max_tool_calls: int = Field(default=8, alias="AGENTIC_MAX_TOOL_CALLS", ge=1, le=30)
    max_result_rows: int = Field(default=100, alias="AGENTIC_MAX_RESULT_ROWS", ge=1, le=1_000)
    sql_timeout_ms: int = Field(default=1_000, alias="AGENTIC_SQL_TIMEOUT_MS", ge=100, le=30_000)

    @field_validator("agent_provider", mode="before")
    @classmethod
    def normalize_provider(cls, value: str) -> str:
        return str(value).strip().lower()

    def ensure_directories(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.knowledge_base_dir.mkdir(parents=True, exist_ok=True)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    load_dotenv()
    values = {
        field.alias: os.getenv(field.alias)
        for field in Settings.model_fields.values()
        if os.getenv(field.alias)
    }
    settings = Settings.model_validate(values)
    settings.ensure_directories()
    return settings

