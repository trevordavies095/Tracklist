# Tracklist Testing Implementation Guide

This guide provides detailed technical information for implementing tests in the Tracklist project.

## Test Configuration

### pytest.ini Configuration

Located at project root, defines test discovery and behavior:

```ini
[tool:pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
asyncio_mode = strict
asyncio_default_fixture_loop_scope = function
addopts =
    --verbose
    --strict-markers
    --tb=short
markers =
    slow: marks tests as slow
    integration: marks tests as integration tests
    unit: marks tests as unit tests
    security: marks tests as security-related tests
```

### Coverage Configuration (pyproject.toml)

```toml
[tool.coverage.run]
source = ["app"]
omit = [
    "*/tests/*",
    "*/alembic/*",
    "*/__init__.py",
    "*/venv/*",
]

[tool.coverage.report]
precision = 2
show_missing = true
skip_covered = false
exclude_lines = [
    "pragma: no cover",
    "if TYPE_CHECKING:",
    # ... other exclusions
]
```

## Core Test Fixtures

### Database Session Management

The test suite uses SQLite in-memory database for isolation and speed:

```python
@pytest.fixture(scope="function")
def db_session():
    """Provides isolated database session for each test."""
    # Creates in-memory SQLite database
    # Rolls back after each test
    # Ensures test isolation
```

### Test Client Configuration

```python
@pytest.fixture(scope="function")
def client(db_session):
    """FastAPI test client with database override."""
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
```

## Testing Patterns by Component

### 1. Model Testing (test_models.py)

Tests database models, relationships, and constraints:

```python
class TestAlbumModel:
    def test_album_creation(self, db_session):
        """Test creating album with all fields."""
        album = Album(
            name="Test Album",
            artist_id=1,
            release_year=2024,
            musicbrainz_id="test-mbid",
            is_rated=False,
            rating_score=None,
            album_bonus=0.33,
            total_tracks=10
        )
        db_session.add(album)
        db_session.commit()

        assert album.id is not None
        assert album.created_at is not None
```

Key areas to test:
- Model creation with required fields
- Field validation and constraints
- Relationship cascades
- Model methods and properties
- String representations (__repr__)

### 2. Service Layer Testing (test_services/)

Tests business logic and service methods:

```python
class TestRatingService:
    def test_rate_track(self, db_session, created_album):
        """Test track rating logic."""
        service = RatingService()
        track = created_album.tracks[0]

        result = service.rate_track(track.id, 0.67, db_session)

        assert result["track"]["rating"] == 0.67
        assert result["track"]["is_rated"] is True
```

Service test considerations:
- Mock external dependencies (MusicBrainz API, etc.)
- Test business rule validation
- Verify database state changes
- Test error handling and exceptions
- Check return value structure

### 3. API Endpoint Testing (test_api/)

Tests REST API endpoints:

```python
class TestAlbumAPI:
    def test_create_album_endpoint(self, client):
        """Test POST /api/v1/albums endpoint."""
        with patch('app.routers.albums.get_rating_service') as mock:
            mock_service = Mock()
            mock_service.create_album_for_rating = AsyncMock(
                return_value={"id": 1, "title": "Album"}
            )
            mock.return_value = mock_service

            response = client.post(
                "/api/v1/albums",
                data={"musicbrainz_id": "test-id"}
            )

            assert response.status_code == 200
            assert response.json()["id"] == 1
```

API test patterns:
- Test all HTTP methods (GET, POST, PUT, DELETE)
- Verify status codes
- Check response structure
- Test query parameters and pagination
- Validate error responses
- Test form data vs JSON payloads

### 4. Async Function Testing

For async operations:

```python
@pytest.mark.asyncio
async def test_async_musicbrainz_fetch(self):
    """Test async MusicBrainz API call."""
    service = MusicBrainzService()

    with patch('httpx.AsyncClient.get') as mock_get:
        mock_get.return_value = AsyncMock(
            status_code=200,
            json=lambda: {"title": "Album"}
        )

        result = await service.get_album_details("mbid")
        assert result["title"] == "Album"
```

## Mocking Strategies

### 1. External API Mocking

```python
# Mock MusicBrainz API
with patch('app.services.musicbrainz.httpx.AsyncClient') as mock_client:
    mock_response = Mock()
    mock_response.json.return_value = {"releases": [...]}
    mock_client.return_value.get = AsyncMock(return_value=mock_response)
```

### 2. Database Mocking

```python
# Mock database session for unit tests
mock_session = Mock(spec=Session)
mock_session.query.return_value.filter.return_value.first.return_value = test_album
```

### 3. File System Mocking

```python
# Mock file operations
with patch('builtins.open', mock_open(read_data='file content')):
    result = function_that_reads_file()
```

### 4. Time/DateTime Mocking

```python
# Mock datetime for consistent tests
with patch('app.models.datetime') as mock_datetime:
    mock_datetime.now.return_value = datetime(2024, 1, 1, 12, 0, 0)
    mock_datetime.utcnow = mock_datetime.now
```

## Error Testing Patterns

### 1. Exception Testing

```python
def test_invalid_rating_raises_error(self, db_session):
    """Test that invalid rating value raises ValidationError."""
    service = RatingService()

    with pytest.raises(ServiceValidationError) as exc_info:
        service.rate_track(1, 0.5, db_session)  # 0.5 is invalid

    assert "Invalid rating value" in str(exc_info.value)
    assert exc_info.value.status_code == 400
```

### 2. API Error Responses

```python
def test_404_for_nonexistent_album(self, client):
    """Test 404 response for non-existent album."""
    response = client.get("/api/v1/albums/99999")

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()
```

### 3. Database Constraint Violations

```python
def test_unique_constraint_violation(self, db_session):
    """Test handling of unique constraint violations."""
    album1 = Album(musicbrainz_id="duplicate-id", name="Album 1")
    album2 = Album(musicbrainz_id="duplicate-id", name="Album 2")

    db_session.add(album1)
    db_session.commit()

    db_session.add(album2)
    with pytest.raises(IntegrityError):
        db_session.commit()
```

## Performance Testing

### 1. Marking Slow Tests

```python
@pytest.mark.slow
def test_large_dataset_processing(self, db_session):
    """Test processing large number of albums."""
    # Create 1000 albums
    albums = [Album(name=f"Album {i}") for i in range(1000)]
    db_session.bulk_save_objects(albums)
    db_session.commit()

    # Test performance-critical operation
    start = time.time()
    result = service.process_all_albums(db_session)
    duration = time.time() - start

    assert duration < 5.0  # Should complete in under 5 seconds
```

### 2. Load Testing Patterns

```python
def test_concurrent_requests(self, client):
    """Test handling concurrent API requests."""
    import concurrent.futures

    def make_request():
        return client.get("/api/v1/albums")

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(make_request) for _ in range(100)]
        results = [f.result() for f in futures]

    assert all(r.status_code == 200 for r in results)
```

## Test Data Management

### 1. Factory Pattern

```python
class AlbumFactory:
    @staticmethod
    def create(db_session, **kwargs):
        """Create album with default values."""
        defaults = {
            "name": "Test Album",
            "artist_id": 1,
            "release_year": 2024,
            "is_rated": False,
        }
        defaults.update(kwargs)

        album = Album(**defaults)
        db_session.add(album)
        db_session.commit()
        return album
```

### 2. Fixture Composition

```python
@pytest.fixture
def rated_album(db_session, created_album):
    """Album with all tracks rated."""
    service = RatingService()
    for track in created_album.tracks:
        service.rate_track(track.id, 1.0, db_session)
    service.submit_album_rating(created_album.id, db_session)
    return created_album
```

## Database Transaction Testing

### 1. Rollback Testing

```python
def test_transaction_rollback_on_error(self, db_session):
    """Test that transactions roll back on error."""
    album = Album(name="Test")
    db_session.add(album)

    # Force an error
    with pytest.raises(Exception):
        with db_session.begin_nested():
            album.name = None  # Violates NOT NULL
            db_session.flush()

    # Verify rollback
    db_session.rollback()
    assert db_session.query(Album).count() == 0
```

### 2. Cascade Delete Testing

```python
def test_cascade_delete(self, db_session, created_album):
    """Test that deleting album deletes tracks."""
    album_id = created_album.id
    track_ids = [t.id for t in created_album.tracks]

    db_session.delete(created_album)
    db_session.commit()

    assert db_session.query(Album).get(album_id) is None
    for track_id in track_ids:
        assert db_session.query(Track).get(track_id) is None
```

## Testing Checklist

Before submitting tests, verify:

### Code Coverage
- [ ] New code has test coverage
- [ ] Critical paths meet coverage targets
- [ ] Edge cases are tested

### Test Quality
- [ ] Tests are independent
- [ ] Tests are deterministic
- [ ] Tests use appropriate fixtures
- [ ] Mocks are properly configured
- [ ] Assertions are specific and meaningful

### Performance
- [ ] Unit tests run quickly (< 100ms)
- [ ] Slow tests are marked appropriately
- [ ] No unnecessary database operations

### Documentation
- [ ] Test names are descriptive
- [ ] Complex tests have docstrings
- [ ] New patterns are documented

## Common Testing Pitfalls

### 1. Test Interdependence
**Problem**: Tests that depend on execution order
**Solution**: Use fixtures for setup, ensure each test is isolated

### 2. Hardcoded Values
**Problem**: Tests break when constants change
**Solution**: Use configuration or fixtures for values

### 3. Over-mocking
**Problem**: Tests pass but code doesn't work
**Solution**: Use integration tests, mock only external dependencies

### 4. Missing Edge Cases
**Problem**: Tests pass but bugs occur with unusual input
**Solution**: Test boundaries, nulls, empty collections, large values

### 5. Async Confusion
**Problem**: Mixing sync and async incorrectly
**Solution**: Use proper async test decorators and AsyncMock

## Advanced Testing Topics

### 1. Parametrized Tests

```python
@pytest.mark.parametrize("rating,expected_score", [
    (0.0, 0),
    (0.33, 33),
    (0.67, 67),
    (1.0, 100),
])
def test_rating_scores(self, rating, expected_score):
    """Test different rating values."""
    result = calculate_score(rating)
    assert result == expected_score
```

### 2. Property-based Testing

```python
from hypothesis import given, strategies as st

@given(st.floats(min_value=0.0, max_value=1.0))
def test_score_bounds(self, rating):
    """Test that scores are always within bounds."""
    score = calculate_score(rating)
    assert 0 <= score <= 100
```

### 3. Snapshot Testing

```python
def test_api_response_structure(self, client, snapshot):
    """Test that API response matches snapshot."""
    response = client.get("/api/v1/albums/1")
    snapshot.assert_match(response.json())
```

## Debugging Failed Tests

### 1. Using pytest debugger
```bash
pytest --pdb  # Drop into debugger on failure
pytest --pdb-trace  # Drop into debugger at start of test
```

### 2. Viewing test output
```bash
pytest -s  # Don't capture stdout
pytest -vv  # Very verbose output
pytest --tb=long  # Long traceback format
```

### 3. Running specific scenarios
```bash
pytest -k "rating"  # Run tests matching "rating"
pytest --lf  # Run last failed tests
pytest --ff  # Run failed tests first
```

## Test Maintenance

### Refactoring Tests
1. Extract common setup to fixtures
2. Create helper functions for repeated assertions
3. Use parametrization for similar tests
4. Group related tests in classes

### Updating Tests
1. Update tests when requirements change
2. Add tests for bug fixes
3. Remove obsolete tests
4. Keep test documentation current

### Test Performance Optimization
1. Use in-memory databases
2. Mock expensive operations
3. Minimize database operations
4. Use fixture scope appropriately
5. Parallelize test execution when possible
