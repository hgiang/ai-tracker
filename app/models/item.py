import enum

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class ContentType(str, enum.Enum):
    NEWS = "news"
    DISCUSSION = "discussion"
    PAPER = "paper"
    REPO = "repo"
    POST = "post"
    ARTICLE = "article"
    PODCAST = "podcast"
    VIDEO = "video"


class Item(Base, TimestampMixin):
    __tablename__ = "items"
    __table_args__ = (
        Index("ix_items_source_item", "source_id", "source_item_id", unique=True),
        Index("ix_items_canonical_url", "canonical_url"),
        Index("ix_items_normalized_title", "normalized_title"),
        Index("ix_items_published_at", "published_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"), nullable=False)
    source_item_id: Mapped[str] = mapped_column(String(500), nullable=False)
    url: Mapped[str] = mapped_column(String(1000), nullable=False)
    canonical_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    normalized_title: Mapped[str] = mapped_column(String(500), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_type: Mapped[ContentType] = mapped_column(
        Enum(ContentType), default=ContentType.NEWS, nullable=False
    )
    author: Mapped[str | None] = mapped_column(String(200), nullable=True)
    published_at: Mapped[str | None] = mapped_column(DateTime(timezone=True), nullable=True)
    fetched_at: Mapped[str] = mapped_column(DateTime(timezone=True), nullable=False)
    relevance_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    points: Mapped[int | None] = mapped_column(Integer, nullable=True)
    comment_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration: Mapped[str | None] = mapped_column(String(20), nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    source: Mapped["Source"] = relationship(back_populates="items")  # noqa: F821
