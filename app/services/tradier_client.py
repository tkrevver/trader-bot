"""Tradier REST API client for market data."""

import aiohttp
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from decimal import Decimal
import pytz

from app.config import settings
from app.utils.logger import logger


class TradierClient:
    """
    Client for Tradier Brokerage API.

    Provides real-time and historical market data for equities.
    API Documentation: https://docs.tradier.com
    """

    def __init__(self, api_token: Optional[str] = None, base_url: Optional[str] = None):
        """
        Initialize Tradier client.

        Args:
            api_token: Tradier API token (uses settings.tradier_api_token if not provided)
            base_url: Base URL for API (uses settings.tradier_api_url if not provided)
        """
        self.api_token = api_token or settings.tradier_api_token
        self.base_url = base_url or settings.tradier_api_url
        self.session: Optional[aiohttp.ClientSession] = None

    async def __aenter__(self):
        """Context manager entry."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        await self.close()

    async def connect(self):
        """Create HTTP session."""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(
                headers={
                    "Authorization": f"Bearer {self.api_token}",
                    "Accept": "application/json"
                }
            )

    async def close(self):
        """Close HTTP session."""
        if self.session and not self.session.closed:
            await self.session.close()

    async def fetch_timesales(
        self,
        symbol: str,
        interval: str = "5min",
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        session_filter: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Fetch time and sales (timesales) data for charting.

        Available intervals and their historical limits:
        - 1min: 20 days (open), 10 days (all)
        - 5min: 40 days (open), 18 days (all)
        - 15min: 40 days (open), 18 days (all)
        - tick: 5 days (open only)

        Args:
            symbol: Stock symbol (e.g., "SPY")
            interval: Time interval (1min, 5min, 15min, tick)
            start: Start date/time (defaults to appropriate lookback based on interval)
            end: End date/time (defaults to now)
            session_filter: "open" for market hours only, "all" for extended hours (defaults to config setting)

        Returns:
            List of timesales bars with timestamp, open, high, low, close, volume
        """
        if not self.session or self.session.closed:
            await self.connect()

        # Use config setting if not specified
        if session_filter is None:
            session_filter = settings.tradier_session_filter

        # Set default date range based on interval
        # IMPORTANT: Use configured timezone (Eastern Time for US markets)
        # Tradier expects times in market timezone (ET)
        if end is None:
            tz = pytz.timezone(settings.timezone)
            end = datetime.now(tz)

        if start is None:
            # Use safe defaults within historical limits
            if interval == "1min":
                start = end - timedelta(days=10 if session_filter == "all" else 20)
            elif interval in ["5min", "15min"]:
                start = end - timedelta(days=18 if session_filter == "all" else 40)
            elif interval == "tick":
                start = end - timedelta(days=5)
            else:
                start = end - timedelta(days=1)  # Default to 1 day

        url = f"{self.base_url}/v1/markets/timesales"
        params = {
            "symbol": symbol.upper(),
            "interval": interval,
            "start": start.strftime("%Y-%m-%d %H:%M"),
            "end": end.strftime("%Y-%m-%d %H:%M"),
            "session_filter": session_filter
        }

        try:
            async with self.session.get(url, params=params) as response:
                response.raise_for_status()
                data = await response.json()

                # Tradier returns data under 'series' -> 'data' key
                if "series" in data and "data" in data["series"]:
                    bars = data["series"]["data"]

                    logger.info(
                        "Fetched timesales data from Tradier",
                        extra={
                            "symbol": symbol,
                            "interval": interval,
                            "bar_count": len(bars),
                            "start": start.isoformat(),
                            "end": end.isoformat()
                        }
                    )

                    return bars
                else:
                    logger.warning(
                        "No timesales data in Tradier response",
                        extra={"symbol": symbol, "response": data}
                    )
                    return []

        except aiohttp.ClientResponseError as e:
            logger.error(
                "Tradier API error",
                extra={
                    "symbol": symbol,
                    "status": e.status,
                    "message": str(e)
                }
            )
            raise
        except Exception as e:
            logger.error(
                "Error fetching timesales from Tradier",
                extra={"symbol": symbol, "error": str(e)}
            )
            raise

    async def fetch_latest_bar(
        self,
        symbol: str,
        interval: str = "1min",
        session_filter: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Fetch the most recent bar for a symbol.

        Args:
            symbol: Stock symbol
            interval: Time interval (1min, 5min, 15min, etc)
            session_filter: "open" for market hours only, "all" for extended hours (defaults to config setting)

        Returns:
            Latest bar or None if not available
        """
        # Fetch last hour of data to ensure we get the latest bar
        # Use configured timezone (Eastern Time) since Tradier expects ET
        tz = pytz.timezone(settings.timezone)
        end = datetime.now(tz)
        start = end - timedelta(hours=1)

        bars = await self.fetch_timesales(
            symbol=symbol,
            interval=interval,
            start=start,
            end=end,
            session_filter=session_filter  # Will use config default if None
        )

        if bars:
            # Return the most recent bar
            latest = bars[-1]
            logger.info(
                "Fetched latest bar from Tradier",
                extra={
                    "symbol": symbol,
                    "interval": interval,
                    "time": latest.get("time"),
                    "close": latest.get("close")
                }
            )
            return latest

        return None

    def parse_bar_to_ohlcv(self, bar: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parse Tradier bar format to our OHLCV format.

        Tradier format:
        {
            "time": "2025-11-07 09:35:00",
            "timestamp": 1730984100,
            "open": 583.45,
            "high": 583.98,
            "low": 583.40,
            "close": 583.75,
            "volume": 125000
        }

        Args:
            bar: Tradier bar data

        Returns:
            Normalized OHLCV bar
        """
        return {
            "t": bar.get("timestamp", 0) * 1000,  # Convert to milliseconds
            "o": Decimal(str(bar.get("open", 0))),
            "h": Decimal(str(bar.get("high", 0))),
            "l": Decimal(str(bar.get("low", 0))),
            "c": Decimal(str(bar.get("close", 0))),
            "v": int(bar.get("volume", 0))
        }
