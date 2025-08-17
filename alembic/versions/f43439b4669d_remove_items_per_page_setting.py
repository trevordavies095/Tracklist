"""remove_items_per_page_setting

Revision ID: f43439b4669d
Revises: c08a1be9510e
Create Date: 2025-08-17 10:31:15.659184

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f43439b4669d'
down_revision = 'c08a1be9510e'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Remove items_per_page column
    op.drop_column('user_settings', 'items_per_page')


def downgrade() -> None:
    # Add back items_per_page column
    op.add_column('user_settings', sa.Column('items_per_page', sa.Integer(), nullable=True))