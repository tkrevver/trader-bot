"""Gap detection tests."""

import pytest
from app.services.data_ingestion import DataIngestionService


@pytest.mark.asyncio
async def test_detect_and_backfill_gaps(test_symbol):
    """Test gap detection and backfill."""
    service = DataIngestionService()

    # Detect gaps in last 2 days
    gaps = await service.detect_and_backfill_gaps(test_symbol, days_back=2)

    # Should return a list (might be empty if no gaps)
    assert isinstance(gaps, list)

    # If gaps found, verify structure
    for gap in gaps:
        assert hasattr(gap, "start_time")
        assert hasattr(gap, "end_time")
        assert hasattr(gap, "missing_bars")
        assert gap.start_time < gap.end_time
        assert gap.missing_bars > 0
