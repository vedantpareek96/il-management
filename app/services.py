from app import db
from app.models import Person, Session, Participation, SessionMetrics, Criteria, ParticipationRoleEnum
from sqlalchemy import func, and_, or_
from datetime import datetime, date
from decimal import Decimal
import logging

logger = logging.getLogger(__name__)


def compute_person_totals(person_id, date_from=None, date_to=None):
    """
    Compute total statistics for a person within a date range.
    Returns dict with: total_guests, total_registrations, effectiveness_pct, sessions_led_count
    """
    logger.debug(f'Computing person totals for: {person_id}, date_from: {date_from}, date_to: {date_to}')
    query = db.session.query(
        func.sum(SessionMetrics.guests_count).label('total_guests'),
        func.sum(SessionMetrics.registrations_count).label('total_registrations'),
        func.count(Session.id.distinct()).label('sessions_led_count')
    ).join(
        Participation, Session.id == Participation.session_id
    ).join(
        SessionMetrics, Session.id == SessionMetrics.session_id
    ).filter(
        Participation.person_id == person_id,
        Participation.role == ParticipationRoleEnum.LEADER
    )
    
    if date_from:
        query = query.filter(Session.date >= date_from)
    if date_to:
        query = query.filter(Session.date <= date_to)
    
    result = query.first()
    
    total_guests = result.total_guests or 0
    total_registrations = result.total_registrations or 0
    sessions_led_count = result.sessions_led_count or 0
    
    effectiveness_pct = compute_effectiveness(total_guests, total_registrations)
    
    logger.debug(f'Person totals computed: guests={total_guests}, registrations={total_registrations}, effectiveness={effectiveness_pct}, sessions={sessions_led_count}')
    return {
        'total_guests': total_guests,
        'total_registrations': total_registrations,
        'effectiveness_pct': effectiveness_pct,
        'sessions_led_count': sessions_led_count
    }


def compute_effectiveness(total_guests, total_registrations):
    """
    Compute effectiveness percentage: (registrations / guests) * 100
    Returns 0 if guests is 0.
    """
    if total_guests == 0:
        return Decimal('0.00')
    return (Decimal(total_registrations) / Decimal(total_guests) * 100).quantize(Decimal('0.01'))


def compute_normalized_distance(person_totals, criteria_row):
    """
    Compute normalized distance between person's actual stats and criteria targets.
    Returns a normalized distance value (lower is better/closer to target).
    """
    if not criteria_row:
        return None
    
    distance = Decimal('0.00')
    weights = []
    
    # Guests target
    if criteria_row.guests_target is not None:
        actual = person_totals.get('total_guests', 0)
        target = criteria_row.guests_target
        if target > 0:
            diff = abs(actual - target) / target
            distance += diff
            weights.append(1)
    
    # Registrations target
    if criteria_row.registrations_target is not None:
        actual = person_totals.get('total_registrations', 0)
        target = criteria_row.registrations_target
        if target > 0:
            diff = abs(actual - target) / target
            distance += diff
            weights.append(1)
    
    # Effectiveness target
    if criteria_row.effectiveness_target_pct is not None:
        actual = person_totals.get('effectiveness_pct', Decimal('0.00'))
        target = Decimal(str(criteria_row.effectiveness_target_pct))
        if target > 0:
            diff = abs(actual - target) / target
            distance += diff
            weights.append(1)
    
    if len(weights) == 0:
        return None
    
    # Normalize by number of criteria
    normalized = distance / len(weights)
    return float(normalized)


def get_recent_sessions_for_person(person_id, date_from=None, date_to=None, limit=10):
    """
    Get recent sessions where person was a leader.
    """
    logger.info(f'Fetching recent sessions for person: {person_id}, limit: {limit}')
    query = db.session.query(Session).join(
        Participation, Session.id == Participation.session_id
    ).filter(
        Participation.person_id == person_id,
        Participation.role == ParticipationRoleEnum.LEADER
    ).order_by(Session.date.desc())
    
    if date_from:
        query = query.filter(Session.date >= date_from)
    if date_to:
        query = query.filter(Session.date <= date_to)
    logger.info(f'Executing query to fetch recent sessions for person: {query}')
    sessions = query.limit(limit).all()
    logger.info(f'Found {sessions} recent sessions for person: {person_id}')
    return sessions
