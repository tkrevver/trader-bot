"""Market data API endpoints."""

from fastapi import APIRouter, Query, HTTPException
from datetime import datetime, timedelta
from typing import Optional

from app.db.repositories.market_data import MarketDataRepository
from app.models.market_data import BarResponse, LatestBarResponse, MarketDataGap, HealthCheckResponse
from app.services.data_ingestion import get_data_ingestion_service
from app.services.materialized_view_refresh import MaterializedViewRefreshService
from app.utils.logger import logger
from app.utils.market_hours import MarketHours

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


@router.post("/{symbol}/ingest-latest")
async def ingest_latest_bar(symbol: str):
    """
    Manually trigger ingestion of the latest bar for a symbol.

    This is what the scheduler calls every minute during market hours.
    Respects extended hours setting from config.

    Args:
        symbol: Trading symbol (e.g., "SPY")

    Returns:
        dict: Ingestion result
    """
    try:
        # Check market status
        market_status = MarketHours.get_market_status()
        market_open = MarketHours.is_extended_market_open()

        data_ingestion = get_data_ingestion_service()
        success = await data_ingestion.ingest_latest_bar(symbol.upper())

        # Provide better error message based on market status
        if not success and not market_open:
            message = f"Market is {market_status} - ingestion skipped"
        elif success:
            message = "Bar ingested successfully"
        else:
            message = "Ingestion failed - check if data is available from Tradier"

        return {
            "symbol": symbol.upper(),
            "success": success,
            "market_status": market_status,
            "market_open": market_open,
            "message": message
        }

    except Exception as e:
        logger.error(
            "Error ingesting latest bar",
            extra={"symbol": symbol, "error": str(e)}
        )
        raise HTTPException(
            status_code=500,
            detail=f"Error ingesting latest bar: {str(e)}"
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

    This endpoint triggers a manual backfill of historical data
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
        logger.info(
            "Manual backfill triggered via API",
            extra={"symbol": symbol, "days": days}
        )

        data_ingestion = get_data_ingestion_service()
        result = await data_ingestion.backfill_with_validation(
            symbol=symbol.upper(),
            start_date=start_date,
            end_date=end_date,
            days=days,
            max_days=30
        )

        return result

    except ValueError as e:
        # Validation errors (date range issues, missing params, etc.)
        raise HTTPException(
            status_code=400,
            detail=str(e)
        )
    except Exception as e:
        logger.error(
            "Error backfilling data",
            extra={"symbol": symbol, "error": str(e)}
        )
        raise HTTPException(
            status_code=500,
            detail=f"Error backfilling data: {str(e)}"
        )


@router.get("/{symbol}/health", response_model=HealthCheckResponse)
async def get_data_health(
    symbol: str,
    hours_back: Optional[int] = Query(
        default=None,
        description="Number of hours to check (1-720)",
        ge=1,
        le=720
    ),
    days_back: Optional[int] = Query(
        default=None,
        description="Number of days to check (1-30)",
        ge=1,
        le=30
    )
):
    """
    Get data health check for a symbol.

    Args:
        symbol: Trading symbol (e.g., "SPY")
        hours_back: Number of hours to check back (1-720)
        days_back: Number of days to check back (1-30)

    Note: Provide either hours_back OR days_back (not both). Defaults to 24 hours if neither specified.

    Returns:
        HealthCheckResponse: Health check results with timestamps in configured timezone
    """
    try:
        # Validate parameters
        if hours_back is not None and days_back is not None:
            raise HTTPException(
                status_code=400,
                detail="Provide either 'hours_back' OR 'days_back', not both"
            )

        # Calculate hours_back from days_back if provided
        if days_back is not None:
            hours_back = days_back * 24
        elif hours_back is None:
            # Default to 24 hours if neither specified
            hours_back = 24

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
        data_ingestion = get_data_ingestion_service()
        stats = await data_ingestion.get_market_data_stats(symbol.upper())
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
        description="Specific view to refresh (ohlcv_5min, ohlcv_15min, ohlcv_30min, ohlcv_daily). If not specified, refreshes all."
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
            "Manual materialized view refresh triggered via API",
            extra={"view_name": view_name, "concurrently": concurrently}
        )

        if view_name:
            # Validate view name
            MaterializedViewRefreshService.validate_view_name(view_name)

            # Refresh specific view
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

    except ValueError as e:
        # Validation errors (invalid view name)
        raise HTTPException(
            status_code=400,
            detail=str(e)
        )
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
