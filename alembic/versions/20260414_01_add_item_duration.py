"""add item duration column

Revision ID: 20260414_01
Revises:
Create Date: 2026-04-14
"""

from alembic import op
import sqlalchemy as sa


revision = "20260414_01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("items", sa.Column("duration", sa.String(length=20), nullable=True))


def downgrade() -> None:
    op.drop_column("items", "duration")
