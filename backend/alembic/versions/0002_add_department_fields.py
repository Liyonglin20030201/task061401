"""add department fields

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-14
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision: str = '0002'
down_revision: Union[str, None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('department', sa.String(64), nullable=True))
    op.add_column('knowledge_bases', sa.Column('departments', JSONB, server_default='[]', nullable=False))


def downgrade() -> None:
    op.drop_column('knowledge_bases', 'departments')
    op.drop_column('users', 'department')
