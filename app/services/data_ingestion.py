"""Data ingestion service with duplicate prevention and gap detection."""

from datetime import datetime, timedelta, timezone
from typing import List, Optional
import asyncio

from app.services.tradier_client import TradierClient
from app.db.repositories.market_data import MarketDataRepository
from app.models.market_data import OHLCVBar, MarketDataGap
from app.utils.market_hours import MarketHours
from app.utils.logger import logger
from app.config import settings


class DataIngestionService:
    """
    Service for ingesting market data from Tradier.

    Features:
    - Duplicate prevention (ON CONFLICT DO NOTHING in database)
    - Real-time data from Tradier (1-minute bars)
    - Gap detection and backfill
    - Market hours awareness
    """

    def __init__(self):
        self.tradier_client = TradierClient()
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

            # Fetch latest bar from Tradier
            async with self.tradier_client as client:
                bar_data = await client.fetch_latest_bar(symbol=symbol, interval="1min")

            if not bar_data:
                logger.warning(
                    "Failed to fetch bar from Tradier",
                    extra={"symbol": symbol, "expected_time": expected_time.isoformat()}
                )
                return False

            # Parse Tradier response to OHLCV format
            parsed_bar = self.tradier_client.parse_bar_to_ohlcv(bar_data)

            # Convert to OHLCVBar model
            bar = OHLCVBar(
                time=datetime.fromtimestamp(parsed_bar["t"] / 1000, tz=timezone.utc),
                symbol=symbol.upper(),
                open=parsed_bar["o"],
                high=parsed_bar["h"],
                low=parsed_bar["l"],
                close=parsed_bar["c"],
                volume=parsed_bar["v"],
                vwap=None,  # Tradier doesn't provide VWAP
                trades=None  # Tradier doesn't provide trade count
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

            # Fetch historical bars from Tradier
            # session_filter defaults to config setting (respects ENABLE_EXTENDED_HOURS)
            async with self.tradier_client as client:
                bars_data = await client.fetch_timesales(
                    symbol=symbol,
                    interval="1min",
                    start=start_date,
                    end=end_date
                )

            # Convert Tradier bars to OHLCVBar models
            bars = []
            for bar_data in bars_data:
                parsed_bar = self.tradier_client.parse_bar_to_ohlcv(bar_data)
                bar = OHLCVBar(
                    time=datetime.fromtimestamp(parsed_bar["t"] / 1000, tz=timezone.utc),
                    symbol=symbol.upper(),
                    open=parsed_bar["o"],
                    high=parsed_bar["h"],
                    low=parsed_bar["l"],
                    close=parsed_bar["c"],
                    volume=parsed_bar["v"],
                    vwap=None,
                    trades=None
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
            dict: Health check results
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

            health = {
                "symbol": symbol,
                "hours_checked": hours_back,
                "bar_count": bar_count,
                "latest_bar_time": latest_bar.time.isoformat() if latest_bar else None,
                "gap_count": len(gaps),
                "gaps": [
                    {
                        "start": gap.start_time.isoformat(),
                        "end": gap.end_time.isoformat(),
                        "missing_bars": gap.missing_bars
                    }
                    for gap in gaps
                ],
                "healthy": len(gaps) == 0 and bar_count > 0
            }

            logger.info(
                "Data health check completed",
                extra=health
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


# Singleton instance
_data_ingestion_service: Optional[DataIngestionService] = None


def get_data_ingestion_service() -> DataIngestionService:
    """Get or create data ingestion service instance."""
    global _data_ingestion_service
    if _data_ingestion_service is None:
        _data_ingestion_service = DataIngestionService()
    return _data_ingestion_service
