"""add_student_approval_status

Revision ID: 6848c391232f
Revises: 49247ed3d1b4
Create Date: 2026-11-11 08:30:10.473163

Replaces the earlier ENUM draft with a VARCHAR column so the approval values can
grow without a MySQL ALTER on the enum type. Values are validated in Python by
``StudentApprovalService`` and ``User.approve()``.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "6848c391232f"
down_revision = "49247ed3d1b4"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "approval_status",
                sa.String(length=20),
                server_default="pending",
                nullable=False,
            )
        )

    # Backfill: every account that already exists is trusted, including students
    # who registered before the approval gate existed. New student registrations
    # are explicitly set to "pending" by the registration route.
    op.execute("UPDATE users SET approval_status = 'approved'")


def downgrade():
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_column("approval_status")
