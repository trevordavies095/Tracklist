"""add artwork cache table and columns

Revision ID: b6afafabd3fd
Revises: ae932220f1fa
Create Date: 2025-08-09 20:48:39.451070

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b6afafabd3fd'
down_revision = 'ae932220f1fa'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create artwork_cache table
    op.create_table('artwork_cache',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('album_id', sa.Integer(), nullable=False),
        sa.Column('original_url', sa.Text(), nullable=True),
        sa.Column('cache_key', sa.Text(), nullable=False),
        sa.Column('file_path', sa.Text(), nullable=True),
        sa.Column('size_variant', sa.Text(), nullable=False),
        sa.Column('width', sa.Integer(), nullable=True),
        sa.Column('height', sa.Integer(), nullable=True),
        sa.Column('file_size_bytes', sa.Integer(), nullable=True),
        sa.Column('content_type', sa.Text(), nullable=True),
        sa.Column('etag', sa.Text(), nullable=True),
        sa.Column('last_fetched_at', sa.DateTime(), nullable=True),
        sa.Column('last_accessed_at', sa.DateTime(), nullable=True),
        sa.Column('access_count', sa.Integer(), nullable=True, default=0),
        sa.Column('is_placeholder', sa.Boolean(), nullable=True, default=False),
        sa.Column('created_at', sa.DateTime(), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.CheckConstraint("size_variant IN ('original', 'large', 'medium', 'small', 'thumbnail')", name='check_size_variant'),
        sa.ForeignKeyConstraint(['album_id'], ['albums.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('cache_key')
    )
    
    # Create indexes
    op.create_index('idx_artwork_cache_album_size', 'artwork_cache', ['album_id', 'size_variant'])
    op.create_index('idx_artwork_cache_key', 'artwork_cache', ['cache_key'])
    op.create_index('idx_artwork_cache_last_accessed', 'artwork_cache', ['last_accessed_at'])
    op.create_index('idx_artwork_cache_album_id', 'artwork_cache', ['album_id'])
    
    # Add columns to albums table
    op.add_column('albums', sa.Column('artwork_cached', sa.Boolean(), nullable=True, default=False))
    op.add_column('albums', sa.Column('artwork_cache_date', sa.DateTime(), nullable=True))
    
    # Clean up the schema_migrations table from our manual migration system
    op.drop_table('schema_migrations')


def downgrade() -> None:
    # Remove columns from albums table
    op.drop_column('albums', 'artwork_cache_date')
    op.drop_column('albums', 'artwork_cached')
    
    # Drop indexes
    op.drop_index('idx_artwork_cache_album_id', table_name='artwork_cache')
    op.drop_index('idx_artwork_cache_last_accessed', table_name='artwork_cache')
    op.drop_index('idx_artwork_cache_key', table_name='artwork_cache')
    op.drop_index('idx_artwork_cache_album_size', table_name='artwork_cache')
    
    # Drop artwork_cache table
    op.drop_table('artwork_cache')