"""backend_call_audit

Revision ID: e8c2f1a7b3d5
Revises: d7b4e2c1a8f3
Create Date: 2026-04-17 22:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e8c2f1a7b3d5'
down_revision: Union[str, None] = 'd7b4e2c1a8f3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "backend_call_audit",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("run_id", sa.String(64), nullable=False, index=True),
        sa.Column("agent", sa.String(64), nullable=False),
        sa.Column("tool", sa.String(128), nullable=False),
        sa.Column("backend", sa.String(64), nullable=False),
        sa.Column("query_hash", sa.String(64), nullable=False),
        sa.Column("response_code", sa.Integer, nullable=True),
        sa.Column("duration_ms", sa.Integer, nullable=False),
        sa.Column("bytes", sa.BigInteger, nullable=True),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_backend_call_audit_run_created",
        "backend_call_audit",
        ["run_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_backend_call_audit_run_created", table_name="backend_call_audit")
    op.drop_table("backend_call_audit")
