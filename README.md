# Tracklist

A personal music album rating system built with FastAPI and SQLite. Rate and track your favorite albums with precision using a 4 point track rating system.

## Features

- **Album Search**: Find albums from the MusicBrainz database
- **Track by Track Rating**: Rate each song with a 4 point scale (Skip, Filler, Good, Standout)
- **Album Scoring**: Automatic score calculation out of 100 based on track ratings
- **Album Management**: View, organize, and manage your rated albums
- **Cover Art**: Automatic cover art fetching from Cover Art Archive
- **MusicBrainz Integration**: Full integration with MusicBrainz for accurate metadata
- **Responsive Design**: Works on desktop and mobile devices

## Screenshots

### Homepage - Dashboard Overview
![Tracklist Homepage](https://i.imgur.com/NWvM7By.png)
*View your recent activity, statistics, and quick access to search and albums*

### My Albums - Collection Management
![My Albums Page](https://i.imgur.com/99XLvdo.png)
*Browse, filter, and manage your rated album collection with color-coded scores*

### Rate Albums - Easy Rating System
![Album Rating](https://i.imgur.com/Fg3mz8a.png)
*Quickly rate albums using keyboard shortcuts*

### Album Results - Detailed Rating Breakdown
![Album Rating Results](https://i.imgur.com/M1Yxe87.png)
*See your final album score with track-by-track rating breakdown and statistics*

### Artist Albums - Browse by Artist
![Artist Albums View](https://i.imgur.com/5AyhlEf.png)
*View all rated albums from a specific artist with scores and completion status*

### Statistics - Track Your Progress
![Statistics Page](https://i.imgur.com/H17DPjZ.png)
*Comprehensive statistics showing your rating patterns, top artists, and album insights*

## Statistics & Insights

Track your music rating journey with detailed statistics:

- **Overview Cards**: Total albums, completion rate, and average scores
- **Most Rated Artist**: Discover which artist dominates your collection
- **Distribution Charts**: Visual breakdown of your track and album ratings
- **Top & Bottom Albums**: Quick access to your favorites and least favorites
- **No-Skip Albums**: Special recognition for perfect albums with no weak tracks

## Rating System

- **Skip (0.0)**: Never want to hear this track
- **Filler (0.33)**: Tolerable, won't skip but not noteworthy
- **Good (0.67)**: Playlist-worthy track
- **Standout (1.0)**: Album highlight, exceptional track

**Score Formula**: `Floor((Average Rating × 10) + Album Bonus) × 10`

## Quick Start

1. Create a `docker-compose.yml` file:

```yaml
version: '3.8'

services:
  tracklist:
    container_name: tracklist
    image: ghcr.io/trevordavies095/tracklist:latest
    ports:
      - "8321:8000"  # Maps port 8321 on host to 8000 in container
    volumes:
      # Named volume for data persistence
      - tracklist_data:/app/data
      # Optional: Mount existing database from host
      # - /path/to/your/data:/app/data
    environment:
      - TRACKLIST_DB_PATH=/app/data/tracklist.db
      - ENVIRONMENT=production
      - LOG_LEVEL=ERROR  # Options: DEBUG, INFO, WARNING, ERROR
    restart: unless-stopped

volumes:
  tracklist_data:  # Docker-managed volume for database
```

2. Start the application:
   ```bash
   docker-compose up -d
   ```

3. Access the application at `http://localhost:8321`

To update to the latest version:
```bash
docker-compose pull
docker-compose up -d
```

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
