# Tracklist - Product Requirements Document

## Overview

Tracklist is a self-hostable web application that allows users to rate music albums using a standardized track-by-track rating system. The application transforms a proven CLI-based rating methodology into an accessible web interface while maintaining rating consistency across all users.

## Product Philosophy

- **Standardized Scale**: All users rate on the same scale to enable meaningful comparisons
- **Track-Level Granularity**: Forces engagement with complete albums rather than superficial ratings
- **Mathematical Consistency**: Objective calculation prevents rating drift over time
- **Self-Hostable**: Users maintain control over their data and can customize deployment

## Core Rating System

### Track Rating Scale
- **0**: Skip always - One of the worst songs you've ever heard
- **0.33**: Filler/tolerable - Don't enjoy but won't skip during full album playthrough
- **0.67**: Good/playlist-worthy - Like the track, would add to playlists
- **1**: Standout/love it - Album highlight, one of your favorites

### Album Score Calculation
```
Floor((Sum of track ratings / Total tracks × 10) + Album Bonus) × 10
```

### Album Bonus Configuration
- **Range**: 0.1 to 0.4 (user configurable)
- **Presets**: 
  - Track-Focused (0.1): Minimal album cohesion bonus
  - Balanced (0.25): Standard approach (proven default)
  - Album-Focused (0.4): Significant bonus for album as artistic unit

## User Interface Requirements

### Page Structure

#### Homepage
- **Recently Rated Albums**: Grid/list of recent ratings with scores and dates
- **Quick Stats**: Total albums rated, average score, recent activity
- **Search Form**: Prominent search bar for album lookup
- **Navigation**: Access to all main sections

#### Search Results Page
- **MusicBrainz Results**: List of matching albums with cover art, artist, year
- **Album Preview**: Before selection, show full album details (tracklist, metadata)
- **Confirmation Step**: User validates correct album before proceeding to rating
- **Responsive Grid**: Works well on mobile and desktop

#### Rating Page
- **Album Header**: Artist, album name, release year, genre, cover art
- **Track List**: All tracks with duration and rating interface
- **Rating Interface**: Color-coded buttons with hover descriptions (no decimal values shown to user)
  - Red (0): "Skip always"
  - Orange/Yellow (0.33): "Filler/tolerable"  
  - Light Green (0.67): "Good/playlist-worthy"
  - Dark Green (1): "Standout/love it"
- **Auto-save**: Individual track ratings saved immediately
- **Live Preview**: Running album score calculation display
- **Submit Action**: Final album score generation and save

#### Reports Page
- **Rating Distribution**: Charts showing score spreads
- **Timeline View**: Ratings over time
- **Top/Bottom Lists**: Highest and lowest rated albums
- **Export Options**: Year-end lists, CSV/JSON downloads

### Responsive Design Requirements
- **Mobile-First**: Primary design target for rating interface
- **Touch-Friendly**: Large buttons, appropriate spacing for mobile rating
- **Progressive Enhancement**: Works without JavaScript, enhanced with it
- **Fast Loading**: Minimal assets, optimized for mobile networks

## Technical Requirements

### Core Functionality
- **Self-Hostable**: Docker container deployment
- **Database**: SQLite for simplicity (single-user focused)
- **User Management**: Single-user for MVP (authentication optional)
- **Data Export**: JSON/CSV export for year-end lists and backups
- **MusicBrainz Integration**: All album/track metadata from MusicBrainz API

### Performance
- **Responsive Design**: Mobile and desktop optimized
- **Fast Loading**: Minimal dependencies, efficient queries
- **API Rate Limiting**: Respect MusicBrainz API limit of 1 call per second
- **API Caching**: Cache MusicBrainz responses to minimize external calls

### Architecture Considerations
- **Database Design**: Structure to support future multi-user expansion
- **API Layer**: Clean separation between frontend and data layer
- **Docker**: Single container with embedded SQLite database for easy deployment
- **Recommended Stack**: FastAPI + SQLite + Tailwind CSS + Alpine.js/HTMX
  - Mobile-first responsive framework
  - Minimal JavaScript complexity
  - Fast development and deployment
  - Use both Alpine.js and HTMX where appropriate for frontend interactivity

## Database Schema

### Core Tables

#### Artists Table
```sql
CREATE TABLE "artists" (
    "id" INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    "name" TEXT NOT NULL,
    "musicbrainz_id" TEXT UNIQUE,
    "created_at" TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

#### Albums Table  
```sql
CREATE TABLE "albums" (
    "id" INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    "artist_id" INTEGER NOT NULL,
    "name" TEXT NOT NULL,
    "release_year" INTEGER,
    "musicbrainz_id" TEXT UNIQUE NOT NULL,
    "cover_art_url" TEXT,
    "genre" TEXT,
    "total_tracks" INTEGER,
    "total_duration_ms" INTEGER,
    "rating_score" INTEGER,
    "album_bonus" REAL DEFAULT 0.25,
    "is_rated" BOOLEAN DEFAULT FALSE,
    "created_at" TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    "rated_at" TIMESTAMP,
    FOREIGN KEY("artist_id") REFERENCES "artists"("id")
);
```

#### Tracks Table
```sql
CREATE TABLE "tracks" (
    "id" INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    "album_id" INTEGER NOT NULL,
    "track_number" INTEGER NOT NULL,
    "name" TEXT NOT NULL,
    "duration_ms" INTEGER,
    "musicbrainz_id" TEXT,
    "track_rating" REAL,
    "created_at" TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY("album_id") REFERENCES "albums"("id") ON DELETE CASCADE
);
```

#### User Settings Table
```sql
CREATE TABLE "user_settings" (
    "id" INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    "user_id" INTEGER DEFAULT 1,
    "album_bonus" REAL DEFAULT 0.25,
    "theme" TEXT DEFAULT 'light',
    "created_at" TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### Key Design Decisions

**Auto-save Track Ratings**: Individual track ratings are saved immediately when selected to prevent data loss if user session ends unexpectedly.

**Rating State Management**: Albums have `is_rated` flag to distinguish between draft ratings (in progress) and completed ratings (final score calculated).

**MusicBrainz Integration**: Required MusicBrainz IDs for albums and optional for artists/tracks ensure metadata consistency and enable re-rating without data loss.

**Future Multi-user Support**: Schema designed with user isolation in mind while maintaining single-user simplicity for MVP.

**Performance Indexes**: Strategic indexes on frequently queried fields (MusicBrainz IDs, rating scores, dates).

### Data Flow
1. Album search → MusicBrainz API → Create album/artist/tracks with `is_rated = FALSE`
2. User rates tracks → Auto-save individual `track_rating` values  
3. User submits → Calculate final `rating_score`, set `is_rated = TRUE`, record `rated_at`
4. Re-rating → Update existing track ratings, recalculate album score

## API Endpoints

### Base Configuration
- **Base URL**: `/api/v1`
- **Authentication**: None required for single-user MVP
- **Response Format**: JSON
- **Error Handling**: Standardized error objects with codes and messages

### Album Search & Management

#### Search Albums via MusicBrainz
```http
GET /api/v1/search/albums?q={query}&limit={limit}&offset={offset}
```
Returns paginated MusicBrainz search results with metadata and rating status.

#### Get Album Details for Rating
```http
GET /api/v1/albums/{musicbrainz_id}/details
```
Fetches complete album information including track listing from MusicBrainz.

#### Create Album for Rating
```http
POST /api/v1/albums
```
Creates local album record from MusicBrainz ID, populating all metadata and tracks.

### Track Rating (Auto-save)

#### Update Track Rating
```http
PUT /api/v1/tracks/{track_id}/rating
```
Saves individual track rating immediately when user clicks rating button.

#### Get Album Rating Progress
```http
GET /api/v1/albums/{album_id}/progress
```
Returns current rating status, completion percentage, and projected score.

### Album Rating Submission

#### Submit Final Album Rating
```http
POST /api/v1/albums/{album_id}/submit
```
Calculates final album score using rating formula and marks album as completed.

### User Data & Reports

#### Get User's Rated Albums
```http
GET /api/v1/albums?sort={sort}&order={order}&limit={limit}&offset={offset}&filter={filter}
```
Paginated list of albums with sorting and filtering options for homepage and reports.

#### Get Album Rating Details
```http
GET /api/v1/albums/{album_id}
```
Complete album rating information including individual track scores and statistics.

#### Get Dashboard Stats
```http
GET /api/v1/stats/dashboard
```
Homepage statistics including recent activity, total counts, and rating distribution.

#### Get Detailed Reports
```http
GET /api/v1/reports/{type}?year={year}
```
Specialized endpoints for rating analytics and year-end list generation.

### Configuration & Export

#### User Settings Management
```http
GET/PUT /api/v1/settings
```
Manage album bonus settings and user preferences.

#### Data Export
```http
GET /api/v1/export/albums?format={format}&year={year}
```
Export rated albums in JSON or CSV format for external use.

### Key API Features

**Auto-save Architecture**: Individual track ratings saved immediately to prevent data loss, separate from final album submission.

**State Management**: Clear distinction between draft and completed ratings with progress tracking.

**MusicBrainz Integration**: Standardized metadata sourcing with local caching via MusicBrainz IDs.

**Flexible Querying**: Support for sorting, filtering, pagination across all list endpoints.

**Error Handling**: Consistent error response format with specific error codes for common scenarios.

## User Stories

### Primary User Flow
1. User lands on homepage, sees recent activity and search form
2. User searches for album via search form
3. System queries MusicBrainz and displays results on search page
4. User selects album and confirms details before proceeding
5. System creates rating page with official metadata and track list
6. User rates tracks (auto-saved individually, no album score yet)
7. User clicks "Submit Rating" to generate final album score
8. User redirected to homepage or album list with new rating visible

### Secondary Flows
- Update existing album ratings
- Configure album bonus preference
- Import data from existing CLI tool
- Export data for backup or migration

## Success Metrics

### User Engagement
- Albums rated per user per month
- Completion rate (started vs. finished ratings)
- Re-rating frequency (engagement over time)

### System Health
- Response time for rating interface
- Data consistency (no lost ratings)
- Uptime and reliability

## Non-Requirements (V1)

- Multi-user authentication and user isolation
- Social features (sharing, comparing with friends)
- Advanced analytics/charts
- Mobile app (web PWA sufficient)
- Real-time collaboration
- Advanced search/recommendation engine
- Musium CLI tool data migration (post-MVP script)

## Technical Constraints

- Must maintain mathematical compatibility with existing CLI tool
- Rating scale cannot be user-customizable (standardization requirement)
- Album bonus must be constrained to prevent score inflation
- Self-hosting should not require complex infrastructure

## Future Considerations

- Multi-user support with authentication and data isolation
- Musium CLI tool data migration utility
- Analytics dashboard (rating distributions, trends over time)
- Advanced filtering (genre, decade, etc.)
- API for third-party integrations
- Collaborative rating features
- PWA offline capabilities