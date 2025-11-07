"""Pytest configuration and shared fixtures."""

import pytest
import asyncio
from app.db.connection import db_pool


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session", autouse=True)
async def setup_database():
    """Setup database connection for all tests."""
    await db_pool.connect()
    yield
    await db_pool.disconnect()


@pytest.fixture
def test_symbol():
    """Default test symbol."""
    return "SPY"
