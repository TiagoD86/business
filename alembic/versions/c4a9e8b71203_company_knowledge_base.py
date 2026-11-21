"""company_knowledge_base

Revision ID: c4a9e8b71203
Revises: f36bd463d014
Create Date: 2026-11-21 15:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c4a9e8b71203'
down_revision: Union[str, Sequence[str], None] = 'f36bd463d014'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'company_knowledge',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('company_name', sa.String(length=160), nullable=False),
        sa.Column('business_profile', sa.Text(), nullable=False),
        sa.Column('goals_and_margins', sa.Text(), nullable=False),
        sa.Column('golden_rules', sa.Text(), nullable=False),
        sa.Column('agent_notes', sa.Text(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('updated_by', sa.String(length=80), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_company_knowledge_is_active'), 'company_knowledge', ['is_active'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_company_knowledge_is_active'), table_name='company_knowledge')
    op.drop_table('company_knowledge')
