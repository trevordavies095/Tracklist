/**
 * Artwork Helper Functions for Frontend Templates
 * Provides utilities for getting cached artwork URLs
 */

// Cache for artwork URLs to avoid repeated lookups
const artworkCache = new Map();
const CACHE_TTL = 5 * 60 * 1000; // 5 minutes

/**
 * Get artwork URL for an album, preferring cached versions
 * @param {Object} album - Album object with id and cover_art_url
 * @param {string} size - Size variant (thumbnail, small, medium, large, original)
 * @param {string} fallback - Fallback URL or path if no artwork available
 * @returns {Promise<string>} - Artwork URL
 */
async function getArtworkUrl(album, size = 'medium', fallback = null) {
    // Quick validation
    if (!album || !album.id) {
        return fallback || '/static/img/album-placeholder.svg';
    }
    
    // Check memory cache first
    const cacheKey = `${album.id}_${size}`;
    const cached = artworkCache.get(cacheKey);
    if (cached && (Date.now() - cached.time) < CACHE_TTL) {
        return cached.url;
    }
    
    try {
        // Check if we should use the cache API endpoint
        const response = await fetch(`/api/albums/${album.id}/artwork-url?size=${size}`, {
            method: 'GET',
            headers: {
                'Accept': 'application/json'
            }
        });
        
        if (response.ok) {
            const data = await response.json();
            if (data.url) {
                // Store in cache
                artworkCache.set(cacheKey, {
                    url: data.url,
                    time: Date.now()
                });
                return data.url;
            }
        }
    } catch (error) {
        console.debug('Failed to fetch cached artwork URL:', error);
    }
    
    // Fallback to original URL or placeholder
    if (album.cover_art_url) {
        return album.cover_art_url;
    }
    
    return fallback || '/static/img/album-placeholder.svg';
}

/**
 * Synchronous version that returns immediately with best available URL
 * @param {Object} album - Album object
 * @param {string} size - Size variant  
 * @param {string} fallback - Fallback URL
 * @returns {string} - Best available artwork URL
 */
function getArtworkUrlSync(album, size = 'medium', fallback = null) {
    // Quick validation
    if (!album || !album.id) {
        return fallback || '/static/img/album-placeholder.svg';
    }
    
    // Check memory cache
    const cacheKey = `${album.id}_${size}`;
    const cached = artworkCache.get(cacheKey);
    if (cached && (Date.now() - cached.time) < CACHE_TTL) {
        return cached.url;
    }
    
    // For now, just return the cover art URL or fallback
    // The async version can be called to update the cache in background
    if (album.cover_art_url) {
        // Trigger async cache check in background
        getArtworkUrl(album, size, fallback).catch(() => {});
        return album.cover_art_url;
    }
    
    return fallback || '/static/img/album-placeholder.svg';
}

/**
 * Generate HTML for album artwork with proper fallback
 * @param {Object} album - Album object
 * @param {string} size - Size variant
 * @param {string} classes - Additional CSS classes
 * @returns {string} - HTML string for the artwork
 */
function getArtworkHtml(album, size = 'medium', classes = '') {
    const sizeClasses = {
        'thumbnail': 'w-12 h-12',
        'small': 'w-16 h-16',
        'medium': 'w-24 h-24',
        'large': 'w-48 h-48',
        'original': 'w-full h-full'
    };
    
    const sizeClass = sizeClasses[size] || sizeClasses['medium'];
    const url = getArtworkUrlSync(album, size);
    const placeholderSvg = `
        <svg class="w-full h-full text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" 
                  d="M9 19V6l12-3v13M9 19c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zm12-3c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zM9 10l12-3">
            </path>
        </svg>
    `;
    
    if (url && url !== '/static/img/album-placeholder.svg') {
        return `
            <div class="${sizeClass} rounded-lg overflow-hidden ${classes}">
                <img src="${url}" 
                     alt="${album.title || 'Album'} cover" 
                     class="w-full h-full object-cover"
                     onerror="this.onerror=null; this.parentElement.innerHTML='<div class=\\'${sizeClass} bg-gradient-to-br from-gray-200 to-gray-300 rounded-lg flex items-center justify-center\\'>${placeholderSvg.replace(/"/g, '\\"')}</div>';">
            </div>
        `;
    } else {
        return `
            <div class="${sizeClass} bg-gradient-to-br from-gray-200 to-gray-300 rounded-lg flex items-center justify-center ${classes}">
                ${placeholderSvg}
            </div>
        `;
    }
}

/**
 * Preload artwork URLs for multiple albums
 * @param {Array} albums - Array of album objects
 * @param {string} size - Size variant to preload
 */
async function preloadArtworkUrls(albums, size = 'medium') {
    if (!albums || !albums.length) return;
    
    // Batch preload artwork URLs
    const promises = albums.map(album => 
        getArtworkUrl(album, size).catch(() => null)
    );
    
    await Promise.all(promises);
}

/**
 * Clear the artwork cache
 */
function clearArtworkCache() {
    artworkCache.clear();
}

// Export for use in modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        getArtworkUrl,
        getArtworkUrlSync,
        getArtworkHtml,
        preloadArtworkUrls,
        clearArtworkCache
    };
}