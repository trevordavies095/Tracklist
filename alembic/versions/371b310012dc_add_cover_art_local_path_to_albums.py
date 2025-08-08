"""add_cover_art_local_path_to_albums

Revision ID: 371b310012dc
Revises: ae932220f1fa
Create Date: 2025-08-08 15:41:20.553257

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '371b310012dc'
down_revision = 'ae932220f1fa'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add column for local cover art path
    op.add_column('albums', sa.Column('cover_art_local_path', sa.Text(), nullable=True))


def downgrade() -> None:
    # Remove the column
    op.drop_column('albums', 'cover_art_local_path')