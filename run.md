# Tracklist - Running Instructions

## Phase 1: Foundation & Database Layer

### Prerequisites

- Python 3.11 or higher
- Docker and Docker Compose (optional, for containerized deployment)

### Local Development Setup

#### 1. Create Virtual Environment

```bash
# Create virtual environment
python3 -m venv venv

# Activate virtual environment
# On macOS/Linux:
source venv/bin/activate
# On Windows:
venv\Scripts\activate
```

#### 2. Install Dependencies

```bash
# Ensure pip is available in the virtual environment
python -m ensurepip --default-pip

# Install dependencies
python -m pip install -r requirements.txt

# Alternative if the above doesn't work:
# python -m pip install --upgrade pip
# python -m pip install -r requirements.txt
```

#### 3. Run the Application

```bash
# Method 1: Using uvicorn directly
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Method 2: Using Python module
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

The application will be available at:
- **Main Application**: http://localhost:8000
- **API Documentation**: http://localhost:8000/docs
- **Alternative Docs**: http://localhost:8000/redoc
- **Health Check**: http://localhost:8000/health

#### 4. Database Initialization

The database is automatically created and initialized when the application starts. The SQLite database file will be created as `tracklist.db` in the project root.

### Docker Deployment

#### 1. Build and Run with Docker Compose

```bash
# Build and start the application
docker-compose up --build

# Run in background
docker-compose up -d --build

# View logs
docker-compose logs -f

# Stop the application
docker-compose down
```

#### 2. Manual Docker Build

```bash
# Build the image
docker build -t tracklist .

# Run the container
docker run -p 8000:8000 \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/logs:/app/logs \
  -e DATABASE_URL=sqlite:///./data/tracklist.db \
  -e LOG_LEVEL=INFO \
  tracklist
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `sqlite:///./tracklist.db` | Database connection URL |
| `LOG_LEVEL` | `INFO` | Logging level (DEBUG, INFO, WARNING, ERROR) |
| `ENABLE_FILE_LOGGING` | `false` | Enable logging to file |
| `LOG_FILE` | `logs/tracklist.log` | Log file path (when file logging enabled) |

### Testing Phase 1

#### 1. Structure Validation

Run the built-in validation script to check Phase 1 implementation:

```bash
python3 validate_phase1.py
```

This validates:
- ✅ Application structure and syntax
- ✅ Test suite structure
- ✅ Configuration files
- ✅ Docker configuration
- ✅ Database schema models
- ✅ Alembic migration setup

#### 2. Running Full Test Suite

**Note**: The full test suite requires dependencies to be installed. If you encounter dependency issues, use the structure validation above.

```bash
# Install test dependencies (if not already installed)
python -m pip install pytest pytest-asyncio pytest-cov httpx

# Run all tests with coverage
pytest tests/ -v --cov=app --cov-report=html --cov-report=term-missing

# Run specific test files
pytest tests/test_models.py -v
pytest tests/test_database.py -v
pytest tests/test_main.py -v

# Run tests without coverage (faster)
pytest tests/ -v
```

#### 3. Test Coverage Report

After running tests with coverage, view the HTML report:

```bash
# Coverage report will be in htmlcov/index.html
open htmlcov/index.html  # macOS
xdg-open htmlcov/index.html  # Linux
```

### Database Management

#### 1. Database Migrations (Future Use)

```bash
# Initialize Alembic (already done)
alembic init alembic

# Create new migration
alembic revision --autogenerate -m "Description of changes"

# Apply migrations
alembic upgrade head

# View migration history
alembic history

# Downgrade to previous version
alembic downgrade -1
```

#### 2. Database Reset

```bash
# Remove database file to reset
rm tracklist.db

# Restart application to recreate database
```

### API Endpoints (Phase 1)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/` | Welcome message |
| `GET` | `/health` | Health check |
| `GET` | `/docs` | Interactive API documentation |
| `GET` | `/redoc` | Alternative API documentation |

### Troubleshooting

#### Common Issues

1. **Python 3.13 Compatibility Issues**
   ```bash
   # If you get pydantic-core build errors with Python 3.13, try:
   
   # Option 1: Install with no binary packages (slower but more compatible)
   python -m pip install --no-binary=pydantic-core -r requirements.txt
   
   # Option 2: Use Python 3.11 or 3.12 instead
   pyenv install 3.12.0  # if using pyenv
   python3.12 -m venv venv
   
   # Option 3: Install core dependencies individually
   python -m pip install fastapi uvicorn sqlalchemy alembic
   python -m pip install --no-binary=pydantic pydantic
   python -m pip install pytest pytest-asyncio pytest-cov httpx
   ```

2. **SQLAlchemy Import Errors**
   ```bash
   # If you get "cannot import name 'Real' from 'sqlalchemy'" error:
   # This has been fixed in the codebase (Real -> REAL)
   # Make sure you have the latest version of the models.py file
   
   # If the issue persists, try downgrading SQLAlchemy:
   python -m pip install "sqlalchemy>=2.0.0,<2.1.0"
   ```

3. **Port Already in Use**
   ```bash
   # Find process using port 8000
   lsof -i :8000
   # Kill the process or use different port
   uvicorn app.main:app --port 8001
   ```

4. **Permission Denied (Docker)**
   ```bash
   # Make sure Docker daemon is running
   sudo systemctl start docker  # Linux
   # or restart Docker Desktop
   ```

5. **Database Locked**
   ```bash
   # Stop all running instances
   # Delete database file and restart
   rm tracklist.db
   ```

6. **Import Errors**
   ```bash
   # Make sure you're in the project root directory
   # and virtual environment is activated
   pwd  # Should show the Tracklist directory
   which python  # Should show venv/bin/python
   ```

7. **Test Failures**
   ```bash
   # If tests fail due to database issues, try:
   rm -f tracklist.db  # Remove any existing database
   pytest tests/ -v   # Run tests again
   
   # If logging tests fail, it may be due to handler conflicts:
   pytest tests/test_logging.py::TestLoggingConfig::test_setup_logging_basic -v -s
   
   # Run tests individually if there are conflicts:
   pytest tests/test_models.py -v
   pytest tests/test_database.py -v
   pytest tests/test_main.py -v
   ```

### Development Workflow

1. **Start Development Server**
   ```bash
   source venv/bin/activate
   uvicorn app.main:app --reload
   ```

2. **Make Changes**
   - Edit files in `app/` directory
   - Server automatically reloads with `--reload` flag

3. **Test Changes**
   ```bash
   python3 validate_phase1.py
   curl http://localhost:8000/health
   ```

4. **Run Full Tests** (when dependencies available)
   ```bash
   pytest tests/ -v
   ```

### Logs and Monitoring

#### 1. Application Logs

```bash
# View logs in real-time (Docker)
docker-compose logs -f tracklist

# View log file (when file logging enabled)
tail -f logs/tracklist.log
```

#### 2. Health Monitoring

```bash
# Check application health
curl http://localhost:8000/health

# Expected response:
# {"status":"healthy","service":"tracklist"}
```

### Next Steps

Phase 1 provides the foundation for:
- **Phase 2**: MusicBrainz Integration & Search
- **Phase 3**: Core Rating System Backend
- **Phase 4**: User Interface & Frontend

The database schema, error handling, and application structure are ready to support these upcoming features.