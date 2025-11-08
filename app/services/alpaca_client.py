"""Alpaca REST API client for market data."""

import aiohttp
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from decimal import Decimal
import pytz

from app.services.base_market_data_client import BaseMarketDataClient
from app.config import settings
from app.utils.logger import logger


class AlpacaClient(BaseMarketDataClient):
    """
    Client for Alpaca Market Data API.

    Provides free 5+ years historical market data for equities.
    API Documentation: https://docs.alpaca.markets/docs/about-market-data-api

    Free Plan Features:
    - 5+ years historical data (since 2016)
    - Real-time data (IEX exchange)
    - 1min, 5min, 15min, 30min, daily bars
    - Aggregate bars, trades & quotes
    """

    # Timeframe mapping: our format -> Alpaca format
    TIMEFRAME_MAP = {
        "1min": "1Min",
        "5min": "5Min",
        "15min": "15Min",
        "30min": "30Min",
        "1hour": "1Hour",
        "daily": "1Day",
        "1day": "1Day"
    }

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        base_url: Optional[str] = None
    ):
        """
        Initialize Alpaca client.

        Args:
            api_key: Alpaca API key ID (uses settings.alpaca_api_key if not provided)
            api_secret: Alpaca API secret key (uses settings.alpaca_api_secret if not provided)
            base_url: Base URL for data API (uses settings.alpaca_api_url if not provided)
        """
        self.api_key = api_key or settings.alpaca_api_key
        self.api_secret = api_secret or settings.alpaca_api_secret
        self.base_url = base_url or settings.alpaca_data_api_url
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
                    "APCA-API-KEY-ID": self.api_key,
                    "APCA-API-SECRET-KEY": self.api_secret,
                    "Accept": "application/json"
                }
            )

    async def close(self):
        """Close HTTP session."""
        if self.session and not self.session.closed:
            await self.session.close()

    def _convert_timeframe(self, interval: str) -> str:
        """
        Convert interval to Alpaca timeframe format.

        Args:
            interval: Interval in our format (1min, 5min, etc.)

        Returns:
            Alpaca timeframe format (1Min, 5Min, etc.)
        """
        return self.TIMEFRAME_MAP.get(interval.lower(), "1Min")

    async def fetch_timesales(
        self,
        symbol: str,
        interval: str = "1min",
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        session_filter: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Fetch historical OHLCV bars from Alpaca.

        Historical data available:
        - 5+ years of data (since 2016)
        - All timeframes: 1Min, 5Min, 15Min, 30Min, 1Hour, 1Day

        Args:
            symbol: Stock symbol (e.g., "SPY")
            interval: Time interval (1min, 5min, 15min, daily)
            start: Start date/time (defaults to 30 days ago)
            end: End date/time (defaults to now)
            session_filter: Not used by Alpaca (kept for interface compatibility)

        Returns:
            List of OHLCV bars in Alpaca format
        """
        if not self.session or self.session.closed:
            await self.connect()

        # Convert timeframe to Alpaca format
        timeframe = self._convert_timeframe(interval)

        # Set default date range
        tz = pytz.timezone(settings.timezone)
        if end is None:
            end = datetime.now(tz)
        if start is None:
            # Default to 30 days back (well within free tier limits)
            start = end - timedelta(days=30)

        # Format dates in ISO 8601 / RFC 3339 format (Alpaca requirement)
        # Alpaca expects UTC timestamps
        start_utc = start.astimezone(pytz.UTC)
        end_utc = end.astimezone(pytz.UTC)

        url = f"{self.base_url}/v2/stocks/{symbol.upper()}/bars"
        params = {
            "timeframe": timeframe,
            "start": start_utc.isoformat(),
            "end": end_utc.isoformat(),
            "limit": 10000,  # Max bars per request
            "feed": "iex"  # Free tier uses IEX feed
        }

        try:
            all_bars = []
            next_page_token = None

            # Handle pagination
            while True:
                if next_page_token:
                    params["page_token"] = next_page_token

                async with self.session.get(url, params=params) as response:
                    response.raise_for_status()
                    data = await response.json()

                    # Alpaca returns data under 'bars' key
                    if "bars" in data and data["bars"]:
                        bars = data["bars"]
                        all_bars.extend(bars)

                        logger.debug(
                            "Fetched bars page from Alpaca",
                            extra={
                                "symbol": symbol,
                                "interval": interval,
                                "bars_in_page": len(bars),
                                "total_bars": len(all_bars)
                            }
                        )
                    else:
                        logger.debug(
                            "No bars in Alpaca response",
                            extra={"symbol": symbol, "response": data}
                        )
                        break

                    # Check for next page
                    next_page_token = data.get("next_page_token")
                    if not next_page_token:
                        break

            logger.info(
                "Fetched timesales data from Alpaca",
                extra={
                    "symbol": symbol,
                    "interval": interval,
                    "bar_count": len(all_bars),
                    "start": start.isoformat(),
                    "end": end.isoformat()
                }
            )

            return all_bars

        except aiohttp.ClientResponseError as e:
            logger.error(
                "Alpaca API error",
                extra={
                    "symbol": symbol,
                    "status": e.status,
                    "message": str(e)
                }
            )
            raise
        except Exception as e:
            logger.error(
                "Error fetching timesales from Alpaca",
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
        Fetch the most recent bar for a symbol from Alpaca.

        Args:
            symbol: Stock symbol
            interval: Time interval (1min, 5min, 15min, etc)
            session_filter: Not used by Alpaca (kept for interface compatibility)

        Returns:
            Latest bar in Alpaca format or None if not available
        """
        # Fetch last hour of data to ensure we get the latest bar
        tz = pytz.timezone(settings.timezone)
        end = datetime.now(tz)
        start = end - timedelta(hours=1)

        bars = await self.fetch_timesales(
            symbol=symbol,
            interval=interval,
            start=start,
            end=end
        )

        if bars:
            # Return the most recent bar
            latest = bars[-1]
            logger.info(
                "Fetched latest bar from Alpaca",
                extra={
                    "symbol": symbol,
                    "interval": interval,
                    "time": latest.get("t"),
                    "close": latest.get("c")
                }
            )
            return latest

        return None

    def parse_bar_to_ohlcv(self, bar: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parse Alpaca bar format to standardized OHLCV format.

        Alpaca format:
        {
            "t": "2023-09-29T04:00:00Z",  # ISO 8601 timestamp
            "o": 172.015,
            "h": 173.06,
            "l": 170.36,
            "c": 171.29,
            "v": 923134,
            "n": 12630,  # Number of trades
            "vw": 171.716432  # VWAP
        }

        Args:
            bar: Alpaca bar data

        Returns:
            Normalized OHLCV bar
        """
        # Parse ISO 8601 timestamp to milliseconds
        timestamp_str = bar.get("t", "")
        try:
            dt = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
            timestamp_ms = int(dt.timestamp() * 1000)
        except (ValueError, AttributeError):
            # Fallback: assume it's already a timestamp
            timestamp_ms = 0

        return {
            "t": timestamp_ms,
            "o": Decimal(str(bar.get("o", 0))),
            "h": Decimal(str(bar.get("h", 0))),
            "l": Decimal(str(bar.get("l", 0))),
            "c": Decimal(str(bar.get("c", 0))),
            "v": int(bar.get("v", 0)),
            "vw": Decimal(str(bar.get("vw"))) if bar.get("vw") else None,
            "n": int(bar.get("n")) if bar.get("n") else None
        }

    @property
    def provider_name(self) -> str:
        """Get the name of the data provider."""
        return "alpaca"
