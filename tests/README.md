# Tracklist Testing Documentation

## Overview

This document provides comprehensive guidance for writing, running, and maintaining tests for the Tracklist application. The test suite uses pytest as the testing framework with coverage reporting via coverage.py.

## Table of Contents

- [Test Structure](#test-structure)
- [Running Tests](#running-tests)
- [Writing Tests](#writing-tests)
- [Test Fixtures](#test-fixtures)
- [Coverage Requirements](#coverage-requirements)
- [Best Practices](#best-practices)
- [Troubleshooting](#troubleshooting)

## Test Structure

```
tests/
├── __init__.py
├── conftest.py                     # Shared fixtures and configuration
├── test_api/                       # API endpoint tests
│   ├── __init__.py
│   ├── test_albums.py             # Album API endpoints
│   └── test_health.py             # Health check endpoints
├── test_services/                  # Service layer tests
│   ├── __init__.py
│   ├── test_rating_service.py    # Core rating service tests
│   └── test_rating_service_comprehensive.py  # Extended coverage tests
├── test_security/                  # Security-related tests
│   ├── __init__.py
│   └── test_auth_system.py       # Authentication system tests
├── test_models.py                  # Database model tests
├── test_database.py               # Database operation tests
├── test_app_initialization.py    # Application startup tests
├── test_async_support.py          # Async functionality tests
├── test_basic.py                  # Basic sanity tests
└── test_auth_system.py            # Authentication system tests
```

## Running Tests

### Basic Test Execution

```bash
# Run all tests
./venv/bin/python -m pytest

# Run with verbose output
./venv/bin/python -m pytest -v

# Run specific test file
./venv/bin/python -m pytest tests/test_models.py

# Run specific test class
./venv/bin/python -m pytest tests/test_services/test_rating_service.py::TestRatingCalculation

# Run specific test method
./venv/bin/python -m pytest tests/test_services/test_rating_service.py::TestRatingCalculation::test_calculate_perfect_album_score
```

### Test Markers

Tests are organized using pytest markers defined in `pytest.ini`:

```bash
# Run only unit tests
./venv/bin/python -m pytest -m unit

# Run only integration tests
./venv/bin/python -m pytest -m integration

# Skip slow tests
./venv/bin/python -m pytest -m "not slow"

# Run security tests
./venv/bin/python -m pytest -m security
```

### Coverage Testing

```bash
# Run with coverage report
./venv/bin/python -m pytest --cov=app --cov-report=term-missing

# Generate HTML coverage report
./venv/bin/python -m pytest --cov=app --cov-report=html

# Run coverage check script
./venv/bin/python scripts/check_coverage.py

# Check coverage for specific modules
./venv/bin/python -m pytest --cov=app.rating_service --cov=app.models
```

## Writing Tests

### Test File Organization

Each test file should follow this structure:

```python
"""
Module description explaining what is being tested.
"""

import pytest
from unittest.mock import Mock, patch, AsyncMock
# Other imports

class TestFeatureName:
    """Test class grouping related tests."""
    
    @pytest.mark.unit  # or integration, slow, security
    def test_specific_behavior(self, fixture_name):
        """Test description explaining the scenario."""
        # Arrange
        expected_value = "something"
        
        # Act
        result = function_under_test()
        
        # Assert
        assert result == expected_value
```

### Testing Patterns

#### 1. Unit Tests

Unit tests should test individual functions or methods in isolation:

```python
@pytest.mark.unit
def test_calculate_album_score(self):
    """Test album score calculation with various ratings."""
    calculator = RatingCalculator()
    ratings = [1.0, 0.67, 0.33]
    
    score = calculator.calculate_album_score(ratings, album_bonus=0.33)
    
    assert score == 67  # Expected calculation result
```

#### 2. Integration Tests

Integration tests verify interactions between components:

```python
@pytest.mark.integration
def test_create_and_rate_album(self, db_session, client):
    """Test complete album creation and rating workflow."""
    # Create album via API
    response = client.post("/api/v1/albums", data={"musicbrainz_id": "test-id"})
    assert response.status_code == 200
    
    album_id = response.json()["id"]
    
    # Rate tracks
    for track_id in response.json()["tracks"]:
        response = client.put(f"/api/v1/tracks/{track_id}/rating", json={"rating": 1.0})
        assert response.status_code == 200
```

#### 3. Async Tests

For testing async functions:

```python
@pytest.mark.asyncio
async def test_async_operation(self):
    """Test asynchronous service operations."""
    service = AsyncService()
    
    result = await service.fetch_data()
    
    assert result is not None
```

#### 4. Mocking External Dependencies

```python
def test_with_external_service(self):
    """Test function that calls external API."""
    with patch('app.services.external_api') as mock_api:
        mock_api.fetch_data.return_value = {"status": "success"}
        
        result = function_using_api()
        
        assert result["status"] == "success"
        mock_api.fetch_data.assert_called_once()
```

### Testing Database Operations

```python
def test_database_operation(self, db_session):
    """Test database CRUD operations."""
    # Create test data
    album = Album(name="Test Album", artist_id=1)
    db_session.add(album)
    db_session.commit()
    
    # Test retrieval
    retrieved = db_session.query(Album).filter_by(name="Test Album").first()
    assert retrieved is not None
    assert retrieved.name == "Test Album"
```

### Testing API Endpoints

```python
def test_api_endpoint(self, client, created_album):
    """Test API endpoint behavior."""
    response = client.get(f"/api/v1/albums/{created_album.id}")
    
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == created_album.id
    assert "title" in data
```

## Test Fixtures

Fixtures provide reusable test data and setup. Key fixtures are defined in `conftest.py`:

### Database Fixtures

- `db_engine`: Creates test database engine
- `db_session`: Provides isolated database session for each test
- `client`: FastAPI test client with database override

### Data Fixtures

- `created_artist`: Creates a test artist
- `created_album`: Creates a test album with tracks
- `sample_albums`: Creates multiple albums for testing
- `mock_musicbrainz_data`: Provides sample MusicBrainz API response

### Usage Example

```python
def test_with_fixtures(self, db_session, created_album):
    """Test using provided fixtures."""
    # created_album is already in db_session
    assert created_album.id is not None
    assert len(created_album.tracks) > 0
```

## Coverage Requirements

### Overall Target
- Minimum overall coverage: 30%
- Current coverage: 31.23%

### Critical Path Targets
- Rating Service: 80% (current: 62.85%)
- Album Operations: 60% (current: 41.50%)
- Authentication: 70% (current: 85%+)
- Data Models: 50% (current: 100%)

### Running Coverage Checks

```bash
# Check if coverage meets requirements
./venv/bin/python scripts/check_coverage.py

# View HTML coverage report
open htmlcov/index.html
```

## Best Practices

### 1. Test Naming
- Use descriptive test names that explain the scenario
- Follow pattern: `test_<what>_<condition>_<expected_result>`
- Example: `test_rate_track_invalid_rating_raises_error`

### 2. Test Independence
- Each test should be independent and not rely on other tests
- Use fixtures for shared setup
- Clean up after tests using fixture teardown

### 3. Assertion Guidelines
- Use specific assertions rather than generic ones
- Include meaningful assertion messages for failures
- Test both positive and negative cases

### 4. Mock Usage
- Mock external dependencies (APIs, file systems, etc.)
- Don't mock the system under test
- Verify mock interactions when relevant

### 5. Test Data
- Use realistic but deterministic test data
- Avoid hardcoding values that might change
- Use factories or fixtures for complex data structures

### 6. Performance
- Mark slow tests with `@pytest.mark.slow`
- Keep unit tests fast (< 100ms)
- Use in-memory SQLite for database tests

## Troubleshooting

### Common Issues

#### 1. Import Errors
```
ModuleNotFoundError: No module named 'app'
```
**Solution**: Ensure you're running tests from the project root directory and using the virtual environment.

#### 2. Database Connection Errors
```
sqlalchemy.exc.OperationalError: (sqlite3.OperationalError) no such table
```
**Solution**: Tests use in-memory SQLite. Ensure models are properly imported and Base.metadata.create_all() is called in fixtures.

#### 3. Async Test Failures
```
RuntimeError: This event loop is already running
```
**Solution**: Use `@pytest.mark.asyncio` decorator and ensure pytest-asyncio is installed.

#### 4. API Endpoint 404 Errors
**Issue**: Tests getting 404 for API endpoints
**Solution**: Check that routes use correct prefix (`/api/v1/`) and that routers are properly included in main app.

#### 5. Mock Patch Failures
```
AttributeError: <module> does not have the attribute
```
**Solution**: Ensure you're patching at the correct import location where the object is used, not where it's defined.

### Debug Techniques

```bash
# Run with debugging output
./venv/bin/python -m pytest -vvs

# Run with pdb on failure
./venv/bin/python -m pytest --pdb

# Show local variables on failure
./venv/bin/python -m pytest -l

# Run specific test with full traceback
./venv/bin/python -m pytest tests/test_file.py::test_name -vvs --tb=long
```

## Security Testing

### Authentication Security Tests

The application includes comprehensive security verification scripts for the authentication system:

#### 1. Security Audit Script (`scripts/security/test_auth_security.py`)

Comprehensive security audit that verifies:
- Passwords are NEVER sent to browser
- HttpOnly cookie configuration
- Session expiry validation
- Endpoint protection
- Network traffic security
- JWT implementation security

```bash
# Run security audit
python3 scripts/security/test_auth_security.py

# Expected output: All critical security checks should pass
```

#### 2. Session Expiry Test (`scripts/security/test_session_expiry.py`)

Tests session expiry by manipulating database timestamps:
- Verifies expired sessions are rejected
- Confirms future-dated sessions work
- Tests session deletion
- Validates remember_me duration

```bash
# Run session expiry test (requires active session)
python3 scripts/security/test_session_expiry.py
```

#### 3. Password Security Verification (`scripts/security/verify_password_security.py`)

Specifically verifies passwords never reach the browser:
- Checks all API responses for password data
- Verifies HttpOnly cookie configuration
- Confirms password masking in forms
- Validates POST-only authentication

```bash
# Run password security verification
python3 scripts/security/verify_password_security.py
```

**Note:** These are standalone security audit scripts located in `scripts/security/`, not part of the pytest test suite. See `docs/SECURITY_VERIFICATION.md` for detailed security documentation.

### Security Test Markers

```bash
# Run only security tests
./venv/bin/python -m pytest -m security

# Run authentication tests
./venv/bin/python -m pytest tests/test_security/test_auth_system.py
```

### Security Verification Checklist

- [ ] Passwords never appear in API responses
- [ ] Session cookies are HttpOnly
- [ ] Sessions expire correctly
- [ ] All endpoints require authentication when enabled
- [ ] Passwords only sent via POST body
- [ ] JWT tokens include expiry claim
- [ ] CSRF protection via SameSite cookies
- [ ] Generic error messages prevent user enumeration

## Test Environment Variables

Tests set the following environment variables automatically via conftest.py:

- `TESTING=true` - Indicates test environment
- `DISABLE_BACKGROUND_TASKS=true` - Prevents background task execution
- `DISABLE_SCHEDULED_TASKS=true` - Prevents scheduled task execution
- `AUTO_MIGRATE_ARTWORK=false` - Disables automatic artwork migration
- `DATABASE_URL=sqlite:///:memory:` - Uses in-memory database
- `LOG_LEVEL=ERROR` - Reduces log noise during tests

## Continuous Integration

The test suite is designed to run in CI environments. Key considerations:

1. All tests should be deterministic
2. No external API calls without mocking
3. Coverage must meet minimum threshold (30%)
4. Tests should complete within reasonable time (< 5 minutes)

### CI Command
```bash
pytest --cov=app --cov-report=xml --cov-report=term
```

## Adding New Tests

When adding new features or fixing bugs:

1. Write tests first (TDD approach recommended)
2. Ensure new code has adequate test coverage
3. Run coverage check to verify targets are met
4. Update this documentation if new patterns are introduced

### Test Template

```python
"""
Tests for [feature/module name].
"""

import pytest
from unittest.mock import Mock, patch

from app.module import ClassUnderTest


class TestClassName:
    """Test [description of what's being tested]."""
    
    @pytest.fixture
    def setup_data(self):
        """Provide test data for this test class."""
        return {"key": "value"}
    
    @pytest.mark.unit
    def test_expected_behavior(self, setup_data):
        """Test that [specific behavior] works correctly."""
        # Arrange
        instance = ClassUnderTest()
        
        # Act
        result = instance.method(setup_data)
        
        # Assert
        assert result is not None
        assert result["key"] == "expected_value"
    
    @pytest.mark.unit
    def test_error_condition(self):
        """Test that [error condition] is handled properly."""
        instance = ClassUnderTest()
        
        with pytest.raises(ExpectedException) as exc_info:
            instance.method_that_should_fail()
        
        assert "expected error message" in str(exc_info.value)
```

## Maintenance

### Regular Tasks
1. Run coverage checks before commits
2. Update tests when modifying code
3. Remove obsolete tests
4. Refactor tests to reduce duplication
5. Keep fixtures up to date with model changes

### Test Review Checklist
- [ ] Tests are independent and can run in any order
- [ ] Test names clearly describe what is being tested
- [ ] Appropriate markers are used (unit, integration, etc.)
- [ ] External dependencies are mocked
- [ ] Both success and failure cases are tested
- [ ] Tests run quickly (< 100ms for unit tests)
- [ ] No hardcoded paths or environment-specific values
- [ ] Assertions have meaningful messages
- [ ] Test data is realistic but deterministic
- [ ] Coverage targets are maintained or improved