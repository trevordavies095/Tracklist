"""
Request validation models using Pydantic
Provides strict validation for all API endpoints
"""

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..utils.validation import (
    MAX_NOTES_LENGTH,
    MAX_SEARCH_LENGTH,
    escape_html,
    sanitize_string,
    validate_integer_id,
    validate_musicbrainz_id,
    validate_rating,
    validate_year,
)


class SearchRequest(BaseModel):
    """Validated search request"""

    model_config = ConfigDict(str_strip_whitespace=True)

    q: Optional[str] = Field(
        None,
        min_length=1,
        max_length=MAX_SEARCH_LENGTH,
        description="General search query",
    )
    artist: Optional[str] = Field(
        None,
        max_length=MAX_SEARCH_LENGTH,
        description="Artist name for structured search",
    )
    album: Optional[str] = Field(
        None,
        max_length=MAX_SEARCH_LENGTH,
        description="Album title for structured search",
    )
    year: Optional[int] = Field(None, ge=1900, le=2100, description="Release year")
    mbid: Optional[str] = Field(
        None,
        pattern="^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$",
        description="MusicBrainz Release ID",
    )
    limit: int = Field(
        default=25, ge=1, le=100, description="Maximum number of results"
    )
    offset: int = Field(default=0, ge=0, le=10000, description="Offset for pagination")

    @field_validator("q", "artist", "album")
    @classmethod
    def sanitize_search_fields(cls, v: Optional[str]) -> Optional[str]:
        """Sanitize search string fields - allow HTML but will be escaped on display"""
        if v is None:
            return None
        # Don't block HTML in search queries - they'll be escaped when displayed
        return sanitize_string(v, MAX_SEARCH_LENGTH, block_html=False)

    @field_validator("mbid")
    @classmethod
    def validate_mbid(cls, v: Optional[str]) -> Optional[str]:
        """Validate MusicBrainz ID"""
        if v is None:
            return None
        return validate_musicbrainz_id(v)

    @field_validator("year")
    @classmethod
    def validate_year_field(cls, v: Optional[int]) -> Optional[int]:
        """Validate year"""
        if v is None:
            return None
        return validate_year(v)


class AlbumCreateRequest(BaseModel):
    """Validated album creation request"""

    model_config = ConfigDict(str_strip_whitespace=True)

    musicbrainz_id: str = Field(
        ...,
        pattern="^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$",
        description="MusicBrainz release ID",
    )

    @field_validator("musicbrainz_id")
    @classmethod
    def validate_mbid(cls, v: str) -> str:
        """Validate MusicBrainz ID"""
        return validate_musicbrainz_id(v)


class TrackRatingRequest(BaseModel):
    """Validated track rating request"""

    rating: float = Field(
        ..., ge=0.0, le=1.0, description="Track rating (0.0, 0.33, 0.67, 1.0)"
    )

    @field_validator("rating")
    @classmethod
    def validate_rating_value(cls, v: float) -> float:
        """Validate rating is one of allowed values"""
        return validate_rating(v)


class AlbumNotesRequest(BaseModel):
    """Validated album notes update request"""

    model_config = ConfigDict(str_strip_whitespace=True)

    notes: str = Field(
        default="",
        max_length=MAX_NOTES_LENGTH,
        description="Album notes (HTML will be escaped)",
    )

    @field_validator("notes")
    @classmethod
    def sanitize_notes(cls, v: str) -> str:
        """Sanitize and escape notes"""
        if not v:
            return ""
        # First sanitize to check for dangerous patterns (allow HTML, will be escaped)
        sanitized = sanitize_string(v, MAX_NOTES_LENGTH, block_html=False)
        # Then escape HTML for safe display
        return escape_html(sanitized)


class AlbumBonusRequest(BaseModel):
    """Validated album bonus update request"""

    album_bonus: float = Field(..., ge=0.0, le=0.4, description="Album bonus value")

    @field_validator("album_bonus")
    @classmethod
    def validate_bonus(cls, v: float) -> float:
        """Validate album bonus is in valid range"""
        # Round to 2 decimal places
        rounded = round(v, 2)
        if rounded < 0.0 or rounded > 0.4:
            raise ValueError("Album bonus must be between 0.0 and 0.4")
        return rounded


class ComparisonRequest(BaseModel):
    """Validated album comparison request"""

    album_ids: list[int] = Field(
        ..., min_length=2, max_length=4, description="Album IDs to compare (2-4 albums)"
    )

    @field_validator("album_ids")
    @classmethod
    def validate_album_ids(cls, v: list[int]) -> list[int]:
        """Validate album IDs"""
        validated_ids = []
        for album_id in v:
            validated_id = validate_integer_id(album_id, min_value=1)
            validated_ids.append(validated_id)

        # Check for duplicates
        if len(set(validated_ids)) != len(validated_ids):
            raise ValueError("Duplicate album IDs not allowed")

        return validated_ids


class ExportRequest(BaseModel):
    """Validated export request"""

    model_config = ConfigDict(str_strip_whitespace=True)

    format: str = Field(
        default="json", pattern="^(json|csv)$", description="Export format"
    )
    include_unrated: bool = Field(default=False, description="Include unrated albums")

    @field_validator("format")
    @classmethod
    def validate_format(cls, v: str) -> str:
        """Validate export format"""
        v = v.lower()
        if v not in ["json", "csv"]:
            raise ValueError("Format must be 'json' or 'csv'")
        return v


class ImportRequest(BaseModel):
    """Validated import request"""

    model_config = ConfigDict(str_strip_whitespace=True)

    mode: str = Field(
        default="merge", pattern="^(merge|replace)$", description="Import mode"
    )
    dry_run: bool = Field(
        default=False, description="Preview import without making changes"
    )

    @field_validator("mode")
    @classmethod
    def validate_mode(cls, v: str) -> str:
        """Validate import mode"""
        v = v.lower()
        if v not in ["merge", "replace"]:
            raise ValueError("Mode must be 'merge' or 'replace'")
        return v


class PaginationParams(BaseModel):
    """Common pagination parameters"""

    limit: int = Field(default=25, ge=1, le=100, description="Items per page")
    offset: int = Field(default=0, ge=0, le=10000, description="Starting position")

    @field_validator("limit")
    @classmethod
    def validate_limit(cls, v: int) -> int:
        """Cap limit at 100"""
        return min(v, 100)


class FilterParams(BaseModel):
    """Common filter parameters for album listings"""

    model_config = ConfigDict(str_strip_whitespace=True)

    artist_id: Optional[int] = Field(None, gt=0, description="Filter by artist ID")
    year: Optional[int] = Field(
        None, ge=1900, le=2100, description="Filter by release year"
    )
    is_rated: Optional[bool] = Field(None, description="Filter by rating status")
    min_score: Optional[int] = Field(
        None, ge=0, le=100, description="Minimum album score"
    )
    max_score: Optional[int] = Field(
        None, ge=0, le=100, description="Maximum album score"
    )
    search: Optional[str] = Field(
        None, max_length=MAX_SEARCH_LENGTH, description="Search in album/artist names"
    )

    @field_validator("search")
    @classmethod
    def sanitize_search(cls, v: Optional[str]) -> Optional[str]:
        """Sanitize search string"""
        if v is None:
            return None
        return sanitize_string(v, MAX_SEARCH_LENGTH)

    @field_validator("min_score", "max_score")
    @classmethod
    def validate_score_range(cls, v: Optional[int], info) -> Optional[int]:
        """Validate score range"""
        if v is None:
            return None

        # Check min <= max if both are set
        if info.field_name == "max_score" and "min_score" in info.data:
            min_score = info.data["min_score"]
            if min_score is not None and v < min_score:
                raise ValueError("max_score must be >= min_score")

        return v


class SortParams(BaseModel):
    """Common sort parameters"""

    sort: str = Field(
        default="created_desc",
        pattern="^(rating|created|updated|album|artist|year)_(asc|desc)$",
        description="Sort field and direction",
    )

    @field_validator("sort")
    @classmethod
    def validate_sort(cls, v: str) -> str:
        """Validate sort parameter"""
        valid_sorts = [
            "rating_desc",
            "rating_asc",
            "created_desc",
            "created_asc",
            "updated_desc",
            "updated_asc",
            "album_asc",
            "album_desc",
            "artist_asc",
            "artist_desc",
            "year_desc",
            "year_asc",
        ]

        if v not in valid_sorts:
            raise ValueError(f"Invalid sort. Must be one of: {', '.join(valid_sorts)}")

        return v
