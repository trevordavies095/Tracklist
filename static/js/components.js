// Alpine.js component functions for Tracklist app

// Alpine.js component for progress tracking
function progressTracker(albumId, initialProgress) {
    return {
        albumId: albumId,
        totalTracks: initialProgress.total_tracks || 0,
        ratedTracks: initialProgress.rated_tracks || 0,
        completionPercentage: initialProgress.completion_percentage || 0,
        projectedScore: initialProgress.projected_score || null,
        finalScore: initialProgress.final_score || null,
        albumBonus: initialProgress.album_bonus || 0.33,
        isSubmitted: initialProgress.is_submitted || false,
        submitting: false,
        
        updateProgress(data) {
            // Update progress when a track rating is updated
            if (data.progress) {
                this.ratedTracks = data.progress.rated_tracks || this.ratedTracks;
                this.completionPercentage = data.progress.completion_percentage || this.completionPercentage;
                this.projectedScore = data.progress.projected_score;
                
                // Add animation class for score updates
                if (this.projectedScore !== null) {
                    const scoreElement = this.$el.querySelector('.text-purple-600');
                    if (scoreElement) {
                        scoreElement.classList.add('score-change');
                        setTimeout(() => {
                            scoreElement.classList.remove('score-change');
                        }, 500);
                    }
                }
            }
        },
        
        submitAlbum() {
            if (this.submitting || this.completionPercentage < 100) return;
            this.submitting = true;
        },
        
        init() {
            // Listen for HTMX events on the submit button
            const submitBtn = this.$el.querySelector('.submit-button');
            if (submitBtn) {
                submitBtn.addEventListener('htmx:afterRequest', (event) => {
                    if (event.detail.successful) {
                        this.submitting = false;
                        this.isSubmitted = true;
                    }
                });
                
                submitBtn.addEventListener('htmx:responseError', () => {
                    this.submitting = false;
                });
            }
            
            // Listen for album submitted event
            window.addEventListener('album-submitted', (event) => {
                if (event.detail.albumId === this.albumId) {
                    this.isSubmitted = true;
                    this.finalScore = event.detail.finalScore;
                }
            });
        },
        
        handleSubmissionSuccess(response) {
            this.submitting = false;
            this.isSubmitted = true;
            this.finalScore = response.rating_score;
            
            // Add celebration animation
            this.$el.classList.add('submission-success');
            setTimeout(() => {
                this.$el.classList.remove('submission-success');
            }, 600);
            
            // Dispatch success event
            this.$dispatch('album-submitted', {
                albumId: this.albumId,
                finalScore: this.finalScore
            });
        },
        
        handleSubmissionError() {
            this.submitting = false;
        }
    }
}

// Alpine.js component for rating buttons
function ratingButtons(trackId, initialRating) {
    return {
        trackId: trackId,
        currentRating: initialRating,
        targetRating: null,
        saving: false,
        
        setRating(rating) {
            if (this.saving) return;
            
            this.targetRating = rating;
            this.saving = true;
            
            // The HTMX request will handle the actual API call
            // We'll update the state when we receive the response
        },
        
        // Listen for HTMX events
        init() {
            // Listen for successful HTMX response
            this.$el.addEventListener('htmx:afterRequest', (event) => {
                if (event.detail.successful) {
                    this.currentRating = this.targetRating;
                    this.saving = false;
                    this.targetRating = null;
                }
            });
            
            // Listen for HTMX errors
            this.$el.addEventListener('htmx:responseError', () => {
                this.saving = false;
                this.targetRating = null;
            });
        },
        
        handleSuccess(response) {
            this.currentRating = this.targetRating;
            this.saving = false;
            this.targetRating = null;
            
            // Dispatch event for parent components to listen
            this.$dispatch('rating-updated', {
                trackId: this.trackId,
                rating: this.currentRating,
                progress: response
            });
        },
        
        handleError() {
            this.saving = false;
            this.targetRating = null;
        }
    }
}