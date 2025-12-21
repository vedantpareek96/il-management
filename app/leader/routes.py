from flask import Blueprint, request, jsonify, current_app
from app import db
from app.models import Person, Session, Participation, SessionMetrics, ParticipationRoleEnum, AuditLog, RoleEnum, \
    TemporarySession, TemporarySessionMetrics
from flask_login import login_required, current_user
from datetime import datetime
import uuid
import json
import logging
from . import bp

logger = logging.getLogger(__name__)

@bp.route('/sessions', methods=['POST'])
@login_required
def create_session():
    """POST /sessions - Create a new session with participants and metrics"""
    logger.info(f'Creating session - User: {current_user.username}')
    data = request.get_json()
    
    # Validate required fields
    required_fields = ['date', 'location', 'participants', 'guests_count', 'registrations_count']
    for field in required_fields:
        if field not in data:
            logger.warning(f'Missing required field in session creation: {field}')
            return jsonify({'error': f'Missing required field: {field}'}), 400
    
    # Validate registrations <= guests
    if data['registrations_count'] > data['guests_count']:
        logger.warning(f'Invalid session data: registrations ({data["registrations_count"]}) > guests ({data["guests_count"]})')
        return jsonify({'error': 'Registrations count cannot exceed guests count'}), 400
    
    if data['registrations_count'] < 0 or data['guests_count'] < 0:
        logger.warning(f'Invalid session data: negative counts')
        return jsonify({'error': 'Counts must be non-negative'}), 400
    room_captain_id = data.get('room_captain_id')
    if room_captain_id:
        SessionMetrics.validate_room_captain(uuid.UUID(room_captain_id))
    try:
        # Start transaction
        session_id = uuid.uuid4()
        
        # Create session
        session = TemporarySession(
            id=session_id,
            date=datetime.strptime(data['date'], '%Y-%m-%d').date(),
            location=data['location'],
            notes=data.get('notes'),
            created_by=current_user.id,
            created_at=datetime.utcnow()
        )
        db.session.add(session)

        
        # Create session metrics
        metrics = TemporarySessionMetrics(
            session_id=session_id,
            guests_count=data['guests_count'],
            registrations_count=data['registrations_count'],
            room_captain_id=uuid.UUID(data['room_captain_id']) if data.get('room_captain_id') else None,
            submitted_by=current_user.id,
            submitted_at=datetime.utcnow()
        )
        db.session.add(metrics)
        
        db.session.commit()
        
        # Audit log
        audit = AuditLog(
            id=uuid.uuid4(),
            actor_id=current_user.id,
            action='session_created',
            payload={
                'session_id': str(session_id),
                'date': data['date'],
                'guests_count': data['guests_count'],
                'registrations_count': data['registrations_count']
            }
        )
        db.session.add(audit)
        db.session.commit()
        
        logger.info(f'Session created successfully: {session_id} by {current_user.username}')
        return jsonify({
            'message': 'Session created successfully',
            'session_id': str(session_id)
        }), 201
        
    except ValueError as e:
        db.session.rollback()
        logger.error(f'Invalid UUID or date format in session creation: {str(e)}', exc_info=True)
        return jsonify({'error': f'Invalid UUID or date format: {str(e)}'}), 400
    except Exception as e:
        db.session.rollback()
        logger.error(f'Error creating session: {str(e)}', exc_info=True)
        return jsonify({'error': str(e)}), 500


@bp.route('/sessions/<session_id>', methods=['GET'])
@login_required
def get_session(session_id):
    """GET /sessions/<id> - Get session details"""
    logger.info(f'Fetching session: {session_id} by {current_user.username}')
    try:
        session = Session.query.get_or_404(uuid.UUID(session_id))
        
        # Get participants
        participants = []
        for participation in session.participations:
            participants.append({
                'person_id': str(participation.person_id),
                'person_name': participation.person.name,
                'role': participation.role.value
            })
        
        # Get metrics
        metrics_data = None
        if session.metrics:
            metrics_data = {
                'guests_count': session.metrics.guests_count,
                'registrations_count': session.metrics.registrations_count,
                'room_captain_id': str(session.metrics.room_captain_id) if session.metrics.room_captain_id else None,
                'submitted_by': str(session.metrics.submitted_by),
                'submitted_at': session.metrics.submitted_at.isoformat()
            }
        
        return jsonify({
            'id': str(session.id),
            'date': session.date.isoformat(),
            'location': session.location,
            'notes': session.notes,
            'created_by': str(session.created_by),
            'created_at': session.created_at.isoformat(),
            'participants': participants,
            'metrics': metrics_data
        }), 200
        
    except ValueError:
        return jsonify({'error': 'Invalid session ID format'}), 400

@bp.route('/people/leaders', methods=['GET'])
@login_required
def get_leaders():
    leaders = Person.query \
        .filter(Person.role == RoleEnum.LEADER) \
        .order_by(Person.name) \
        .all()

    return jsonify([
        {"id": str(p.id), "name": p.name}
        for p in leaders
    ])

@bp.route('/people/<person_id>/stats', methods=['GET'])
@login_required
def get_person_stats(person_id):
    """GET /people/<id>/stats?date_from=&date_to= - Get person statistics"""
    try:
        person_uuid = uuid.UUID(person_id)
        person = Person.query.get_or_404(person_uuid)
        
        # Parse date filters
        date_from = None
        date_to = None
        if request.args.get('date_from'):
            date_from = datetime.strptime(request.args.get('date_from'), '%Y-%m-%d').date()
        if request.args.get('date_to'):
            date_to = datetime.strptime(request.args.get('date_to'), '%Y-%m-%d').date()
        
        # Compute totals using service
        from app.services import compute_person_totals, get_recent_sessions_for_person
        
        totals = compute_person_totals(person_uuid, date_from, date_to)
        
        # Get recent sessions
        recent_sessions = get_recent_sessions_for_person(person_uuid, date_from, date_to, limit=10)
        sessions_list = []
        logger.info("Recent sessions fetched for person stats.")
        for sess in recent_sessions:
            logger.info(f"Processing session ID: {sess.id}")
            logger.info("Session data: " + json.dumps(sess.__dict__, default=str))
            sessions_list.append({
                'id': str(sess.id),
                'date': sess.date.isoformat(),
                'location': sess.location,
                'stats': {
                    'guests_count': sess.metrics.guests_count if sess.metrics else None,
                    'registrations_count': sess.metrics.registrations_count if sess.metrics else None,
                    'effectiveness_pct': (
                        (sess.metrics.registrations_count / sess.metrics.guests_count * 100)
                        if sess.metrics and sess.metrics.guests_count > 0 else None
                    )
                } if sess.metrics else {}
            })
        
        logger.info(f'Person stats retrieved: {person.name} (ID: {person_id})')
        return jsonify({
            'person_id': str(person.id),
            'person_name': person.name,
            'totals': totals,
            'recent_sessions': sessions_list
        }), 200
        
    except ValueError:
        logger.warning(f'Invalid person ID format: {person_id}')
        return jsonify({'error': 'Invalid person ID format'}), 400
