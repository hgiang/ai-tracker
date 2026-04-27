from datetime import datetime

from pydantic import BaseModel

from app.models.item import ContentType


class ItemOut(BaseModel):
    id: int
    source_id: int
    source_item_id: str
    url: str
    canonical_url: str
    title: str
    summary: str | None
    content_type: ContentType
    author: str | None
    published_at: datetime | None
    fetched_at: datetime
    relevance_score: float
    points: int | None
    comment_count: int | None
    duration: str | None

    model_config = {"from_attributes": True}


class ItemList(BaseModel):
    items: list[ItemOut]
    total: int
    page: int
    limit: int


class NormalizedItem(BaseModel):
    """Schema used by adapters to return normalized data."""

    source_item_id: str
    url: str
    title: str
    summary: str | None = None
    content_type: ContentType = ContentType.NEWS
    author: str | None = None
    published_at: datetime | None = None
    points: int | None = None
    comment_count: int | None = None
    duration: str | None = None
    metadata_json: str | None = None
