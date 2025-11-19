from flask import Blueprint, request, jsonify, render_template, redirect, url_for, flash, current_app
from app import db
from app.models import Person, RoleEnum, AuditLog
from app.forms import SignupForm, LoginForm
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import login_user, logout_user, login_required, current_user
import uuid
import logging
from . import bp

logger = logging.getLogger(__name__)

@bp.route('/signup', methods=['POST'])
def signup():
    """POST /signup - Create a new user account"""
    logger.info('API signup request received')
    form = SignupForm()
    
    if not form.validate():
        logger.warning(f'Signup validation failed: {form.errors}')
        return jsonify({'error': 'Validation failed', 'errors': form.errors}), 400
    
    # Check if username already exists
    existing_user = Person.query.filter_by(username=form.username.data).first()
    if existing_user:
        logger.warning(f'Signup attempt with existing username: {form.username.data}')
        return jsonify({'error': 'Username already exists'}), 400
    
    # Create new user
    try:
        person = Person(
            id=uuid.uuid4(),
            username=form.username.data,
            password_hash=generate_password_hash(form.password.data),
            name=form.name.data,
            region=form.region.data,
            role=RoleEnum[form.role.data.upper()]
        )
        print(person)
        db.session.add(person)
        db.session.commit()
        
        # Audit log
        audit = AuditLog(
            id=uuid.uuid4(),
            actor_id=person.id,
            action='user_signup',
            payload={'username': person.username, 'role': person.role.value}
        )
        db.session.add(audit)
        db.session.commit()
        
        logger.info(f'User created successfully: {person.username} (ID: {person.id})')
        return jsonify({
            'message': 'User created successfully',
            'user_id': str(person.id),
            'username': person.username
        }), 201
    except Exception as e:
        db.session.rollback()
        logger.error(f'Error creating user: {str(e)}', exc_info=True)
        return jsonify({'error': str(e)}), 500


@bp.route('/login', methods=['POST'])
def login():
    """POST /login - Authenticate user and create session"""
    form = LoginForm()
    logger.info(f'API login attempt for username: {form.username.data if form.username.data else "unknown"}')
    
    if not form.validate():
        logger.warning(f'Login validation failed: {form.errors}')
        return jsonify({'error': 'Validation failed', 'errors': form.errors}), 400
    
    person = Person.query.filter_by(username=form.username.data).first()
    
    if not person or not check_password_hash(person.password_hash, form.password.data):
        logger.warning(f'Failed login attempt for username: {form.username.data}')
        return jsonify({'error': 'Invalid username or password'}), 401
    
    login_user(person, remember=True)
    
    # Audit log
    audit = AuditLog(
        id=uuid.uuid4(),
        actor_id=person.id,
        action='user_login',
        payload={'username': person.username}
    )
    db.session.add(audit)
    db.session.commit()
    
    logger.info(f'User logged in successfully: {person.username} (ID: {person.id})')
    return jsonify({
        'message': 'Login successful',
        'user': {
            'id': str(person.id),
            'username': person.username,
            'name': person.name,
            'role': person.role.value,
            'region': person.region
        }
    }), 200


@bp.route('/me', methods=['GET'])
@login_required
def me():
    """GET /me - Get current user information"""
    logger.info(f'User info requested for: {current_user.username}')
    return jsonify({
        'id': str(current_user.id),
        'username': current_user.username,
        'name': current_user.name,
        'role': current_user.role.value,
        'region': current_user.region,
        'is_admin': current_user.is_admin
    }), 200


@bp.route('/logout', methods=['POST'])
@login_required
def logout():
    """POST /logout - Logout current user"""
    logger.info(f'User logout: {current_user.username}')
    # Audit log
    audit = AuditLog(
        id=uuid.uuid4(),
        actor_id=current_user.id,
        action='user_logout',
        payload={'username': current_user.username}
    )
    db.session.add(audit)
    db.session.commit()
    
    logout_user()
    logger.info(f'User logged out successfully: {current_user.username if hasattr(current_user, "username") else "unknown"}')
    return jsonify({'message': 'Logout successful'}), 200


@bp.route('/signup', methods=['GET'])
def signup_ui():
    """GET /signup - Signup form page"""
    logger.info('Signup page accessed')
    form = SignupForm()
    return render_template('signup.html', form=form)


@bp.route('/signup', methods=['POST'])
def signup_ui_post():
    """POST /signup - Handle signup form submission"""
    logger.info('Signup form submission received')
    form = SignupForm()
    
    if form.validate_on_submit():
        # Check if username already exists
        existing_user = Person.query.filter_by(username=form.username.data).first()
        if existing_user:
            logger.warning(f'Signup attempt with existing username: {form.username.data}')
            flash('Username already exists', 'error')
            return render_template('signup.html', form=form)
        
        # Create new user
        try:
            person = Person(
                id=uuid.uuid4(),
                username=form.username.data,
                password_hash=generate_password_hash(form.password.data),
                name=form.name.data,
                region=form.region.data,
                role=RoleEnum[form.role.data.upper()]
            )
            db.session.add(person)
            db.session.commit()
            
            # Audit log
            audit = AuditLog(
                id=uuid.uuid4(),
                actor_id=person.id,
                action='user_signup',
                payload={'username': person.username, 'role': person.role.value}
            )
            db.session.add(audit)
            db.session.commit()
            
            logger.info(f'User account created via UI: {person.username} (ID: {person.id})')
            flash('Account created successfully! Please login.', 'success')
            return redirect(url_for('auth.login_ui'))
        except Exception as e:
            db.session.rollback()
            logger.error(f'Error creating user account: {str(e)}', exc_info=True)
            flash(f'Error creating account: {str(e)}', 'error')
    
    return render_template('signup.html', form=form)


@bp.route('/login', methods=['GET'])
def login_ui():
    """GET /login - Login form page"""
    logger.info('Login page accessed')
    form = LoginForm()
    return render_template('login.html', form=form)


@bp.route('/login', methods=['POST'])
def login_ui_post():
    """POST /login - Handle login form submission"""
    logger.info(f'Login form submission for username: {form.username.data if hasattr(form, "username") else "unknown"}')
    form = LoginForm()
    
    if form.validate_on_submit():
        person = Person.query.filter_by(username=form.username.data).first()
        
        if person and check_password_hash(person.password_hash, form.password.data):
            login_user(person, remember=True)
            
            # Audit log
            audit = AuditLog(
                id=uuid.uuid4(),
                actor_id=person.id,
                action='user_login',
                payload={'username': person.username}
            )
            db.session.add(audit)
            db.session.commit()
            
            logger.info(f'User logged in via UI: {person.username} (ID: {person.id})')
            flash(f'Welcome back, {person.name}!', 'success')
            return redirect(url_for('main.dashboard'))
        else:
            logger.warning(f'Failed login attempt via UI for username: {form.username.data}')
            flash('Invalid username or password', 'error')
    
    return render_template('login.html', form=form)


@bp.route('/logout', methods=['GET'])
@login_required
def logout_ui():
    """GET /logout - Logout user and redirect"""
    username = current_user.username
    logger.info(f'User logout via UI: {username}')
    # Audit log
    audit = AuditLog(
        id=uuid.uuid4(),
        actor_id=current_user.id,
        action='user_logout',
        payload={'username': username}
    )
    db.session.add(audit)
    db.session.commit()
    
    logout_user()
    logger.info(f'User logged out successfully via UI: {username}')
    flash('You have been logged out', 'success')
    return redirect(url_for('auth.login_ui'))
