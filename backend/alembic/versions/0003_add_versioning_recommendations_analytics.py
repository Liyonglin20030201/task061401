"""add versioning, recommendations, and analytics tables

Revision ID: 0003
Revises: 0002_add_department_fields
Create Date: 2026-06-14
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB
from pgvector.sqlalchemy import Vector

revision = '0003'
down_revision = '0002_add_department_fields'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'document_versions',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('document_id', UUID(as_uuid=True), sa.ForeignKey('documents.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('version_number', sa.Integer(), nullable=False),
        sa.Column('file_path', sa.String(512), nullable=False),
        sa.Column('file_hash', sa.String(64), nullable=False),
        sa.Column('content_snapshot', sa.Text(), nullable=True),
        sa.Column('change_summary', sa.Text(), server_default=''),
        sa.Column('uploaded_by', UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.UniqueConstraint('document_id', 'version_number', name='uq_doc_version'),
    )

    op.create_table(
        'document_embeddings',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('document_id', UUID(as_uuid=True), sa.ForeignKey('documents.id', ondelete='CASCADE'), nullable=False, unique=True),
        sa.Column('embedding', Vector(1536), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
    )

    op.create_table(
        'question_clusters',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('kb_id', UUID(as_uuid=True), sa.ForeignKey('knowledge_bases.id'), nullable=True),
        sa.Column('representative_question', sa.Text(), nullable=False),
        sa.Column('question_count', sa.Integer(), server_default='1'),
        sa.Column('centroid_embedding', Vector(1536), nullable=True),
        sa.Column('avg_rating', sa.Float(), nullable=True),
        sa.Column('avg_confidence', sa.Float(), nullable=True),
        sa.Column('last_asked_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
    )

    op.add_column('messages', sa.Column('confidence_score', sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column('messages', 'confidence_score')
    op.drop_table('question_clusters')
    op.drop_table('document_embeddings')
    op.drop_table('document_versions')
