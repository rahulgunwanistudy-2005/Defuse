"""Persist metadata context for independent child-pipeline action processes."""

import sqlalchemy as sa
from alembic import op

revision = "20261027_artifacts"
down_revision = "6665f018592a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "action_leases",
        sa.Column("incident_id", sa.String(64), sa.ForeignKey("incidents.id"), primary_key=True),
        sa.Column("action_id", sa.String(300), primary_key=True),
        sa.Column("owner", sa.String(32), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "incident_artifacts",
        sa.Column("incident_id", sa.String(64), sa.ForeignKey("incidents.id"), primary_key=True),
        sa.Column("name", sa.String(300), primary_key=True),
        sa.Column("data", sa.JSON(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("action_leases")
    op.drop_table("incident_artifacts")
