"""Tests for Tradier API client."""

import pytest
from datetime import datetime, timedelta
import pytz

from app.services.tradier_client import TradierClient
from app.config import settings


@pytest.mark.asyncio
async def test_tradier_client_connect():
    """Test that Tradier client can connect."""
    client = TradierClient()

    try:
        await client.connect()
        assert client.session is not None
        assert not client.session.closed
    finally:
        await client.disconnect()


@pytest.mark.asyncio
async def test_fetch_timesales():
    """Test fetching timesales data from Tradier."""
    if not settings.tradier_api_token:
        pytest.skip("Tradier API token not configured")

    client = TradierClient()

    try:
        # Get data for the last day
        tz = pytz.timezone(settings.timezone)
        end = datetime.now(tz)
        start = end - timedelta(days=1)

        bars = await client.fetch_timesales(
            symbol="SPY",
            interval="1min",
            start=start,
            end=end,
            session_filter="open"
        )

        # Should have some bars (unless market was closed the entire day)
        assert isinstance(bars, list)

        # If we have bars, verify structure
        if bars:
            bar = bars[0]
            assert "time" in bar
            assert "open" in bar
            assert "high" in bar
            assert "low" in bar
            assert "close" in bar
            assert "volume" in bar

    finally:
        await client.disconnect()


@pytest.mark.asyncio
async def test_fetch_latest_bar():
    """Test fetching the latest bar from Tradier."""
    if not settings.tradier_api_token:
        pytest.skip("Tradier API token not configured")

    client = TradierClient()

    try:
        bar = await client.fetch_latest_bar(symbol="SPY", interval="1min")

        # Bar may be None if market is closed
        if bar is not None:
            assert "time" in bar
            assert "open" in bar
            assert "high" in bar
            assert "low" in bar
            assert "close" in bar
            assert "volume" in bar

    finally:
        await client.disconnect()


@pytest.mark.asyncio
async def test_parse_bar_to_ohlcv():
    """Test parsing Tradier bar format to our OHLCV format."""
    client = TradierClient()

    tradier_bar = {
        "time": "2025-11-07T09:30:00",
        "timestamp": 1730984400,
        "open": 667.91,
        "high": 667.98,
        "low": 666.57,
        "close": 666.58,
        "volume": 1103355,
        "vwap": 667.25059
    }

    parsed = client.parse_bar_to_ohlcv(tradier_bar)

    assert parsed["t"] == 1730984400000  # Timestamp in milliseconds
    assert parsed["o"] == pytest.approx(667.91)
    assert parsed["h"] == pytest.approx(667.98)
    assert parsed["l"] == pytest.approx(666.57)
    assert parsed["c"] == pytest.approx(666.58)
    assert parsed["v"] == 1103355
