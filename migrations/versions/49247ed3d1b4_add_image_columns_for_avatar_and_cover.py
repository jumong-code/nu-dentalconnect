"""add_image_columns_for_avatar_and_cover

Revision ID: 49247ed3d1b4
Revises: 7c2e0a4b6f11
Create Date: 2026-11-11 01:02:18.293569

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '49247ed3d1b4'
down_revision = '7c2e0a4b6f11'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("patients") as batch_op:
        batch_op.add_column(sa.Column("avatar_image", sa.String(length=255), nullable=True))
    with op.batch_alter_table("dentistry_students") as batch_op:
        batch_op.add_column(sa.Column("avatar_image", sa.String(length=255), nullable=True))
    with op.batch_alter_table("recruitment_listings") as batch_op:
        batch_op.add_column(sa.Column("cover_image", sa.String(length=255), nullable=True))


def downgrade():
    with op.batch_alter_table("recruitment_listings") as batch_op:
        batch_op.drop_column("cover_image")
    with op.batch_alter_table("dentistry_students") as batch_op:
        batch_op.drop_column("avatar_image")
    with op.batch_alter_table("patients") as batch_op:
        batch_op.drop_column("avatar_image")