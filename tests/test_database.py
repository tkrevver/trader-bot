"""Database connection and partition management tests."""

import pytest
from app.db.connection import db_pool
from app.db.partition_manager import PartitionManager


@pytest.fixture(autouse=True)
async def setup_test_database():
    """Setup database connection for each test."""
    # Ensure fresh connection for each test
    if db_pool._pool is not None:
        await db_pool.disconnect()

    await db_pool.connect()
    yield
    await db_pool.disconnect()


@pytest.mark.asyncio
async def test_database_connection():
    """Test database connection is established."""
    # Database should be connected via fixture
    assert db_pool._pool is not None

    # Test basic query
    result = await db_pool.fetchval("SELECT 1")
    assert result == 1


@pytest.mark.asyncio
async def test_partition_management():
    """Test automatic partition management."""
    # Ensure partitions exist
    result = await PartitionManager.ensure_partitions_exist(weeks_ahead=4)

    assert "total_existing" in result
    assert "created" in result
    assert "skipped" in result
    assert isinstance(result["total_existing"], int)
    assert result["total_existing"] > 0

    # List partitions
    partitions = await PartitionManager.list_partitions()
    assert len(partitions) > 0

    # Each partition should have expected structure
    for partition in partitions:
        assert "name" in partition
        assert partition["name"].startswith("ohlcv_1min_")
