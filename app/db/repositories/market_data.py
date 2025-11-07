"""Market data repository for database operations."""

from datetime import datetime
from typing import List, Optional
from decimal import Decimal

from app.db.connection import db_pool
from app.models.market_data import OHLCVBar, MarketDataGap
from app.utils.logger import logger


class MarketDataRepository:
    """Repository for market data operations."""

    @staticmethod
    async def insert_bar(bar: OHLCVBar) -> bool:
        """
        Insert a single OHLCV bar into the database.

        Args:
            bar: OHLCVBar to insert

        Returns:
            bool: True if inserted successfully, False otherwise
        """
        try:
            query = """
                INSERT INTO ohlcv_1min (time, symbol, open, high, low, close, volume, vwap, trades)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                ON CONFLICT (time, symbol) DO NOTHING
            """

            await db_pool.execute(
                query,
                bar.time,
                bar.symbol,
                bar.open,
                bar.high,
                bar.low,
                bar.close,
                bar.volume,
                bar.vwap,
                bar.trades
            )

            logger.debug(
                "Inserted bar",
                extra={"symbol": bar.symbol, "time": bar.time.isoformat()}
            )

            return True

        except Exception as e:
            logger.error(
                "Error inserting bar",
                extra={"symbol": bar.symbol, "time": bar.time.isoformat(), "error": str(e)}
            )
            return False

    @staticmethod
    async def insert_bars_bulk(bars: List[OHLCVBar]) -> int:
        """
        Insert multiple OHLCV bars in bulk.

        Args:
            bars: List of OHLCVBar to insert

        Returns:
            int: Number of bars inserted
        """
        if not bars:
            return 0

        try:
            query = """
                INSERT INTO ohlcv_1min (time, symbol, open, high, low, close, volume, vwap, trades)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                ON CONFLICT (time, symbol) DO NOTHING
            """

            # Prepare data for bulk insert
            values = [
                (
                    bar.time,
                    bar.symbol,
                    bar.open,
                    bar.high,
                    bar.low,
                    bar.close,
                    bar.volume,
                    bar.vwap,
                    bar.trades
                )
                for bar in bars
            ]

            # Execute bulk insert
            async with db_pool.pool.acquire() as conn:
                await conn.executemany(query, values)

            logger.info(
                "Bulk inserted bars",
                extra={"count": len(bars), "symbol": bars[0].symbol if bars else None}
            )

            return len(bars)

        except Exception as e:
            logger.error(
                "Error bulk inserting bars",
                extra={"count": len(bars), "error": str(e)}
            )
            return 0

    @staticmethod
    async def get_latest_bar(symbol: str, timeframe: str = "1min") -> Optional[OHLCVBar]:
        """
        Get the latest bar for a symbol.

        Args:
            symbol: Trading symbol
            timeframe: Timeframe (1min, 5min, 15min, 30min, daily)

        Returns:
            Optional[OHLCVBar]: Latest bar or None
        """
        try:
            # Map timeframe to table/view
            table_map = {
                "1min": "ohlcv_1min",
                "5min": "ohlcv_5min",
                "15min": "ohlcv_15min",
                "30min": "ohlcv_30min",
                "daily": "ohlcv_daily"
            }

            table = table_map.get(timeframe, "ohlcv_1min")

            query = f"""
                SELECT time, symbol, open, high, low, close, volume, vwap, trades
                FROM {table}
                WHERE symbol = $1
                ORDER BY time DESC
                LIMIT 1
            """

            row = await db_pool.fetchrow(query, symbol)

            if row:
                return OHLCVBar(
                    time=row["time"],
                    symbol=row["symbol"],
                    open=Decimal(str(row["open"])),
                    high=Decimal(str(row["high"])),
                    low=Decimal(str(row["low"])),
                    close=Decimal(str(row["close"])),
                    volume=row["volume"],
                    vwap=Decimal(str(row["vwap"])) if row["vwap"] else None,
                    trades=row["trades"]
                )

            return None

        except Exception as e:
            logger.error(
                "Error getting latest bar",
                extra={"symbol": symbol, "timeframe": timeframe, "error": str(e)}
            )
            return None

    @staticmethod
    async def get_bars(
        symbol: str,
        start_time: datetime,
        end_time: datetime,
        timeframe: str = "1min",
        limit: Optional[int] = None
    ) -> List[OHLCVBar]:
        """
        Get bars for a symbol within a time range.

        Args:
            symbol: Trading symbol
            start_time: Start time (inclusive)
            end_time: End time (inclusive)
            timeframe: Timeframe (1min, 5min, 15min, 30min, daily)
            limit: Maximum number of bars to return

        Returns:
            List[OHLCVBar]: List of bars
        """
        try:
            # Map timeframe to table/view
            table_map = {
                "1min": "ohlcv_1min",
                "5min": "ohlcv_5min",
                "15min": "ohlcv_15min",
                "30min": "ohlcv_30min",
                "daily": "ohlcv_daily"
            }

            table = table_map.get(timeframe, "ohlcv_1min")

            query = f"""
                SELECT time, symbol, open, high, low, close, volume, vwap, trades
                FROM {table}
                WHERE symbol = $1
                AND time >= $2
                AND time <= $3
                ORDER BY time ASC
            """

            if limit:
                query += f" LIMIT {limit}"

            rows = await db_pool.fetch(query, symbol, start_time, end_time)

            bars = [
                OHLCVBar(
                    time=row["time"],
                    symbol=row["symbol"],
                    open=Decimal(str(row["open"])),
                    high=Decimal(str(row["high"])),
                    low=Decimal(str(row["low"])),
                    close=Decimal(str(row["close"])),
                    volume=row["volume"],
                    vwap=Decimal(str(row["vwap"])) if row["vwap"] else None,
                    trades=row["trades"]
                )
                for row in rows
            ]

            return bars

        except Exception as e:
            logger.error(
                "Error getting bars",
                extra={
                    "symbol": symbol,
                    "start": start_time.isoformat(),
                    "end": end_time.isoformat(),
                    "error": str(e)
                }
            )
            return []

    @staticmethod
    async def check_for_gaps(
        symbol: str,
        start_time: datetime,
        end_time: datetime,
        expected_interval_minutes: int = 1
    ) -> List[MarketDataGap]:
        """
        Check for gaps in market data.

        Args:
            symbol: Trading symbol
            start_time: Start time
            end_time: End time
            expected_interval_minutes: Expected interval between bars in minutes

        Returns:
            List[MarketDataGap]: List of detected gaps
        """
        try:
            query = """
                WITH bar_gaps AS (
                    SELECT
                        time AS current_time,
                        LEAD(time) OVER (ORDER BY time) AS next_time,
                        EXTRACT(EPOCH FROM (LEAD(time) OVER (ORDER BY time) - time)) / 60 AS minutes_gap
                    FROM ohlcv_1min
                    WHERE symbol = $1
                    AND time >= $2
                    AND time <= $3
                )
                SELECT current_time, next_time, minutes_gap
                FROM bar_gaps
                WHERE minutes_gap > $4
                ORDER BY current_time
            """

            rows = await db_pool.fetch(
                query,
                symbol,
                start_time,
                end_time,
                expected_interval_minutes
            )

            gaps = []
            for row in rows:
                if row["next_time"]:
                    gap = MarketDataGap(
                        symbol=symbol,
                        timeframe="1min",
                        start_time=row["current_time"],
                        end_time=row["next_time"],
                        missing_bars=int(row["minutes_gap"]) - 1
                    )
                    gaps.append(gap)

            if gaps:
                logger.warning(
                    "Detected market data gaps",
                    extra={"symbol": symbol, "gap_count": len(gaps)}
                )

            return gaps

        except Exception as e:
            logger.error(
                "Error checking for gaps",
                extra={"symbol": symbol, "error": str(e)}
            )
            return []

    @staticmethod
    async def bar_exists(symbol: str, time: datetime) -> bool:
        """
        Check if a bar exists for a symbol at a specific time.

        Args:
            symbol: Trading symbol
            time: Bar timestamp

        Returns:
            bool: True if bar exists, False otherwise
        """
        try:
            query = """
                SELECT EXISTS(
                    SELECT 1 FROM ohlcv_1min
                    WHERE symbol = $1 AND time = $2
                )
            """

            exists = await db_pool.fetchval(query, symbol, time)
            return bool(exists)

        except Exception as e:
            logger.error(
                "Error checking bar existence",
                extra={"symbol": symbol, "time": time.isoformat(), "error": str(e)}
            )
            return False

    @staticmethod
    async def get_bar_count(
        symbol: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> int:
        """
        Get count of bars for a symbol.

        Args:
            symbol: Trading symbol
            start_time: Optional start time
            end_time: Optional end time

        Returns:
            int: Number of bars
        """
        try:
            if start_time and end_time:
                query = """
                    SELECT COUNT(*) FROM ohlcv_1min
                    WHERE symbol = $1 AND time >= $2 AND time <= $3
                """
                count = await db_pool.fetchval(query, symbol, start_time, end_time)
            elif start_time:
                query = """
                    SELECT COUNT(*) FROM ohlcv_1min
                    WHERE symbol = $1 AND time >= $2
                """
                count = await db_pool.fetchval(query, symbol, start_time)
            else:
                query = """
                    SELECT COUNT(*) FROM ohlcv_1min
                    WHERE symbol = $1
                """
                count = await db_pool.fetchval(query, symbol)

            return count or 0

        except Exception as e:
            logger.error(
                "Error getting bar count",
                extra={"symbol": symbol, "error": str(e)}
            )
            return 0
