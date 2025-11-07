"""Polygon.io (Massive) REST API client with timestamp verification and retry logic."""

import httpx
import asyncio
from datetime import datetime, timedelta
from typing import Optional, List
from decimal import Decimal

from app.config import settings
from app.utils.logger import logger
from app.models.market_data import OHLCVBar


class PolygonClient:
    """
    REST API client for Polygon.io (now Massive).

    Implements:
    - Timestamp verification with retry logic
    - Historical data fetching for backfill
    - Proper error handling and rate limiting
    """

    def __init__(self):
        self.api_key = settings.polygon_api_key
        self.base_url = settings.polygon_rest_url
        self.client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self):
        """Async context manager entry."""
        self.client = httpx.AsyncClient(timeout=30.0)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self.client:
            await self.client.aclose()

    async def fetch_latest_bar(
        self,
        symbol: str,
        timeframe: str = "1",
        multiplier: str = "minute"
    ) -> Optional[dict]:
        """
        Fetch the most recent bar for a symbol.

        Args:
            symbol: Trading symbol (e.g., "SPY")
            timeframe: Timeframe multiplier (e.g., "1")
            multiplier: Timeframe unit (e.g., "minute", "hour", "day")

        Returns:
            Optional[dict]: Latest bar data or None if not found
        """
        if not self.client:
            raise RuntimeError("Client not initialized. Use async context manager.")

        try:
            # Get bars from the last day
            to_date = datetime.utcnow()
            from_date = to_date - timedelta(days=1)

            url = f"{self.base_url}/v2/aggs/ticker/{symbol}/range/{timeframe}/{multiplier}/{from_date.strftime('%Y-%m-%d')}/{to_date.strftime('%Y-%m-%d')}"

            params = {
                "apiKey": self.api_key,
                "limit": 1,
                "sort": "desc"  # Most recent first
            }

            logger.debug(
                "Fetching latest bar from Polygon",
                extra={"symbol": symbol, "url": url}
            )

            response = await self.client.get(url, params=params)
            response.raise_for_status()

            data = response.json()

            if data.get("status") == "OK" and data.get("results"):
                bar = data["results"][0]
                logger.debug(
                    "Fetched latest bar",
                    extra={
                        "symbol": symbol,
                        "timestamp": bar.get("t"),
                        "close": bar.get("c")
                    }
                )
                return bar
            else:
                logger.warning(
                    "No bar data returned from Polygon",
                    extra={"symbol": symbol, "response": data}
                )
                return None

        except httpx.HTTPStatusError as e:
            logger.error(
                "HTTP error fetching latest bar",
                extra={
                    "symbol": symbol,
                    "status_code": e.response.status_code,
                    "error": str(e)
                }
            )
            return None
        except Exception as e:
            logger.error(
                "Error fetching latest bar",
                extra={"symbol": symbol, "error": str(e)}
            )
            return None

    async def fetch_and_verify_bar(
        self,
        symbol: str,
        expected_time: datetime,
        max_retries: int = 3
    ) -> Optional[OHLCVBar]:
        """
        Fetch bar and verify it matches the expected timestamp.

        Implements retry logic with increasing delays to handle cases where
        Polygon hasn't aggregated the latest bar yet.

        Args:
            symbol: Trading symbol
            expected_time: Expected bar timestamp
            max_retries: Maximum number of retry attempts

        Returns:
            Optional[OHLCVBar]: Verified bar or None if not found/stale
        """
        retry_delays = [2, 5, 10]  # seconds between retries

        for attempt in range(max_retries):
            logger.debug(
                "Fetching bar with verification",
                extra={
                    "symbol": symbol,
                    "expected_time": expected_time.isoformat(),
                    "attempt": attempt + 1
                }
            )

            # Fetch latest bar
            bar_data = await self.fetch_latest_bar(symbol)

            if not bar_data:
                logger.warning(
                    "No bar data returned",
                    extra={"symbol": symbol, "attempt": attempt + 1}
                )

                # Retry if not last attempt
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delays[attempt])
                    continue
                else:
                    return None

            # Parse bar timestamp (Polygon returns milliseconds since epoch)
            bar_timestamp = datetime.fromtimestamp(bar_data["t"] / 1000)

            # Verify timestamp matches expected time (within 1 minute tolerance)
            time_diff = abs((bar_timestamp - expected_time).total_seconds())

            if time_diff <= 60:  # Within 1 minute
                logger.info(
                    "Bar verified successfully",
                    extra={
                        "symbol": symbol,
                        "expected": expected_time.isoformat(),
                        "actual": bar_timestamp.isoformat(),
                        "attempt": attempt + 1
                    }
                )

                # Convert to OHLCVBar model
                return OHLCVBar(
                    time=bar_timestamp,
                    symbol=symbol,
                    open=Decimal(str(bar_data["o"])),
                    high=Decimal(str(bar_data["h"])),
                    low=Decimal(str(bar_data["l"])),
                    close=Decimal(str(bar_data["c"])),
                    volume=bar_data["v"],
                    vwap=Decimal(str(bar_data.get("vw", 0))) if bar_data.get("vw") else None,
                    trades=bar_data.get("n")
                )

            elif bar_timestamp < expected_time:
                # Got stale bar, Polygon hasn't aggregated new one yet
                logger.warning(
                    "Received stale bar",
                    extra={
                        "symbol": symbol,
                        "expected": expected_time.isoformat(),
                        "actual": bar_timestamp.isoformat(),
                        "attempt": attempt + 1
                    }
                )

                # Retry if not last attempt
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delays[attempt])
                    continue
                else:
                    logger.error(
                        "Could not get expected bar after retries",
                        extra={"symbol": symbol, "expected_time": expected_time.isoformat()}
                    )
                    return None

            else:
                # Got future bar (unexpected)
                logger.error(
                    "Received future bar",
                    extra={
                        "symbol": symbol,
                        "expected": expected_time.isoformat(),
                        "actual": bar_timestamp.isoformat()
                    }
                )
                return None

        return None

    async def fetch_historical_bars(
        self,
        symbol: str,
        from_date: datetime,
        to_date: datetime,
        timeframe: str = "1",
        multiplier: str = "minute",
        limit: int = 50000
    ) -> List[OHLCVBar]:
        """
        Fetch historical bars for backtesting or backfill.

        Args:
            symbol: Trading symbol
            from_date: Start date
            to_date: End date
            timeframe: Timeframe multiplier
            multiplier: Timeframe unit
            limit: Maximum number of bars to fetch

        Returns:
            List[OHLCVBar]: List of historical bars
        """
        if not self.client:
            raise RuntimeError("Client not initialized. Use async context manager.")

        try:
            url = f"{self.base_url}/v2/aggs/ticker/{symbol}/range/{timeframe}/{multiplier}/{from_date.strftime('%Y-%m-%d')}/{to_date.strftime('%Y-%m-%d')}"

            params = {
                "apiKey": self.api_key,
                "limit": limit,
                "adjusted": "true",
                "sort": "asc"
            }

            logger.info(
                "Fetching historical bars",
                extra={
                    "symbol": symbol,
                    "from_date": from_date.isoformat(),
                    "to_date": to_date.isoformat(),
                    "limit": limit
                }
            )

            response = await self.client.get(url, params=params)
            response.raise_for_status()

            data = response.json()

            if data.get("status") == "OK" and data.get("results"):
                bars = []
                for bar_data in data["results"]:
                    bar = OHLCVBar(
                        time=datetime.fromtimestamp(bar_data["t"] / 1000),
                        symbol=symbol,
                        open=Decimal(str(bar_data["o"])),
                        high=Decimal(str(bar_data["h"])),
                        low=Decimal(str(bar_data["l"])),
                        close=Decimal(str(bar_data["c"])),
                        volume=bar_data["v"],
                        vwap=Decimal(str(bar_data.get("vw", 0))) if bar_data.get("vw") else None,
                        trades=bar_data.get("n")
                    )
                    bars.append(bar)

                logger.info(
                    "Fetched historical bars",
                    extra={"symbol": symbol, "count": len(bars)}
                )

                return bars
            else:
                logger.warning(
                    "No historical data returned",
                    extra={"symbol": symbol, "response": data}
                )
                return []

        except httpx.HTTPStatusError as e:
            logger.error(
                "HTTP error fetching historical bars",
                extra={
                    "symbol": symbol,
                    "status_code": e.response.status_code,
                    "error": str(e)
                }
            )
            return []
        except Exception as e:
            logger.error(
                "Error fetching historical bars",
                extra={"symbol": symbol, "error": str(e)}
            )
            return []

    async def get_ticker_details(self, symbol: str) -> Optional[dict]:
        """
        Get ticker details (company info, market cap, etc).

        Args:
            symbol: Trading symbol

        Returns:
            Optional[dict]: Ticker details or None
        """
        if not self.client:
            raise RuntimeError("Client not initialized. Use async context manager.")

        try:
            url = f"{self.base_url}/v3/reference/tickers/{symbol}"
            params = {"apiKey": self.api_key}

            response = await self.client.get(url, params=params)
            response.raise_for_status()

            data = response.json()

            if data.get("status") == "OK" and data.get("results"):
                return data["results"]
            else:
                return None

        except Exception as e:
            logger.error(
                "Error fetching ticker details",
                extra={"symbol": symbol, "error": str(e)}
            )
            return None


# Singleton instance
_polygon_client: Optional[PolygonClient] = None


async def get_polygon_client() -> PolygonClient:
    """Get or create Polygon client instance."""
    global _polygon_client
    if _polygon_client is None:
        _polygon_client = PolygonClient()
    return _polygon_client
