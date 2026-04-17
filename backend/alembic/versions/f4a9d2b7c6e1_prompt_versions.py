"""prompt_versions

Revision ID: f4a9d2b7c6e1
Revises: e8c2f1a7b3d5
Create Date: 2026-04-17 23:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f4a9d2b7c6e1'
down_revision: Union[str, None] = 'e8c2f1a7b3d5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "prompt_versions",
        sa.Column("version_id", sa.String(64), primary_key=True),  # sha256 of content
        sa.Column("agent", sa.String(64), nullable=False, index=True),
        sa.Column("system_prompt", sa.Text, nullable=False),
        sa.Column("tool_schemas", sa.JSON, nullable=True),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("agent", "sha256", name="uq_prompt_agent_sha"),
    )


def downgrade() -> None:
    op.drop_table("prompt_versions")
