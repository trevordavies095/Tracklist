# Contributing to Tracklist

Thank you for your interest in contributing to Tracklist! This document provides guidelines and instructions for contributing to the project.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [Making Changes](#making-changes)
- [Testing](#testing)
- [Pull Request Process](#pull-request-process)
- [CI/CD Requirements](#cicd-requirements)
- [Code Style](#code-style)
- [Commit Messages](#commit-messages)
- [Security](#security)

## Code of Conduct

By participating in this project, you agree to abide by our Code of Conduct:
- Be respectful and inclusive
- Welcome newcomers and help them get started
- Focus on constructive criticism
- Accept feedback gracefully

## Getting Started

1. Fork the repository
2. Clone your fork: `git clone https://github.com/YOUR_USERNAME/Tracklist.git`
3. Add upstream remote: `git remote add upstream https://github.com/trevordavies095/Tracklist.git`
4. Create a new branch: `git checkout -b feature/your-feature-name`

## Development Setup

### Prerequisites

- Python 3.9 or higher
- Docker (optional, for containerized development)
- Git

### Local Development

1. Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements-dev.txt
   ```

3. Copy environment variables:
   ```bash
   cp .env.example .env
   # Edit .env with your configuration
   ```

4. Run database migrations:
   ```bash
   alembic upgrade head
   ```

5. Start the development server:
   ```bash
   uvicorn app.main:app --reload
   ```

### Docker Development

1. Build and run with Docker Compose:
   ```bash
   docker-compose up --build
   ```

## Making Changes

### Branch Naming

Use descriptive branch names following these patterns:
- `feature/description` - New features
- `fix/description` - Bug fixes
- `docs/description` - Documentation changes
- `refactor/description` - Code refactoring
- `test/description` - Test additions or fixes
- `chore/description` - Maintenance tasks

### Development Workflow

1. Keep your fork synchronized:
   ```bash
   git fetch upstream
   git checkout main
   git merge upstream/main
   ```

2. Make your changes in a feature branch
3. Write or update tests for your changes
4. Ensure all tests pass
5. Update documentation if needed
6. Commit your changes with clear messages

## Testing

### Running Tests Locally

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=app --cov-report=html

# Run specific test file
pytest tests/test_specific.py

# Run tests in parallel
pytest -n auto

# Run only fast tests
pytest -m "not slow"
```

### Test Requirements

- All new features must include tests
- Bug fixes should include regression tests
- Maintain or improve code coverage (minimum 70%)
- Tests must pass on all supported Python versions (3.9-3.13)

### Test Categories

Mark your tests appropriately:
```python
@pytest.mark.unit  # Unit tests
@pytest.mark.integration  # Integration tests
@pytest.mark.slow  # Slow tests
@pytest.mark.security  # Security-related tests
```

## Pull Request Process

### Before Submitting

1. **Run tests**: `pytest`
2. **Check type hints**: `mypy app/`
3. **Format code**: `black .`
4. **Lint code**: `flake8 .`
5. **Security scan**: `bandit -r app/`

### PR Requirements

Your pull request must:

- ✅ Pass all CI checks
- ✅ Include tests for new functionality
- ✅ Maintain or improve code coverage
- ✅ Follow code style guidelines
- ✅ Have a clear, descriptive title
- ✅ Include a detailed description of changes
- ✅ Reference any related issues
- ✅ Be up to date with the main branch

### PR Template

When creating a PR, please fill out the template:

```markdown
## Description
Brief description of changes

## Type of Change
- [ ] Bug fix
- [ ] New feature
- [ ] Breaking change
- [ ] Documentation update

## Testing
- [ ] Tests pass locally
- [ ] New tests added
- [ ] Coverage maintained/improved

## Checklist
- [ ] Code follows style guidelines
- [ ] Self-review completed
- [ ] Documentation updated
- [ ] No new warnings
```

## CI/CD Requirements

All pull requests to main or develop branches trigger automated CI/CD pipelines that must pass:

### Automated Checks

1. **Linting**
   - Black formatting
   - Flake8 style checks
   - MyPy type checking

2. **Security**
   - Bandit security scanning
   - Safety dependency checks
   - CodeQL analysis
   - Trivy container scanning (for Docker changes)

3. **Testing**
   - Multi-version Python tests (3.9-3.13)
   - Coverage reporting (minimum 70%)
   - Test result publication

### Required Status Checks

The following checks must pass before merging:
- `lint` - Code style and formatting
- `security` - Security vulnerability scanning
- `test` - All test suites
- `test-summary` - Test results summary
- `all-checks` - Meta check ensuring all required checks pass

Note: Docker images are built automatically after merging to main or develop branches, not during PRs.

## Code Style

### Python Style Guide

We follow PEP 8 with these specifications:

- **Line length**: 100 characters maximum
- **Imports**: Sorted with `isort`, grouped by standard/third-party/local
- **Formatting**: Enforced with `black`
- **Type hints**: Required for all public functions
- **Docstrings**: Google style for all public modules/classes/functions

### Example

```python
from typing import Optional, List

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models import Album


def get_album_by_id(
    db: Session,
    album_id: str,
    include_tracks: bool = False
) -> Optional[Album]:
    """Retrieve an album by its ID.

    Args:
        db: Database session
        album_id: MusicBrainz album ID
        include_tracks: Whether to include track information

    Returns:
        Album object if found, None otherwise

    Raises:
        HTTPException: If database error occurs
    """
    try:
        album = db.query(Album).filter(Album.id == album_id).first()
        if album and include_tracks:
            # Load tracks relationship
            album.tracks
        return album
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

## Commit Messages

### Format

Follow the Conventional Commits specification:

```
<type>(<scope>): <subject>

<body>

<footer>
```

### Types

- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `style`: Code style changes (formatting, etc.)
- `refactor`: Code refactoring
- `test`: Test additions or fixes
- `chore`: Maintenance tasks
- `perf`: Performance improvements
- `ci`: CI/CD changes

### Examples

```bash
feat(search): add album cover art to search results

fix(rating): correct average calculation for albums with no ratings

docs(api): update OpenAPI documentation for new endpoints

chore(deps): update FastAPI to 0.104.0
```

## Security

### Reporting Security Issues

**DO NOT** create public issues for security vulnerabilities. Instead:

1. Email security concerns to the maintainers
2. Include detailed information about the vulnerability
3. Wait for confirmation before public disclosure

### Security Best Practices

When contributing:

- Never commit secrets, tokens, or credentials
- Use environment variables for configuration
- Validate and sanitize all user inputs
- Follow OWASP security guidelines
- Keep dependencies up to date
- Run security scans before submitting PRs

### Security Tools

```bash
# Run security scans
bandit -r app/
safety check
pip-audit

# Check for secrets
pre-commit run detect-private-key --all-files
```

## Getting Help

If you need help:

1. Check existing [documentation](../README.md)
2. Search [existing issues](https://github.com/trevordavies095/Tracklist/issues)
3. Join discussions in [issues](https://github.com/trevordavies095/Tracklist/issues)
4. Ask questions in pull request comments

## Recognition

Contributors are recognized in:
- The project's README
- Release notes
- GitHub's contributor graph

Thank you for contributing to Tracklist! 🎵
