"""Initial migration

Revision ID: 001_initial
Revises:
Create Date: 2024-01-01 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '001_initial'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ---------------------------------------------------------
    # ENUMS (robust, never-fail version)
    # ---------------------------------------------------------

    # Role enum
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE roleenum AS ENUM ('LEADER','STAFF','ADMIN');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)

    # Participation role enum
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE participationroleenum AS ENUM 
                ('LEADER','REGISTRATION_EXPERT','ROOM_CAPTAIN');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)

    role_enum = postgresql.ENUM(
        'LEADER', 'STAFF', 'ADMIN',
        name='roleenum',
        create_type=False
    )

    participation_role_enum = postgresql.ENUM(
        'LEADER', 'REGISTRATION_EXPERT', 'ROOM_CAPTAIN',
        name='participationroleenum',
        create_type=False
    )

    # ---------------------------------------------------------
    # person table
    # ---------------------------------------------------------
    op.create_table(
        'person',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('username', sa.String(80), nullable=False),
        sa.Column('password_hash', sa.String(255), nullable=False),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('region', sa.String(100), nullable=False),
        sa.Column('role', role_enum, nullable=False, server_default='LEADER'),
        sa.Column('assisting_with', postgresql.JSONB(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False,
                  server_default=sa.text('CURRENT_TIMESTAMP'))
    )
    op.create_index('ix_person_username', 'person', ['username'], unique=True)
    op.create_index('ix_person_region', 'person', ['region'])

    # ---------------------------------------------------------
    # session table
    # ---------------------------------------------------------
    op.create_table(
        'session',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('location', sa.Text(), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False,
                  server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['created_by'], ['person.id'])
    )
    op.create_index('ix_session_date', 'session', ['date'])

    # ---------------------------------------------------------
    # participation table
    # ---------------------------------------------------------
    op.create_table(
        'participation',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('session_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('person_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('role', participation_role_enum, nullable=False),
        sa.ForeignKeyConstraint(['session_id'], ['session.id']),
        sa.ForeignKeyConstraint(['person_id'], ['person.id']),
        sa.UniqueConstraint('session_id', 'person_id', 'role',
                            name='uq_participation_session_person_role')
    )
    op.create_index('ix_participation_person_id', 'participation', ['person_id'])
    op.create_index('ix_participation_person_role', 'participation', ['person_id', 'role'])

    # ---------------------------------------------------------
    # session_metrics table
    # ---------------------------------------------------------
    op.create_table(
        'session_metrics',
        sa.Column('session_id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('guests_count', sa.Integer(), nullable=False),
        sa.Column('registrations_count', sa.Integer(), nullable=False),
        sa.Column('room_captain_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('submitted_by', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('submitted_at', sa.DateTime(), nullable=False,
                  server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['session_id'], ['session.id']),
        sa.ForeignKeyConstraint(['room_captain_id'], ['person.id']),
        sa.ForeignKeyConstraint(['submitted_by'], ['person.id']),
        sa.CheckConstraint('guests_count >= 0', name='ck_guests_count_non_negative'),
        sa.CheckConstraint('registrations_count >= 0', name='ck_registrations_count_non_negative'),
        sa.CheckConstraint('registrations_count <= guests_count',
                           name='ck_registrations_leq_guests')
    )
    op.create_index('ix_session_metrics_guests_count', 'session_metrics', ['guests_count'])
    op.create_index('ix_session_metrics_registrations_count', 'session_metrics',
                    ['registrations_count'])

    # ---------------------------------------------------------
    # criteria table
    # ---------------------------------------------------------
    op.create_table(
        'criteria',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('person_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('guests_target', sa.Integer(), nullable=True),
        sa.Column('registrations_target', sa.Integer(), nullable=True),
        sa.Column('effectiveness_target_pct', sa.Numeric(5, 2), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False,
                  server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['person_id'], ['person.id'])
    )

    # ---------------------------------------------------------
    # audit_log table
    # ---------------------------------------------------------
    op.create_table(
        'audit_log',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('actor_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('action', sa.Text(), nullable=False),
        sa.Column('payload', postgresql.JSONB(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False,
                  server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['actor_id'], ['person.id'])
    )
    op.create_index('ix_audit_log_created_at', 'audit_log', ['created_at'])

    op.create_table(
        'temporary_session',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=sa.text('gen_random_uuid()')),
        sa.Column('session_data', postgresql.JSONB, nullable=False),
        sa.Column('submitted_by', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('status', sa.String(), server_default='pending'),
        sa.Column('submitted_at', sa.DateTime(), server_default=sa.func.now())
    )

    # Create TemporarySessionMetrics table
    op.create_table(
        'temporary_session_metrics',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=sa.text('gen_random_uuid()')),
        sa.Column('session_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('session.id'), nullable=False),
        sa.Column('guests_count', sa.Integer(), nullable=False),
        sa.Column('registrations_count', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(), server_default='pending')
    )

def downgrade() -> None:
    op.drop_index('ix_audit_log_created_at', table_name='audit_log')
    op.drop_table('audit_log')
    op.drop_table('criteria')
    op.drop_index('ix_session_metrics_registrations_count', table_name='session_metrics')
    op.drop_index('ix_session_metrics_guests_count', table_name='session_metrics')
    op.drop_table('session_metrics')
    op.drop_index('ix_participation_person_role', table_name='participation')
    op.drop_index('ix_participation_person_id', table_name='participation')
    op.drop_table('participation')
    op.drop_index('ix_session_date', table_name='session')
    op.drop_table('session')
    op.drop_index('ix_person_region', table_name='person')
    op.drop_index('ix_person_username', table_name='person')
    op.drop_table('person')
    op.drop_table('temporary_session_metrics')
    op.drop_table('temporary_session')

    op.execute('DROP TYPE IF EXISTS participationroleenum')
    op.execute('DROP TYPE IF EXISTS roleenum')

