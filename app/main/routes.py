from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from app import db
from app.models import Person, Session, Participation, SessionMetrics, ParticipationRoleEnum, RoleEnum, TemporarySession
from app.forms import RegisterStatisticForm, StaffStatsFilterForm, LeaderboardFilterForm
from app.services import compute_person_totals, get_recent_sessions_for_person, compute_effectiveness
from app.staff.routes import leaderboard as api_leaderboard
from flask_login import login_required, current_user
from datetime import datetime, date
import uuid
import logging
from . import bp

logger = logging.getLogger(__name__)

@bp.route('/')
def index():
    return redirect(url_for('main.dashboard'))


@bp.route('/dashboard')
@login_required
def dashboard():
    """Dashboard with role-based buttons"""
    logger.info(f'Dashboard accessed by: {current_user.username} (role: {current_user.role.value})')
    return render_template('dashboard.html')


@bp.route('/register-statistic', methods=['GET', 'POST'])
@login_required
def register_statistic():
    """Register statistic form page"""
    logger.info(f'Register statistic page accessed by: {current_user.username}')
    form = RegisterStatisticForm()
    
    # Populate participants and room captain dropdowns
    all_people = Person.query.filter(Person.role.in_([RoleEnum.LEADER, RoleEnum.STAFF])).all()
    form.participants.choices = [(str(p.id), f"{p.name} ({p.region})") for p in all_people]
    form.room_captain_id.choices = [('', 'None')] + [(str(p.id), f"{p.name} ({p.region})") for p in all_people]
    
    # Pre-select current user as participant
    if request.method == 'GET':
        form.participants.data = [str(current_user.id)]
    
    if form.validate_on_submit():
        # Validate registrations <= guests
        if form.registrations_count.data > form.guests_count.data:
            flash('Registrations count cannot exceed guests count', 'error')
            return render_template('register_statistic.html', form=form)
        
        try:
            # Create session
            session_id = uuid.uuid4()
            session = Session(
                id=session_id,
                date=form.date.data,
                location=form.location.data,
                notes=form.notes.data or None,
                created_by=current_user.id,
                created_at=datetime.utcnow()
            )
            db.session.add(session)
            
            # Create participation rows
            for person_id_str in form.participants.data:
                person_id = uuid.UUID(person_id_str)
                # Current user is always a leader
                role = ParticipationRoleEnum.LEADER if person_id == current_user.id else ParticipationRoleEnum.REGISTRATION_EXPERT
                participation = Participation(
                    id=uuid.uuid4(),
                    session_id=session_id,
                    person_id=person_id,
                    role=role
                )
                db.session.add(participation)
            
            # Create session metrics
            room_captain_id = uuid.UUID(form.room_captain_id.data) if form.room_captain_id.data else None
            metrics = SessionMetrics(
                session_id=session_id,
                guests_count=form.guests_count.data,
                registrations_count=form.registrations_count.data,
                room_captain_id=room_captain_id,
                submitted_by=current_user.id,
                submitted_at=datetime.utcnow()
            )
            db.session.add(metrics)
            db.session.commit()
            
            logger.info(f'Session registered via UI: {session_id} by {current_user.username}')
            flash('Session registered successfully!', 'success')
            return redirect(url_for('main.dashboard'))
        except Exception as e:
            db.session.rollback()
            logger.error(f'Error creating session via UI: {str(e)}', exc_info=True)
            flash(f'Error creating session: {str(e)}', 'error')
    
    return render_template('register_statistic.html', form=form)


@bp.route('/my-stats')
@login_required
def my_stats():
    """My stats page for leaders"""
    logger.info(f'My stats page accessed by: {current_user.username}')
    if current_user.role.value != 'leader':
        logger.warning(f'Non-leader attempted to access my-stats: {current_user.username} (role: {current_user.role.value})')
        flash('This page is only available for leaders.', 'error')
        return redirect(url_for('main.dashboard'))
    
    # Get date filters
    date_from = None
    date_to = None
    if request.args.get('date_from'):
        try:
            date_from = datetime.strptime(request.args.get('date_from'), '%Y-%m-%d').date()
        except:
            pass
    if request.args.get('date_to'):
        try:
            date_to = datetime.strptime(request.args.get('date_to'), '%Y-%m-%d').date()
        except:
            pass
    
    # Compute stats using services
    try:
        totals = compute_person_totals(current_user.id, date_from, date_to)
        recent_sessions = get_recent_sessions_for_person(current_user.id, date_from, date_to, limit=10)
        
        sessions_list = []
        for sess in recent_sessions:
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
        
        stats = {
            'totals': totals,
            'recent_sessions': sessions_list
        }
    except Exception as e:
        flash(f'Error: {str(e)}', 'error')
        stats = {'totals': {'total_guests': 0, 'total_registrations': 0, 'effectiveness_pct': 0, 'sessions_led_count': 0}, 'recent_sessions': []}
    
    return render_template('my_stats.html', stats=stats)


@bp.route('/staff-stats', methods=['GET'])
@login_required
def staff_stats():
    """Staff cumulative stats page"""
    logger.info(f'Staff stats page accessed by: {current_user.username}')
    if current_user.role.value not in ['staff', 'admin']:
        logger.warning(f'Unauthorized access to staff-stats: {current_user.username} (role: {current_user.role.value})')
        flash('This page is only available for staff and admins.', 'error')
        return redirect(url_for('main.dashboard'))
    
    filter_form = StaffStatsFilterForm()
    
    # Populate region dropdown
    regions = db.session.query(Person.region).distinct().all()
    filter_form.region.choices = [('', 'All Regions')] + [(r[0], r[0]) for r in regions]
    
    # Set form values from query params
    if request.args.get('region'):
        filter_form.region.data = request.args.get('region')
    if request.args.get('date_from'):
        try:
            filter_form.date_from.data = datetime.strptime(request.args.get('date_from'), '%Y-%m-%d').date()
        except:
            pass
    if request.args.get('date_to'):
        try:
            filter_form.date_to.data = datetime.strptime(request.args.get('date_to'), '%Y-%m-%d').date()
        except:
            pass
    
    # Build query params for leaderboard API
    # Create a mock request context with the right args
    from flask import has_request_context
    import types
    
    # Store original request args
    original_get = request.args.get
    
    # Create a custom args object
    class CustomArgs:
        def __init__(self, params):
            self._params = params
        
        def get(self, key, default=None):
            return self._params.get(key, default)
    
    custom_args = CustomArgs({})
    if filter_form.region.data:
        custom_args._params['region'] = filter_form.region.data
    if filter_form.date_from.data:
        custom_args._params['date_from'] = filter_form.date_from.data.isoformat()
    if filter_form.date_to.data:
        custom_args._params['date_to'] = filter_form.date_to.data.isoformat()
    submitted_statistics = TemporarySession.query.filter_by(status='pending').all()

    # Temporarily replace request.args
    original_args_obj = request.args
    request.args = custom_args
    
    try:
        response = api_leaderboard()
        logger.info(f'Api Leader Board Response: {response[0].get_json()}')
        if isinstance(response, tuple):
            flask_response, status = response

            data = flask_response.get_json() or {}

            if status >= 400:
                flash(data.get('error', 'Error fetching data'), 'error')
                leaderboard_data = []
            else:
                leaderboard_data = data.get('leaderboard_data', [])
        else:
            data = response.get_json() if hasattr(response, 'get_json') else {}
            leaderboard_data = data.get('leaderboard_data', [])
        # else:
        #     leaderboard_data = response.get('leaderboard', []) if isinstance(response, dict) else []
    except Exception as e:
        flash(f'Error: {str(e)}', 'error')
        leaderboard_data = []
    finally:
        # Restore original args
        request.args = original_args_obj
    
    return render_template('staff_stats.html', filter_form=filter_form, leaderboard_data=leaderboard_data, submitted_statistics = submitted_statistics)


@bp.route('/leaderboard', methods=['GET'])
@login_required
def leaderboard():
    """Leaderboard page with sortable table"""
    filter_form = LeaderboardFilterForm()
    
    # Populate region dropdown
    regions = db.session.query(Person.region).distinct().all()
    filter_form.region.choices = [('', 'All Regions')] + [(r[0], r[0]) for r in regions]
    
    # Set form values from query params
    if request.args.get('region'):
        filter_form.region.data = request.args.get('region')
    if request.args.get('date_from'):
        try:
            filter_form.date_from.data = datetime.strptime(request.args.get('date_from'), '%Y-%m-%d').date()
        except:
            pass
    if request.args.get('date_to'):
        try:
            filter_form.date_to.data = datetime.strptime(request.args.get('date_to'), '%Y-%m-%d').date()
        except:
            pass
    if request.args.get('metric'):
        filter_form.metric.data = request.args.get('metric')
    
    # Build query params
    # Create a custom args object
    class CustomArgs:
        def __init__(self, params):
            self._params = params
        
        def get(self, key, default=None):
            return self._params.get(key, default)
    
    custom_args = CustomArgs({})
    if filter_form.region.data:
        custom_args._params['region'] = filter_form.region.data
    if filter_form.date_from.data:
        custom_args._params['date_from'] = filter_form.date_from.data.isoformat()
    if filter_form.date_to.data:
        custom_args._params['date_to'] = filter_form.date_to.data.isoformat()
    if filter_form.metric.data:
        custom_args._params['metric'] = filter_form.metric.data
    custom_args._params['limit'] = 50
    
    # Temporarily replace request.args
    original_args_obj = request.args
    request.args = custom_args
    
    try:
        response = api_leaderboard()
        if isinstance(response, tuple):
            flask_response, status = response

            data = flask_response.get_json() or {}

            if status >= 400:
                flash(data.get('error', 'Error fetching data'), 'error')
                leaderboard_data = []
            else:
                leaderboard_data = data.get('leaderboard_data', [])
        else:
            data = response.get_json() if hasattr(response, 'get_json') else {}
            leaderboard_data = data.get('leaderboard_data', [])
    except Exception as e:
        flash(f'Error: {str(e)}', 'error')
        leaderboard_data = []
    finally:
        # Restore original args
        request.args = original_args_obj
    
    return render_template('leaderboard.html', filter_form=filter_form, leaderboard_data=leaderboard_data)
