"""agent_priors

Revision ID: c3a1f9e4b2d1
Revises: 18ead3c4e6b7
Create Date: 2026-04-17 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3a1f9e4b2d1'
down_revision: Union[str, None] = '18ead3c4e6b7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agent_priors",
        sa.Column("agent_name", sa.String(128), primary_key=True),
        sa.Column(
            "prior",
            sa.Float,
            nullable=False,
            server_default=sa.text("0.65"),
        ),
        sa.Column(
            "sample_count",
            sa.BigInteger,
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    op.drop_table("agent_priors")
