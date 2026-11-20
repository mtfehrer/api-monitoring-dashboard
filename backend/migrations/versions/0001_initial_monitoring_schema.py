"""Initial monitoring schema.

Revision ID: 0001
Revises: None
"""
from alembic import op
import sqlalchemy as sa


revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'monitors',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('url', sa.Text(), nullable=False),
        sa.Column('interval_seconds', sa.Integer(), nullable=False),
        sa.Column('expected_status', sa.Integer(), nullable=False),
        sa.Column('timeout_seconds', sa.Float(), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('next_run_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('awaiting_since', sa.DateTime(timezone=True), nullable=True),
        sa.Column('generation', sa.Integer(), nullable=False),
        sa.Column('failure_streak', sa.Integer(), nullable=False),
        sa.Column('first_failure_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('recovery_streak', sa.Integer(), nullable=False),
        sa.CheckConstraint('enabled = (next_run_at IS NOT NULL)', name='monitor_schedule_enabled'),
        sa.CheckConstraint('expected_status BETWEEN 100 AND 599', name='monitor_status_range'),
        sa.CheckConstraint('interval_seconds BETWEEN 5 AND 3600', name='monitor_interval_range'),
        sa.CheckConstraint('timeout_seconds > 0 AND timeout_seconds < interval_seconds', name='monitor_timeout_range'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_monitors_due', 'monitors', ['next_run_at', 'id'], unique=False, postgresql_where=sa.text('enabled'))
    op.create_table(
        'check_results',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('monitor_id', sa.Integer(), nullable=False),
        sa.Column('scheduled_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('elapsed_ms', sa.Integer(), nullable=False),
        sa.Column('success', sa.Boolean(), nullable=False),
        sa.Column('http_status', sa.Integer(), nullable=True),
        sa.Column('failure_reason', sa.Text(), nullable=True),
        sa.Column('gap_before', sa.Boolean(), nullable=False),
        sa.Column('generation', sa.Integer(), nullable=False),
        sa.CheckConstraint('elapsed_ms >= 0', name='check_elapsed_nonnegative'),
        sa.ForeignKeyConstraint(['monitor_id'], ['monitors.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('monitor_id', 'scheduled_at', name='uq_check_monitor_slot'),
    )
    op.create_index('ix_checks_monitor_started', 'check_results', ['monitor_id', 'started_at', 'id'], unique=False)
    op.create_table(
        'incidents',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('monitor_id', sa.Integer(), nullable=False),
        sa.Column('first_failure_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('confirmed_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['monitor_id'], ['monitors.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_incidents_monitor_confirmed', 'incidents', ['monitor_id', 'confirmed_at'], unique=False)
    op.create_index('uq_incident_monitor_open', 'incidents', ['monitor_id'], unique=True, postgresql_where=sa.text('resolved_at IS NULL'))
    op.create_table(
        'notifications',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('incident_id', sa.Integer(), nullable=False),
        sa.Column('event_type', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.CheckConstraint("event_type IN ('outage', 'recovery')", name='notification_event_type'),
        sa.ForeignKeyConstraint(['incident_id'], ['incidents.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('incident_id', 'event_type', name='uq_notification_incident_event'),
    )
    op.create_index('ix_notifications_created', 'notifications', ['created_at', 'id'], unique=False)


def downgrade():
    op.drop_index('ix_notifications_created', table_name='notifications')
    op.drop_table('notifications')
    op.drop_index('uq_incident_monitor_open', table_name='incidents', postgresql_where=sa.text('resolved_at IS NULL'))
    op.drop_index('ix_incidents_monitor_confirmed', table_name='incidents')
    op.drop_table('incidents')
    op.drop_index('ix_checks_monitor_started', table_name='check_results')
    op.drop_table('check_results')
    op.drop_index('ix_monitors_due', table_name='monitors', postgresql_where=sa.text('enabled'))
    op.drop_table('monitors')
