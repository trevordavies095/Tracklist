<p align="center">
  <img src="https://i.imgur.com/l8gi1kL.jpeg" alt="Tracklist Logo" />
</p>

# Tracklist

A self-hosted music album rating application that enables precise album scoring through track-by-track ratings.

## Overview

Tracklist is a web application for rating and tracking music albums. It integrates with the MusicBrainz database to provide accurate metadata and uses a four-point track rating system to calculate album scores.

### Features

- Search and import album data from MusicBrainz database
- Rate individual tracks on a four-point scale
- Automatic album score calculation (0-100 scale)
- Cover art fetching from Cover Art Archive
- Album collection management with filtering and sorting
- Statistical reports and insights
- Responsive web interface

### Rating System

Track ratings:
- **0.0** - Skip: Track to be avoided
- **0.33** - Filler: Tolerable but not noteworthy
- **0.67** - Good: Playlist-worthy track
- **1.0** - Standout: Exceptional track

Album scores are calculated using: `Floor((Average Track Rating × 10 + Album Bonus) × 10)`

The album bonus defaults to 0.33 and can be configured between 0.1 and 0.4.

## Installation

### Docker Compose (Recommended)

1. Create a `docker-compose.yml` file:

```yaml
version: '3.8'

services:
  tracklist:
    container_name: tracklist
    image: ghcr.io/trevordavies095/tracklist:latest
    ports:
      - "8000:8000"
    volumes:
      - tracklist_data:/app/data
      - tracklist_logs:/app/logs
      - tracklist_cache:/app/static/artwork_cache
    environment:
      - DATABASE_URL=sqlite:///./data/tracklist.db
      - LOG_LEVEL=INFO
      - DEFAULT_ALBUM_BONUS=0.33
    restart: unless-stopped

volumes:
  tracklist_data:
  tracklist_logs:
  tracklist_cache:
```

2. Start the application:
```bash
docker-compose up -d
```

3. Access the application at `http://localhost:8000`

### Local Development

1. Clone the repository:
```bash
git clone https://github.com/trevordavies095/tracklist.git
cd tracklist
```

2. Create a virtual environment and install dependencies:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

3. Initialize the database:
```bash
alembic upgrade head
```

4. Run the application:
```bash
uvicorn app.main:app --reload --port 8000
```

## Documentation

- **Web Interface**: `http://localhost:8000`
- **API Documentation**: `http://localhost:8000/docs`
- **OpenAPI Schema**: `http://localhost:8000/openapi.json`
- **ReDoc**: `http://localhost:8000/redoc`

## Screenshot

![Statistics Dashboard](https://i.imgur.com/8y1N94s.png)

## Configuration

Environment variables:

- `DATABASE_URL`: Database connection string (default: `sqlite:///./data/tracklist.db`)
- `LOG_LEVEL`: Logging level (DEBUG, INFO, WARNING, ERROR)
- `DEFAULT_ALBUM_BONUS`: Default album bonus for score calculation (0.1-0.4, default: 0.33)

Additional configuration options are available in the docker-compose.yml file for cache management, scheduled tasks, and artwork processing.

## Acknowledgments

- [MusicBrainz](https://musicbrainz.org/) for music metadata
- [Cover Art Archive](https://coverartarchive.org/) for album artwork
- FastAPI framework and SQLAlchemy ORM

## License

MIT License - see LICENSE file for details.