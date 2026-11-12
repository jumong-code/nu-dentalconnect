"""Store student-owned appointment listing templates.

Revision ID: 1e0c92bb72f1
Revises: a5fd38a6e1d2
Create Date: 2026-11-10

"""
from alembic import op
import sqlalchemy as sa


revision = "1e0c92bb72f1"
down_revision = "a5fd38a6e1d2"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "student_listing_templates",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("student_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("category", sa.String(length=100), nullable=False),
        sa.Column("location", sa.String(length=180), nullable=False),
        sa.Column("preferred_schedule", sa.String(length=180), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("eligibility", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["student_id"], ["dentistry_students.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("student_listing_templates", schema=None) as batch_op:
        batch_op.create_index("ix_student_listing_templates_student_id", ["student_id"], unique=False)


def downgrade():
    with op.batch_alter_table("student_listing_templates", schema=None) as batch_op:
        batch_op.drop_index("ix_student_listing_templates_student_id")
    op.drop_table("student_listing_templates")
