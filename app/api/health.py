"""Health check API endpoints."""

from fastapi import APIRouter, status
from pydantic import BaseModel
from typing import Dict
from app.config import settings
from app.db.connection import db_pool
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
            components["database"] = "healthy"
        else:
            components["database"] = "disconnected"
    except Exception as e:
        logger.error("Database health check failed", extra={"error": str(e)})
        components["database"] = f"unhealthy: {str(e)}"

    # Check Polygon.io (placeholder - will implement later)
    components["polygon"] = "not_configured"

    # Check Broker (placeholder - will implement later)
    components["broker"] = "not_configured"

    # Determine overall status
    overall_status = "healthy" if all(
        v in ["healthy", "not_configured"] for v in components.values()
    ) else "unhealthy"

    return DetailedHealthResponse(
        status=overall_status,
        version="1.0.0",
        environment=settings.environment,
        components=components
    )
