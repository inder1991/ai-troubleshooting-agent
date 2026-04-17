"""outbox

Revision ID: a60b28e2d6b9
Revises: 6789cbb99151
Create Date: 2026-04-17 09:49:46.328451

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a60b28e2d6b9'
down_revision: Union[str, None] = '6789cbb99151'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "investigation_outbox",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("run_id", sa.String(64), nullable=False, index=True),
        sa.Column("seq", sa.BigInteger, nullable=False),
        sa.Column("kind", sa.String(64), nullable=False),
        sa.Column("payload", sa.JSON, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column("relayed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("run_id", "seq", name="uq_outbox_run_seq"),
    )
    op.create_index(
        "ix_outbox_unrelayed",
        "investigation_outbox",
        ["relayed_at"],
        postgresql_where=sa.text("relayed_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_outbox_unrelayed", table_name="investigation_outbox")
    op.drop_table("investigation_outbox")
