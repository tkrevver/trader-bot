"""Service for refreshing PostgreSQL materialized views."""

from app.db.connection import db_pool
from app.utils.logger import logger


class MaterializedViewRefreshService:
    """Service to refresh aggregated timeframe materialized views."""

    VIEWS = ["ohlcv_5min", "ohlcv_15min", "ohlcv_30min", "ohlcv_daily"]

    @staticmethod
    async def refresh_view(view_name: str, concurrently: bool = True) -> bool:
        """
        Refresh a single materialized view.

        Args:
            view_name: Name of the materialized view
            concurrently: If True, refresh without locking the view (PostgreSQL 9.4+)

        Returns:
            bool: True if refresh was successful
        """
        try:
            refresh_cmd = f"REFRESH MATERIALIZED VIEW {'CONCURRENTLY' if concurrently else ''} {view_name}"

            logger.info(f"Refreshing materialized view: {view_name}")

            await db_pool.execute(refresh_cmd)

            logger.info(f"Successfully refreshed materialized view: {view_name}")
            return True

        except Exception as e:
            logger.error(
                f"Error refreshing materialized view: {view_name}",
                extra={"view": view_name, "error": str(e)}
            )
            return False

    @staticmethod
    async def refresh_all_views(concurrently: bool = True) -> dict:
        """
        Refresh all aggregated timeframe materialized views.

        Args:
            concurrently: If True, refresh without locking the views

        Returns:
            dict: Summary of refresh results
        """
        try:
            logger.info("Starting refresh of all materialized views")

            results = {
                "total": len(MaterializedViewRefreshService.VIEWS),
                "successful": 0,
                "failed": 0,
                "views": {}
            }

            for view_name in MaterializedViewRefreshService.VIEWS:
                success = await MaterializedViewRefreshService.refresh_view(
                    view_name=view_name,
                    concurrently=concurrently
                )

                results["views"][view_name] = "success" if success else "failed"

                if success:
                    results["successful"] += 1
                else:
                    results["failed"] += 1

            logger.info(
                "Completed refresh of all materialized views",
                extra=results
            )

            return results

        except Exception as e:
            logger.error(
                "Error refreshing all materialized views",
                extra={"error": str(e)}
            )
            return {
                "total": len(MaterializedViewRefreshService.VIEWS),
                "successful": 0,
                "failed": len(MaterializedViewRefreshService.VIEWS),
                "error": str(e)
            }

    @staticmethod
    async def get_view_stats() -> dict:
        """
        Get statistics about materialized views.

        Returns:
            dict: Statistics for each view
        """
        try:
            stats = {}

            for view_name in MaterializedViewRefreshService.VIEWS:
                # Get row count
                count_query = f"SELECT COUNT(*) FROM {view_name}"
                count = await db_pool.fetchval(count_query)

                # Get size
                size_query = f"SELECT pg_size_pretty(pg_total_relation_size('{view_name}'))"
                size = await db_pool.fetchval(size_query)

                # Get last refresh time (not available in standard PostgreSQL)
                # This would require tracking separately or using pg_stat_user_tables

                stats[view_name] = {
                    "row_count": count,
                    "size": size
                }

            logger.info("Retrieved materialized view statistics", extra=stats)
            return stats

        except Exception as e:
            logger.error(
                "Error getting view statistics",
                extra={"error": str(e)}
            )
            return {}


# Convenience functions
async def refresh_all_views(concurrently: bool = True) -> dict:
    """Refresh all materialized views."""
    return await MaterializedViewRefreshService.refresh_all_views(concurrently=concurrently)


async def refresh_view(view_name: str, concurrently: bool = True) -> bool:
    """Refresh a specific materialized view."""
    return await MaterializedViewRefreshService.refresh_view(
        view_name=view_name,
        concurrently=concurrently
    )


async def get_view_stats() -> dict:
    """Get statistics about materialized views."""
    return await MaterializedViewRefreshService.get_view_stats()
