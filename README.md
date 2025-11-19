# Introduction Leader Application

Flask application for Introduction Leader management with PostgreSQL backend.

## Setup Instructions

### 1. Create Virtual Environment

```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Environment Variables

Copy `.env.example` to `.env` and configure:

```bash
cp .env.example .env
```

Export the following environment variables:

```bash
export DATABASE_URL=postgresql://username:password@localhost:5432/dbname
export SECRET_KEY=your-secret-key-here
export FLASK_APP=app
```

**Important:** Replace `username`, `password`, and `dbname` with your actual PostgreSQL credentials. The database must exist before running migrations.

### 4. Database Setup

The initial migration is already created. Run migrations to set up the database:

```bash
export DATABASE_URL=postgresql://username:password@localhost:5432/dbname
flask db upgrade
```

This will create all tables, indexes, constraints, and ENUM types.

If you need to create a new migration:

```bash
flask db migrate -m "Description of changes"
flask db upgrade
```

### 5. Run Development Server

```bash
./run.sh
```

Or manually:

```bash
export FLASK_APP=app
export FLASK_ENV=development
export DATABASE_URL=postgresql://username:password@localhost:5432/dbname
export SECRET_KEY=your-secret-key-here
flask run
```

Then open your browser to:

```
http://localhost:5000
```

The application will be available at the root URL. No separate frontend build step is required - the UI is served directly by Flask using Jinja2 templates.

## Logging

The application automatically creates log files in the `logs/` directory. Logs are written to `logs/app.log` with automatic rotation (10MB per file, 10 backup files).

Logs include:
- Application startup and shutdown
- All HTTP requests and responses
- User authentication events (login, logout, signup)
- Database operations
- Errors and exceptions with stack traces
- Business logic operations (session creation, stats computation, etc.)

Log files are automatically created when you run the application. The logs directory will be created if it doesn't exist.

## Backend API Endpoints

### Authentication
- `POST /auth/signup` - Create new user account
- `POST /auth/login` - Authenticate and login
- `GET /auth/me` - Get current user info (requires authentication)
- `POST /auth/logout` - Logout current user

### Sessions
- `POST /sessions` - Create new session with participants and metrics (requires authentication)
- `GET /sessions/<id>` - Get session details (requires authentication)

### Person Statistics
- `GET /people/<id>/stats?date_from=&date_to=` - Get person statistics (requires authentication)

### Leaderboard
- `GET /leaderboard?region=&date_from=&date_to=&metric=(registrations|guests|effectiveness)&limit=50` - Get leaderboard (requires authentication)

### People List
- `GET /people?filter=(close_to_target|not_led_in_months)&region=&limit=` - Get filtered people list (requires authentication)

### Criteria Management
- `GET /admin/criteria` - Get all criteria (requires authentication)
- `POST /admin/criteria` - Create new criteria (admin only)

### Admin Endpoints
- `GET /admin/users` - List all users (admin only)
- `GET /admin/users/<id>` - Get user details (admin only)
- `GET /admin/sessions` - List all sessions (admin only)

## Database Models

- **Person**: Users with roles (leader, staff, admin)
- **Session**: Introduction sessions
- **Participation**: Links people to sessions with roles
- **SessionMetrics**: Metrics for each session (guests, registrations)
- **Criteria**: Targets for guests, registrations, and effectiveness
- **AuditLog**: Audit trail for all POST/PUT/DELETE actions

## Security

- Passwords are hashed using werkzeug.security
- All POST endpoints require authentication
- Admin endpoints require admin role
- Database constraints enforce data integrity (e.g., registrations <= guests)
- All actions are logged to AuditLog
