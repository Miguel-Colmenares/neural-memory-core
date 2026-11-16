"""Esquema inicial: núcleo de memoria, proyectos, tareas y usuarios.

Revision ID: 0001
Revises:
Create Date: 2026-11-16
"""
from typing import Sequence, Union

from alembic import op
import pgvector.sqlalchemy
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '0001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table('change_log',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('entity_type', sa.String(length=40), nullable=False),
    sa.Column('entity_id', sa.String(length=64), nullable=False),
    sa.Column('project_id', sa.UUID(), nullable=True),
    sa.Column('action', sa.String(length=40), nullable=False),
    sa.Column('summary', sa.Text(), nullable=False),
    sa.Column('details', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('actor', sa.String(length=80), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_change_log_created_at', 'change_log', ['created_at'], unique=False)
    op.create_index('ix_change_log_entity', 'change_log', ['entity_type', 'entity_id'], unique=False)
    op.create_index(op.f('ix_change_log_project_id'), 'change_log', ['project_id'], unique=False)
    op.create_table('projects',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('slug', sa.String(length=120), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('objectives', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("status IN ('active', 'paused', 'completed', 'archived')", name='ck_projects_status'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('slug')
    )
    op.create_table('users',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('username', sa.String(length=80), nullable=False),
    sa.Column('password_hash', sa.String(length=200), nullable=False),
    sa.Column('role', sa.String(length=20), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("role IN ('admin', 'editor', 'reader')", name='ck_users_role'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('username')
    )
    op.create_table('memories',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('memory_type', sa.String(length=20), nullable=False),
    sa.Column('kind', sa.String(length=50), nullable=False),
    sa.Column('title', sa.String(length=300), nullable=True),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('content_hash', sa.String(length=64), nullable=False),
    sa.Column('source_type', sa.String(length=30), nullable=False),
    sa.Column('source_ref', sa.String(length=500), nullable=True),
    sa.Column('provenance', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('project_id', sa.UUID(), nullable=True),
    sa.Column('module', sa.String(length=50), nullable=True),
    sa.Column('tags', postgresql.ARRAY(sa.String(length=80)), nullable=False),
    sa.Column('importance', sa.SmallInteger(), nullable=False),
    sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('status', sa.String(length=10), nullable=False),
    sa.Column('occurred_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('created_by', sa.String(length=80), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('search_vector', postgresql.TSVECTOR(), sa.Computed("setweight(to_tsvector('spanish'::regconfig, coalesce(title, '')), 'A') || setweight(to_tsvector('spanish'::regconfig, content), 'B')", persisted=True), nullable=False),
    sa.CheckConstraint("memory_type IN ('episodic', 'semantic', 'project', 'preference', 'document')", name='ck_memories_type'),
    sa.CheckConstraint("source_type IN ('manual', 'conversation', 'document', 'import', 'api', 'module')", name='ck_memories_source_type'),
    sa.CheckConstraint("status IN ('active', 'archived')", name='ck_memories_status'),
    sa.CheckConstraint('importance BETWEEN 1 AND 5', name='ck_memories_importance'),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_memories_content_hash'), 'memories', ['content_hash'], unique=False)
    op.create_index('ix_memories_created_at', 'memories', ['created_at'], unique=False)
    op.create_index(op.f('ix_memories_kind'), 'memories', ['kind'], unique=False)
    op.create_index(op.f('ix_memories_project_id'), 'memories', ['project_id'], unique=False)
    op.create_index('ix_memories_search_vector', 'memories', ['search_vector'], unique=False, postgresql_using='gin')
    op.create_index('ix_memories_tags', 'memories', ['tags'], unique=False, postgresql_using='gin')
    op.create_index('ix_memories_type_status', 'memories', ['memory_type', 'status'], unique=False)
    op.create_table('project_relations',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('source_project_id', sa.UUID(), nullable=False),
    sa.Column('target_project_id', sa.UUID(), nullable=False),
    sa.Column('relation_type', sa.String(length=50), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint('source_project_id <> target_project_id', name='ck_project_rel_distinct'),
    sa.ForeignKeyConstraint(['source_project_id'], ['projects.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['target_project_id'], ['projects.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('source_project_id', 'target_project_id', 'relation_type')
    )
    op.create_index(op.f('ix_project_relations_source_project_id'), 'project_relations', ['source_project_id'], unique=False)
    op.create_index(op.f('ix_project_relations_target_project_id'), 'project_relations', ['target_project_id'], unique=False)
    op.create_table('tasks',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('project_id', sa.UUID(), nullable=True),
    sa.Column('title', sa.String(length=300), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('priority', sa.SmallInteger(), nullable=False),
    sa.Column('due_date', sa.Date(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint("status IN ('pending', 'in_progress', 'done', 'cancelled')", name='ck_tasks_status'),
    sa.CheckConstraint('priority BETWEEN 1 AND 5', name='ck_tasks_priority'),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_tasks_project_id'), 'tasks', ['project_id'], unique=False)
    op.create_index(op.f('ix_tasks_status'), 'tasks', ['status'], unique=False)
    op.create_table('memory_embeddings',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('memory_id', sa.UUID(), nullable=False),
    sa.Column('chunk_index', sa.Integer(), nullable=False),
    sa.Column('chunk_text', sa.Text(), nullable=False),
    sa.Column('provider', sa.String(length=40), nullable=False),
    sa.Column('model', sa.String(length=200), nullable=False),
    sa.Column('embedding', pgvector.sqlalchemy.vector.VECTOR(dim=384), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['memory_id'], ['memories.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('memory_id', 'chunk_index')
    )
    op.create_index('ix_memory_embeddings_hnsw', 'memory_embeddings', ['embedding'], unique=False, postgresql_using='hnsw', postgresql_ops={'embedding': 'vector_cosine_ops'})
    op.create_index(op.f('ix_memory_embeddings_memory_id'), 'memory_embeddings', ['memory_id'], unique=False)
    op.create_table('memory_relations',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('source_id', sa.UUID(), nullable=False),
    sa.Column('target_id', sa.UUID(), nullable=False),
    sa.Column('relation_type', sa.String(length=40), nullable=False),
    sa.Column('origin', sa.String(length=10), nullable=False),
    sa.Column('confidence', sa.Float(), nullable=True),
    sa.Column('note', sa.Text(), nullable=True),
    sa.Column('created_by', sa.String(length=80), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("origin IN ('auto', 'manual')", name='ck_memory_rel_origin'),
    sa.CheckConstraint('source_id <> target_id', name='ck_memory_rel_distinct'),
    sa.ForeignKeyConstraint(['source_id'], ['memories.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['target_id'], ['memories.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('source_id', 'target_id', 'relation_type')
    )
    op.create_index(op.f('ix_memory_relations_source_id'), 'memory_relations', ['source_id'], unique=False)
    op.create_index(op.f('ix_memory_relations_target_id'), 'memory_relations', ['target_id'], unique=False)
    op.create_table('memory_versions',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('memory_id', sa.UUID(), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('snapshot', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('change_type', sa.String(length=30), nullable=False),
    sa.Column('change_reason', sa.Text(), nullable=True),
    sa.Column('changed_fields', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('changed_by', sa.String(length=80), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['memory_id'], ['memories.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('memory_id', 'version')
    )
    op.create_index(op.f('ix_memory_versions_memory_id'), 'memory_versions', ['memory_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_memory_versions_memory_id'), table_name='memory_versions')
    op.drop_table('memory_versions')
    op.drop_index(op.f('ix_memory_relations_target_id'), table_name='memory_relations')
    op.drop_index(op.f('ix_memory_relations_source_id'), table_name='memory_relations')
    op.drop_table('memory_relations')
    op.drop_index(op.f('ix_memory_embeddings_memory_id'), table_name='memory_embeddings')
    op.drop_index('ix_memory_embeddings_hnsw', table_name='memory_embeddings', postgresql_using='hnsw', postgresql_ops={'embedding': 'vector_cosine_ops'})
    op.drop_table('memory_embeddings')
    op.drop_index(op.f('ix_tasks_status'), table_name='tasks')
    op.drop_index(op.f('ix_tasks_project_id'), table_name='tasks')
    op.drop_table('tasks')
    op.drop_index(op.f('ix_project_relations_target_project_id'), table_name='project_relations')
    op.drop_index(op.f('ix_project_relations_source_project_id'), table_name='project_relations')
    op.drop_table('project_relations')
    op.drop_index('ix_memories_type_status', table_name='memories')
    op.drop_index('ix_memories_tags', table_name='memories', postgresql_using='gin')
    op.drop_index('ix_memories_search_vector', table_name='memories', postgresql_using='gin')
    op.drop_index(op.f('ix_memories_project_id'), table_name='memories')
    op.drop_index(op.f('ix_memories_kind'), table_name='memories')
    op.drop_index('ix_memories_created_at', table_name='memories')
    op.drop_index(op.f('ix_memories_content_hash'), table_name='memories')
    op.drop_table('memories')
    op.drop_table('users')
    op.drop_table('projects')
    op.drop_index(op.f('ix_change_log_project_id'), table_name='change_log')
    op.drop_index('ix_change_log_entity', table_name='change_log')
    op.drop_index('ix_change_log_created_at', table_name='change_log')
    op.drop_table('change_log')
