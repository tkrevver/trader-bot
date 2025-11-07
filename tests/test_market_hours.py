"""Market hours utilities tests."""

import pytest
from datetime import datetime
from app.utils.market_hours import MarketHours


def test_get_current_time_et():
    """Test getting current time in ET timezone."""
    current_time = MarketHours.get_current_time_et()

    assert isinstance(current_time, datetime)
    assert current_time.tzinfo is not None


def test_is_market_open():
    """Test market open check."""
    is_open = MarketHours.is_market_open()

    assert isinstance(is_open, bool)


def test_get_market_status():
    """Test getting market status."""
    status = MarketHours.get_market_status()

    assert isinstance(status, str)
    assert status in ["open", "closed", "pre_market", "after_hours"]


def test_get_next_market_open():
    """Test getting next market open time."""
    next_open = MarketHours.get_next_market_open()

    assert isinstance(next_open, datetime)
    assert next_open.tzinfo is not None

    # Next open should be in the future
    current_time = MarketHours.get_current_time_et()
    assert next_open > current_time
