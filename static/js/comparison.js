/**
 * Album Comparison JavaScript Module
 * Handles interactive comparison functionality, album selection, and dynamic updates
 */

console.log('comparison.js loaded');

class AlbumComparison {
    constructor() {
        this.ratedAlbums = [];
        this.currentComparison = null;
        this.isLoading = false;
        this.searchDebounceTimers = {};
        this.initializeComponents();
    }
    
    async initializeComponents() {
        try {
            // Show loading state
            this.showLoadingState(true);
            
            // Load rated albums for selection
            await this.loadRatedAlbums();
            
            // Setup event listeners
            this.setupEventListeners();
            
            // Check URL parameters for initial comparison - AFTER albums are loaded
            this.checkURLParameters();
            
            // Hide loading state
            this.showLoadingState(false);
            
        } catch (error) {
            console.error('Failed to initialize album comparison:', error);
            this.showLoadingState(false);
            this.showError('Failed to initialize comparison tool. Please refresh the page.');
        }
    }
    
    async loadRatedAlbums() {
        try {
            console.log('Loading rated albums...');
            const response = await fetch('/api/v1/albums/rated');
            
            if (!response.ok) {
                const errorText = await response.text();
                throw new Error(`HTTP ${response.status}: ${errorText}`);
            }
            
            const data = await response.json();
            console.log('API Response:', data);
            
            if (!data || !Array.isArray(data.albums)) {
                throw new Error('Invalid response format - expected albums array');
            }
            
            this.ratedAlbums = data.albums;
            console.log(`Loaded ${this.ratedAlbums.length} rated albums`);
            
            // Log first few albums to verify structure
            if (this.ratedAlbums.length > 0) {
                console.log('Sample album structure:', this.ratedAlbums[0]);
                console.log('Album IDs:', this.ratedAlbums.map(a => a.id));
            }
            
            // Setup search inputs
            this.setupSearchInputs();
            
        } catch (error) {
            console.error('Error loading rated albums:', error);
            this.showError(`Failed to load albums: ${error.message}`);
            throw error; // Re-throw to be caught by initializeComponents
        }
    }
    
    setupSearchInputs() {
        const album1Search = document.getElementById('album1-search');
        const album2Search = document.getElementById('album2-search');
        
        console.log('DOM Check - album1-search:', album1Search);
        console.log('DOM Check - album2-search:', album2Search);
        
        if (!album1Search || !album2Search) {
            console.error('Search inputs not found in DOM');
            console.log('Available elements with ID containing "album":', 
                Array.from(document.querySelectorAll('[id*="album"]')).map(el => el.id));
            return;
        }
        
        console.log('Setting up search inputs', album1Search, album2Search);
        
        // Setup search input event listeners
        album1Search.addEventListener('input', (e) => this.handleSearchInput(e, 1));
        album1Search.addEventListener('focus', (e) => this.handleSearchFocus(e, 1));
        album1Search.addEventListener('blur', (e) => this.handleSearchBlur(e, 1));
        album1Search.addEventListener('keydown', (e) => this.handleSearchKeydown(e, 1));
        
        album2Search.addEventListener('input', (e) => this.handleSearchInput(e, 2));
        album2Search.addEventListener('focus', (e) => this.handleSearchFocus(e, 2));
        album2Search.addEventListener('blur', (e) => this.handleSearchBlur(e, 2));
        album2Search.addEventListener('keydown', (e) => this.handleSearchKeydown(e, 2));
        
        // Close dropdowns when clicking outside
        document.addEventListener('click', (e) => this.handleDocumentClick(e));
        
        console.log('Search inputs setup completed');
    }
    
    handleSearchInput(event, albumNumber) {
        const searchTerm = event.target.value.trim();
        
        console.log(`=== SEARCH INPUT EVENT ===`);
        console.log(`Album ${albumNumber} search: "${searchTerm}"`);
        console.log(`Event type: ${event.type}`);
        console.log(`Albums available: ${this.ratedAlbums.length}`);
        
        // Clear any existing timer for this input
        if (this.searchDebounceTimers[albumNumber]) {
            clearTimeout(this.searchDebounceTimers[albumNumber]);
        }
        
        // If search is empty, hide results and clear selection
        if (!searchTerm) {
            console.log(`Empty search, hiding results for album ${albumNumber}`);
            this.hideSearchResults(albumNumber);
            this.clearAlbumSelection(albumNumber, false);
            return;
        }
        
        console.log(`Setting debounce timer for search...`);
        // Debounce search to avoid too many updates
        this.searchDebounceTimers[albumNumber] = setTimeout(() => {
            console.log(`Debounce timer fired, performing search...`);
            this.performSearch(searchTerm, albumNumber);
        }, 150);
    }
    
    handleSearchFocus(event, albumNumber) {
        const searchTerm = event.target.value.trim();
        if (searchTerm && !event.target.dataset.selectedId) {
            // Only show results if there's a search term and no selection
            this.performSearch(searchTerm, albumNumber);
        }
    }
    
    handleSearchBlur(event, albumNumber) {
        // Delay hiding results to allow for clicks on results
        setTimeout(() => {
            this.hideSearchResults(albumNumber);
        }, 200);
    }
    
    handleSearchKeydown(event, albumNumber) {
        const resultsContainer = document.getElementById(`album${albumNumber}-results`);
        const activeResult = resultsContainer.querySelector('.result-item.active');
        
        switch (event.key) {
            case 'ArrowDown':
                event.preventDefault();
                this.navigateResults(albumNumber, 'down');
                break;
            case 'ArrowUp':
                event.preventDefault();
                this.navigateResults(albumNumber, 'up');
                break;
            case 'Enter':
                event.preventDefault();
                if (activeResult) {
                    this.selectAlbum(albumNumber, JSON.parse(activeResult.dataset.album));
                }
                break;
            case 'Escape':
                this.hideSearchResults(albumNumber);
                event.target.blur();
                break;
        }
    }
    
    handleDocumentClick(event) {
        // Close all dropdowns if clicking outside
        if (!event.target.closest('.relative')) {
            this.hideSearchResults(1);
            this.hideSearchResults(2);
        }
    }
    
    performSearch(searchTerm, albumNumber) {
        console.log(`Performing search for "${searchTerm}" in album ${albumNumber}`);
        console.log(`Total albums available: ${this.ratedAlbums.length}`);
        
        const results = this.searchAlbums(searchTerm);
        console.log(`Found ${results.length} results:`, results);
        
        this.displaySearchResults(results, albumNumber);
    }
    
    searchAlbums(searchTerm) {
        const term = searchTerm.toLowerCase();
        
        return this.ratedAlbums
            .filter(album => {
                const albumName = (album.name || '').toLowerCase();
                const artistName = (album.artist || '').toLowerCase();
                return albumName.includes(term) || artistName.includes(term);
            })
            .map(album => ({
                ...album,
                relevance: this.calculateRelevance(album, term)
            }))
            .sort((a, b) => b.relevance - a.relevance)
            .slice(0, 10); // Limit to top 10 results
    }
    
    calculateRelevance(album, searchTerm) {
        const albumName = (album.name || '').toLowerCase();
        const artistName = (album.artist || '').toLowerCase();
        
        let score = 0;
        
        // Exact matches get higher scores
        if (albumName === searchTerm) score += 100;
        if (artistName === searchTerm) score += 90;
        
        // Starts with matches
        if (albumName.startsWith(searchTerm)) score += 50;
        if (artistName.startsWith(searchTerm)) score += 40;
        
        // Contains matches
        if (albumName.includes(searchTerm)) score += 20;
        if (artistName.includes(searchTerm)) score += 15;
        
        // Higher rated albums get slight boost
        score += (album.score || 0) / 10;
        
        return score;
    }
    
    displaySearchResults(results, albumNumber) {
        const resultsContainer = document.getElementById(`album${albumNumber}-results`);
        const searchInput = document.getElementById(`album${albumNumber}-search`);
        
        if (!resultsContainer) {
            console.error(`Results container not found for album ${albumNumber}`);
            return;
        }
        
        if (results.length === 0) {
            resultsContainer.innerHTML = '<div class="p-3 text-muted text-sm">No albums found</div>';
            resultsContainer.classList.remove('hidden');
            searchInput.setAttribute('aria-expanded', 'true');
            return;
        }
        
        const resultItems = results.map((album, index) => this.createResultItem(album, index)).join('');
        resultsContainer.innerHTML = resultItems;
        resultsContainer.classList.remove('hidden');
        searchInput.setAttribute('aria-expanded', 'true');
        
        // Add click listeners to result items
        resultsContainer.querySelectorAll('.result-item').forEach(item => {
            item.addEventListener('click', () => {
                const album = JSON.parse(item.dataset.album);
                this.selectAlbum(albumNumber, album);
            });
        });
        
        console.log(`Displayed ${results.length} results for album ${albumNumber}`);
    }
    
    createResultItem(album, index) {
        return `
            <div class="result-item p-3 hover:bg-surface-secondary cursor-pointer border-b border-default last:border-b-0" 
                 data-album='${JSON.stringify(album)}'
                 role="option"
                 aria-selected="false"
                 id="album-option-${album.id}">
                <div class="flex items-center space-x-3">
                    <div class="flex-shrink-0">
                        <div class="w-10 h-10 bg-surface-secondary rounded flex items-center justify-center text-xs text-muted">
                            ${album.score || 0}
                        </div>
                    </div>
                    <div class="flex-1 min-w-0">
                        <div class="text-sm font-medium text-primary truncate">${album.name || 'Unknown Album'}</div>
                        <div class="text-sm text-muted truncate">${album.artist || 'Unknown Artist'}</div>
                        ${album.year ? `<div class="text-xs text-secondary">${album.year}</div>` : ''}
                    </div>
                    <div class="flex-shrink-0">
                        <div class="text-lg font-semibold text-blue-600">${album.score || 0}</div>
                    </div>
                </div>
            </div>
        `;
    }
    
    navigateResults(albumNumber, direction) {
        const resultsContainer = document.getElementById(`album${albumNumber}-results`);
        const items = resultsContainer.querySelectorAll('.result-item');
        const activeItem = resultsContainer.querySelector('.result-item.active');
        
        let newIndex = 0;
        
        if (activeItem) {
            const currentIndex = Array.from(items).indexOf(activeItem);
            activeItem.classList.remove('active');
            activeItem.setAttribute('aria-selected', 'false');
            
            if (direction === 'down') {
                newIndex = (currentIndex + 1) % items.length;
            } else {
                newIndex = (currentIndex - 1 + items.length) % items.length;
            }
        }
        
        if (items[newIndex]) {
            items[newIndex].classList.add('active');
            items[newIndex].setAttribute('aria-selected', 'true');
            items[newIndex].scrollIntoView({ block: 'nearest' });
        }
    }
    
    selectAlbum(albumNumber, album) {
        const searchInput = document.getElementById(`album${albumNumber}-search`);
        const clearButton = document.getElementById(`album${albumNumber}-clear`);
        
        // Set input value and store selected ID
        searchInput.value = `${album.name} - ${album.artist}`;
        searchInput.dataset.selectedId = album.id;
        
        // Show clear button
        clearButton.classList.remove('hidden');
        
        // Hide results
        this.hideSearchResults(albumNumber);
        
        // Update compare button
        this.updateCompareButton();
        
        console.log(`Selected album ${albumNumber}:`, album);
    }
    
    clearAlbumSelection(albumNumber, updateUI = true) {
        const searchInput = document.getElementById(`album${albumNumber}-search`);
        const clearButton = document.getElementById(`album${albumNumber}-clear`);
        
        if (updateUI) {
            searchInput.value = '';
        }
        searchInput.dataset.selectedId = '';
        clearButton.classList.add('hidden');
        
        this.hideSearchResults(albumNumber);
        this.updateCompareButton();
        
        console.log(`Cleared album ${albumNumber} selection`);
    }
    
    hideSearchResults(albumNumber) {
        const resultsContainer = document.getElementById(`album${albumNumber}-results`);
        const searchInput = document.getElementById(`album${albumNumber}-search`);
        
        if (resultsContainer) {
            resultsContainer.classList.add('hidden');
        }
        
        if (searchInput) {
            searchInput.setAttribute('aria-expanded', 'false');
        }
        
        // Remove active state from all items
        if (resultsContainer) {
            resultsContainer.querySelectorAll('.result-item.active').forEach(item => {
                item.classList.remove('active');
                item.setAttribute('aria-selected', 'false');
            });
        }
    }
    
    setupEventListeners() {
        const compareButton = document.getElementById('compare-button');
        
        if (compareButton) {
            compareButton.addEventListener('click', () => this.compareAlbums());
        }
        
        // Setup keyboard shortcuts
        document.addEventListener('keydown', (e) => {
            if (e.ctrlKey || e.metaKey) {
                if (e.key === 'Enter') {
                    e.preventDefault();
                    this.compareAlbums();
                }
            }
        });
    }
    
    updateCompareButton() {
        const compareButton = document.getElementById('compare-button');
        if (!compareButton) return;
        
        // Get selected album IDs from search inputs
        const album1Id = this.getSelectedAlbumId(1);
        const album2Id = this.getSelectedAlbumId(2);
        
        console.log('Updating compare button:', { album1Id, album2Id });
        
        // Enable button only if both albums selected and different
        const canCompare = album1Id && album2Id && album1Id !== album2Id;
        compareButton.disabled = !canCompare;
        
        if (album1Id && album2Id && album1Id === album2Id) {
            this.showError('Please select two different albums to compare');
        } else {
            this.hideError();
        }
    }
    
    getSelectedAlbumId(albumNumber) {
        // Get from search input
        const searchInput = document.getElementById(`album${albumNumber}-search`);
        if (searchInput && searchInput.dataset.selectedId) {
            return searchInput.dataset.selectedId;
        }
        
        return null;
    }
    
    async compareAlbums() {
        const album1Id = this.getSelectedAlbumId(1);
        const album2Id = this.getSelectedAlbumId(2);
        
        if (!album1Id || !album2Id) {
            this.showError('Please select both albums to compare');
            return;
        }
        
        if (album1Id === album2Id) {
            this.showError('Please select two different albums to compare');
            return;
        }
        
        try {
            this.showLoading(true);
            this.hideError();
            
            // Redirect to comparison view with both albums
            window.location.href = `/albums/compare?album1=${album1Id}&album2=${album2Id}`;
            
        } catch (error) {
            console.error('Error comparing albums:', error);
            this.showError('Failed to compare albums. Please try again.');
        } finally {
            this.showLoading(false);
        }
    }
    
    checkURLParameters() {
        const urlParams = new URLSearchParams(window.location.search);
        const album1Id = urlParams.get('album1');
        const album2Id = urlParams.get('album2');
        
        console.log('=== URL PARAMETER CHECK ===');
        console.log('URL:', window.location.search);
        console.log('Parsed params:', { album1Id, album2Id });
        console.log('Albums loaded:', this.ratedAlbums.length);
        
        if (album1Id || album2Id) {
            console.log('Attempting to set selected albums...');
            this.setSelectedAlbums(album1Id, album2Id);
        } else {
            console.log('No URL parameters found');
        }
    }
    
    setSelectedAlbums(album1Id, album2Id) {
        console.log('=== SET SELECTED ALBUMS ===');
        console.log('Input IDs:', { album1Id, album2Id });
        
        // Handle search inputs
        const album1Search = document.getElementById('album1-search');
        const album2Search = document.getElementById('album2-search');
        const album1Clear = document.getElementById('album1-clear');
        const album2Clear = document.getElementById('album2-clear');
        
        console.log('DOM elements found:', {
            album1Search: !!album1Search,
            album2Search: !!album2Search,
            album1Clear: !!album1Clear,
            album2Clear: !!album2Clear
        });
        
        if (album1Search && album1Id) {
            console.log(`Looking for album with ID ${album1Id} in ${this.ratedAlbums.length} albums`);
            const album1 = this.ratedAlbums.find(a => {
                console.log(`Comparing: ${a.id} (type: ${typeof a.id}) with ${album1Id} (type: ${typeof album1Id})`);
                return a.id == album1Id;
            });
            
            if (album1) {
                const displayText = `${album1.name} - ${album1.artist}`;
                console.log(`Found album1: ${displayText}`);
                album1Search.value = displayText;
                album1Search.dataset.selectedId = album1Id;
                // Show clear button
                if (album1Clear) {
                    album1Clear.classList.remove('hidden');
                }
                console.log(`Pre-filled album1 search with: ${album1.name}`);
            } else {
                console.warn(`Album with ID ${album1Id} not found in rated albums`);
                console.log('Available album IDs:', this.ratedAlbums.map(a => a.id));
                this.showError(`First album (ID: ${album1Id}) not found or not rated`);
            }
        }
        
        if (album2Search && album2Id) {
            const album2 = this.ratedAlbums.find(a => a.id == album2Id);
            if (album2) {
                album2Search.value = `${album2.name} - ${album2.artist}`;
                album2Search.dataset.selectedId = album2Id;
                // Show clear button
                if (album2Clear) {
                    album2Clear.classList.remove('hidden');
                }
                console.log(`Pre-filled album2 search with: ${album2.name}`);
            } else {
                console.warn(`Album with ID ${album2Id} not found in rated albums`);
                this.showError(`Second album (ID: ${album2Id}) not found or not rated`);
            }
        }
        
        // Update compare button state
        this.updateCompareButton();
    }
    
    showLoadingState(show) {
        const container = document.querySelector('.max-w-7xl');
        if (!container) return;
        
        if (show) {
            // Add loading overlay to the page
            if (!document.getElementById('comparison-loading')) {
                const loadingDiv = document.createElement('div');
                loadingDiv.id = 'comparison-loading';
                loadingDiv.className = 'fixed inset-0 bg-background bg-opacity-75 dark:bg-opacity-90 flex items-center justify-center z-50';
                loadingDiv.innerHTML = `
                    <div class="text-center">
                        <div class="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto mb-4"></div>
                        <p class="text-secondary">Loading albums for comparison...</p>
                    </div>
                `;
                document.body.appendChild(loadingDiv);
            }
        } else {
            // Remove loading overlay
            const loadingDiv = document.getElementById('comparison-loading');
            if (loadingDiv) {
                loadingDiv.remove();
            }
        }
    }
    
    showLoading(show) {
        const compareButton = document.getElementById('compare-button');
        if (!compareButton) return;
        
        if (show) {
            compareButton.disabled = true;
            compareButton.textContent = 'Comparing...';
            compareButton.classList.add('loading');
        } else {
            compareButton.textContent = 'Compare Albums';
            compareButton.classList.remove('loading');
            this.updateCompareButton(); // Re-evaluate button state
        }
    }
    
    showError(message) {
        this.hideError(); // Remove any existing error
        
        const container = document.querySelector('.max-w-7xl');
        if (!container) return;
        
        const errorDiv = document.createElement('div');
        errorDiv.id = 'comparison-error';
        errorDiv.className = 'bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-800 rounded-md p-4 mb-4';
        errorDiv.innerHTML = `
            <div class="flex items-center">
                <svg class="w-5 h-5 text-red-400 mr-2" fill="currentColor" viewBox="0 0 20 20">
                    <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clip-rule="evenodd"></path>
                </svg>
                <span class="text-red-800 dark:text-red-400 text-sm font-medium">${message}</span>
            </div>
        `;
        
        container.insertBefore(errorDiv, container.firstChild);
        
        // Auto-hide after 5 seconds
        setTimeout(() => this.hideError(), 5000);
    }
    
    hideError() {
        const errorDiv = document.getElementById('comparison-error');
        if (errorDiv) {
            errorDiv.remove();
        }
    }
}

// Global comparison functionality
window.albumComparison = null;

// Global functions for template usage
window.compareAlbums = function() {
    if (window.albumComparison) {
        window.albumComparison.compareAlbums();
    }
};

window.clearAlbumSelection = function(albumNumber) {
    if (window.albumComparison) {
        window.albumComparison.clearAlbumSelection(albumNumber, true);
    }
};

// Initialize comparison functionality when DOM is ready
console.log('Setting up DOMContentLoaded listener');
document.addEventListener('DOMContentLoaded', function() {
    console.log('DOMContentLoaded fired');
    // Only initialize on comparison page
    const comparisonPage = document.querySelector('.max-w-7xl');
    const pageTitle = document.title;
    
    console.log('Page check:', {
        comparisonPage: !!comparisonPage,
        pageTitle: pageTitle,
        pathname: window.location.pathname
    });
    
    if (comparisonPage && (pageTitle.includes('Compare') || window.location.pathname.includes('compare'))) {
        console.log('Initializing album comparison');
        window.albumComparison = new AlbumComparison();
    } else {
        console.log('Not a comparison page, skipping initialization');
    }
});

// Quick comparison functionality for album pages
class QuickCompare {
    static async openComparisonModal(currentAlbumId) {
        try {
            // Redirect to comparison page with current album pre-selected
            window.location.href = `/albums/compare?album1=${currentAlbumId}`;
        } catch (error) {
            console.error('Error opening comparison:', error);
        }
    }
}

// Global functions for quick comparison
window.openComparisonModal = QuickCompare.openComparisonModal;