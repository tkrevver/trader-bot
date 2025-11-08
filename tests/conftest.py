"""Pytest configuration and shared fixtures."""

import pytest


@pytest.fixture
def test_symbol():
    """Default test symbol."""
    return "SPY"
