from flask import Flask, request, g
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
import os
import uuid
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime

db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()


def setup_logging(app):
    """Configure logging for the application"""
    if not app.debug:
        # Create logs directory if it doesn't exist
        log_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'logs')
        os.makedirs(log_dir, exist_ok=True)
        
        # Log file path
        log_file = os.path.join(log_dir, 'app.log')
        
        # Configure file handler with rotation
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=10240000,  # 10MB
            backupCount=10
        )
        file_handler.setFormatter(logging.Formatter(
            '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
        ))
        file_handler.setLevel(logging.INFO)
        
        # Configure console handler
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(logging.Formatter(
            '%(asctime)s %(levelname)s: %(message)s'
        ))
        console_handler.setLevel(logging.INFO)
        
        # Add handlers to app logger
        app.logger.addHandler(file_handler)
        app.logger.addHandler(console_handler)
        app.logger.setLevel(logging.INFO)
        
        # Also configure SQLAlchemy logger
        logging.getLogger('sqlalchemy.engine').setLevel(logging.WARNING)
        
        app.logger.info('Application startup - Logging configured')


def create_app():
    app = Flask(__name__)
    
    # Load configuration from environment variables
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'test')
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'postgresql://postgres:postgres@localhost:5432/il')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    # Setup logging
    setup_logging(app)
    app.logger.info('Creating Flask application')
    
    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login_ui'
    app.logger.info('Extensions initialized')
    
    # Configure Flask-Login
    @login_manager.user_loader
    def load_user(user_id):
        from app.models import Person
        app.logger.debug(f'Loading user: {user_id}')
        return Person.query.get(uuid.UUID(user_id))
    
    # Register blueprints
    from app.auth import bp as auth_bp
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.logger.info('Registered auth blueprint')
    
    from app.main import bp as main_bp
    app.register_blueprint(main_bp, url_prefix='')
    app.logger.info('Registered main blueprint')
    
    from app.leader import bp as leader_bp
    app.register_blueprint(leader_bp, url_prefix='/leader')
    app.logger.info('Registered leader blueprint')
    
    from app.staff import bp as staff_bp
    app.register_blueprint(staff_bp, url_prefix='/staff')
    app.logger.info('Registered staff blueprint')
    
    from app.admin import bp as admin_bp
    app.register_blueprint(admin_bp, url_prefix='/admin')
    app.logger.info('Registered admin blueprint')
    
    # Request logging middleware
    @app.before_request
    def before_request():
        app.logger.info(f'Request: {request.method} {request.path} from {request.remote_addr}')
        if request.method in ['POST', 'PUT', 'DELETE']:
            from flask_login import current_user
            from app.models import AuditLog
            
            g.audit_actor_id = current_user.id if current_user.is_authenticated else None
            g.audit_action = f'{request.method.lower()}_{request.endpoint}'
            g.audit_payload = request.get_json(silent=True) or {}
            app.logger.info(f'Audit: {g.audit_action} by user {g.audit_actor_id}')
    
    @app.after_request
    def after_request(response):
        app.logger.info(f'Response: {response.status_code} for {request.method} {request.path}')
        if request.method in ['POST', 'PUT', 'DELETE'] and hasattr(g, 'audit_actor_id'):
            from app.models import AuditLog
            
            try:
                audit = AuditLog(
                    id=uuid.uuid4(),
                    actor_id=g.audit_actor_id,
                    action=g.audit_action,
                    payload=g.audit_payload,
                    created_at=datetime.utcnow()
                )
                db.session.add(audit)
                db.session.commit()
                app.logger.info(f'Audit log created: {g.audit_action}')
            except Exception as e:
                # Don't fail the request if audit logging fails
                app.logger.error(f'Failed to create audit log: {str(e)}', exc_info=True)
                db.session.rollback()
        
        return response
    
    @app.errorhandler(404)
    def not_found(error):
        app.logger.warning(f'404 Not Found: {request.path}')
        return {'error': 'Not Found'}, 404
    
    @app.errorhandler(500)
    def internal_error(error):
        app.logger.error(f'500 Internal Server Error: {str(error)}', exc_info=True)
        return {'error': 'Internal Server Error'}, 500
    
    app.logger.info('Flask application created successfully')
    return app
