"""add_authentication_system

Revision ID: 4147b4f90513
Revises: f43439b4669d
Create Date: 2025-08-26 14:48:20.596525

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = '4147b4f90513'
down_revision = 'f43439b4669d'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Get current columns to avoid duplicates
    conn = op.get_bind()
    inspector = inspect(conn)
    existing_columns = [col['name'] for col in inspector.get_columns('user_settings')]
    
    # Add authentication-related columns (only if they don't exist)
    if 'auth_enabled' not in existing_columns:
        op.add_column('user_settings', sa.Column('auth_enabled', sa.Boolean(), nullable=True))
    
    if 'password_hash' not in existing_columns:
        op.add_column('user_settings', sa.Column('password_hash', sa.Text(), nullable=True))
    
    if 'session_token' not in existing_columns:
        op.add_column('user_settings', sa.Column('session_token', sa.Text(), nullable=True))
    
    if 'session_expiry' not in existing_columns:
        op.add_column('user_settings', sa.Column('session_expiry', sa.DateTime(), nullable=True))
    
    if 'last_login' not in existing_columns:
        op.add_column('user_settings', sa.Column('last_login', sa.DateTime(), nullable=True))
    
    if 'is_setup_complete' not in existing_columns:
        op.add_column('user_settings', sa.Column('is_setup_complete', sa.Boolean(), nullable=True))
    
    # Set default values for existing rows
    op.execute("""
        UPDATE user_settings 
        SET auth_enabled = false,
            is_setup_complete = false
        WHERE auth_enabled IS NULL
    """)


def downgrade() -> None:
    # Remove the authentication columns
    op.drop_column('user_settings', 'is_setup_complete')
    op.drop_column('user_settings', 'last_login')
    op.drop_column('user_settings', 'session_expiry')
    op.drop_column('user_settings', 'session_token')
    op.drop_column('user_settings', 'password_hash')
    op.drop_column('user_settings', 'auth_enabled')