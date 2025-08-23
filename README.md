<p align="center">
  <img src="https://i.imgur.com/l8gi1kL.jpeg" alt="Tracklist Logo" />
</p>

# Tracklist

![Python](https://img.shields.io/badge/python-3.9+-blue.svg)
![Docker](https://img.shields.io/badge/docker-ready-brightgreen.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-00ADD8.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)
[![MusicBrainz](https://img.shields.io/badge/powered%20by-MusicBrainz-orange.svg)](https://musicbrainz.org/)

A self-hosted music album rating application that enables precise album scoring through track-by-track ratings.

⭐ **If you find this project useful, please consider giving it a star!**

## Overview

Tracklist is a web application for rating and tracking music albums. It integrates with the MusicBrainz database to provide accurate metadata and uses a four-point track rating system to calculate album scores.

## Demo

Click below for a quick demo

[![Tracklist Demo](https://img.youtube.com/vi/jvPUX0ZAfY0/0.jpg)](https://www.youtube.com/watch?v=jvPUX0ZAfY0)


*Complete workflow: Search → Rate → Track Progress → View Stats*

### Features

**Core Functionality**
- Search and import album metadata from MusicBrainz database
- Track-by-track rating system with four-point scale
- Automatic album score calculation (0-100 scale)
- Cover art fetching and intelligent caching from Cover Art Archive
- Artist and album relationship tracking

**Collection Management**
- Advanced filtering by artist, year, rating status, and score ranges
- Multi-criteria sorting (rating, release date, artist name)
- Album comparison tool for side-by-side analysis
- Bulk operations for collection organization

**Analytics & Visualization**
- Comprehensive statistics dashboard with rating distributions
- Artist performance metrics and top-rated album tracking
- Year-based analytics and trends
- No-skip album identification
- Topsters-style collage generation for visual album grids

**User Experience**
- Dark mode support with system-aware theming
- Mobile-responsive interface
- Real-time search with debouncing
- Progress tracking for in-progress albums
- Customizable album bonus scoring (0.1-0.4 range)

### Rating System

Track ratings:
- **0.0** - Skip: Track to be avoided
- **0.33** - Filler: Tolerable but not noteworthy
- **0.67** - Good: Playlist-worthy track
- **1.0** - Standout: Exceptional track

Album scores are calculated using:
<br>
$\lfloor \left (\left (\frac{Sum of track ratings}{Total Number of Tracks} \cdot 10  \right ) + Album Bonus  \right ) \cdot 10 \rfloor$

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

![Statistics Dashboard](https://i.imgur.com/KHNwpAV.png)

## Configuration

Environment variables:

- `DATABASE_URL`: Database connection string (default: `sqlite:///./data/tracklist.db`)
- `LOG_LEVEL`: Logging level (DEBUG, INFO, WARNING, ERROR)

Additional configuration options are available in the docker-compose.yml file for cache management, scheduled tasks, and artwork processing.

## Acknowledgments

- [MusicBrainz](https://musicbrainz.org/) for music metadata
- [Cover Art Archive](https://coverartarchive.org/) for album artwork
- FastAPI framework and SQLAlchemy ORM

## License

MIT License - see LICENSE file for details.
