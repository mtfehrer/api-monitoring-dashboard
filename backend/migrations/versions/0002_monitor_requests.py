"""Store each monitor's HTTP request configuration.

Revision ID: 0002
Revises: 0001
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("monitors", sa.Column("method", sa.Text(), server_default="GET", nullable=False))
    op.add_column("monitors", sa.Column(
        "request_headers", JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False,
    ))
    op.add_column("monitors", sa.Column("request_body", sa.Text(), nullable=True))


def downgrade():
    op.drop_column("monitors", "request_body")
    op.drop_column("monitors", "request_headers")
    op.drop_column("monitors", "method")
