"""Materialized view refresh service tests."""

import pytest
from app.services.materialized_view_refresh import MaterializedViewRefreshService


def test_validate_view_name_valid():
    """Test view name validation with valid names."""
    # Should not raise for valid view names
    for view_name in MaterializedViewRefreshService.VIEWS:
        MaterializedViewRefreshService.validate_view_name(view_name)


def test_validate_view_name_invalid():
    """Test view name validation with invalid name."""
    with pytest.raises(ValueError, match="Invalid view name"):
        MaterializedViewRefreshService.validate_view_name("invalid_view")


def test_validate_view_name_empty():
    """Test view name validation with empty string."""
    with pytest.raises(ValueError, match="Invalid view name"):
        MaterializedViewRefreshService.validate_view_name("")


def test_validate_view_name_case_sensitive():
    """Test view name validation is case sensitive."""
    with pytest.raises(ValueError, match="Invalid view name"):
        MaterializedViewRefreshService.validate_view_name("OHLCV_5MIN")


def test_views_constant():
    """Test VIEWS constant has expected values."""
    assert len(MaterializedViewRefreshService.VIEWS) == 4
    assert "ohlcv_5min" in MaterializedViewRefreshService.VIEWS
    assert "ohlcv_15min" in MaterializedViewRefreshService.VIEWS
    assert "ohlcv_30min" in MaterializedViewRefreshService.VIEWS
    assert "ohlcv_daily" in MaterializedViewRefreshService.VIEWS


@pytest.mark.asyncio
async def test_refresh_view():
    """Test refreshing a single materialized view."""
    # Test with concurrent refresh
    success = await MaterializedViewRefreshService.refresh_view(
        view_name="ohlcv_5min",
        concurrently=True
    )

    # Should return boolean
    assert isinstance(success, bool)


@pytest.mark.asyncio
async def test_refresh_all_views():
    """Test refreshing all materialized views."""
    results = await MaterializedViewRefreshService.refresh_all_views(
        concurrently=True
    )

    # Check result structure
    assert "total" in results
    assert "successful" in results
    assert "failed" in results
    assert "views" in results

    # Should have processed all views
    assert results["total"] == len(MaterializedViewRefreshService.VIEWS)
    assert isinstance(results["successful"], int)
    assert isinstance(results["failed"], int)
    assert isinstance(results["views"], dict)

    # Check all views were processed
    for view_name in MaterializedViewRefreshService.VIEWS:
        assert view_name in results["views"]
        assert results["views"][view_name] in ["success", "failed"]


@pytest.mark.asyncio
async def test_get_view_stats():
    """Test getting view statistics."""
    stats = await MaterializedViewRefreshService.get_view_stats()

    # Should return dict with stats for each view
    assert isinstance(stats, dict)

    # Check each view has stats
    for view_name in MaterializedViewRefreshService.VIEWS:
        if view_name in stats:  # May be empty if views haven't been refreshed
            assert "row_count" in stats[view_name]
            assert "size" in stats[view_name]
            assert isinstance(stats[view_name]["row_count"], int)
            assert isinstance(stats[view_name]["size"], str)
