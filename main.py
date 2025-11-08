"""Main FastAPI application entry point."""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.db.connection import db_pool
from app.db.partition_manager import ensure_partitions_exist
from app.utils.logger import logger
from app.api import health, market_data, scheduler, tasks, backtest
from app.tasks.scheduler import get_scheduler_service


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

    # Ensure database partitions exist for current + next 4 weeks
    try:
        logger.info("Checking database partitions")
        partition_result = await ensure_partitions_exist(weeks_ahead=4)
        logger.info(
            "Partition check completed",
            extra={
                "created": len(partition_result.get("created", [])),
                "total_existing": partition_result.get("total_existing", 0)
            }
        )
    except Exception as e:
        logger.error("Failed to ensure partitions exist", extra={"error": str(e)})
        # Don't raise - partitions might already exist

    # Start scheduler for data ingestion and background jobs
    try:
        logger.info("Starting scheduler")
        scheduler = get_scheduler_service()
        scheduler.start()
        logger.info("Scheduler started successfully")
    except Exception as e:
        logger.error("Failed to start scheduler", extra={"error": str(e)})
        # Continue even if scheduler fails to start

    yield

    # Shutdown
    logger.info("Shutting down application")

    # Shutdown scheduler
    try:
        scheduler = get_scheduler_service()
        scheduler.shutdown()
        logger.info("Scheduler shut down")
    except Exception as e:
        logger.error("Error shutting down scheduler", extra={"error": str(e)})

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
app.include_router(market_data.router)
app.include_router(scheduler.router)
app.include_router(tasks.router)
app.include_router(backtest.router)


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
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug
    )
