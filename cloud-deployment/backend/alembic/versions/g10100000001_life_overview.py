"""Keep the life outline with the person, independently of story segments."""
from alembic import op
import sqlalchemy as sa
revision = 'g10100000001'
down_revision = 'f10100000001'
branch_labels = None
depends_on = None

def upgrade():
    op.add_column('family_members', sa.Column('life_interview', sa.JSON(), nullable=True))

def downgrade():
    if op.get_bind().scalar(sa.text('SELECT COUNT(*) FROM family_members WHERE life_interview IS NOT NULL')):
        raise RuntimeError('Back up person life outlines before explicit removal and downgrade')
    op.drop_column('family_members', 'life_interview')
