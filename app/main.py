"""Main FastAPI application entry point."""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.db.connection import db_pool
from app.utils.logger import logger
from app.api import health


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan context manager.
    Handles startup and shutdown events.
    """
    # Startup
    logger.info(
        "Starting application",
        extra={
            "app_name": settings.app_name,
            "environment": settings.environment
        }
    )

    # Connect to database
    try:
        await db_pool.connect()
        logger.info("Database connection established")
    except Exception as e:
        logger.error("Failed to connect to database", extra={"error": str(e)})
        raise

    yield

    # Shutdown
    logger.info("Shutting down application")

    # Disconnect from database
    try:
        await db_pool.disconnect()
        logger.info("Database connection closed")
    except Exception as e:
        logger.error("Error closing database connection", extra={"error": str(e)})


# Create FastAPI app
app = FastAPI(
    title=settings.app_name,
    description="Automated trading bot for day/swing trading",
    version="1.0.0",
    lifespan=lifespan
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(health.router)


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": "Welcome to Trader Bot API",
        "version": "1.0.0",
        "environment": settings.environment,
        "docs": "/docs"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug
    )
