/**
 * Progress indicator for lazy loading
 * Shows loading progress bar at top of page
 */

(function() {
    'use strict';
    
    let progressBar = null;
    let progressBarInner = null;
    let updateTimer = null;
    
    /**
     * Create progress bar element
     */
    function createProgressBar() {
        if (progressBar) return;
        
        progressBar = document.createElement('div');
        progressBar.className = 'lazy-load-progress';
        
        progressBarInner = document.createElement('div');
        progressBarInner.className = 'lazy-load-progress-bar';
        
        progressBar.appendChild(progressBarInner);
        document.body.appendChild(progressBar);
    }
    
    /**
     * Update progress bar
     */
    function updateProgress() {
        if (!window.LazyLoad) return;
        
        const stats = window.LazyLoad.getStats();
        
        if (stats.total === 0) {
            hideProgress();
            return;
        }
        
        const percentage = stats.percentage;
        
        if (!progressBar) {
            createProgressBar();
        }
        
        // Show progress bar
        progressBar.classList.add('active');
        progressBarInner.style.width = percentage + '%';
        
        // Hide when complete
        if (percentage >= 100) {
            setTimeout(hideProgress, 500);
        }
    }
    
    /**
     * Hide progress bar
     */
    function hideProgress() {
        if (progressBar) {
            progressBar.classList.remove('active');
            setTimeout(() => {
                progressBarInner.style.width = '0';
            }, 300);
        }
        
        if (updateTimer) {
            clearInterval(updateTimer);
            updateTimer = null;
        }
    }
    
    /**
     * Start monitoring progress
     */
    function startMonitoring() {
        if (updateTimer) return;
        
        // Update every 100ms while loading
        updateTimer = setInterval(updateProgress, 100);
        
        // Initial update
        updateProgress();
    }
    
    /**
     * Initialize progress monitoring
     */
    function init() {
        // Wait for LazyLoad to be available
        if (!window.LazyLoad) {
            setTimeout(init, 100);
            return;
        }
        
        // Listen for lazy load events
        document.addEventListener('lazyload:loaded', updateProgress);
        document.addEventListener('lazyload:error', updateProgress);
        
        // Start monitoring if images exist
        const lazyImages = document.querySelectorAll('img[data-src]');
        if (lazyImages.length > 0) {
            startMonitoring();
        }
        
        // Monitor for dynamically added images
        const observer = new MutationObserver(() => {
            const newLazyImages = document.querySelectorAll('img[data-src]');
            if (newLazyImages.length > 0 && !updateTimer) {
                startMonitoring();
            }
        });
        
        observer.observe(document.body, {
            childList: true,
            subtree: true
        });
    }
    
    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
    
})();