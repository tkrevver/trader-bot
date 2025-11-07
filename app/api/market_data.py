"""Market data API endpoints."""

from fastapi import APIRouter, Query, HTTPException
from datetime import datetime, timedelta
from typing import Optional

from app.db.repositories.market_data import MarketDataRepository
from app.models.market_data import BarResponse, LatestBarResponse, MarketDataGap
from app.services.data_ingestion import get_data_ingestion_service
from app.services.materialized_view_refresh import MaterializedViewRefreshService
from app.utils.logger import logger

router = APIRouter(prefix="/api/v1/market-data", tags=["Market Data"])


@router.get("/{symbol}/latest", response_model=LatestBarResponse)
async def get_latest_bar(
    symbol: str,
    timeframe: str = Query(
        default="1min",
        description="Timeframe (1min, 5min, 15min, 30min, daily)"
    )
):
    """
    Get the latest OHLCV bar for a symbol.

    Args:
        symbol: Trading symbol (e.g., "SPY")
        timeframe: Timeframe (1min, 5min, 15min, 30min, daily)

    Returns:
        LatestBarResponse: Latest bar data
    """
    try:
        repo = MarketDataRepository()
        bar = await repo.get_latest_bar(symbol=symbol.upper(), timeframe=timeframe)

        return LatestBarResponse(
            symbol=symbol.upper(),
            timeframe=timeframe,
            bar=bar
        )

    except Exception as e:
        logger.error(
            "Error getting latest bar",
            extra={"symbol": symbol, "timeframe": timeframe, "error": str(e)}
        )
        raise HTTPException(
            status_code=500,
            detail=f"Error fetching latest bar: {str(e)}"
        )


@router.get("/{symbol}/history", response_model=BarResponse)
async def get_historical_bars(
    symbol: str,
    start_time: Optional[datetime] = Query(
        default=None,
        description="Start time (ISO format)"
    ),
    end_time: Optional[datetime] = Query(
        default=None,
        description="End time (ISO format)"
    ),
    timeframe: str = Query(
        default="1min",
        description="Timeframe (1min, 5min, 15min, 30min, daily)"
    ),
    limit: Optional[int] = Query(
        default=100,
        description="Maximum number of bars to return",
        le=5000
    )
):
    """
    Get historical OHLCV bars for a symbol.

    Args:
        symbol: Trading symbol (e.g., "SPY")
        start_time: Start time (defaults to 24 hours ago)
        end_time: End time (defaults to now)
        timeframe: Timeframe (1min, 5min, 15min, 30min, daily)
        limit: Maximum number of bars to return

    Returns:
        BarResponse: Historical bar data
    """
    try:
        # Set default time range if not provided
        if end_time is None:
            end_time = datetime.utcnow()
        if start_time is None:
            start_time = end_time - timedelta(hours=24)

        repo = MarketDataRepository()
        bars = await repo.get_bars(
            symbol=symbol.upper(),
            start_time=start_time,
            end_time=end_time,
            timeframe=timeframe,
            limit=limit
        )

        return BarResponse(
            symbol=symbol.upper(),
            timeframe=timeframe,
            bars=bars,
            count=len(bars)
        )

    except Exception as e:
        logger.error(
            "Error getting historical bars",
            extra={
                "symbol": symbol,
                "start": start_time.isoformat() if start_time else None,
                "end": end_time.isoformat() if end_time else None,
                "error": str(e)
            }
        )
        raise HTTPException(
            status_code=500,
            detail=f"Error fetching historical bars: {str(e)}"
        )


@router.get("/{symbol}/gaps", response_model=list[MarketDataGap])
async def check_for_gaps(
    symbol: str,
    days_back: int = Query(
        default=5,
        description="Number of days to check back",
        ge=1,
        le=30
    )
):
    """
    Check for gaps in market data.

    Args:
        symbol: Trading symbol (e.g., "SPY")
        days_back: Number of days to check back (1-30)

    Returns:
        list[MarketDataGap]: List of detected gaps
    """
    try:
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(days=days_back)

        repo = MarketDataRepository()
        gaps = await repo.check_for_gaps(
            symbol=symbol.upper(),
            start_time=start_time,
            end_time=end_time,
            expected_interval_minutes=1
        )

        logger.info(
            "Gap check completed",
            extra={"symbol": symbol, "gap_count": len(gaps)}
        )

        return gaps

    except Exception as e:
        logger.error(
            "Error checking for gaps",
            extra={"symbol": symbol, "error": str(e)}
        )
        raise HTTPException(
            status_code=500,
            detail=f"Error checking for gaps: {str(e)}"
        )


@router.post("/{symbol}/backfill")
async def backfill_data(
    symbol: str,
    start_date: Optional[datetime] = Query(
        None,
        description="Start date for backfill (required if days not provided)"
    ),
    end_date: Optional[datetime] = Query(
        None,
        description="End date for backfill (required if days not provided)"
    ),
    days: Optional[int] = Query(
        None,
        description="Number of days to backfill from today (alternative to start_date/end_date)",
        ge=1,
        le=30
    )
):
    """
    Backfill historical data for a symbol.

    This endpoint triggers a manual backfill of historical data from Polygon.io
    and automatically detects and fills any gaps in the data.

    You can specify dates in two ways:
    1. Explicit dates: Provide both start_date and end_date
    2. Days back: Provide days parameter (e.g., days=7 for last 7 days)

    Args:
        symbol: Trading symbol (e.g., "SPY")
        start_date: Start date for backfill (optional if using days)
        end_date: End date for backfill (optional if using days)
        days: Number of days to backfill from today (optional if using start_date/end_date)

    Returns:
        dict: Backfill results including gap detection
    """
    try:
        # Calculate dates based on input
        if days is not None:
            # Use days parameter
            end_date = datetime.utcnow()
            start_date = end_date - timedelta(days=days)
        elif start_date is None or end_date is None:
            # Neither days nor both dates provided
            raise HTTPException(
                status_code=400,
                detail="Either provide 'days' parameter OR both 'start_date' and 'end_date'"
            )

        logger.info(
            "Manual backfill triggered",
            extra={
                "symbol": symbol,
                "start": start_date.isoformat(),
                "end": end_date.isoformat()
            }
        )

        # Validate date range
        if start_date >= end_date:
            raise HTTPException(
                status_code=400,
                detail="start_date must be before end_date"
            )

        # Limit backfill range to avoid API rate limits
        max_days = 30
        if (end_date - start_date).days > max_days:
            raise HTTPException(
                status_code=400,
                detail=f"Date range too large. Maximum {max_days} days allowed."
            )

        # Perform backfill
        data_ingestion = get_data_ingestion_service()
        count = await data_ingestion.backfill_historical_data(
            symbol=symbol.upper(),
            start_date=start_date,
            end_date=end_date
        )

        # Always check for gaps to ensure data completeness
        gaps = await data_ingestion.detect_and_backfill_gaps(
            symbol=symbol.upper(),
            days_back=(end_date - start_date).days
        )

        return {
            "symbol": symbol.upper(),
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "bars_inserted": count,
            "gaps_found": len(gaps),
            "gaps": [
                {
                    "start_time": gap.start_time.isoformat(),
                    "end_time": gap.end_time.isoformat(),
                    "missing_bars": gap.missing_bars
                }
                for gap in gaps
            ],
            "success": count > 0
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Error backfilling data",
            extra={"symbol": symbol, "error": str(e)}
        )
        raise HTTPException(
            status_code=500,
            detail=f"Error backfilling data: {str(e)}"
        )


@router.get("/{symbol}/health")
async def get_data_health(
    symbol: str,
    hours_back: int = Query(
        default=24,
        description="Number of hours to check",
        ge=1,
        le=168  # 1 week max
    )
):
    """
    Get data health check for a symbol.

    Args:
        symbol: Trading symbol (e.g., "SPY")
        hours_back: Number of hours to check back (1-168)

    Returns:
        dict: Health check results
    """
    try:
        data_ingestion = get_data_ingestion_service()
        health = await data_ingestion.get_data_health_check(
            symbol=symbol.upper(),
            hours_back=hours_back
        )

        return health

    except Exception as e:
        logger.error(
            "Error getting data health",
            extra={"symbol": symbol, "error": str(e)}
        )
        raise HTTPException(
            status_code=500,
            detail=f"Error getting data health: {str(e)}"
        )


@router.get("/{symbol}/stats")
async def get_market_data_stats(symbol: str):
    """
    Get statistics about market data for a symbol.

    Args:
        symbol: Trading symbol (e.g., "SPY")

    Returns:
        dict: Market data statistics
    """
    try:
        repo = MarketDataRepository()

        # Get bar counts for different time ranges
        now = datetime.utcnow()
        day_ago = now - timedelta(days=1)
        week_ago = now - timedelta(weeks=1)
        month_ago = now - timedelta(days=30)

        stats = {
            "symbol": symbol.upper(),
            "bar_counts": {
                "last_24h": await repo.get_bar_count(symbol.upper(), day_ago, now),
                "last_7d": await repo.get_bar_count(symbol.upper(), week_ago, now),
                "last_30d": await repo.get_bar_count(symbol.upper(), month_ago, now),
                "total": await repo.get_bar_count(symbol.upper())
            },
            "latest_bar": None
        }

        # Get latest bar
        latest = await repo.get_latest_bar(symbol.upper())
        if latest:
            stats["latest_bar"] = {
                "time": latest.time.isoformat(),
                "close": str(latest.close),
                "volume": latest.volume
            }

        return stats

    except Exception as e:
        logger.error(
            "Error getting market data stats",
            extra={"symbol": symbol, "error": str(e)}
        )
        raise HTTPException(
            status_code=500,
            detail=f"Error getting stats: {str(e)}"
        )


@router.post("/views/refresh")
async def refresh_materialized_views(
    view_name: Optional[str] = Query(
        default=None,
        description="Specific view to refresh (5min, 15min, 30min, daily). If not specified, refreshes all."
    ),
    concurrently: bool = Query(
        default=True,
        description="Use CONCURRENT refresh (non-blocking)"
    )
):
    """
    Manually trigger refresh of materialized views for aggregated timeframes.

    This endpoint allows manual refresh of the materialized views that aggregate
    1-minute data into larger timeframes (5min, 15min, 30min, daily).

    The views are automatically refreshed every 5 minutes by the scheduler during
    market hours, but this endpoint can be used to force an immediate refresh.

    Args:
        view_name: Optional specific view to refresh (ohlcv_5min, ohlcv_15min, ohlcv_30min, ohlcv_daily)
        concurrently: If True, uses CONCURRENT refresh (non-blocking, but slower)

    Returns:
        dict: Refresh results
    """
    try:
        logger.info(
            "Manual materialized view refresh triggered",
            extra={"view_name": view_name, "concurrently": concurrently}
        )

        if view_name:
            # Refresh specific view
            valid_views = ["ohlcv_5min", "ohlcv_15min", "ohlcv_30min", "ohlcv_daily"]
            if view_name not in valid_views:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid view name. Must be one of: {', '.join(valid_views)}"
                )

            success = await MaterializedViewRefreshService.refresh_view(
                view_name=view_name,
                concurrently=concurrently
            )

            return {
                "view": view_name,
                "status": "success" if success else "failed",
                "concurrently": concurrently
            }
        else:
            # Refresh all views
            results = await MaterializedViewRefreshService.refresh_all_views(
                concurrently=concurrently
            )

            return results

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Error refreshing materialized views",
            extra={"view_name": view_name, "error": str(e)}
        )
        raise HTTPException(
            status_code=500,
            detail=f"Error refreshing views: {str(e)}"
        )


@router.get("/views/stats")
async def get_materialized_view_stats():
    """
    Get statistics about materialized views.

    Returns information about the aggregated timeframe views including
    row counts and sizes.

    Returns:
        dict: Statistics for each materialized view
    """
    try:
        stats = await MaterializedViewRefreshService.get_view_stats()

        return {
            "views": stats,
            "total_views": len(stats)
        }

    except Exception as e:
        logger.error(
            "Error getting materialized view stats",
            extra={"error": str(e)}
        )
        raise HTTPException(
            status_code=500,
            detail=f"Error getting view stats: {str(e)}"
        )
