"""Data ingestion service tests."""

import pytest
from datetime import datetime, timedelta, timezone
from app.services.data_ingestion import DataIngestionService
from app.utils.market_hours import MarketHours


@pytest.mark.asyncio
async def test_get_data_health_check(test_symbol):
    """Test data health check."""
    service = DataIngestionService()

    health = await service.get_data_health_check(test_symbol, hours_back=24)

    assert "symbol" in health
    assert "bar_count" in health
    assert "gap_count" in health
    assert "healthy" in health
    assert health["symbol"] == test_symbol
    assert isinstance(health["bar_count"], int)
    assert isinstance(health["gap_count"], int)
    assert isinstance(health["healthy"], bool)


@pytest.mark.asyncio
async def test_ingest_latest_bar_market_closed(test_symbol):
    """Test data ingestion when market is closed."""
    service = DataIngestionService()

    # This test only runs when market is closed
    if not MarketHours.is_market_open():
        result = await service.ingest_latest_bar(test_symbol)

        # Should return False when market is closed
        assert result is False


@pytest.mark.asyncio
async def test_ingest_latest_bar_market_open(test_symbol):
    """Test data ingestion when market is open."""
    service = DataIngestionService()

    # This test only runs when market is open
    if MarketHours.is_market_open():
        result = await service.ingest_latest_bar(test_symbol)

        # Result might be False due to delayed API data, but should not raise error
        assert isinstance(result, bool)


@pytest.mark.asyncio
async def test_backfill_with_validation_days_param(test_symbol):
    """Test backfill with validation using days parameter."""
    service = DataIngestionService()

    # Test with days parameter (small range to avoid rate limits)
    result = await service.backfill_with_validation(
        symbol=test_symbol,
        days=2,
        max_days=30
    )

    assert "symbol" in result
    assert "start_date" in result
    assert "end_date" in result
    assert "bars_inserted" in result
    assert "gaps_found" in result
    assert "gaps" in result
    assert "success" in result
    assert result["symbol"] == test_symbol
    assert isinstance(result["bars_inserted"], int)
    assert isinstance(result["gaps_found"], int)
    assert isinstance(result["gaps"], list)
    assert isinstance(result["success"], bool)


@pytest.mark.asyncio
async def test_backfill_with_validation_explicit_dates(test_symbol):
    """Test backfill with validation using explicit dates."""
    service = DataIngestionService()

    # Use explicit dates (2 days ago to yesterday)
    end_date = datetime.now(timezone.utc) - timedelta(days=1)
    start_date = end_date - timedelta(days=2)

    result = await service.backfill_with_validation(
        symbol=test_symbol,
        start_date=start_date,
        end_date=end_date,
        max_days=30
    )

    assert result["symbol"] == test_symbol
    assert isinstance(result["bars_inserted"], int)
    assert isinstance(result["success"], bool)


@pytest.mark.asyncio
async def test_backfill_with_validation_missing_params(test_symbol):
    """Test backfill validation error when missing both days and dates."""
    service = DataIngestionService()

    # Should raise ValueError when neither days nor both dates provided
    with pytest.raises(ValueError, match="Either provide 'days' parameter OR both"):
        await service.backfill_with_validation(
            symbol=test_symbol,
            start_date=None,
            end_date=None,
            days=None
        )


@pytest.mark.asyncio
async def test_backfill_with_validation_invalid_date_range(test_symbol):
    """Test backfill validation error for invalid date range."""
    service = DataIngestionService()

    # Start date after end date should raise ValueError
    end_date = datetime.now(timezone.utc) - timedelta(days=5)
    start_date = datetime.now(timezone.utc) - timedelta(days=1)

    with pytest.raises(ValueError, match="start_date must be before end_date"):
        await service.backfill_with_validation(
            symbol=test_symbol,
            start_date=start_date,
            end_date=end_date
        )


@pytest.mark.asyncio
async def test_backfill_with_validation_exceeds_max_days(test_symbol):
    """Test backfill validation error when exceeding max days."""
    service = DataIngestionService()

    # Date range exceeding max_days should raise ValueError
    with pytest.raises(ValueError, match="Date range too large"):
        await service.backfill_with_validation(
            symbol=test_symbol,
            days=50,  # Exceeds default max of 30
            max_days=30
        )


@pytest.mark.asyncio
async def test_get_market_data_stats(test_symbol):
    """Test market data statistics retrieval."""
    service = DataIngestionService()

    stats = await service.get_market_data_stats(test_symbol)

    assert "symbol" in stats
    assert "bar_counts" in stats
    assert "latest_bar" in stats
    assert stats["symbol"] == test_symbol

    # Check bar_counts structure
    bar_counts = stats["bar_counts"]
    assert "last_24h" in bar_counts
    assert "last_7d" in bar_counts
    assert "last_30d" in bar_counts
    assert "total" in bar_counts

    # All counts should be integers
    assert isinstance(bar_counts["last_24h"], int)
    assert isinstance(bar_counts["last_7d"], int)
    assert isinstance(bar_counts["last_30d"], int)
    assert isinstance(bar_counts["total"], int)

    # Counts should be non-negative and logically ordered
    assert bar_counts["last_24h"] >= 0
    assert bar_counts["last_7d"] >= bar_counts["last_24h"]
    assert bar_counts["last_30d"] >= bar_counts["last_7d"]
    assert bar_counts["total"] >= bar_counts["last_30d"]

    # latest_bar can be None or dict
    if stats["latest_bar"] is not None:
        assert "time" in stats["latest_bar"]
        assert "close" in stats["latest_bar"]
        assert "volume" in stats["latest_bar"]
