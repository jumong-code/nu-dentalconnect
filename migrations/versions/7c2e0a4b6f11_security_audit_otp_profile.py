"""Add email verification, audit history, and student profile fields.

Revision ID: 7c2e0a4b6f11
Revises: 1e0c92bb72f1
"""
from alembic import op
import sqlalchemy as sa


revision = "7c2e0a4b6f11"
down_revision = "1e0c92bb72f1"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(sa.Column("email_verified", sa.Boolean(), nullable=True))
    op.execute(sa.text("UPDATE users SET email_verified = 1"))
    with op.batch_alter_table("users") as batch_op:
        batch_op.alter_column("email_verified", existing_type=sa.Boolean(), nullable=False)
        batch_op.add_column(sa.Column("auth_version", sa.Integer(), nullable=False, server_default="0"))
    with op.batch_alter_table("dentistry_students") as batch_op:
        batch_op.alter_column("program_year", new_column_name="year_level", existing_type=sa.String(length=80), existing_nullable=True)
        batch_op.add_column(sa.Column("facebook_url", sa.String(length=255), nullable=True))
    with op.batch_alter_table("recruitment_listings") as batch_op:
        batch_op.add_column(sa.Column("submission_key", sa.String(length=64), nullable=True))
        batch_op.create_index("uq_recruitment_listings_submission_key", ["submission_key"], unique=True)

    op.create_table(
        "otp_verifications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("code_digest", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("consumed_at", sa.DateTime(), nullable=True),
        sa.Column("attempts", sa.SmallInteger(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_otp_verifications_user_id", "otp_verifications", ["user_id"])
    op.create_index("ix_otp_verifications_created_at", "otp_verifications", ["created_at"])
    op.create_index("ix_otp_verifications_expires_at", "otp_verifications", ["expires_at"])
    op.create_index("ix_otp_user_created", "otp_verifications", ["user_id", "created_at"])

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("actor_user_id", sa.Integer(), nullable=True),
        sa.Column("actor_email", sa.String(length=255), nullable=False),
        sa.Column("action", sa.String(length=80), nullable=False),
        sa.Column("entity_type", sa.String(length=80), nullable=False),
        sa.Column("entity_id", sa.String(length=80), nullable=True),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("ip_address", sa.String(length=45), nullable=True),
        sa.Column("user_agent", sa.String(length=300), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_audit_logs_actor_user_id", "audit_logs", ["actor_user_id"])
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"])
    op.create_index("ix_audit_logs_created_id", "audit_logs", ["created_at", "id"])


def downgrade():
    op.drop_index("ix_audit_logs_created_id", table_name="audit_logs")
    op.drop_index("ix_audit_logs_created_at", table_name="audit_logs")
    op.drop_index("ix_audit_logs_action", table_name="audit_logs")
    op.drop_index("ix_audit_logs_actor_user_id", table_name="audit_logs")
    op.drop_table("audit_logs")
    op.drop_index("ix_otp_user_created", table_name="otp_verifications")
    op.drop_index("ix_otp_verifications_expires_at", table_name="otp_verifications")
    op.drop_index("ix_otp_verifications_created_at", table_name="otp_verifications")
    op.drop_index("ix_otp_verifications_user_id", table_name="otp_verifications")
    op.drop_table("otp_verifications")
    with op.batch_alter_table("recruitment_listings") as batch_op:
        batch_op.drop_index("uq_recruitment_listings_submission_key")
        batch_op.drop_column("submission_key")
    with op.batch_alter_table("dentistry_students") as batch_op:
        batch_op.drop_column("facebook_url")
        batch_op.alter_column("year_level", new_column_name="program_year", existing_type=sa.String(length=80), existing_nullable=True)
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("auth_version")
        batch_op.drop_column("email_verified")
