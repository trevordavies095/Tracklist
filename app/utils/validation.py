"""
Input validation and sanitization utilities
Provides security-focused validation for user inputs
"""

import re
import html
import logging
from pathlib import Path
from typing import Optional, Any
from urllib.parse import quote, unquote

logger = logging.getLogger(__name__)

# Constants for validation
MAX_SEARCH_LENGTH = 200
MAX_NOTES_LENGTH = 5000
MAX_PATH_LENGTH = 255
MAX_INT_ID = 2147483647  # Max 32-bit integer

# Regex patterns for validation
MUSICBRAINZ_ID_PATTERN = re.compile(
    r"^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$"
)
SAFE_STRING_PATTERN = re.compile(r"^[\w\s\-.,!?()'\"/&]+$")
SAFE_FILENAME_PATTERN = re.compile(r"^[\w\-_.]+$")
SQL_INJECTION_PATTERNS = [
    re.compile(r"(\b(SELECT|INSERT|UPDATE|DELETE|DROP|UNION|ALTER|CREATE)\b)", re.IGNORECASE),
    re.compile(r"(--|#|/\*|\*/|;|\||&&|\|\||xp_|sp_|0x)", re.IGNORECASE),
]
XSS_PATTERNS = [
    re.compile(r"<script", re.IGNORECASE),
    re.compile(r"javascript:", re.IGNORECASE),
    re.compile(r"on\w+\s*=", re.IGNORECASE),  # onclick, onload, etc.
    re.compile(r"<iframe", re.IGNORECASE),
    re.compile(r"<embed", re.IGNORECASE),
    re.compile(r"<object", re.IGNORECASE),
]


def sanitize_string(value: str, max_length: int = MAX_SEARCH_LENGTH, block_html: bool = True) -> str:
    """
    Sanitize a string input for safe use
    
    Args:
        value: String to sanitize
        max_length: Maximum allowed length
        block_html: If True, reject HTML/JS patterns; if False, allow but escape
        
    Returns:
        Sanitized string
        
    Raises:
        ValueError: If input contains dangerous patterns (when block_html=True)
    """
    if not value:
        return ""
    
    # Truncate to max length
    value = value[:max_length]
    
    # Strip whitespace
    value = value.strip()
    
    # Check for SQL injection patterns - always block these
    for pattern in SQL_INJECTION_PATTERNS:
        if pattern.search(value):
            logger.warning(f"Potential SQL injection attempt detected: {value[:50]}...")
            raise ValueError("Invalid characters in input")
    
    # Check for XSS patterns
    if block_html:
        for pattern in XSS_PATTERNS:
            if pattern.search(value):
                logger.warning(f"Potential XSS attempt detected: {value[:50]}...")
                raise ValueError("Invalid HTML/JavaScript in input")
    
    return value


def escape_html(value: str) -> str:
    """
    Escape HTML special characters to prevent XSS
    
    Args:
        value: String to escape
        
    Returns:
        HTML-escaped string
    """
    if not value:
        return ""
    return html.escape(value, quote=True)


def validate_musicbrainz_id(mbid: str) -> str:
    """
    Validate a MusicBrainz ID format
    
    Args:
        mbid: MusicBrainz ID to validate
        
    Returns:
        Validated MusicBrainz ID
        
    Raises:
        ValueError: If ID format is invalid
    """
    if not mbid:
        raise ValueError("MusicBrainz ID is required")
    
    mbid = mbid.strip().lower()
    
    if not MUSICBRAINZ_ID_PATTERN.match(mbid):
        raise ValueError(
            "Invalid MusicBrainz ID format. Expected: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
        )
    
    return mbid


def validate_integer_id(value: Any, min_value: int = 1, max_value: int = MAX_INT_ID) -> int:
    """
    Validate an integer ID
    
    Args:
        value: Value to validate
        min_value: Minimum allowed value
        max_value: Maximum allowed value
        
    Returns:
        Validated integer
        
    Raises:
        ValueError: If value is not a valid integer in range
    """
    try:
        int_value = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"Invalid integer value: {value}")
    
    if int_value < min_value or int_value > max_value:
        raise ValueError(f"Integer value must be between {min_value} and {max_value}")
    
    return int_value


def validate_year(year: Any) -> int:
    """
    Validate a year value
    
    Args:
        year: Year to validate
        
    Returns:
        Validated year
        
    Raises:
        ValueError: If year is invalid
    """
    return validate_integer_id(year, min_value=1900, max_value=2100)


def validate_rating(rating: Any) -> float:
    """
    Validate a track rating value
    
    Args:
        rating: Rating to validate
        
    Returns:
        Validated rating
        
    Raises:
        ValueError: If rating is not valid
    """
    valid_ratings = [0.0, 0.33, 0.67, 1.0]
    
    try:
        float_rating = float(rating)
    except (TypeError, ValueError):
        raise ValueError(f"Invalid rating value: {rating}")
    
    # Handle floating point precision issues
    # Round to 2 decimal places first
    float_rating = round(float_rating, 2)
    
    # Check if it's close to any valid rating (within 0.01)
    for valid in valid_ratings:
        if abs(float_rating - valid) < 0.01:
            return valid
    
    # If not close to any valid rating, reject it
    raise ValueError(
        f"Invalid rating: {rating}. Must be one of: {valid_ratings}"
    )


def validate_path(path_str: str, base_path: Path, allow_symlinks: bool = False) -> Path:
    """
    Validate a file path to prevent directory traversal
    
    Args:
        path_str: Path string to validate
        base_path: Base directory that path must be within
        allow_symlinks: Whether to allow symbolic links
        
    Returns:
        Validated Path object
        
    Raises:
        ValueError: If path is invalid or outside base directory
    """
    if not path_str:
        raise ValueError("Path is required")
    
    # Check for suspicious patterns
    if ".." in path_str or path_str.startswith("/") or path_str.startswith("~"):
        raise ValueError("Invalid path: contains traversal attempt")
    
    # Resolve to absolute path
    try:
        path = Path(base_path) / path_str
        resolved_path = path.resolve()
    except Exception as e:
        raise ValueError(f"Invalid path: {e}")
    
    # Ensure path is within base directory
    try:
        resolved_path.relative_to(base_path.resolve())
    except ValueError:
        raise ValueError("Path is outside allowed directory")
    
    # Check symlinks if not allowed
    if not allow_symlinks and path.is_symlink():
        raise ValueError("Symbolic links are not allowed")
    
    return resolved_path


def validate_filename(filename: str) -> str:
    """
    Validate a filename for safety
    
    Args:
        filename: Filename to validate
        
    Returns:
        Validated filename
        
    Raises:
        ValueError: If filename is invalid
    """
    if not filename:
        raise ValueError("Filename is required")
    
    # Check for path traversal attempts
    if ".." in filename or "/" in filename or "\\" in filename:
        raise ValueError("Filename contains path traversal characters")
    
    # Remove any path components
    filename = Path(filename).name
    
    # Check length
    if len(filename) > MAX_PATH_LENGTH:
        raise ValueError(f"Filename too long (max {MAX_PATH_LENGTH} characters)")
    
    # Check for safe characters
    if not SAFE_FILENAME_PATTERN.match(filename):
        raise ValueError("Filename contains invalid characters")
    
    # Check for reserved names (Windows)
    reserved_names = [
        "CON", "PRN", "AUX", "NUL",
        "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
        "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9"
    ]
    
    name_without_ext = filename.split(".")[0].upper()
    if name_without_ext in reserved_names:
        raise ValueError("Filename uses reserved system name")
    
    return filename


def validate_pagination(limit: int, offset: int) -> tuple[int, int]:
    """
    Validate pagination parameters
    
    Args:
        limit: Number of items per page
        offset: Starting position
        
    Returns:
        Tuple of (validated_limit, validated_offset)
        
    Raises:
        ValueError: If parameters are invalid
    """
    # Validate limit
    if limit < 1:
        raise ValueError("Limit must be at least 1")
    if limit > 100:
        limit = 100  # Cap at 100
    
    # Validate offset
    if offset < 0:
        raise ValueError("Offset cannot be negative")
    if offset > 10000:
        raise ValueError("Offset too large")
    
    return limit, offset


def sanitize_for_logging(value: str, max_length: int = 100) -> str:
    """
    Sanitize a value for safe logging (prevent log injection)
    
    Args:
        value: Value to sanitize
        max_length: Maximum length for logged value
        
    Returns:
        Sanitized string safe for logging
    """
    if not value:
        return ""
    
    # Remove newlines and control characters
    value = re.sub(r'[\r\n\t\x00-\x1f\x7f-\x9f]', ' ', value)
    
    # Truncate
    if len(value) > max_length:
        value = value[:max_length] + "..."
    
    return value


def validate_json_field(data: dict, field: str, required: bool = True, 
                        field_type: type = str, max_length: Optional[int] = None) -> Any:
    """
    Validate a field from JSON data
    
    Args:
        data: JSON data dictionary
        field: Field name to validate
        required: Whether field is required
        field_type: Expected type of field
        max_length: Maximum length for string fields
        
    Returns:
        Validated field value
        
    Raises:
        ValueError: If field is invalid
    """
    if field not in data:
        if required:
            raise ValueError(f"Missing required field: {field}")
        return None
    
    value = data[field]
    
    # Type check
    if not isinstance(value, field_type):
        raise ValueError(f"Field '{field}' must be of type {field_type.__name__}")
    
    # Length check for strings
    if field_type == str and max_length and len(value) > max_length:
        raise ValueError(f"Field '{field}' exceeds maximum length of {max_length}")
    
    return value