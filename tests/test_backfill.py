"""Historical data backfill tests."""

import pytest
from datetime import datetime, timedelta
from app.services.data_ingestion import DataIngestionService


@pytest.mark.asyncio
async def test_backfill_historical_data(test_symbol):
    """Test historical data backfill."""
    service = DataIngestionService()

    # Backfill last 2 days as a test
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=2)

    count = await service.backfill_historical_data(
        symbol=test_symbol,
        start_date=start_date,
        end_date=end_date
    )

    # Count should be a non-negative integer
    assert isinstance(count, int)
    assert count >= 0
