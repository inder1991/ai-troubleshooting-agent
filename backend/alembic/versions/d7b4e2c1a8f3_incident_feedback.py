"""incident_feedback

Revision ID: d7b4e2c1a8f3
Revises: c3a1f9e4b2d1
Create Date: 2026-04-17 20:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd7b4e2c1a8f3'
down_revision: Union[str, None] = 'c3a1f9e4b2d1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "incident_feedback",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("run_id", sa.String(64), nullable=False, index=True),
        sa.Column("was_correct", sa.Boolean, nullable=False),
        sa.Column("actual_root_cause", sa.Text, nullable=True),
        sa.Column("freeform", sa.Text, nullable=True),
        sa.Column("submitter", sa.String(128), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "run_id", "submitter", name="uq_incident_feedback_run_submitter"
        ),
    )


def downgrade() -> None:
    op.drop_table("incident_feedback")
