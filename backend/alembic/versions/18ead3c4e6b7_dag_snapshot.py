"""dag_snapshot

Revision ID: 18ead3c4e6b7
Revises: a60b28e2d6b9
Create Date: 2026-04-17 10:18:11.823593

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '18ead3c4e6b7'
down_revision: Union[str, None] = 'a60b28e2d6b9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "investigation_dag_snapshot",
        sa.Column("run_id", sa.String(64), primary_key=True),
        sa.Column("payload", sa.JSON, nullable=False),
        sa.Column(
            "schema_version",
            sa.Integer,
            nullable=False,
            server_default=sa.text("1"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    op.drop_table("investigation_dag_snapshot")
