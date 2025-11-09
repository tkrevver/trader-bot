"""Data ingestion service with duplicate prevention and gap detection."""

from datetime import datetime, timedelta, timezone
from typing import List, Optional
import asyncio
import calendar

from app.services.market_data_client_factory import get_market_data_client
from app.services.base_market_data_client import BaseMarketDataClient
from app.db.repositories.market_data import MarketDataRepository
from app.db.partition_manager import PartitionManager
from app.models.market_data import OHLCVBar, MarketDataGap
from app.utils.market_hours import MarketHours
from app.utils.logger import logger
from app.config import settings


class DataIngestionService:
    """
    Service for ingesting market data from configured provider.

    Supports multiple data providers:
    - Tradier: Real-time data, 20 days historical (1min bars)
    - Alpaca: Free tier with 5+ years historical data

    Features:
    - Duplicate prevention (ON CONFLICT DO NOTHING in database)
    - Real-time or near-real-time data (1-minute bars)
    - Gap detection and backfill
    - Market hours awareness
    """

    def __init__(self):
        self.market_data_client: BaseMarketDataClient = get_market_data_client()
        self.market_data_repo = MarketDataRepository()
        self.symbols = ["SPY"]  # Default symbol, can be expanded

    async def ingest_latest_bar(self, symbol: str) -> bool:
        """
        Ingest the latest minute bar for a symbol.

        This is called every minute by the scheduler during market hours.
        Respects extended hours setting from config.

        Args:
            symbol: Trading symbol to ingest

        Returns:
            bool: True if bar was ingested successfully, False otherwise
        """
        try:
            # Check if market is open (respects extended hours setting)
            if not MarketHours.is_extended_market_open():
                logger.debug(
                    "Market is closed, skipping data ingestion",
                    extra={"symbol": symbol}
                )
                return False

            # Calculate expected bar timestamp (previous minute)
            now = MarketHours.get_current_time_et()
            expected_time = now.replace(second=0, microsecond=0) - timedelta(minutes=1)

            logger.info(
                "Ingesting latest bar",
                extra={
                    "symbol": symbol,
                    "expected_time": expected_time.isoformat()
                }
            )

            # Check if bar already exists (duplicate prevention)
            bar_exists = await self.market_data_repo.bar_exists(symbol, expected_time)
            if bar_exists:
                logger.debug(
                    "Bar already exists, skipping",
                    extra={"symbol": symbol, "time": expected_time.isoformat()}
                )
                return True

            # Fetch latest bar from market data provider
            async with self.market_data_client as client:
                bar_data = await client.fetch_latest_bar(symbol=symbol, interval="1min")

            if not bar_data:
                logger.warning(
                    f"Failed to fetch bar from {self.market_data_client.provider_name}",
                    extra={
                        "symbol": symbol,
                        "expected_time": expected_time.isoformat(),
                        "provider": self.market_data_client.provider_name
                    }
                )
                return False

            # Parse provider response to OHLCV format
            parsed_bar = self.market_data_client.parse_bar_to_ohlcv(bar_data)

            # Convert to OHLCVBar model
            bar = OHLCVBar(
                time=datetime.fromtimestamp(parsed_bar["t"] / 1000, tz=timezone.utc),
                symbol=symbol.upper(),
                open=parsed_bar["o"],
                high=parsed_bar["h"],
                low=parsed_bar["l"],
                close=parsed_bar["c"],
                volume=parsed_bar["v"],
                vwap=parsed_bar.get("vw"),  # VWAP if provided by data source
                trades=parsed_bar.get("n")  # Trade count if provided by data source
            )

            # Insert bar into database
            success = await self.market_data_repo.insert_bar(bar)

            if success:
                logger.info(
                    "Successfully ingested bar",
                    extra={
                        "symbol": symbol,
                        "time": bar.time.isoformat(),
                        "close": str(bar.close),
                        "volume": bar.volume
                    }
                )
                return True
            else:
                logger.error(
                    "Failed to insert bar into database",
                    extra={"symbol": symbol, "time": bar.time.isoformat()}
                )
                return False

        except Exception as e:
            logger.error(
                "Error ingesting latest bar",
                extra={"symbol": symbol, "error": str(e)}
            )
            return False

    async def ingest_latest_bars_all_symbols(self) -> dict:
        """
        Ingest latest bars for all configured symbols.

        This is called by the scheduler every minute.
        Respects extended hours setting from config.

        Returns:
            dict: Summary of ingestion results
        """
        results = {
            "total": len(self.symbols),
            "successful": 0,
            "failed": 0,
            "skipped": 0
        }

        try:
            # Check if market is open (respects extended hours setting)
            if not MarketHours.is_extended_market_open():
                logger.info("Market is closed, skipping data ingestion")
                results["skipped"] = len(self.symbols)
                return results

            # Ingest bars for all symbols
            tasks = [self.ingest_latest_bar(symbol) for symbol in self.symbols]
            ingestion_results = await asyncio.gather(*tasks, return_exceptions=True)

            # Count results
            for result in ingestion_results:
                if isinstance(result, Exception):
                    results["failed"] += 1
                elif result:
                    results["successful"] += 1
                else:
                    results["failed"] += 1

            logger.info(
                "Data ingestion completed",
                extra=results
            )

            return results

        except Exception as e:
            logger.error(
                "Error ingesting latest bars for all symbols",
                extra={"error": str(e)}
            )
            return results

    async def backfill_historical_data(
        self,
        symbol: str,
        start_date: datetime,
        end_date: datetime
    ) -> int:
        """
        Backfill historical data for a symbol.

        Args:
            symbol: Trading symbol
            start_date: Start date
            end_date: End date

        Returns:
            int: Number of bars inserted
        """
        try:
            logger.info(
                "Starting historical data backfill",
                extra={
                    "symbol": symbol,
                    "start_date": start_date.isoformat(),
                    "end_date": end_date.isoformat()
                }
            )

            # Fetch historical bars from market data provider
            # session_filter defaults to config setting (respects ENABLE_EXTENDED_HOURS)
            async with self.market_data_client as client:
                bars_data = await client.fetch_timesales(
                    symbol=symbol,
                    interval="1min",
                    start=start_date,
                    end=end_date
                )

            # Convert provider bars to OHLCVBar models
            bars = []
            for bar_data in bars_data:
                parsed_bar = self.market_data_client.parse_bar_to_ohlcv(bar_data)
                bar = OHLCVBar(
                    time=datetime.fromtimestamp(parsed_bar["t"] / 1000, tz=timezone.utc),
                    symbol=symbol.upper(),
                    open=parsed_bar["o"],
                    high=parsed_bar["h"],
                    low=parsed_bar["l"],
                    close=parsed_bar["c"],
                    volume=parsed_bar["v"],
                    vwap=parsed_bar.get("vw"),  # VWAP if provided by data source
                    trades=parsed_bar.get("n")  # Trade count if provided by data source
                )
                bars.append(bar)

            if not bars:
                logger.warning(
                    "No historical bars fetched",
                    extra={"symbol": symbol}
                )
                return 0

            # Insert bars in bulk (duplicates will be ignored)
            count = await self.market_data_repo.insert_bars_bulk(bars)

            logger.info(
                "Historical data backfill completed",
                extra={
                    "symbol": symbol,
                    "bars_fetched": len(bars),
                    "bars_inserted": count
                }
            )

            return count

        except Exception as e:
            logger.error(
                "Error backfilling historical data",
                extra={"symbol": symbol, "error": str(e)}
            )
            return 0

    async def detect_and_backfill_gaps(
        self,
        symbol: str,
        days_back: int = 5
    ) -> List[MarketDataGap]:
        """
        Detect gaps in market data and attempt to backfill them.

        Args:
            symbol: Trading symbol
            days_back: Number of days to check back

        Returns:
            List[MarketDataGap]: List of detected (and attempted to fill) gaps
        """
        try:
            end_time = datetime.utcnow()
            start_time = end_time - timedelta(days=days_back)

            logger.info(
                "Checking for data gaps",
                extra={
                    "symbol": symbol,
                    "start": start_time.isoformat(),
                    "end": end_time.isoformat()
                }
            )

            # Detect gaps
            gaps = await self.market_data_repo.check_for_gaps(
                symbol=symbol,
                start_time=start_time,
                end_time=end_time,
                expected_interval_minutes=1
            )

            if not gaps:
                logger.info(
                    "No data gaps detected",
                    extra={"symbol": symbol}
                )
                return []

            logger.warning(
                "Data gaps detected, attempting to backfill",
                extra={"symbol": symbol, "gap_count": len(gaps)}
            )

            # Attempt to backfill each gap
            for gap in gaps:
                logger.info(
                    "Backfilling gap",
                    extra={
                        "symbol": gap.symbol,
                        "start": gap.start_time.isoformat(),
                        "end": gap.end_time.isoformat(),
                        "missing_bars": gap.missing_bars
                    }
                )

                # Backfill this gap
                await self.backfill_historical_data(
                    symbol=gap.symbol,
                    start_date=gap.start_time,
                    end_date=gap.end_time
                )

            return gaps

        except Exception as e:
            logger.error(
                "Error detecting and backfilling gaps",
                extra={"symbol": symbol, "error": str(e)}
            )
            return []

    async def get_data_health_check(self, symbol: str, hours_back: int = 24) -> dict:
        """
        Perform a health check on market data.

        Args:
            symbol: Trading symbol
            hours_back: Number of hours to check back

        Returns:
            dict: Health check results (timestamps will be serialized to configured timezone by API layer)
        """
        try:
            end_time = datetime.utcnow()
            start_time = end_time - timedelta(hours=hours_back)

            # Get bar count
            bar_count = await self.market_data_repo.get_bar_count(
                symbol=symbol,
                start_time=start_time,
                end_time=end_time
            )

            # Get latest bar
            latest_bar = await self.market_data_repo.get_latest_bar(symbol)

            # Check for gaps
            gaps = await self.market_data_repo.check_for_gaps(
                symbol=symbol,
                start_time=start_time,
                end_time=end_time
            )

            # Return raw gap objects - API layer will serialize to configured timezone
            health = {
                "symbol": symbol,
                "hours_checked": hours_back,
                "bar_count": bar_count,
                "latest_bar_time": latest_bar.time if latest_bar else None,
                "gap_count": len(gaps),
                "gaps": gaps,  # Return MarketDataGap objects with datetime fields
                "healthy": len(gaps) == 0 and bar_count > 0
            }

            logger.info(
                "Data health check completed",
                extra={
                    "symbol": symbol,
                    "hours_checked": hours_back,
                    "bar_count": bar_count,
                    "gap_count": len(gaps),
                    "healthy": health["healthy"]
                }
            )

            return health

        except Exception as e:
            logger.error(
                "Error performing data health check",
                extra={"symbol": symbol, "error": str(e)}
            )
            return {
                "symbol": symbol,
                "healthy": False,
                "error": str(e)
            }

    @staticmethod
    def parse_month_to_dates(month_str: str) -> tuple[datetime, datetime]:
        """
        Parse month string (YYYY-MM) to start and end dates.

        Args:
            month_str: Month in format YYYY-MM

        Returns:
            tuple: (start_date, end_date) for the month

        Raises:
            ValueError: If month format is invalid
        """
        try:
            year, month = map(int, month_str.split("-"))

            # Validate month range
            if not (1 <= month <= 12):
                raise ValueError(f"Invalid month: {month}. Must be between 1 and 12")

            # Start of month
            start_date = datetime(year, month, 1, 0, 0, 0, tzinfo=timezone.utc)

            # End of month (last day at 23:59:59)
            last_day = calendar.monthrange(year, month)[1]
            end_date = datetime(year, month, last_day, 23, 59, 59, tzinfo=timezone.utc)

            return start_date, end_date

        except (ValueError, AttributeError) as e:
            raise ValueError(
                f"Invalid month format: {month_str}. Expected format: YYYY-MM (e.g., 2024-01)"
            ) from e

    async def ensure_partitions_for_date_range(
        self,
        start_date: datetime,
        end_date: datetime,
        table_name: str = "ohlcv_1min"
    ) -> dict:
        """
        Ensure partitions exist for a given date range.

        Creates partitions for all weeks that overlap with the specified date range.

        Args:
            start_date: Start date
            end_date: End date
            table_name: Name of partitioned table

        Returns:
            dict: Partition creation summary
        """
        try:
            logger.info(
                "Ensuring partitions exist for date range",
                extra={
                    "start": start_date.isoformat(),
                    "end": end_date.isoformat(),
                    "table": table_name
                }
            )

            # Get list of existing partitions
            from app.db.connection import db_pool

            existing = await db_pool.fetch("""
                SELECT tablename
                FROM pg_tables
                WHERE schemaname = 'public'
                AND tablename LIKE $1
                ORDER BY tablename
            """, f"{table_name}_%")

            existing_partitions = {row['tablename'] for row in existing}

            # Calculate start of the week containing start_date (Monday)
            current = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
            current = current - timedelta(days=current.weekday())

            # Calculate end boundary
            end_boundary = end_date.replace(hour=23, minute=59, second=59, microsecond=999999)

            created = []
            skipped = []

            # Create partitions for each week in the range
            while current <= end_boundary:
                week_end = current + timedelta(weeks=1)

                # Use ISO calendar week number for partition name
                iso_year, iso_week, _ = current.isocalendar()
                partition_name = f"{table_name}_{iso_year}_w{iso_week:02d}"

                if partition_name not in existing_partitions:
                    try:
                        # Create partition
                        await db_pool.execute(f"""
                            CREATE TABLE {partition_name} PARTITION OF {table_name}
                            FOR VALUES FROM ('{current.isoformat()}') TO ('{week_end.isoformat()}')
                        """)
                        created.append(partition_name)
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
                        # Continue to next partition even if one fails
                else:
                    skipped.append(partition_name)

                current = week_end

            logger.info(
                "Partition check completed",
                extra={
                    "partitions_created": len(created),
                    "partitions_skipped": len(skipped)
                }
            )

            return {
                "created": created,
                "skipped": skipped,
                "total_created": len(created),
                "total_skipped": len(skipped)
            }

        except Exception as e:
            logger.error(
                "Error ensuring partitions for date range",
                extra={"error": str(e)}
            )
            raise

    async def backfill_with_validation(
        self,
        symbol: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        days: Optional[int] = None,
        max_days: int = 30
    ) -> dict:
        """
        Backfill historical data with date validation and automatic gap detection.

        Supports two ways to specify date range:
        1. Explicit dates: Provide both start_date and end_date
        2. Days back: Provide days parameter (e.g., days=7 for last 7 days)

        Args:
            symbol: Trading symbol
            start_date: Start date for backfill (optional if using days)
            end_date: End date for backfill (optional if using days)
            days: Number of days to backfill from today (optional if using dates)
            max_days: Maximum allowed days in range (default: 30)

        Returns:
            dict: Backfill results including gap detection

        Raises:
            ValueError: If date parameters are invalid
        """
        try:
            # Calculate dates based on input
            if days is not None:
                # Use days parameter
                end_date = datetime.utcnow()
                start_date = end_date - timedelta(days=days)
            elif start_date is None or end_date is None:
                # Neither days nor both dates provided
                raise ValueError("Either provide 'days' parameter OR both 'start_date' and 'end_date'")

            logger.info(
                "Backfill with validation requested",
                extra={
                    "symbol": symbol,
                    "start": start_date.isoformat(),
                    "end": end_date.isoformat()
                }
            )

            # Validate date range
            if start_date >= end_date:
                raise ValueError("start_date must be before end_date")

            # Limit backfill range to avoid API rate limits
            if (end_date - start_date).days > max_days:
                raise ValueError(f"Date range too large. Maximum {max_days} days allowed.")

            # Ensure partitions exist for this date range
            await self.ensure_partitions_for_date_range(start_date, end_date)

            # Perform backfill
            count = await self.backfill_historical_data(
                symbol=symbol,
                start_date=start_date,
                end_date=end_date
            )

            # Always check for gaps to ensure data completeness
            gaps = await self.detect_and_backfill_gaps(
                symbol=symbol,
                days_back=(end_date - start_date).days
            )

            return {
                "symbol": symbol,
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "bars_inserted": count,
                "gaps_found": len(gaps),
                "gaps": [
                    {
                        "start_time": gap.start_time.isoformat(),
                        "end_time": gap.end_time.isoformat(),
                        "missing_bars": gap.missing_bars
                    }
                    for gap in gaps
                ],
                "success": count > 0
            }

        except ValueError as e:
            logger.error(
                "Validation error in backfill",
                extra={"symbol": symbol, "error": str(e)}
            )
            raise
        except Exception as e:
            logger.error(
                "Error in backfill with validation",
                extra={"symbol": symbol, "error": str(e)}
            )
            raise

    async def backfill_month(
        self,
        symbol: str,
        month: str
    ) -> dict:
        """
        Backfill historical data for a specific month.

        Args:
            symbol: Trading symbol
            month: Month in format YYYY-MM (e.g., "2024-01")

        Returns:
            dict: Backfill results including gap detection

        Raises:
            ValueError: If month format is invalid
        """
        try:
            # Parse month to start/end dates
            start_date, end_date = self.parse_month_to_dates(month)

            logger.info(
                "Backfilling data for month",
                extra={
                    "symbol": symbol,
                    "month": month,
                    "start": start_date.isoformat(),
                    "end": end_date.isoformat()
                }
            )

            # Use backfill_with_validation with max_days=31 for month
            result = await self.backfill_with_validation(
                symbol=symbol,
                start_date=start_date,
                end_date=end_date,
                max_days=31
            )

            # Add month to result
            result["month"] = month

            return result

        except ValueError as e:
            logger.error(
                "Validation error in month backfill",
                extra={"symbol": symbol, "month": month, "error": str(e)}
            )
            raise
        except Exception as e:
            logger.error(
                "Error in month backfill",
                extra={"symbol": symbol, "month": month, "error": str(e)}
            )
            raise

    async def backfill_year(
        self,
        symbol: str,
        year: int
    ) -> dict:
        """
        Backfill historical data for an entire year (month by month).

        This method processes each month sequentially to avoid API rate limits
        and ensures partitions are created for each month before backfilling.

        Args:
            symbol: Trading symbol
            year: Year to backfill (e.g., 2024)

        Returns:
            dict: Aggregated backfill results for all months

        Raises:
            ValueError: If year is invalid
        """
        try:
            # Validate year
            current_year = datetime.utcnow().year
            if year < 2000 or year > current_year:
                raise ValueError(f"Invalid year: {year}. Must be between 2000 and {current_year}")

            logger.info(
                "Backfilling data for year",
                extra={"symbol": symbol, "year": year}
            )

            total_bars = 0
            total_gaps = 0
            monthly_results = []
            failed_months = []

            # Process each month sequentially
            for month_num in range(1, 13):
                month_str = f"{year}-{month_num:02d}"

                try:
                    logger.info(
                        "Processing month",
                        extra={"symbol": symbol, "month": month_str}
                    )

                    # Backfill this month
                    month_result = await self.backfill_month(symbol, month_str)

                    total_bars += month_result.get("bars_inserted", 0)
                    total_gaps += month_result.get("gaps_found", 0)

                    monthly_results.append({
                        "month": month_str,
                        "bars_inserted": month_result.get("bars_inserted", 0),
                        "gaps_found": month_result.get("gaps_found", 0),
                        "success": month_result.get("success", False)
                    })

                    logger.info(
                        "Month backfill completed",
                        extra={
                            "symbol": symbol,
                            "month": month_str,
                            "bars": month_result.get("bars_inserted", 0)
                        }
                    )

                except Exception as e:
                    logger.error(
                        "Failed to backfill month",
                        extra={"symbol": symbol, "month": month_str, "error": str(e)}
                    )
                    failed_months.append({
                        "month": month_str,
                        "error": str(e)
                    })
                    # Continue to next month even if one fails

            return {
                "symbol": symbol,
                "year": year,
                "total_bars_inserted": total_bars,
                "total_gaps_found": total_gaps,
                "months_processed": len(monthly_results),
                "months_failed": len(failed_months),
                "monthly_results": monthly_results,
                "failed_months": failed_months,
                "success": len(failed_months) == 0 and total_bars > 0
            }

        except ValueError as e:
            logger.error(
                "Validation error in year backfill",
                extra={"symbol": symbol, "year": year, "error": str(e)}
            )
            raise
        except Exception as e:
            logger.error(
                "Error in year backfill",
                extra={"symbol": symbol, "year": year, "error": str(e)}
            )
            raise

    async def get_market_data_stats(self, symbol: str) -> dict:
        """
        Get comprehensive statistics about market data for a symbol.

        Args:
            symbol: Trading symbol

        Returns:
            dict: Market data statistics including bar counts and latest bar
        """
        try:
            # Get bar counts for different time ranges
            now = datetime.utcnow()
            day_ago = now - timedelta(days=1)
            week_ago = now - timedelta(weeks=1)
            month_ago = now - timedelta(days=30)

            stats = {
                "symbol": symbol,
                "bar_counts": {
                    "last_24h": await self.market_data_repo.get_bar_count(symbol, day_ago, now),
                    "last_7d": await self.market_data_repo.get_bar_count(symbol, week_ago, now),
                    "last_30d": await self.market_data_repo.get_bar_count(symbol, month_ago, now),
                    "total": await self.market_data_repo.get_bar_count(symbol)
                },
                "latest_bar": None
            }

            # Get latest bar
            latest = await self.market_data_repo.get_latest_bar(symbol)
            if latest:
                stats["latest_bar"] = {
                    "time": latest.time.isoformat(),
                    "close": str(latest.close),
                    "volume": latest.volume
                }

            logger.info(
                "Market data stats retrieved",
                extra={"symbol": symbol, "total_bars": stats["bar_counts"]["total"]}
            )

            return stats

        except Exception as e:
            logger.error(
                "Error getting market data stats",
                extra={"symbol": symbol, "error": str(e)}
            )
            raise


# Singleton instance
_data_ingestion_service: Optional[DataIngestionService] = None


def get_data_ingestion_service() -> DataIngestionService:
    """Get or create data ingestion service instance."""
    global _data_ingestion_service
    if _data_ingestion_service is None:
        _data_ingestion_service = DataIngestionService()
    return _data_ingestion_service
