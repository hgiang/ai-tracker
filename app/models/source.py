from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class Source(Base, TimestampMixin):
    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    slug: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    adapter_type: Mapped[str] = mapped_column(String(50), nullable=False)
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    config_json: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)

    checkpoints: Mapped[list["SourceCheckpoint"]] = relationship(
        back_populates="source", cascade="all, delete-orphan"
    )
    items: Mapped[list["Item"]] = relationship(  # noqa: F821
        back_populates="source", cascade="all, delete-orphan"
    )


class SourceCheckpoint(Base):
    __tablename__ = "source_checkpoints"
    __table_args__ = (UniqueConstraint("source_id", "checkpoint_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"), nullable=False)
    checkpoint_key: Mapped[str] = mapped_column(String(100), nullable=False)
    checkpoint_value: Mapped[str] = mapped_column(String(500), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    source: Mapped["Source"] = relationship(back_populates="checkpoints")
