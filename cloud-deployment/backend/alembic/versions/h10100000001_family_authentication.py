"""Add shared family accounts and device sessions without changing family data."""
from alembic import op
import sqlalchemy as sa
revision = 'h10100000001'
down_revision = 'g10100000001'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('family_accounts',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('username', sa.String(32), nullable=False, unique=True),
        sa.Column('password_hash', sa.String(255), nullable=False),
        sa.Column('family_id', sa.String(36), sa.ForeignKey('families.id', ondelete='RESTRICT'), nullable=False, unique=True),
        sa.Column('enabled', sa.Boolean(), nullable=False),
        sa.Column('legacy', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False))
    op.create_table('device_sessions',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('account_id', sa.String(36), sa.ForeignKey('family_accounts.id', ondelete='CASCADE'), nullable=False),
        sa.Column('token_hash', sa.String(64), nullable=False, unique=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True))
    op.create_index('ix_device_sessions_account_id', 'device_sessions', ['account_id'])
    op.create_table('auth_rate_limits',
        sa.Column('key', sa.String(64), primary_key=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('attempts', sa.Integer(), nullable=False))


def downgrade():
    if op.get_bind().scalar(sa.text('SELECT COUNT(*) FROM family_accounts')):
        raise RuntimeError('Back up accounts and revoke sessions before explicitly removing authentication data')
    op.drop_table('auth_rate_limits')
    op.drop_table('device_sessions')
    op.drop_table('family_accounts')
