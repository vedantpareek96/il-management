
from app.models import Person, Session, Participation, SessionMetrics, Criteria, ParticipationRoleEnum, RoleEnum
from app.services import compute_person_totals, compute_effectiveness, compute_normalized_distance
from sqlalchemy import func, desc, or_
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify
from app import db
from app.models import TemporarySession,AuditLog
from flask_login import login_required, current_user
import uuid
import logging


bp = Blueprint('staff', __name__)
logger = logging.getLogger(__name__)


@bp.route('/inbox', methods=['GET'])
@login_required
def inbox():
    """GET /staff/inbox - Fetch statistics awaiting approval"""
    logger.info(f"Fetching inbox for staff: {current_user.username}")
    statistics = TemporarySession.query.filter_by(status='pending').all()

    # Prepare the response structure
    response = []
    for stat in statistics:
        response.append({
            'id': str(stat.id),
            'session_data': stat.session_data,
            'submitted_by': str(stat.submitted_by),
            'submitted_at': stat.submitted_at.isoformat(),
            'status': stat.status
        })

    logger.info(f"Found {len(statistics)} statistics awaiting approval.")
    return jsonify(response), 200


@bp.route('/approve/<id>', methods=['POST'])
@login_required
def approve(id):
    """POST /staff/approve/<id> - Approve a statistic and move it to the main session table"""
    logger.info(f"Approving statistic ID: {id} by {current_user.username}")
    statistic = TemporarySession.query.get_or_404(id)

    try:
        # Logic to create the main session entry from the temporary one
        # Assuming you have a function or logic that handles transforming
        # the temporary statistic into the main session record.

        # Move it to the main session table here (pseudo-code)
        # main_session = Session(...)
        # db.session.add(main_session)

        # Mark as approved
        statistic.status = 'approved'
        db.session.commit()

        # Audit log
        audit = AuditLog(
            id=uuid.uuid4(),
            actor_id=current_user.id,
            action='approve_statistic',
            payload={'statistic_id': id}
        )
        db.session.add(audit)
        db.session.commit()

        logger.info(f"Statistic ID: {id} approved successfully.")
        return jsonify({'message': 'Statistic approved successfully'}), 200
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error approving statistic ID: {id}: {str(e)}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@bp.route('/reject/<id>', methods=['POST'])
@login_required
def reject(id):
    """POST /staff/reject/<id> - Reject a statistic and update its status"""
    logger.info(f"Rejecting statistic ID: {id} by {current_user.username}")
    statistic = TemporarySession.query.get_or_404(id)

    try:
        # Mark the statistic as rejected
        statistic.status = 'rejected'
        db.session.commit()

        # Audit log
        audit = AuditLog(
            id=uuid.uuid4(),
            actor_id=current_user.id,
            action='reject_statistic',
            payload={'statistic_id': id}
        )
        db.session.add(audit)
        db.session.commit()

        logger.info(f"Statistic ID: {id} rejected successfully.")
        return jsonify({'message': 'Statistic rejected successfully'}), 200
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error rejecting statistic ID: {id}: {str(e)}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@bp.route('/leaderboard', methods=['GET'])
@login_required
def leaderboard():
    """GET /leaderboard?region=&date_from=&date_to=&metric=(registrations|guests|effectiveness)&limit=50"""
    logger.info(f'Leaderboard requested by: {current_user.username}')
    # Parse query parameters
    region = request.args.get('region')
    date_from = None
    date_to = None
    if request.args.get('date_from'):
        date_from = datetime.strptime(request.args.get('date_from'), '%Y-%m-%d').date()
    if request.args.get('date_to'):
        date_to = datetime.strptime(request.args.get('date_to'), '%Y-%m-%d').date()
    
    metric = request.args.get('metric', 'registrations')  # default: registrations
    limit = int(request.args.get('limit', 50))
    
    # Build base query
    query = db.session.query(
        Person.id,
        Person.name,
        Person.region,
        func.sum(SessionMetrics.guests_count).label('total_guests'),
        func.sum(SessionMetrics.registrations_count).label('total_registrations')
    ).join(
        Participation, Person.id == Participation.person_id
    ).join(
        Session, Participation.session_id == Session.id
    ).join(
        SessionMetrics, Session.id == SessionMetrics.session_id
    ).filter(
        Participation.role == ParticipationRoleEnum.LEADER
    )
    
    # Apply filters
    if region:
        query = query.filter(Person.region == region)
    if date_from:
        query = query.filter(Session.date >= date_from)
    if date_to:
        query = query.filter(Session.date <= date_to)
    
    # Group by person
    query = query.group_by(Person.id, Person.name, Person.region)
    
    # Order by metric
    if metric == 'registrations':
        query = query.order_by(desc('total_registrations'))
    elif metric == 'guests':
        query = query.order_by(desc('total_guests'))
    elif metric == 'effectiveness':
        # Calculate effectiveness and order by it
        query = query.having(func.sum(SessionMetrics.guests_count) > 0)
        # We'll calculate effectiveness in Python for simplicity
        results = query.limit(limit * 2).all()  # Get more to filter
        leaderboard_data = []
        for row in results:
            effectiveness = compute_effectiveness(row.total_guests, row.total_registrations)
            leaderboard_data.append({
                'person_id': str(row.id),
                'name': row.name,
                'region': row.region,
                'total_guests': row.total_guests or 0,
                'total_registrations': row.total_registrations or 0,
                'effectiveness_pct': float(effectiveness)
            })
        leaderboard_data.sort(key=lambda x: x['effectiveness_pct'], reverse=True)
        return jsonify({'leaderboard': leaderboard_data[:limit]}), 200
    else:
        return jsonify({'error': 'Invalid metric. Use: registrations, guests, or effectiveness'}), 400
    
    # Execute query and format results
    results = query.limit(limit).all()
    leaderboard_data = []
    for row in results:
        effectiveness = compute_effectiveness(row.total_guests, row.total_registrations)
        leaderboard_data.append({
            'person_id': str(row.id),
            'name': row.name,
            'region': row.region,
            'total_guests': row.total_guests or 0,
            'total_registrations': row.total_registrations or 0,
            'effectiveness_pct': float(effectiveness)
        })
    
    logger.info(f'Leaderboard returned {len(leaderboard_data)} entries')
    return jsonify({'leaderboard_data': leaderboard_data}), 200


@bp.route('/people', methods=['GET'])
@login_required
def get_people():
    """GET /people?filter=(close_to_target|not_led_in_months)&region=&limit= - Get filtered people list"""
    filter_type = request.args.get('filter')
    region = request.args.get('region')
    limit = int(request.args.get('limit', 50))
    
    query = Person.query.filter(Person.role == RoleEnum.LEADER)
    
    if region:
        query = query.filter(Person.region == region)
    
    if filter_type == 'close_to_target':
        # Get all people with criteria
        people = query.all()
        people_with_distance = []
        
        for person in people:
            # Get global criteria or person-specific criteria
            criteria = Criteria.query.filter(
                or_(Criteria.person_id == person.id, Criteria.person_id.is_(None))
            ).order_by(
                Criteria.person_id.desc()  # Prefer person-specific over global
            ).first()
            
            if criteria:
                # Compute person totals (all time)
                totals = compute_person_totals(person.id)
                distance = compute_normalized_distance(totals, criteria)
                
                if distance is not None:
                    people_with_distance.append({
                        'person': person,
                        'distance': distance,
                        'totals': totals
                    })
        
        # Sort by distance (closest to target first)
        people_with_distance.sort(key=lambda x: x['distance'])
        
        result = []
        for item in people_with_distance[:limit]:
            result.append({
                'person_id': str(item['person'].id),
                'name': item['person'].name,
                'region': item['person'].region,
                'distance_to_target': item['distance'],
                'totals': item['totals']
            })
        
        return jsonify({'people': result}), 200
        
    elif filter_type == 'not_led_in_months':
        # Find people who haven't led a session in the last N months
        months = int(request.args.get('months', 3))
        cutoff_date = datetime.utcnow().date() - timedelta(days=months * 30)
        
        # Get all leaders
        all_leaders = query.all()
        
        # Find those without recent leadership participations
        inactive_leaders = []
        for leader in all_leaders:
            recent_session = db.session.query(Session).join(
                Participation, Session.id == Participation.session_id
            ).filter(
                Participation.person_id == leader.id,
                Participation.role == ParticipationRoleEnum.LEADER,
                Session.date >= cutoff_date
            ).first()
            
            if not recent_session:
                inactive_leaders.append({
                    'person_id': str(leader.id),
                    'name': leader.name,
                    'region': leader.region
                })
        
        return jsonify({'people': inactive_leaders[:limit]}), 200
    
    else:
        # Return all leaders (no filter)
        people = query.limit(limit).all()
        result = [{
            'person_id': str(p.id),
            'name': p.name,
            'region': p.region
        } for p in people]
        
        return jsonify({'people': result}), 200
