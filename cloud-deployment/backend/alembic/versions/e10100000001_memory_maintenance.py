"""Stage edited photos and persist deletion/cleanup retries."""
from alembic import op
import sqlalchemy as sa
revision = 'e10100000001'
down_revision = 'd10100000001'
branch_labels = None
depends_on = None

def upgrade():
    op.add_column('media_assets', sa.Column('editing_memory_id', sa.String(36), nullable=True))
    op.create_foreign_key('fk_media_editing_memory', 'media_assets', 'memories', ['editing_memory_id'], ['id'], ondelete='CASCADE')
    op.create_index('ix_media_assets_editing_memory_id', 'media_assets', ['editing_memory_id'])
    op.create_table('media_cleanup_jobs', sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('family_id', sa.String(36), sa.ForeignKey('families.id', ondelete='CASCADE'), nullable=False),
        sa.Column('attempts', sa.Integer(), nullable=False, server_default='0'), sa.Column('created_at', sa.DateTime(timezone=True), nullable=False))
    op.create_table('memory_deletions', sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('family_id', sa.String(36), sa.ForeignKey('families.id', ondelete='CASCADE'), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False), sa.Column('created_at', sa.DateTime(timezone=True), nullable=False))

def downgrade():
    db = op.get_bind()
    if db.scalar(sa.text('SELECT COUNT(*) FROM media_cleanup_jobs')) or db.scalar(sa.text('SELECT COUNT(*) FROM media_assets WHERE editing_memory_id IS NOT NULL')):
        raise RuntimeError('Complete pending photo cleanup and discard/save staged photos before downgrade')
    op.drop_table('memory_deletions')
    op.drop_table('media_cleanup_jobs')
    op.drop_constraint('fk_media_editing_memory', 'media_assets', type_='foreignkey')
    op.drop_index('ix_media_assets_editing_memory_id', table_name='media_assets')
    op.drop_column('media_assets', 'editing_memory_id')
