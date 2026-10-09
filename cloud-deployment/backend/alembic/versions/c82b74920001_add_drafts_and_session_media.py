"""Add confirmed drafts and uploaded session attachments."""
from alembic import op
import sqlalchemy as sa
revision='c82b74920001'
down_revision='b2951a5cb807'
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('memory_drafts',
        sa.Column('id',sa.String(36),primary_key=True),
        sa.Column('session_id',sa.String(36),sa.ForeignKey('chat_sessions.id',ondelete='CASCADE'),nullable=False,unique=True),
        sa.Column('revision',sa.String(36),nullable=False),
        sa.Column('source_hash',sa.String(64),nullable=False),
        sa.Column('payload',sa.JSON(),nullable=False),
        sa.Column('saved_memory_id',sa.String(36),sa.ForeignKey('memories.id',ondelete='SET NULL'),nullable=True),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False))
    op.alter_column('media_assets','memory_id',existing_type=sa.String(36),nullable=True)
    op.add_column('media_assets',sa.Column('session_id',sa.String(36),nullable=True))
    op.create_foreign_key('fk_media_session','media_assets','chat_sessions',['session_id'],['id'],ondelete='CASCADE')

def downgrade():
    op.drop_constraint('fk_media_session','media_assets',type_='foreignkey')
    op.drop_column('media_assets','session_id')
    op.drop_table('memory_drafts')
    # Session-only uploads must be removed explicitly before restoring NOT NULL.
    op.alter_column('media_assets','memory_id',existing_type=sa.String(36),nullable=False)
