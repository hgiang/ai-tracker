"""add item feedback columns

Revision ID: 20260513_01
Revises: 20260414_01
Create Date: 2026-05-13
"""

from alembic import op
import sqlalchemy as sa


revision = "20260513_01"
down_revision = "20260414_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("items", sa.Column("user_feedback", sa.String(length=10), nullable=True))
    op.add_column("items", sa.Column("feedback_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("items", "feedback_at")
    op.drop_column("items", "user_feedback")
