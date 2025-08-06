# Tracklist

A personal music album rating system built with FastAPI and SQLite. Discover, rate, and track your favorite albums with precision using a 4-point track rating system.

## Features

- **Album Search**: Find albums from the MusicBrainz database
- **Track-by-Track Rating**: Rate each song with a 4-point scale (Skip, Filler, Good, Standout)
- **Album Scoring**: Automatic score calculation out of 100 based on track ratings
- **Album Management**: View, organize, and manage your rated albums
- **Cover Art**: Automatic cover art fetching from Cover Art Archive
- **MusicBrainz Integration**: Full integration with MusicBrainz for accurate metadata
- **Responsive Design**: Works on desktop and mobile devices

## Screenshots

### Homepage - Dashboard Overview
![Tracklist Homepage](https://i.imgur.com/ebkdXMC.png)
*View your recent activity, statistics, and quick access to search and albums*

### My Albums - Collection Management
![My Albums Page](https://i.imgur.com/RoQHmbL.png)
*Browse, filter, and manage your rated album collection with color-coded scores*

### Album Results - Detailed Rating Breakdown
![Album Rating Results](https://i.imgur.com/Bbtv30S.png)
*See your final album score with track-by-track rating breakdown and statistics*

### Artist Albums - Browse by Artist
![Artist Albums View](https://i.imgur.com/U9EXubd.png)
*View all rated albums from a specific artist with scores and completion status*

## Rating System

- **Skip (0.0)**: Never want to hear this track
- **Filler (0.33)**: Tolerable, won't skip but not noteworthy
- **Good (0.67)**: Playlist-worthy track
- **Standout (1.0)**: Album highlight, exceptional track

**Score Formula**: `Floor((Average Rating × 10) + Album Bonus) × 10`

## Quick Start

### Using Docker (Recommended)

1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/tracklist.git
   cd tracklist
   ```

2. Copy and configure environment variables:
   ```bash
   cp .env.example .env
   # Edit .env with your preferences
   ```

3. Run with Docker Compose:
   ```bash
   docker-compose up -d
   ```

4. Access the application at `http://localhost:8000`

### Local Development

1. **Prerequisites**:
   - Python 3.9+
   - pip

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure environment**:
   ```bash
   cp .env.example .env
   # Edit .env with your database path and preferences
   ```

4. **Run the application**:
   ```bash
   python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   ```

## Configuration

Key configuration options in `.env`:

- `TRACKLIST_DB_PATH`: Database file location
- `MUSICBRAINZ_USER_AGENT`: Your app identifier for MusicBrainz API
- `LOG_LEVEL`: Logging verbosity
- `SECRET_KEY`: Session security key

See `.env.example` for full configuration options.

## Project Structure

```
tracklist/
├── app/                    # Application code
│   ├── routers/           # API routes
│   ├── services/          # External service integrations
│   ├── models.py          # Database models
│   ├── rating_service.py  # Core rating logic
│   └── main.py           # FastAPI application
├── templates/             # HTML templates
├── static/               # CSS and JavaScript
├── tests/                # Test suite
├── docs/                 # Documentation
├── scripts/              # Utility scripts
└── requirements.txt      # Python dependencies
```

## API

The application provides both a web interface and REST API:

- `GET /api/v1/albums` - List albums
- `POST /api/v1/albums` - Create album for rating
- `PUT /api/v1/albums/{id}/tracks/{track_id}/rate` - Rate a track
- `POST /api/v1/albums/{id}/submit` - Submit final album rating

## Development

### Running Tests

```bash
pytest
```

### Code Quality

The project uses:
- **FastAPI** for the web framework
- **SQLAlchemy** for database ORM
- **Alembic** for database migrations
- **pytest** for testing
- **Tailwind CSS** for styling

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments

- [MusicBrainz](https://musicbrainz.org/) for music metadata
- [Cover Art Archive](https://coverartarchive.org/) for album artwork
- FastAPI and SQLAlchemy communities