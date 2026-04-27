import json
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, model_validator

AdapterType = Literal[
    "hackernews", "reddit", "arxiv", "github", "rss", "x", "bluesky", "polymarket", "hf_papers"
]


class SourceOut(BaseModel):
    id: int
    name: str
    slug: str
    adapter_type: str
    url: str
    enabled: bool
    config: dict[str, Any] | None = None
    created_at: datetime

    model_config = {"from_attributes": True}

    @model_validator(mode="before")
    @classmethod
    def parse_config_json(cls, data: Any) -> Any:
        if hasattr(data, "config_json"):
            raw = data.config_json
            if raw:
                try:
                    parsed = json.loads(raw) if isinstance(raw, str) else raw
                except (json.JSONDecodeError, TypeError):
                    parsed = None
                if hasattr(data, "__dict__"):
                    data.__dict__["config"] = parsed
        return data


class SourceCreate(BaseModel):
    name: str
    adapter_type: AdapterType
    url: str
    config: dict[str, Any] | None = None


class SourceConfigPatch(BaseModel):
    config: dict[str, Any]


class SyncResult(BaseModel):
    source: str
    fetched: int
    new: int
    duplicates: int
    converged: int = 0
    error: str | None = None
