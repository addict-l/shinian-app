"""Add compatible story information and message attachment foundations."""
from alembic import op
import sqlalchemy as sa

revision = 'd10100000001'
down_revision = 'c82b74920002'
branch_labels = None
depends_on = None


def upgrade():
    for table in ('chat_sessions', 'memories'):
        op.add_column(table, sa.Column('information', sa.JSON(), nullable=True))
        op.add_column(table, sa.Column('version', sa.Integer(), nullable=False, server_default='1'))
    op.add_column('memories', sa.Column('primary_person_id', sa.String(36), nullable=True))
    op.create_foreign_key('fk_memory_primary_person', 'memories', 'family_members', ['primary_person_id'], ['id'], ondelete='SET NULL')
    # Only an explicit source session provides evidence of the narrative subject.
    op.execute(sa.text('UPDATE memories SET primary_person_id = (SELECT primary_person_id FROM chat_sessions WHERE chat_sessions.id = memories.source_session_id) WHERE source_session_id IS NOT NULL'))
    op.add_column('media_assets', sa.Column('message_id', sa.String(36), nullable=True))
    op.add_column('media_assets', sa.Column('position', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('media_assets', sa.Column('content_hash', sa.String(64), nullable=True))
    op.create_foreign_key('fk_media_message', 'media_assets', 'chat_messages', ['message_id'], ['id'], ondelete='SET NULL')
    op.create_index('ix_media_assets_message_id', 'media_assets', ['message_id'])


def downgrade():
    op.drop_constraint('fk_media_message', 'media_assets', type_='foreignkey')
    op.drop_index('ix_media_assets_message_id', table_name='media_assets')
    for column in ('content_hash', 'position', 'message_id'):
        op.drop_column('media_assets', column)
    op.drop_constraint('fk_memory_primary_person', 'memories', type_='foreignkey')
    op.drop_column('memories', 'primary_person_id')
    for table in ('memories', 'chat_sessions'):
        op.drop_column(table, 'version')
        op.drop_column(table, 'information')
