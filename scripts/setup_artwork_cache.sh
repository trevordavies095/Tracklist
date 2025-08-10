#!/bin/bash
#
# Setup script for artwork cache directory structure and permissions
# This script ensures the artwork cache directories exist with proper permissions
#

set -e

# Configuration
CACHE_BASE_DIR="${ARTWORK_CACHE_DIR:-./static/artwork_cache}"
SIZES=("original" "large" "medium" "small" "thumbnail")

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Functions
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Create directory structure
create_directories() {
    log_info "Creating artwork cache directory structure..."
    
    # Create base directory if it doesn't exist
    if [ ! -d "$CACHE_BASE_DIR" ]; then
        mkdir -p "$CACHE_BASE_DIR"
        log_info "Created base directory: $CACHE_BASE_DIR"
    else
        log_info "Base directory already exists: $CACHE_BASE_DIR"
    fi
    
    # Create size-specific subdirectories
    for size in "${SIZES[@]}"; do
        dir="$CACHE_BASE_DIR/$size"
        if [ ! -d "$dir" ]; then
            mkdir -p "$dir"
            log_info "Created directory: $dir"
        else
            log_info "Directory already exists: $dir"
        fi
    done
}

# Set proper permissions
set_permissions() {
    log_info "Setting permissions for artwork cache directories..."
    
    # Check if running in Docker (as tracklist user)
    if [ "$USER" = "tracklist" ] || [ -n "$DOCKER_CONTAINER" ]; then
        # In Docker container - set less restrictive permissions
        chmod 755 "$CACHE_BASE_DIR"
        for size in "${SIZES[@]}"; do
            chmod 755 "$CACHE_BASE_DIR/$size"
        done
        log_info "Set Docker container permissions (755)"
    else
        # Local development - set user-only permissions
        chmod 700 "$CACHE_BASE_DIR"
        for size in "${SIZES[@]}"; do
            chmod 700 "$CACHE_BASE_DIR/$size"
        done
        log_info "Set local development permissions (700)"
    fi
    
    # Set README to be readable
    if [ -f "$CACHE_BASE_DIR/README.md" ]; then
        chmod 644 "$CACHE_BASE_DIR/README.md"
    fi
}

# Verify structure
verify_structure() {
    log_info "Verifying directory structure..."
    
    local all_good=true
    
    # Check base directory
    if [ ! -d "$CACHE_BASE_DIR" ]; then
        log_error "Base directory missing: $CACHE_BASE_DIR"
        all_good=false
    fi
    
    # Check each size directory
    for size in "${SIZES[@]}"; do
        dir="$CACHE_BASE_DIR/$size"
        if [ ! -d "$dir" ]; then
            log_error "Directory missing: $dir"
            all_good=false
        elif [ ! -w "$dir" ]; then
            log_error "Directory not writable: $dir"
            all_good=false
        else
            log_info "✓ $dir"
        fi
    done
    
    if $all_good; then
        log_info "Directory structure verification passed!"
        return 0
    else
        log_error "Directory structure verification failed!"
        return 1
    fi
}

# Clean empty directories (optional)
clean_empty() {
    log_info "Cleaning empty cache directories..."
    
    for size in "${SIZES[@]}"; do
        dir="$CACHE_BASE_DIR/$size"
        if [ -d "$dir" ] && [ -z "$(ls -A "$dir")" ]; then
            log_info "Directory is empty: $dir"
        fi
    done
}

# Display statistics
show_stats() {
    log_info "Artwork cache statistics:"
    
    if [ -d "$CACHE_BASE_DIR" ]; then
        for size in "${SIZES[@]}"; do
            dir="$CACHE_BASE_DIR/$size"
            if [ -d "$dir" ]; then
                count=$(find "$dir" -type f 2>/dev/null | wc -l)
                size_mb=$(du -sm "$dir" 2>/dev/null | cut -f1)
                echo "  $size: $count files, ${size_mb}MB"
            fi
        done
        
        total_count=$(find "$CACHE_BASE_DIR" -type f 2>/dev/null | wc -l)
        total_size=$(du -sm "$CACHE_BASE_DIR" 2>/dev/null | cut -f1)
        echo "  ---"
        echo "  Total: $total_count files, ${total_size}MB"
    else
        log_warn "Cache directory does not exist yet"
    fi
}

# Main execution
main() {
    echo "Artwork Cache Setup Script"
    echo "=========================="
    echo ""
    
    # Parse arguments
    case "${1:-setup}" in
        setup)
            create_directories
            set_permissions
            verify_structure
            ;;
        verify)
            verify_structure
            ;;
        stats)
            show_stats
            ;;
        clean)
            clean_empty
            ;;
        permissions)
            set_permissions
            ;;
        *)
            echo "Usage: $0 [setup|verify|stats|clean|permissions]"
            echo ""
            echo "Commands:"
            echo "  setup       - Create directories and set permissions (default)"
            echo "  verify      - Verify directory structure"
            echo "  stats       - Show cache statistics"
            echo "  clean       - Clean empty directories"
            echo "  permissions - Reset permissions only"
            exit 1
            ;;
    esac
    
    echo ""
    log_info "Done!"
}

# Run main function
main "$@"