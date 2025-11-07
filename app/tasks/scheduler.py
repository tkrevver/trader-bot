"""APScheduler configuration and job scheduling."""

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime
import asyncio

from app.utils.logger import logger
from app.utils.market_hours import MarketHours
from app.services.data_ingestion import get_data_ingestion_service
from app.services.materialized_view_refresh import MaterializedViewRefreshService


class SchedulerService:
    """Service for managing scheduled tasks."""

    def __init__(self):
        self.scheduler = AsyncIOScheduler(timezone='America/New_York')
        self.data_ingestion = get_data_ingestion_service()

    async def ingest_market_data_job(self):
        """
        Scheduled job to ingest latest market data.

        Runs every minute at :05 seconds during market hours.
        """
        try:
            logger.info("Running data ingestion job")

            # Check if market is open
            if not MarketHours.is_market_open():
                logger.debug("Market is closed, skipping data ingestion job")
                return

            # Ingest latest bars for all symbols
            results = await self.data_ingestion.ingest_latest_bars_all_symbols()

            logger.info(
                "Data ingestion job completed",
                extra=results
            )

        except Exception as e:
            logger.error(
                "Error in data ingestion job",
                extra={"error": str(e)}
            )

    async def gap_detection_job(self):
        """
        Scheduled job to detect and backfill gaps.

        Runs once per hour during market hours.
        """
        try:
            logger.info("Running gap detection job")

            # Check if market is open
            if not MarketHours.is_market_open():
                logger.debug("Market is closed, skipping gap detection job")
                return

            # Detect and backfill gaps for all symbols
            symbols = self.data_ingestion.symbols

            for symbol in symbols:
                gaps = await self.data_ingestion.detect_and_backfill_gaps(
                    symbol=symbol,
                    days_back=5
                )

                if gaps:
                    logger.warning(
                        "Gaps detected and backfilled",
                        extra={"symbol": symbol, "gap_count": len(gaps)}
                    )

        except Exception as e:
            logger.error(
                "Error in gap detection job",
                extra={"error": str(e)}
            )

    async def data_health_check_job(self):
        """
        Scheduled job to perform data health checks.

        Runs every 15 minutes during market hours.
        """
        try:
            logger.info("Running data health check job")

            # Check if market is open
            if not MarketHours.is_market_open():
                logger.debug("Market is closed, skipping health check job")
                return

            # Perform health check for all symbols
            symbols = self.data_ingestion.symbols

            for symbol in symbols:
                health = await self.data_ingestion.get_data_health_check(
                    symbol=symbol,
                    hours_back=24
                )

                if not health.get("healthy", False):
                    logger.warning(
                        "Data health check failed",
                        extra=health
                    )
                else:
                    logger.info(
                        "Data health check passed",
                        extra=health
                    )

        except Exception as e:
            logger.error(
                "Error in data health check job",
                extra={"error": str(e)}
            )

    async def refresh_materialized_views_job(self):
        """
        Scheduled job to refresh materialized views for aggregated timeframes.

        Runs every 5 minutes during market hours to keep aggregated data fresh.
        Uses CONCURRENT refresh to avoid locking the views.
        """
        try:
            logger.info("Running materialized view refresh job")

            # Check if market is open (only refresh during trading hours)
            if not MarketHours.is_market_open():
                logger.debug("Market is closed, skipping view refresh job")
                return

            # Refresh all views concurrently (non-blocking)
            results = await MaterializedViewRefreshService.refresh_all_views(
                concurrently=True
            )

            logger.info(
                "Materialized view refresh job completed",
                extra=results
            )

        except Exception as e:
            logger.error(
                "Error in materialized view refresh job",
                extra={"error": str(e)}
            )

    def start(self):
        """Start the scheduler and register jobs."""
        try:
            # Data ingestion job - runs every minute at :05 seconds
            # This gives Polygon.io time to aggregate the previous minute's bar
            self.scheduler.add_job(
                self.ingest_market_data_job,
                trigger=CronTrigger(
                    minute='*',
                    second=5,
                    timezone='America/New_York'
                ),
                id='data_ingestion',
                name='Market Data Ingestion',
                replace_existing=True,
                max_instances=1,
                misfire_grace_time=30  # Allow 30 seconds grace time for missed jobs
            )

            # Gap detection job - runs hourly at :10 minutes past the hour
            self.scheduler.add_job(
                self.gap_detection_job,
                trigger=CronTrigger(
                    minute=10,
                    timezone='America/New_York'
                ),
                id='gap_detection',
                name='Gap Detection and Backfill',
                replace_existing=True,
                max_instances=1
            )

            # Data health check job - runs every 15 minutes
            self.scheduler.add_job(
                self.data_health_check_job,
                trigger=CronTrigger(
                    minute='*/15',
                    timezone='America/New_York'
                ),
                id='data_health_check',
                name='Data Health Check',
                replace_existing=True,
                max_instances=1
            )

            # Materialized view refresh job - runs every 5 minutes
            # Refreshes aggregated timeframe views (5min, 15min, 30min, daily)
            self.scheduler.add_job(
                self.refresh_materialized_views_job,
                trigger=CronTrigger(
                    minute='*/5',
                    timezone='America/New_York'
                ),
                id='refresh_materialized_views',
                name='Refresh Materialized Views',
                replace_existing=True,
                max_instances=1
            )

            # Start the scheduler
            self.scheduler.start()

            logger.info(
                "Scheduler started successfully",
                extra={
                    "jobs": [
                        {"id": job.id, "name": job.name, "next_run": job.next_run_time}
                        for job in self.scheduler.get_jobs()
                    ]
                }
            )

        except Exception as e:
            logger.error(
                "Error starting scheduler",
                extra={"error": str(e)}
            )
            raise

    def shutdown(self):
        """Shutdown the scheduler gracefully."""
        try:
            logger.info("Shutting down scheduler")
            self.scheduler.shutdown(wait=True)
            logger.info("Scheduler shut down successfully")

        except Exception as e:
            logger.error(
                "Error shutting down scheduler",
                extra={"error": str(e)}
            )

    def get_job_status(self) -> list:
        """
        Get status of all scheduled jobs.

        Returns:
            list: List of job information
        """
        try:
            jobs = []
            for job in self.scheduler.get_jobs():
                jobs.append({
                    "id": job.id,
                    "name": job.name,
                    "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None,
                    "trigger": str(job.trigger)
                })
            return jobs

        except Exception as e:
            logger.error(
                "Error getting job status",
                extra={"error": str(e)}
            )
            return []

    def pause_job(self, job_id: str) -> bool:
        """
        Pause a scheduled job.

        Args:
            job_id: Job ID

        Returns:
            bool: True if paused successfully
        """
        try:
            self.scheduler.pause_job(job_id)
            logger.info(f"Job paused: {job_id}")
            return True

        except Exception as e:
            logger.error(
                "Error pausing job",
                extra={"job_id": job_id, "error": str(e)}
            )
            return False

    def resume_job(self, job_id: str) -> bool:
        """
        Resume a paused job.

        Args:
            job_id: Job ID

        Returns:
            bool: True if resumed successfully
        """
        try:
            self.scheduler.resume_job(job_id)
            logger.info(f"Job resumed: {job_id}")
            return True

        except Exception as e:
            logger.error(
                "Error resuming job",
                extra={"job_id": job_id, "error": str(e)}
            )
            return False


# Singleton instance
_scheduler_service = None


def get_scheduler_service() -> SchedulerService:
    """Get or create scheduler service instance."""
    global _scheduler_service
    if _scheduler_service is None:
        _scheduler_service = SchedulerService()
    return _scheduler_service
