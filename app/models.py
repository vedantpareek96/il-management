from app import db
from sqlalchemy import Column, String, Integer, Date, Text, Numeric, CheckConstraint, UniqueConstraint, ForeignKey, \
    Enum as SQLEnum, Enum
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY
from sqlalchemy.sql import func
from datetime import datetime
import uuid
import enum


class RoleEnum(enum.Enum):
    LEADER = 'leader'
    STAFF = 'staff'
    ADMIN = 'admin'


class ParticipationRoleEnum(enum.Enum):
    LEADER = 'LEADER'
    REGISTRATION_EXPERT = 'REGISTRATION_EXPERT'
    ROOM_CAPTAIN = 'ROOM_CAPTAIN'


class Person(db.Model):
    __tablename__ = 'person'
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username = Column(String(80), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    name = Column(String(200), nullable=False)
    region = Column(String(100), nullable=False, index=True)
    role = db.Column(SQLEnum(RoleEnum), nullable=False, default=RoleEnum.LEADER)
    assisting_with = Column(JSONB, nullable=True)
    created_at = Column(db.DateTime, nullable=False, default=datetime.utcnow)

    def get_id(self):
        return str(self.id)

    @property
    def is_active(self):
        return True

    @property
    def is_authenticated(self):
        return True

    @property
    def is_anonymous(self):
        return False

    @property
    def is_admin(self):
        return self.role == RoleEnum.ADMIN

    def __repr__(self):
        return f'<Person {self.username}>'


class Session(db.Model):
    __tablename__ = 'session'
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    date = Column(Date, nullable=False, index=True)
    location = Column(Text, nullable=False)
    notes = Column(Text, nullable=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey('person.id'), nullable=False)
    created_at = Column(db.DateTime, nullable=False, default=datetime.utcnow)
    
    creator = db.relationship('Person', foreign_keys=[created_by], backref='created_sessions')
    
    def __repr__(self):
        return f'<Session {self.id} {self.date}>'


class Participation(db.Model):
    __tablename__ = 'participation'
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey('session.id'), nullable=False)
    person_id = Column(UUID(as_uuid=True), ForeignKey('person.id'), nullable=False, index=True)
    role = Column(SQLEnum(ParticipationRoleEnum), nullable=False)
    
    session = db.relationship('Session', backref='participations')
    person = db.relationship('Person', backref='participations')
    
    __table_args__ = (
        UniqueConstraint('session_id', 'person_id', 'role', name='uq_participation_session_person_role'),
        db.Index('ix_participation_person_role', 'person_id', 'role'),
    )
    
    def __repr__(self):
        return f'<Participation {self.person_id} {self.role}>'


class SessionMetrics(db.Model):
    __tablename__ = 'session_metrics'
    
    session_id = Column(UUID(as_uuid=True), ForeignKey('session.id'), primary_key=True)
    guests_count = Column(Integer, nullable=False, index=True)
    registrations_count = Column(Integer, nullable=False, index=True)
    room_captain_id = Column(UUID(as_uuid=True), ForeignKey('person.id'), nullable=True)
    submitted_by = Column(UUID(as_uuid=True), ForeignKey('person.id'), nullable=False)
    submitted_at = Column(db.DateTime, nullable=False, default=datetime.utcnow)
    
    session = db.relationship('Session', backref=db.backref('metrics', uselist=False))
    room_captain = db.relationship('Person', foreign_keys=[room_captain_id], backref='room_captain_sessions')
    submitter = db.relationship('Person', foreign_keys=[submitted_by], backref='submitted_metrics')
    
    __table_args__ = (
        CheckConstraint('guests_count >= 0', name='ck_guests_count_non_negative'),
        CheckConstraint('registrations_count >= 0', name='ck_registrations_count_non_negative'),
        CheckConstraint('registrations_count <= guests_count', name='ck_registrations_leq_guests'),
    )
    
    def __repr__(self):
        return f'<SessionMetrics {self.session_id}>'

    @staticmethod
    def validate_room_captain(person_id):
        person = Person.query.get(person_id)
        if not person or person.role != RoleEnum.LEADER:
            raise ValueError("Room Captain must be a leader.")


class Criteria(db.Model):
    __tablename__ = 'criteria'
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    person_id = Column(UUID(as_uuid=True), ForeignKey('person.id'), nullable=True)
    guests_target = Column(Integer, nullable=True)
    registrations_target = Column(Integer, nullable=True)
    effectiveness_target_pct = Column(Numeric(5, 2), nullable=True)
    created_at = Column(db.DateTime, nullable=False, default=datetime.utcnow)
    
    person = db.relationship('Person', backref='criteria')
    
    def __repr__(self):
        return f'<Criteria {self.id}>'


class AuditLog(db.Model):
    __tablename__ = 'audit_log'
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    actor_id = Column(UUID(as_uuid=True), ForeignKey('person.id'), nullable=True)
    action = Column(Text, nullable=False)
    payload = Column(JSONB, nullable=True)
    created_at = Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)
    
    actor = db.relationship('Person', backref='audit_logs')
    
    def __repr__(self):
        return f'<AuditLog {self.action} {self.created_at}>'

class TemporarySession(db.Model):
    __tablename__ = 'temporary_session'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_data = Column(JSONB, nullable=False)
    submitted_by = Column(UUID(as_uuid=True), ForeignKey('person.id'), nullable=False)
    status = Column(String, default='pending')  # status can be 'pending', 'approved', 'rejected'
    submitted_at = Column(db.DateTime, default=datetime.utcnow)

class TemporarySessionMetrics(db.Model):
    __tablename__ = 'temporary_session_metrics'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey('session.id'))
    guests_count = Column(Integer, nullable=False)
    registrations_count = Column(Integer, nullable=False)
    status = Column(String, default='pending')  # similar status handling
