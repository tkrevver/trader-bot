"""Health check API endpoints."""

from fastapi import APIRouter, status
from pydantic import BaseModel
from typing import Dict
from app.config import settings
from app.db.connection import db_pool
from app.tasks.scheduler import get_scheduler_service
from app.utils.logger import logger


router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    """Health check response model."""
    status: str
    version: str
    environment: str


class DetailedHealthResponse(BaseModel):
    """Detailed health check response model."""
    status: str
    version: str
    environment: str
    components: Dict[str, str]


@router.get("/health", response_model=HealthResponse, status_code=status.HTTP_200_OK)
async def health_check():
    """
    Basic health check endpoint.

    Returns:
        HealthResponse: Basic health status
    """
    return HealthResponse(
        status="healthy",
        version="1.0.0",
        environment=settings.environment
    )


@router.get("/health/detailed", response_model=DetailedHealthResponse, status_code=status.HTTP_200_OK)
async def detailed_health_check():
    """
    Detailed health check endpoint with component status.

    Returns:
        DetailedHealthResponse: Detailed health status including components
    """
    components = {}

    # Check database connection
    try:
        if db_pool._pool is not None:
            await db_pool.fetchval("SELECT 1")
            bar_count = await db_pool.fetchval("SELECT COUNT(*) FROM ohlcv_1min")
            components["database"] = f"healthy ({bar_count} bars)"
        else:
            components["database"] = "disconnected"
    except Exception as e:
        logger.error("Database health check failed", extra={"error": str(e)})
        components["database"] = f"unhealthy: {str(e)}"

    # Check scheduler
    try:
        scheduler = get_scheduler_service()
        is_running = scheduler.scheduler.running
        job_count = len(scheduler.scheduler.get_jobs())
        components["scheduler"] = f"{'running' if is_running else 'stopped'} ({job_count} jobs)"
    except Exception as e:
        components["scheduler"] = f"unhealthy: {str(e)}"

    # Check Polygon.io
    try:
        if settings.polygon_api_key and settings.polygon_rest_url:
            components["polygon"] = "configured"
        else:
            components["polygon"] = "not_configured"
    except Exception as e:
        components["polygon"] = f"error: {str(e)}"

    # Check Broker (placeholder - will implement later)
    components["broker"] = "not_configured"

    # Determine overall status
    # Consider healthy if all components are either healthy, configured, or not_configured
    overall_status = "healthy" if all(
        not v.startswith("unhealthy") and not v.startswith("error")
        for v in components.values()
    ) else "unhealthy"

    return DetailedHealthResponse(
        status=overall_status,
        version="1.0.0",
        environment=settings.environment,
        components=components
    )
