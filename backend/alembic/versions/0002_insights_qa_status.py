"""insight run status and Q&A abstention

Revision ID: 0002
Revises: 0001
"""
import sqlalchemy as sa
from alembic import op

revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('insights', sa.Column('status', sa.String(length=20), server_default='done', nullable=False))
    op.add_column('insights', sa.Column('error', sa.Text(), nullable=True))
    op.add_column('insights', sa.Column('transcript_hash', sa.String(length=64), nullable=True))
    op.add_column('qa_turns', sa.Column('abstained', sa.Boolean(), server_default='false', nullable=False))
    op.add_column('qa_turns', sa.Column('abstain_reason', sa.String(length=40), nullable=True))
    op.add_column('qa_turns', sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False))


def downgrade() -> None:
    op.drop_column('qa_turns', 'created_at')
    op.drop_column('qa_turns', 'abstain_reason')
    op.drop_column('qa_turns', 'abstained')
    op.drop_column('insights', 'transcript_hash')
    op.drop_column('insights', 'error')
    op.drop_column('insights', 'status')
