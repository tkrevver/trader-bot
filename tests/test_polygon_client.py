"""Polygon.io API client tests."""

import pytest
from datetime import datetime
from app.services.polygon_client import PolygonClient


@pytest.mark.asyncio
async def test_polygon_client_fetch_latest_bar(test_symbol):
    """Test fetching latest bar from Polygon.io API."""
    async with PolygonClient() as client:
        bar = await client.fetch_latest_bar(test_symbol)

        # Note: bar might be None outside market hours or with delayed data
        if bar:
            # Verify expected fields
            assert "t" in bar  # timestamp
            assert "o" in bar  # open
            assert "h" in bar  # high
            assert "l" in bar  # low
            assert "c" in bar  # close
            assert "v" in bar  # volume

            # Verify timestamp is valid
            timestamp = datetime.fromtimestamp(bar["t"] / 1000)
            assert isinstance(timestamp, datetime)

            # Verify price values are positive
            assert bar["o"] > 0
            assert bar["h"] > 0
            assert bar["l"] > 0
            assert bar["c"] > 0
            assert bar["v"] > 0
