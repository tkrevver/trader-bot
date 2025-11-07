"""Scheduler management API endpoints."""

from fastapi import APIRouter
from app.tasks.scheduler import get_scheduler_service
from app.utils.logger import logger

router = APIRouter(prefix="/api/v1/scheduler", tags=["Scheduler"])


@router.get("/status")
async def get_scheduler_status():
    """
    Get scheduler status and job information.

    Returns:
        dict: Scheduler status and jobs
    """
    try:
        scheduler = get_scheduler_service()

        return {
            "running": scheduler.scheduler.running,
            "jobs": scheduler.get_job_status()
        }

    except Exception as e:
        logger.error("Error getting scheduler status", extra={"error": str(e)})
        return {
            "running": False,
            "error": str(e)
        }


@router.post("/jobs/{job_id}/pause")
async def pause_job(job_id: str):
    """
    Pause a scheduled job.

    Args:
        job_id: Job ID to pause

    Returns:
        dict: Result of pause operation
    """
    try:
        scheduler = get_scheduler_service()
        success = scheduler.pause_job(job_id)

        return {
            "success": success,
            "job_id": job_id,
            "action": "paused"
        }

    except Exception as e:
        logger.error(
            "Error pausing job",
            extra={"job_id": job_id, "error": str(e)}
        )
        return {
            "success": False,
            "job_id": job_id,
            "error": str(e)
        }


@router.post("/jobs/{job_id}/resume")
async def resume_job(job_id: str):
    """
    Resume a paused job.

    Args:
        job_id: Job ID to resume

    Returns:
        dict: Result of resume operation
    """
    try:
        scheduler = get_scheduler_service()
        success = scheduler.resume_job(job_id)

        return {
            "success": success,
            "job_id": job_id,
            "action": "resumed"
        }

    except Exception as e:
        logger.error(
            "Error resuming job",
            extra={"job_id": job_id, "error": str(e)}
        )
        return {
            "success": False,
            "job_id": job_id,
            "error": str(e)
        }
