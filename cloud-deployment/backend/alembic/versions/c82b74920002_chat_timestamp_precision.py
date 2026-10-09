"""Preserve message ordering within one second."""
from alembic import op
from sqlalchemy.dialects.mysql import DATETIME
revision = 'c82b74920002'
down_revision = 'c82b74920001'
branch_labels = None
depends_on = None

def upgrade():
    op.alter_column('chat_messages', 'created_at', existing_type=DATETIME(), type_=DATETIME(fsp=6), existing_nullable=False)

def downgrade():
    op.alter_column('chat_messages', 'created_at', existing_type=DATETIME(fsp=6), type_=DATETIME(), existing_nullable=False)
