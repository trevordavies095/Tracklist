# Artwork Cache Directory

This directory contains cached album artwork in various sizes to optimize performance and reduce external API calls.

## Directory Structure

```
artwork_cache/
├── original/      # Full resolution images as fetched from source
├── large/         # 192x192px - Album detail pages
├── medium/        # 64x64px - Album lists and cards
├── small/         # 48x48px - Compact lists and tables
└── thumbnail/     # 80x80px - Grid views and previews
```

## File Naming Convention

Files are named using the cache key (MD5 hash) with the original file extension:
- Pattern: `{cache_key}.{extension}`
- Example: `a1b2c3d4e5f6.jpg`

## Size Specifications

| Size      | Dimensions | Use Case                          |
|-----------|------------|-----------------------------------|
| original  | Variable   | Source image, archival purposes   |
| large     | 192x192    | Album rating/detail pages         |
| medium    | 64x64      | Album lists, cards, stats page    |
| small     | 48x48      | Tables, recent activity lists     |
| thumbnail | 80x80      | Grid views, search results        |

## Maintenance

- Files are automatically managed by the application
- Cleanup of unused images happens periodically
- Do not manually modify files in this directory
- This directory is excluded from version control

## Permissions

- Directory: 755 (rwxr-xr-x)
- Files: 644 (rw-r--r--)
- Owner: Application user (tracklist in Docker)

## Cache Policy

- Images are cached on first access
- Last access time is tracked for cleanup
- Images not accessed for 30 days may be removed
- Original images are preserved longer than variants