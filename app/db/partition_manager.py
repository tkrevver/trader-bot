"""Automatic partition management for TimescaleDB."""

from datetime import datetime, timedelta
from app.db.connection import db_pool
from app.utils.logger import logger


class PartitionManager:
    """Manages automatic creation of table partitions."""

    @staticmethod
    async def ensure_partitions_exist(table_name: str = "ohlcv_1min", weeks_ahead: int = 4) -> dict:
        """
        Ensure partitions exist for the current date plus weeks_ahead.

        This prevents insert failures when data arrives for dates without partitions.
        Called during application startup.

        Args:
            table_name: Name of the partitioned table (default: "ohlcv_1min")
            weeks_ahead: Number of weeks ahead to create partitions (default: 4)

        Returns:
            dict: Summary of created partitions
        """
        try:
            current_date = datetime.utcnow()
            end_date = current_date + timedelta(weeks=weeks_ahead)

            logger.info(
                "Checking partitions",
                extra={
                    "table": table_name,
                    "current_date": current_date.isoformat(),
                    "end_date": end_date.isoformat(),
                    "weeks_ahead": weeks_ahead
                }
            )

            # Get list of existing partitions
            existing = await db_pool.fetch("""
                SELECT tablename
                FROM pg_tables
                WHERE schemaname = 'public'
                AND tablename LIKE $1
                ORDER BY tablename
            """, f"{table_name}_%")

            existing_partitions = {row['tablename'] for row in existing}

            logger.info(
                "Found existing partitions",
                extra={"count": len(existing_partitions), "partitions": list(existing_partitions)}
            )

            # Calculate start date (beginning of current week)
            start = current_date.replace(hour=0, minute=0, second=0, microsecond=0)
            start = start - timedelta(days=start.weekday())  # Start of week (Monday)

            created = []
            skipped = []

            while start <= end_date:
                week_end = start + timedelta(weeks=1)

                # Use ISO calendar week number for partition name
                iso_year, iso_week, _ = start.isocalendar()
                partition_name = f"{table_name}_{iso_year}_w{iso_week:02d}"

                # Always create partitions - this runs for current + N weeks ahead
                # so we don't need to filter by year like in the API endpoint
                if partition_name not in existing_partitions:
                    try:
                        # Create partition
                        await db_pool.execute(f"""
                            CREATE TABLE {partition_name} PARTITION OF {table_name}
                            FOR VALUES FROM ('{start.isoformat()}') TO ('{week_end.isoformat()}')
                        """)
                        created.append(partition_name)
                        logger.info(
                            "Created partition",
                            extra={
                                "partition": partition_name,
                                "start": start.isoformat(),
                                "end": week_end.isoformat()
                            }
                        )
                    except Exception as e:
                        logger.error(
                            "Failed to create partition",
                            extra={
                                "partition": partition_name,
                                "error": str(e)
                            }
                        )
                        # Continue to next partition even if one fails
                else:
                    skipped.append(partition_name)

                start = week_end

            result = {
                "created": created,
                "skipped": skipped,
                "total_existing": len(existing_partitions),
                "total_created": len(created)
            }

            if created:
                logger.info(
                    "Partition creation completed",
                    extra={
                        "created_count": len(created),
                        "skipped_count": len(skipped),
                        "created_partitions": created
                    }
                )
            else:
                logger.info("All required partitions already exist")

            return result

        except Exception as e:
            logger.error(
                "Error ensuring partitions exist",
                extra={"error": str(e), "table": table_name}
            )
            raise

    @staticmethod
    async def list_partitions(table_name: str = "ohlcv_1min") -> list[dict]:
        """
        List all partitions for a given table.

        Args:
            table_name: Name of the partitioned table

        Returns:
            list[dict]: List of partition information
        """
        try:
            query = """
                SELECT
                    c.relname AS partition_name,
                    pg_get_expr(c.relpartbound, c.oid) AS partition_bounds,
                    pg_size_pretty(pg_total_relation_size(c.oid)) AS size
                FROM pg_class c
                JOIN pg_inherits i ON i.inhrelid = c.oid
                JOIN pg_class p ON p.oid = i.inhparent
                WHERE p.relname = $1
                ORDER BY c.relname
            """

            results = await db_pool.fetch(query, table_name)

            partitions = [
                {
                    "name": row["partition_name"],
                    "bounds": row["partition_bounds"],
                    "size": row["size"]
                }
                for row in results
            ]

            logger.info(
                "Listed partitions",
                extra={"table": table_name, "count": len(partitions)}
            )

            return partitions

        except Exception as e:
            logger.error(
                "Error listing partitions",
                extra={"error": str(e), "table": table_name}
            )
            raise

    @staticmethod
    async def create_partitions_for_year(
        year: int,
        table_name: str = "ohlcv_1min"
    ) -> dict:
        """
        Create partitions for all weeks in a specific year.

        This is safe to re-run - existing partitions will be skipped.

        Args:
            year: Year to create partitions for (e.g., 2024)
            table_name: Name of the partitioned table

        Returns:
            dict: Summary with created, skipped, and total counts
        """
        try:
            logger.info(
                "Creating partitions for year",
                extra={
                    "table": table_name,
                    "year": year
                }
            )

            # Start from the first day of the year
            start_date = datetime(year, 1, 1)
            # End at the last day of the year
            end_date = datetime(year, 12, 31, 23, 59, 59)

            # Calculate the first Monday of the year (or Jan 1 if it's Monday)
            start = start_date - timedelta(days=start_date.weekday())

            # Get list of existing partitions
            existing = await db_pool.fetch("""
                SELECT tablename
                FROM pg_tables
                WHERE schemaname = 'public'
                AND tablename LIKE $1
                ORDER BY tablename
            """, f"{table_name}_%")

            existing_partitions = {row['tablename'] for row in existing}

            created = []
            skipped = []

            # Create partitions for each week
            current = start
            while current <= end_date:
                week_end = current + timedelta(weeks=1)

                # Use ISO calendar week number for partition name
                iso_year, iso_week, _ = current.isocalendar()

                # Create partition if it starts within the target calendar year
                # OR if it overlaps with the target year (handles edge cases like Dec 30-31)
                if current.year == year or (current.year < year and week_end.year == year):
                    partition_name = f"{table_name}_{iso_year}_w{iso_week:02d}"

                    if partition_name not in existing_partitions:
                        try:
                            # Create partition
                            await db_pool.execute(f"""
                                CREATE TABLE {partition_name} PARTITION OF {table_name}
                                FOR VALUES FROM ('{current.isoformat()}') TO ('{week_end.isoformat()}')
                            """)
                            created.append({
                                "name": partition_name,
                                "start": current.date().isoformat(),
                                "end": week_end.date().isoformat()
                            })
                            logger.info(
                                "Created partition",
                                extra={
                                    "partition": partition_name,
                                    "start": current.isoformat(),
                                    "end": week_end.isoformat()
                                }
                            )
                        except Exception as e:
                            logger.error(
                                "Failed to create partition",
                                extra={
                                    "partition": partition_name,
                                    "error": str(e)
                                }
                            )
                            raise
                    else:
                        skipped.append(partition_name)

                current = week_end

            result = {
                "year": year,
                "table": table_name,
                "created": created,
                "skipped": skipped,
                "summary": {
                    "total_created": len(created),
                    "total_skipped": len(skipped),
                    "total_existing": len(existing_partitions)
                }
            }

            logger.info(
                f"Partition creation for {year} completed",
                extra={
                    "year": year,
                    "created_count": len(created),
                    "skipped_count": len(skipped)
                }
            )

            return result

        except Exception as e:
            logger.error(
                f"Error creating partitions for {year}",
                extra={"error": str(e), "year": year, "table": table_name}
            )
            raise

    @staticmethod
    async def drop_partitions_for_year(
        year: int,
        table_name: str = "ohlcv_1min"
    ) -> list[dict]:
        """
        Drop all partitions for a specific year.

        WARNING: This permanently deletes data! Use with caution.

        Args:
            year: Year to drop partitions for
            table_name: Name of the partitioned table

        Returns:
            list[dict]: List of dropped partition names
        """
        try:
            logger.warning(
                "Dropping partitions for year",
                extra={
                    "table": table_name,
                    "year": year
                }
            )

            # Get list of all partitions
            existing = await db_pool.fetch("""
                SELECT tablename
                FROM pg_tables
                WHERE schemaname = 'public'
                AND tablename LIKE $1
                ORDER BY tablename
            """, f"{table_name}_%")

            # Filter to only partitions for the specified year
            year_pattern = f"_{year}_w"
            dropped = []

            for row in existing:
                partition_name = row['tablename']

                if year_pattern in partition_name:
                    # Drop the partition
                    await db_pool.execute(f"DROP TABLE IF EXISTS {partition_name}")
                    dropped.append({"name": partition_name})
                    logger.warning(
                        "Dropped partition",
                        extra={"partition": partition_name}
                    )

            logger.warning(
                "Year partition cleanup completed",
                extra={"year": year, "dropped_count": len(dropped)}
            )

            return dropped

        except Exception as e:
            logger.error(
                "Error dropping year partitions",
                extra={"error": str(e), "table": table_name, "year": year}
            )
            raise


# Convenience functions
async def ensure_partitions_exist(weeks_ahead: int = 4) -> dict:
    """Ensure partitions exist for the next few weeks."""
    return await PartitionManager.ensure_partitions_exist(weeks_ahead=weeks_ahead)


async def list_partitions() -> list[dict]:
    """List all partitions."""
    return await PartitionManager.list_partitions()


async def drop_old_partitions(older_than_weeks: int = 52) -> list[str]:
    """Drop partitions older than specified weeks."""
    return await PartitionManager.drop_old_partitions(older_than_weeks=older_than_weeks)
