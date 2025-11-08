"""APScheduler configuration and job scheduling."""

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import asyncio
import aiohttp

from app.utils.logger import logger
from app.utils.market_hours import MarketHours
from app.config import settings


class SchedulerService:
    """Service for managing scheduled tasks.

    All jobs call API endpoints (not services directly) to ensure consistent flow
    and proper database connection handling.
    """

    def __init__(self):
        self.scheduler = AsyncIOScheduler(timezone='America/New_York')
        self.api_base_url = f"http://{settings.host}:{settings.port}/api/v1"
        self.symbols = ["SPY"]  # Symbols to track

    async def ingest_market_data_job(self):
        """
        Scheduled job to ingest latest market data.

        Runs every minute at :05 seconds during market hours.
        Calls the API endpoint instead of service directly.
        Respects extended hours setting from config.
        """
        try:
            logger.info("Running data ingestion job")

            # Check if market is open (respects extended hours setting)
            if not MarketHours.is_extended_market_open():
                logger.debug("Market is closed, skipping data ingestion job")
                return

            # Call the ingest endpoint for each symbol
            async with aiohttp.ClientSession() as session:
                tasks = []
                for symbol in self.symbols:
                    url = f"{self.api_base_url}/market-data/{symbol}/ingest-latest"
                    tasks.append(session.post(url))

                responses = await asyncio.gather(*tasks, return_exceptions=True)

                successful = sum(1 for r in responses if not isinstance(r, Exception) and r.status == 200)
                failed = len(responses) - successful

            logger.info(
                "Data ingestion job completed",
                extra={"total": len(self.symbols), "successful": successful, "failed": failed}
            )

        except Exception as e:
            logger.error(
                "Error in data ingestion job",
                extra={"error": str(e)}
            )

    async def data_health_check_job(self):
        """
        Scheduled job to perform data health checks.

        Runs every 15 minutes during market hours.
        Respects extended hours setting from config.
        """
        try:
            logger.info("Running data health check job")

            # Check if market is open (respects extended hours setting)
            if not MarketHours.is_extended_market_open():
                logger.debug("Market is closed, skipping health check job")
                return

            # Call the health endpoint for each symbol
            async with aiohttp.ClientSession() as session:
                for symbol in self.symbols:
                    url = f"{self.api_base_url}/market-data/{symbol}/health?hours_back=24"
                    try:
                        async with session.get(url) as response:
                            if response.status == 200:
                                health = await response.json()
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
                            else:
                                logger.error(
                                    "Health check failed",
                                    extra={"symbol": symbol, "status": response.status}
                                )
                    except Exception as e:
                        logger.error(
                            "Error calling health endpoint",
                            extra={"symbol": symbol, "error": str(e)}
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
        Respects extended hours setting from config.
        """
        try:
            logger.info("Running materialized view refresh job")

            # Check if market is open (respects extended hours setting)
            if not MarketHours.is_extended_market_open():
                logger.debug("Market is closed, skipping view refresh job")
                return

            # Call the views/refresh endpoint
            async with aiohttp.ClientSession() as session:
                url = f"{self.api_base_url}/market-data/views/refresh?concurrently=true"
                try:
                    async with session.post(url) as response:
                        if response.status == 200:
                            results = await response.json()
                            logger.info(
                                "Materialized view refresh job completed",
                                extra=results
                            )
                        else:
                            logger.error(
                                "View refresh failed",
                                extra={"status": response.status}
                            )
                except Exception as e:
                    logger.error(
                        "Error calling views/refresh endpoint",
                        extra={"error": str(e)}
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
            # This gives Tradier time to aggregate the previous minute's bar
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

            # NOTE: Data health check job is DISABLED
            # This job logs issues to stdout without persistence or deduplication.
            # Without a database-backed issue tracking system, it will:
            # - Re-log the same health failures every 15 min (96+ duplicates per day)
            # - Lose all issue history on app restart
            # - Not work correctly with multiple app instances
            #
            # To enable this job properly, implement:
            # 1. Database table for tracking issues (first_seen, last_seen, resolved_at)
            # 2. Deduplication logic (only log when issue state changes)
            # 3. Auto-resolution (mark resolved when health restored)
            # 4. Admin UI endpoint to view/manage unresolved issues
            #
            # For now, use manual API calls:
            # - GET /api/v1/market-data/{symbol}/health?days_back=7

            # Data health check job - runs every 15 minutes (includes gap detection)
            # self.scheduler.add_job(
            #     self.data_health_check_job,
            #     trigger=CronTrigger(
            #         minute='*/15',
            #         timezone='America/New_York'
            #     ),
            #     id='data_health_check',
            #     name='Data Health Check',
            #     replace_existing=True,
            #     max_instances=1
            # )

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
