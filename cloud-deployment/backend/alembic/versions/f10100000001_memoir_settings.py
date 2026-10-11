"""Per-person book settings and independently imported cover photos."""
from alembic import op
import sqlalchemy as sa
revision = 'f10100000001'
down_revision = 'e10100000001'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('memoir_settings',
        sa.Column('person_id', sa.String(36), sa.ForeignKey('family_members.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('family_id', sa.String(36), sa.ForeignKey('families.id', ondelete='CASCADE'), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False), sa.Column('settings', sa.JSON(), nullable=False),
        sa.Column('request_id', sa.String(36), nullable=False), sa.Column('request_hash', sa.String(64), nullable=False))
    op.add_column('media_assets', sa.Column('memoir_person_id', sa.String(36), nullable=True))
    op.create_foreign_key('fk_media_memoir_person', 'media_assets', 'family_members', ['memoir_person_id'], ['id'], ondelete='CASCADE')
    op.create_index('ix_media_assets_memoir_person_id', 'media_assets', ['memoir_person_id'])


def downgrade():
    db = op.get_bind()
    if db.scalar(sa.text('SELECT COUNT(*) FROM memoir_settings')) or db.scalar(sa.text('SELECT COUNT(*) FROM media_assets WHERE memoir_person_id IS NOT NULL')):
        raise RuntimeError('Back up and remove memoir settings/imported covers explicitly before downgrade')
    op.drop_constraint('fk_media_memoir_person', 'media_assets', type_='foreignkey')
    op.drop_index('ix_media_assets_memoir_person_id', table_name='media_assets')
    op.drop_column('media_assets', 'memoir_person_id')
    op.drop_table('memoir_settings')
