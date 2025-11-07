"""Market data repository tests."""

import pytest
from app.db.repositories.market_data import MarketDataRepository


@pytest.mark.asyncio
async def test_get_latest_bar(test_symbol):
    """Test retrieving latest bar from database."""
    repo = MarketDataRepository()

    # Get latest bar (might be None if database is empty)
    latest_bar = await repo.get_latest_bar(test_symbol)

    if latest_bar:
        assert latest_bar.symbol == test_symbol
        assert latest_bar.time is not None
        assert latest_bar.open > 0
        assert latest_bar.high > 0
        assert latest_bar.low > 0
        assert latest_bar.close > 0
        assert latest_bar.volume >= 0


@pytest.mark.asyncio
async def test_get_bar_count(test_symbol):
    """Test getting bar count from database."""
    repo = MarketDataRepository()

    count = await repo.get_bar_count(test_symbol)

    assert isinstance(count, int)
    assert count >= 0
