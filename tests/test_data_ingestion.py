"""Data ingestion service tests."""

import pytest
from datetime import datetime, timedelta
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
