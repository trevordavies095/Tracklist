from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
import logging
import os
from .database import create_tables, init_db
from .exceptions import TracklistException, NotFoundError, ValidationError, ConflictError
from .logging_config import setup_logging

# Setup logging
log_level = os.getenv("LOG_LEVEL", "INFO")
log_file = os.getenv("LOG_FILE", "logs/tracklist.log") if os.getenv("ENABLE_FILE_LOGGING", "false").lower() == "true" else None
setup_logging(level=log_level, log_file=log_file)

logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="Tracklist",
    description="Self-hostable music album rating application",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)


@app.on_event("startup")
async def startup_event():
    """Initialize database on startup"""
    logger.info("Starting Tracklist application...")
    try:
        create_tables()
        init_db()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "tracklist"}


@app.get("/")
async def root():
    """Root endpoint"""
    return {"message": "Welcome to Tracklist - Music Album Rating System"}


@app.exception_handler(TracklistException)
async def tracklist_exception_handler(request: Request, exc: TracklistException):
    """Handle custom Tracklist exceptions"""
    logger.error(f"Tracklist exception: {exc.message}", extra={"details": exc.details})
    return JSONResponse(
        status_code=500,
        content={
            "error": exc.message,
            "details": exc.details
        }
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle request validation errors"""
    logger.warning(f"Validation error: {exc.errors()}")
    return JSONResponse(
        status_code=422,
        content={
            "error": "Validation error",
            "details": exc.errors()
        }
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler"""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "message": "An unexpected error occurred"
        }
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)