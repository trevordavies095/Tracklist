# Tracklist Project Structure

## Overview
Tracklist is a FastAPI-based web application for rating music albums track-by-track. It uses SQLAlchemy for database management and integrates with MusicBrainz for album metadata.

## Directory Structure

```
tracklist/
├── app/                    # Main application code
│   ├── routers/           # API endpoints and web routes
│   │   ├── albums.py      # Album management endpoints
│   │   ├── reports.py     # Statistics and reporting
│   │   ├── search.py      # MusicBrainz search integration
│   │   ├── settings.py    # User settings management
│   │   └── templates.py   # HTML template routes
│   ├── services/          # Business logic and services
│   │   ├── artwork_*.py  # Artwork caching system
│   │   ├── collage_service.py     # Album collage generation
│   │   ├── comparison_service.py  # Album comparison logic
│   │   ├── export_service.py      # Database export
│   │   ├── import_service.py      # Database import
│   │   └── scheduled_tasks.py     # Background task management
│   ├── main.py           # FastAPI application setup
│   ├── models.py         # SQLAlchemy database models
│   ├── database.py       # Database configuration
│   ├── exceptions.py     # Custom exception classes
│   └── *.py              # Other core modules
├── templates/            # Jinja2 HTML templates
│   ├── album/           # Album-specific templates
│   ├── albums/          # Album listing templates
│   └── components/      # Reusable template components
├── static/              # Static assets
│   ├── css/            # Stylesheets
│   ├── js/             # JavaScript files
│   └── artwork_cache/  # Cached album artwork
├── alembic/            # Database migrations
├── data/               # SQLite database storage
├── logs/               # Application logs
└── requirements.txt    # Python dependencies
```

## Key Components

### API Architecture
- **FastAPI Framework**: Modern async web framework with automatic API documentation
- **RESTful Endpoints**: Located in `app/routers/`, organized by feature
- **Service Layer**: Business logic separated in `app/services/`

### Database
- **SQLAlchemy ORM**: Database abstraction layer
- **Alembic Migrations**: Database schema versioning
- **SQLite Default**: Lightweight database (configurable for PostgreSQL/MySQL)

### Frontend
- **Jinja2 Templates**: Server-side rendering
- **HTMX Integration**: Dynamic UI updates without full page reloads
- **Alpine.js**: Lightweight JavaScript framework for interactivity
- **Tailwind CSS**: Utility-first CSS framework

### External Integrations
- **MusicBrainz API**: Album metadata and track listings
- **Cover Art Archive**: Album artwork fetching

### Background Services
- **Artwork Caching**: Automatic download and optimization of album covers
- **Scheduled Tasks**: Periodic cleanup and maintenance
- **Rate Limiting**: API request throttling for external services

## Configuration

### Environment Variables
- `DATABASE_URL`: Database connection string
- `LOG_LEVEL`: Logging verbosity (DEBUG, INFO, WARNING, ERROR)
- `AUTO_MIGRATE_ARTWORK`: Enable automatic artwork caching
- `CACHE_RETENTION_DAYS`: How long to keep cached images

### Docker Support
- `Dockerfile`: Container image definition
- `docker-compose.yml`: Multi-container orchestration
- `entrypoint.sh`: Container initialization script

## Development

### Setup
1. Create virtual environment: `python -m venv venv`
2. Install dependencies: `pip install -r requirements.txt`
3. Run migrations: `alembic upgrade head`
4. Start server: `uvicorn app.main:app --reload`

### API Documentation
- Interactive Swagger UI: Visit `/docs`
- ReDoc alternative: Visit `/redoc`
- OpenAPI schema: `/openapi.json`

### Code Quality
- Formatting: `black app/`
- Linting: `flake8 app/`
- Type checking: `mypy app/`