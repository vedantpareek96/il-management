from flask import Blueprint, request, jsonify, render_template, redirect, url_for, flash, current_app
from app import db
from app.models import Person, Session, Criteria, AuditLog, RoleEnum
from app.forms import CriteriaForm
from flask_login import login_required, current_user
from datetime import datetime
import uuid
import logging
from . import bp

logger = logging.getLogger(__name__)

def admin_required(f):
    """Decorator to require admin role"""
    from functools import wraps
    
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if not current_user.is_admin:
            return jsonify({'error': 'Admin access required'}), 403
        return f(*args, **kwargs)
    return decorated_function


@bp.route('/criteria', methods=['GET'])
@login_required
def get_criteria():
    """GET /criteria - Get all criteria (global and person-specific)"""
    logger.info(f'Criteria list requested by: {current_user.username}')
    criteria_list = Criteria.query.order_by(Criteria.person_id, Criteria.created_at.desc()).all()
    
    result = []
    for crit in criteria_list:
        result.append({
            'id': str(crit.id),
            'person_id': str(crit.person_id) if crit.person_id else None,
            'guests_target': crit.guests_target,
            'registrations_target': crit.registrations_target,
            'effectiveness_target_pct': float(crit.effectiveness_target_pct) if crit.effectiveness_target_pct else None,
            'created_at': crit.created_at.isoformat()
        })
    
    return jsonify({'criteria': result}), 200


@bp.route('/criteria', methods=['POST'])
@admin_required
def create_criteria():
    """POST /criteria - Create new criteria (admin only)"""
    logger.info(f'Creating criteria by admin: {current_user.username}')
    data = request.get_json()
    
    try:
        criteria = Criteria(
            id=uuid.uuid4(),
            person_id=uuid.UUID(data['person_id']) if data.get('person_id') else None,
            guests_target=data.get('guests_target'),
            registrations_target=data.get('registrations_target'),
            effectiveness_target_pct=data.get('effectiveness_target_pct'),
            created_at=datetime.utcnow()
        )
        db.session.add(criteria)
        db.session.commit()
        
        # Audit log
        audit = AuditLog(
            id=uuid.uuid4(),
            actor_id=current_user.id,
            action='criteria_created',
            payload={
                'criteria_id': str(criteria.id),
                'person_id': str(criteria.person_id) if criteria.person_id else None
            }
        )
        db.session.add(audit)
        db.session.commit()
        
        logger.info(f'Criteria created successfully: {criteria.id} by {current_user.username}')
        return jsonify({
            'message': 'Criteria created successfully',
            'criteria_id': str(criteria.id)
        }), 201
        
    except ValueError as e:
        db.session.rollback()
        logger.error(f'Invalid UUID format in criteria creation: {str(e)}', exc_info=True)
        return jsonify({'error': f'Invalid UUID format: {str(e)}'}), 400
    except Exception as e:
        db.session.rollback()
        logger.error(f'Error creating criteria: {str(e)}', exc_info=True)
        return jsonify({'error': str(e)}), 500


@bp.route('/users', methods=['GET'])
@admin_required
def list_users():
    """GET /users - List all users (admin only)"""
    users = Person.query.all()
    
    result = [{
        'id': str(u.id),
        'username': u.username,
        'name': u.name,
        'region': u.region,
        'role': u.role.value,
        'created_at': u.created_at.isoformat()
    } for u in users]
    
    return jsonify({'users': result}), 200


@bp.route('/users/<user_id>', methods=['GET'])
@admin_required
def get_user(user_id):
    """GET /users/<id> - Get user details (admin only)"""
    try:
        user = Person.query.get_or_404(uuid.UUID(user_id))
        return jsonify({
            'id': str(user.id),
            'username': user.username,
            'name': user.name,
            'region': user.region,
            'role': user.role.value,
            'assisting_with': user.assisting_with,
            'created_at': user.created_at.isoformat()
        }), 200
    except ValueError:
        return jsonify({'error': 'Invalid user ID format'}), 400


@bp.route('/sessions', methods=['GET'])
@admin_required
def list_sessions():
    """GET /sessions - List all sessions (admin only)"""
    sessions = Session.query.order_by(Session.date.desc()).limit(100).all()
    
    result = []
    for sess in sessions:
        result.append({
            'id': str(sess.id),
            'date': sess.date.isoformat(),
            'location': sess.location,
            'created_by': str(sess.created_by),
            'created_at': sess.created_at.isoformat()
        })
    
    return jsonify({'sessions': result}), 200


@bp.route('/criteria', methods=['GET', 'POST'])
@admin_required
def criteria_management():
    """GET /admin/criteria - Criteria management page with generic table"""
    form = CriteriaForm()
    
    # Populate person dropdown
    all_people = Person.query.all()
    form.person_id.choices = [('', 'Global (leave empty)')] + [(str(p.id), f"{p.name} ({p.region})") for p in all_people]
    
    # Get all criteria
    criteria_list = Criteria.query.order_by(Criteria.person_id, Criteria.created_at.desc()).all()
    
    # Build generic table data
    criteria_data = []
    all_keys = set()
    
    for crit in criteria_list:
        item = {
            'id': str(crit.id),
            'person_id': str(crit.person_id) if crit.person_id else None,
            'guests_target': crit.guests_target,
            'registrations_target': crit.registrations_target,
            'effectiveness_target_pct': float(crit.effectiveness_target_pct) if crit.effectiveness_target_pct else None,
            'created_at': crit.created_at.isoformat()
        }
        criteria_data.append(item)
        all_keys.update(item.keys())
    
    all_keys = sorted(list(all_keys))
    
    if form.validate_on_submit():
        try:
            criteria = Criteria(
                id=uuid.uuid4(),
                person_id=uuid.UUID(form.person_id.data) if form.person_id.data else None,
                guests_target=form.guests_target.data,
                registrations_target=form.registrations_target.data,
                effectiveness_target_pct=form.effectiveness_target_pct.data,
                created_at=datetime.utcnow()
            )
            db.session.add(criteria)
            db.session.commit()
            
            # Audit log
            audit = AuditLog(
                id=uuid.uuid4(),
                actor_id=current_user.id,
                action='criteria_created',
                payload={
                    'criteria_id': str(criteria.id),
                    'person_id': str(criteria.person_id) if criteria.person_id else None
                }
            )
            db.session.add(audit)
            db.session.commit()
            
            flash('Criteria created successfully!', 'success')
            return redirect(url_for('admin.criteria_management'))
        except ValueError as e:
            db.session.rollback()
            flash(f'Invalid UUID format: {str(e)}', 'error')
        except Exception as e:
            db.session.rollback()
            flash(f'Error: {str(e)}', 'error')
    
    return render_template('criteria.html', form=form, criteria_data=criteria_data, all_keys=all_keys)

