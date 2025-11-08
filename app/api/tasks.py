"""Admin task API endpoints."""

from fastapi import APIRouter, Query, HTTPException

from app.db.partition_manager import PartitionManager
from app.utils.logger import logger

router = APIRouter(prefix="/api/v1/tasks", tags=["Admin Tasks"])


@router.post("/partitions/create")
async def create_partitions(
    year: int = Query(
        ...,
        description="Year to create partitions for (e.g., 2024)",
        ge=2020,
        le=2030
    ),
    table_name: str = Query(
        ...,
        description="Name of the partitioned table"
    )
):
    """
    Create database partitions for all weeks in a specific year.

    This endpoint creates weekly partitions for the specified year.
    It is safe to re-run - existing partitions will be skipped.

    Args:
        year: Year to create partitions for (2020-2030)
        table_name: Name of the partitioned table

    Returns:
        dict: Summary of created and skipped partitions
    """
    try:
        logger.info(
            "Creating partitions via API",
            extra={
                "table": table_name,
                "year": year
            }
        )

        result = await PartitionManager.create_partitions_for_year(year, table_name)
        return result

    except Exception as e:
        logger.error(
            f"Error creating partitions for {year}",
            extra={"error": str(e), "year": year, "table": table_name}
        )
        raise HTTPException(
            status_code=500,
            detail=f"Error creating partitions: {str(e)}"
        )


@router.get("/partitions/list")
async def list_partitions(
    table_name: str = Query(
        ...,
        description="Name of the partitioned table"
    ),
    year: int = Query(
        None,
        description="Optional year to filter partitions (e.g., 2024)",
        ge=2020,
        le=2030
    )
):
    """
    List existing partitions for a table.

    Optionally filter by year to see only partitions for a specific year.

    Args:
        table_name: Name of the partitioned table
        year: Optional year to filter partitions

    Returns:
        dict: List of partitions with their details
    """
    try:
        partitions = await PartitionManager.list_partitions(table_name)

        # Filter by year if specified
        if year is not None:
            year_suffix = f"_{year}_"
            partitions = [p for p in partitions if year_suffix in p["name"]]

        logger.info(
            "Listed partitions",
            extra={"table": table_name, "year": year, "count": len(partitions)}
        )

        return {
            "table": table_name,
            "year": year,
            "partitions": partitions,
            "total_count": len(partitions)
        }

    except Exception as e:
        logger.error(
            "Error listing partitions",
            extra={"error": str(e), "table": table_name}
        )
        raise HTTPException(
            status_code=500,
            detail=f"Error listing partitions: {str(e)}"
        )


@router.delete("/partitions/drop-year")
async def drop_partitions_for_year(
    year: int = Query(
        ...,
        description="Year to drop partitions for (e.g., 2025)",
        ge=2020,
        le=2030
    ),
    table_name: str = Query(
        ...,
        description="Name of the partitioned table"
    ),
    confirm: bool = Query(
        default=False,
        description="Must be true to actually drop partitions (safety check)"
    )
):
    """
    Drop all partitions for a specific year.

    ⚠️ WARNING: This PERMANENTLY DELETES DATA!

    Use this when you need to recreate partitions for a year (e.g., fixing incorrect bounds).

    Safety features:
    - Requires confirm=true to actually drop
    - Lists what will be dropped first
    - Only drops partitions matching the year pattern

    Typical use case:
    1. Call with confirm=false to preview what will be dropped
    2. Verify the list is correct
    3. Call with confirm=true to actually drop
    4. Recreate partitions with correct bounds
    5. Re-populate data via backfill

    Args:
        year: Year to drop partitions for
        table_name: Name of the partitioned table
        confirm: Must be true to actually drop (default: false)

    Returns:
        dict: List of partitions that were/would be dropped
    """
    try:
        logger.warning(
            "Drop year partitions requested via API",
            extra={
                "table": table_name,
                "year": year,
                "confirm": confirm
            }
        )

        if confirm:
            # Actually drop the partitions
            dropped = await PartitionManager.drop_partitions_for_year(year, table_name)

            result = {
                "table": table_name,
                "year": year,
                "confirm": confirm,
                "partitions": dropped,
                "count": len(dropped),
                "message": f"Dropped {len(dropped)} partition(s) for {year}"
            }

            logger.warning(
                "Year partition cleanup completed",
                extra={"year": year, "dropped_count": len(dropped)}
            )

            return result
        else:
            # Preview mode - show what would be dropped
            all_partitions = await PartitionManager.list_partitions(table_name)

            # Filter to only partitions for the specified year
            year_pattern = f"_{year}_w"
            to_drop = [
                {"name": p["name"]}
                for p in all_partitions
                if year_pattern in p["name"]
            ]

            result = {
                "table": table_name,
                "year": year,
                "confirm": confirm,
                "partitions": to_drop,
                "count": len(to_drop),
                "message": f"Would drop {len(to_drop)} partition(s) for {year}"
            }

            logger.info(
                "Year partition drop preview (dry run)",
                extra={"year": year, "preview_count": len(to_drop)}
            )

            return result

    except Exception as e:
        logger.error(
            "Error dropping year partitions",
            extra={"error": str(e), "table": table_name, "year": year}
        )
        raise HTTPException(
            status_code=500,
            detail=f"Error dropping partitions: {str(e)}"
        )
