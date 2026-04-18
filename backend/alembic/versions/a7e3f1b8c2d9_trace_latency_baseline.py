"""trace_latency_baseline — rolling P99 per (service, operation)

Populated every 5 minutes by workers/trace_baseline_populator. Read by
BaselineRegressionDetector to flag span durations that exceed the
historical P99 for their (service, operation) key. TA-PR2b.

Revision ID: a7e3f1b8c2d9
Revises: f4a9d2b7c6e1
Create Date: 2026-04-18 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a7e3f1b8c2d9'
down_revision: Union[str, None] = 'f4a9d2b7c6e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "trace_latency_baseline",
        sa.Column("service_name", sa.String(128), primary_key=True),
        sa.Column("operation_name", sa.String(255), primary_key=True),
        sa.Column("p99_ms_7d", sa.Float, nullable=False),
        sa.Column("sample_count", sa.Integer, nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    # Index on updated_at so the populator can cheaply find stale rows
    # that need re-aggregation or eviction.
    op.create_index(
        "ix_trace_latency_baseline_updated_at",
        "trace_latency_baseline",
        ["updated_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_trace_latency_baseline_updated_at", "trace_latency_baseline")
    op.drop_table("trace_latency_baseline")
