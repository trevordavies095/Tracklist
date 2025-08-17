"""extend_user_settings_for_configurable_settings

Revision ID: c08a1be9510e
Revises: b6afafabd3fd
Create Date: 2025-08-17 09:26:29.284323

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c08a1be9510e'
down_revision = 'b6afafabd3fd'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Get current columns to avoid duplicates
    from sqlalchemy import inspect
    from sqlalchemy.sql import text
    
    conn = op.get_bind()
    inspector = inspect(conn)
    existing_columns = [col['name'] for col in inspector.get_columns('user_settings')]
    
    # Add new columns for extended settings (only if they don't exist)
    if 'auto_migrate_artwork' not in existing_columns:
        op.add_column('user_settings', sa.Column('auto_migrate_artwork', sa.Boolean(), nullable=True))
    if 'cache_retention_days' not in existing_columns:
        op.add_column('user_settings', sa.Column('cache_retention_days', sa.Integer(), nullable=True))
    if 'cache_max_size_mb' not in existing_columns:
        op.add_column('user_settings', sa.Column('cache_max_size_mb', sa.Integer(), nullable=True))
    if 'cache_cleanup_enabled' not in existing_columns:
        op.add_column('user_settings', sa.Column('cache_cleanup_enabled', sa.Boolean(), nullable=True))
    if 'cache_cleanup_schedule' not in existing_columns:
        op.add_column('user_settings', sa.Column('cache_cleanup_schedule', sa.String(20), nullable=True))
    if 'items_per_page' not in existing_columns:
        op.add_column('user_settings', sa.Column('items_per_page', sa.Integer(), nullable=True))
    if 'default_sort_order' not in existing_columns:
        op.add_column('user_settings', sa.Column('default_sort_order', sa.String(20), nullable=True))
    if 'date_format' not in existing_columns:
        op.add_column('user_settings', sa.Column('date_format', sa.String(20), nullable=True))
    if 'auto_cache_artwork' not in existing_columns:
        op.add_column('user_settings', sa.Column('auto_cache_artwork', sa.Boolean(), nullable=True))
    if 'migration_batch_size' not in existing_columns:
        op.add_column('user_settings', sa.Column('migration_batch_size', sa.Integer(), nullable=True))
    if 'cache_cleanup_time' not in existing_columns:
        op.add_column('user_settings', sa.Column('cache_cleanup_time', sa.String(10), nullable=True))
    
    # Set default values for existing rows
    op.execute("""
        UPDATE user_settings 
        SET auto_migrate_artwork = true,
            cache_retention_days = 365,
            cache_max_size_mb = 5000,
            cache_cleanup_enabled = true,
            cache_cleanup_schedule = 'daily',
            items_per_page = 20,
            default_sort_order = 'created_desc',
            date_format = 'YYYY-MM-DD',
            auto_cache_artwork = true,
            migration_batch_size = 10,
            cache_cleanup_time = '03:00'
        WHERE auto_migrate_artwork IS NULL
    """)


def downgrade() -> None:
    # Remove the added columns
    op.drop_column('user_settings', 'cache_cleanup_time')
    op.drop_column('user_settings', 'migration_batch_size')
    op.drop_column('user_settings', 'auto_cache_artwork')
    op.drop_column('user_settings', 'date_format')
    op.drop_column('user_settings', 'default_sort_order')
    op.drop_column('user_settings', 'items_per_page')
    op.drop_column('user_settings', 'cache_cleanup_schedule')
    op.drop_column('user_settings', 'cache_cleanup_enabled')
    op.drop_column('user_settings', 'cache_max_size_mb')
    op.drop_column('user_settings', 'cache_retention_days')
    op.drop_column('user_settings', 'auto_migrate_artwork')