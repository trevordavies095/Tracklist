/**
 * Lazy Loading Library for Album Artwork
 * Uses Intersection Observer API for efficient image loading
 */

(function() {
    'use strict';
    
    // Configuration
    const config = {
        rootMargin: '50px 0px', // Start loading 50px before image enters viewport
        threshold: 0.01, // Trigger when 1% of image is visible
        fadeInDuration: 300, // Animation duration in ms
        retryAttempts: 3,
        retryDelay: 1000,
        placeholderClass: 'artwork-placeholder',
        loadingClass: 'artwork-loading',
        loadedClass: 'artwork-loaded',
        errorClass: 'artwork-error'
    };
    
    // Cache for loaded images
    const imageCache = new Set();
    
    /**
     * Initialize lazy loading for all images with data-src attribute
     */
    function initLazyLoading() {
        // Check for Intersection Observer support
        if (!('IntersectionObserver' in window)) {
            console.warn('Intersection Observer not supported, loading all images');
            loadAllImages();
            return;
        }
        
        // Create observer
        const imageObserver = new IntersectionObserver(handleIntersection, {
            rootMargin: config.rootMargin,
            threshold: config.threshold
        });
        
        // Observe all lazy images
        const lazyImages = document.querySelectorAll('img[data-src]');
        lazyImages.forEach(img => {
            // Add placeholder class
            img.classList.add(config.placeholderClass);
            
            // Set up placeholder if not already present
            if (!img.src) {
                img.src = '/static/img/album-placeholder.svg';
            }
            
            // Start observing
            imageObserver.observe(img);
        });
        
        // Also handle images that might be added dynamically
        observeDynamicImages(imageObserver);
        
        console.log(`Lazy loading initialized for ${lazyImages.length} images`);
    }
    
    /**
     * Handle intersection events
     */
    function handleIntersection(entries, observer) {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                const img = entry.target;
                loadImage(img);
                observer.unobserve(img);
            }
        });
    }
    
    /**
     * Load a single image
     */
    function loadImage(img, attemptNumber = 1) {
        const src = img.dataset.src;
        
        if (!src) return;
        
        // Check if already cached
        if (imageCache.has(src)) {
            applyImage(img, src);
            return;
        }
        
        // Add loading state
        img.classList.add(config.loadingClass);
        img.classList.remove(config.errorClass);
        
        // Create a new image element to load in background
        const tempImg = new Image();
        
        tempImg.onload = function() {
            // Add to cache
            imageCache.add(src);
            
            // Apply to actual image element
            applyImage(img, src);
        };
        
        tempImg.onerror = function() {
            img.classList.remove(config.loadingClass);
            
            if (attemptNumber < config.retryAttempts) {
                // Retry after delay
                setTimeout(() => {
                    console.log(`Retrying image load (attempt ${attemptNumber + 1}): ${src}`);
                    loadImage(img, attemptNumber + 1);
                }, config.retryDelay * attemptNumber);
            } else {
                // Max retries reached
                img.classList.add(config.errorClass);
                console.error(`Failed to load image after ${config.retryAttempts} attempts: ${src}`);
                
                // Dispatch custom event for error handling
                img.dispatchEvent(new CustomEvent('lazyload:error', {
                    detail: { src, attempts: attemptNumber }
                }));
            }
        };
        
        // Start loading
        tempImg.src = src;
    }
    
    /**
     * Apply loaded image with fade-in effect
     */
    function applyImage(img, src) {
        // Remove loading state
        img.classList.remove(config.loadingClass);
        img.classList.remove(config.placeholderClass);
        
        // Add fade-in transition
        img.style.opacity = '0';
        img.style.transition = `opacity ${config.fadeInDuration}ms ease-in-out`;
        
        // Set source
        img.src = src;
        
        // Remove data-src to mark as loaded
        delete img.dataset.src;
        
        // Trigger fade-in
        requestAnimationFrame(() => {
            img.style.opacity = '1';
            img.classList.add(config.loadedClass);
            
            // Clean up transition after animation
            setTimeout(() => {
                img.style.transition = '';
            }, config.fadeInDuration);
        });
        
        // Dispatch custom event
        img.dispatchEvent(new CustomEvent('lazyload:loaded', {
            detail: { src }
        }));
    }
    
    /**
     * Fallback for browsers without Intersection Observer
     */
    function loadAllImages() {
        const lazyImages = document.querySelectorAll('img[data-src]');
        lazyImages.forEach(img => {
            img.src = img.dataset.src;
            delete img.dataset.src;
        });
    }
    
    /**
     * Watch for dynamically added images
     */
    function observeDynamicImages(observer) {
        // Use MutationObserver to watch for new images
        if (!('MutationObserver' in window)) return;
        
        const mutationObserver = new MutationObserver(mutations => {
            mutations.forEach(mutation => {
                mutation.addedNodes.forEach(node => {
                    if (node.nodeType === 1) { // Element node
                        // Check if it's an image with data-src
                        if (node.tagName === 'IMG' && node.dataset.src) {
                            node.classList.add(config.placeholderClass);
                            if (!node.src) {
                                node.src = '/static/img/album-placeholder.svg';
                            }
                            observer.observe(node);
                        }
                        
                        // Also check children
                        const lazyImages = node.querySelectorAll?.('img[data-src]');
                        lazyImages?.forEach(img => {
                            img.classList.add(config.placeholderClass);
                            if (!img.src) {
                                img.src = '/static/img/album-placeholder.svg';
                            }
                            observer.observe(img);
                        });
                    }
                });
            });
        });
        
        mutationObserver.observe(document.body, {
            childList: true,
            subtree: true
        });
    }
    
    /**
     * Preload images for improved performance
     */
    function preloadImages(urls) {
        urls.forEach(url => {
            if (!imageCache.has(url)) {
                const img = new Image();
                img.onload = () => imageCache.add(url);
                img.src = url;
            }
        });
    }
    
    /**
     * Force load specific images (useful for priority content)
     */
    function forceLoad(selector) {
        const images = document.querySelectorAll(selector);
        images.forEach(img => {
            if (img.dataset.src) {
                loadImage(img);
            }
        });
    }
    
    /**
     * Get loading statistics
     */
    function getStats() {
        const total = document.querySelectorAll('img[data-src], img.artwork-loaded').length;
        const loaded = document.querySelectorAll('img.artwork-loaded').length;
        const loading = document.querySelectorAll('img.artwork-loading').length;
        const errors = document.querySelectorAll('img.artwork-error').length;
        
        return {
            total,
            loaded,
            loading,
            errors,
            cached: imageCache.size,
            percentage: total > 0 ? Math.round((loaded / total) * 100) : 0
        };
    }
    
    // Public API
    window.LazyLoad = {
        init: initLazyLoading,
        preload: preloadImages,
        forceLoad: forceLoad,
        getStats: getStats,
        config: config
    };
    
    // Auto-initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initLazyLoading);
    } else {
        initLazyLoading();
    }
    
})();