"""Tests for Alpaca API client."""

import pytest
from datetime import datetime, timedelta
import pytz
from decimal import Decimal

from app.services.alpaca_client import AlpacaClient
from app.config import settings


@pytest.mark.asyncio
async def test_alpaca_client_connect():
    """Test that Alpaca client can connect."""
    client = AlpacaClient()

    try:
        await client.connect()
        assert client.session is not None
        assert not client.session.closed
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_alpaca_context_manager():
    """Test Alpaca client as context manager."""
    async with AlpacaClient() as client:
        assert client.session is not None
        assert not client.session.closed


@pytest.mark.asyncio
async def test_fetch_timesales():
    """Test fetching historical bars from Alpaca."""
    if not settings.alpaca_api_key or not settings.alpaca_api_secret:
        pytest.skip("Alpaca API credentials not configured")

    async with AlpacaClient() as client:
        # Get data for the last 2 days
        tz = pytz.timezone(settings.timezone)
        end = datetime.now(tz)
        start = end - timedelta(days=2)

        bars = await client.fetch_timesales(
            symbol="SPY",
            interval="1min",
            start=start,
            end=end
        )

        # Should have some bars
        assert isinstance(bars, list)

        # If we have bars, verify structure (Alpaca format)
        if bars:
            bar = bars[0]
            assert "t" in bar  # ISO 8601 timestamp
            assert "o" in bar  # open
            assert "h" in bar  # high
            assert "l" in bar  # low
            assert "c" in bar  # close
            assert "v" in bar  # volume
            # Alpaca also provides:
            # "n" - number of trades
            # "vw" - VWAP


@pytest.mark.asyncio
async def test_fetch_timesales_pagination():
    """Test fetching large date range with pagination."""
    if not settings.alpaca_api_key or not settings.alpaca_api_secret:
        pytest.skip("Alpaca API credentials not configured")

    async with AlpacaClient() as client:
        # Get 30 days of 1-minute data (should trigger pagination)
        tz = pytz.timezone(settings.timezone)
        end = datetime.now(tz)
        start = end - timedelta(days=30)

        bars = await client.fetch_timesales(
            symbol="SPY",
            interval="1min",
            start=start,
            end=end
        )

        # Should have bars (even if market was closed some days)
        assert isinstance(bars, list)


@pytest.mark.asyncio
async def test_fetch_latest_bar():
    """Test fetching the latest bar from Alpaca."""
    if not settings.alpaca_api_key or not settings.alpaca_api_secret:
        pytest.skip("Alpaca API credentials not configured")

    async with AlpacaClient() as client:
        bar = await client.fetch_latest_bar(symbol="SPY", interval="1min")

        # Bar may be None if market is closed or delayed data
        if bar is not None:
            assert "t" in bar
            assert "o" in bar
            assert "h" in bar
            assert "l" in bar
            assert "c" in bar
            assert "v" in bar


@pytest.mark.asyncio
async def test_fetch_historical_5min_bars():
    """Test fetching 5-minute historical bars."""
    if not settings.alpaca_api_key or not settings.alpaca_api_secret:
        pytest.skip("Alpaca API credentials not configured")

    async with AlpacaClient() as client:
        tz = pytz.timezone(settings.timezone)
        end = datetime.now(tz)
        start = end - timedelta(days=7)

        bars = await client.fetch_timesales(
            symbol="SPY",
            interval="5min",
            start=start,
            end=end
        )

        assert isinstance(bars, list)


def test_parse_bar_to_ohlcv():
    """Test parsing Alpaca bar format to standardized OHLCV format."""
    client = AlpacaClient()

    alpaca_bar = {
        "t": "2023-09-29T04:00:00Z",
        "o": 172.015,
        "h": 173.06,
        "l": 170.36,
        "c": 171.29,
        "v": 923134,
        "n": 12630,  # Number of trades
        "vw": 171.716432  # VWAP
    }

    parsed = client.parse_bar_to_ohlcv(alpaca_bar)

    # Check timestamp conversion from ISO 8601 to milliseconds
    assert parsed["t"] > 0
    assert isinstance(parsed["t"], int)

    # Check OHLCV values
    assert parsed["o"] == Decimal("172.015")
    assert parsed["h"] == Decimal("173.06")
    assert parsed["l"] == Decimal("170.36")
    assert parsed["c"] == Decimal("171.29")
    assert parsed["v"] == 923134

    # Check additional Alpaca fields
    assert parsed["vw"] == Decimal("171.716432")
    assert parsed["n"] == 12630


def test_parse_bar_without_optional_fields():
    """Test parsing Alpaca bar without VWAP and trade count."""
    client = AlpacaClient()

    alpaca_bar = {
        "t": "2023-09-29T04:00:00Z",
        "o": 172.015,
        "h": 173.06,
        "l": 170.36,
        "c": 171.29,
        "v": 923134
    }

    parsed = client.parse_bar_to_ohlcv(alpaca_bar)

    assert parsed["vw"] is None
    assert parsed["n"] is None


def test_timeframe_conversion():
    """Test conversion from our format to Alpaca format."""
    client = AlpacaClient()

    assert client._convert_timeframe("1min") == "1Min"
    assert client._convert_timeframe("5min") == "5Min"
    assert client._convert_timeframe("15min") == "15Min"
    assert client._convert_timeframe("30min") == "30Min"
    assert client._convert_timeframe("1hour") == "1Hour"
    assert client._convert_timeframe("daily") == "1Day"
    assert client._convert_timeframe("1day") == "1Day"

    # Test case insensitivity
    assert client._convert_timeframe("1MIN") == "1Min"
    assert client._convert_timeframe("DAILY") == "1Day"

    # Test unknown format defaults to 1Min
    assert client._convert_timeframe("unknown") == "1Min"


def test_provider_name():
    """Test that provider name is correctly set."""
    client = AlpacaClient()
    assert client.provider_name == "alpaca"
