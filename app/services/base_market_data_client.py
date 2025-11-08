"""Abstract base class for market data clients."""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional, Dict, Any, List


class BaseMarketDataClient(ABC):
    """
    Abstract base class for market data providers.

    This interface ensures all market data clients (Tradier, Alpaca, etc.)
    implement the same methods for data fetching and parsing.
    """

    @abstractmethod
    async def connect(self):
        """Create/initialize client connection."""
        pass

    @abstractmethod
    async def close(self):
        """Close client connection."""
        pass

    @abstractmethod
    async def __aenter__(self):
        """Context manager entry."""
        pass

    @abstractmethod
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        pass

    @abstractmethod
    async def fetch_timesales(
        self,
        symbol: str,
        interval: str = "1min",
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        session_filter: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Fetch historical OHLCV bars.

        Args:
            symbol: Stock symbol (e.g., "SPY")
            interval: Time interval (1min, 5min, 15min, daily)
            start: Start date/time
            end: End date/time
            session_filter: "open" for market hours only, "all" for extended hours

        Returns:
            List of OHLCV bars in provider's native format
        """
        pass

    @abstractmethod
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
            session_filter: "open" for market hours only, "all" for extended hours

        Returns:
            Latest bar in provider's native format or None if not available
        """
        pass

    @abstractmethod
    def parse_bar_to_ohlcv(self, bar: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parse provider's bar format to standardized OHLCV format.

        Standardized format:
        {
            "t": int,  # Timestamp in milliseconds
            "o": Decimal,  # Open price
            "h": Decimal,  # High price
            "l": Decimal,  # Low price
            "c": Decimal,  # Close price
            "v": int,  # Volume
            "vw": Optional[Decimal],  # VWAP (if available)
            "n": Optional[int]  # Number of trades (if available)
        }

        Args:
            bar: Bar data in provider's native format

        Returns:
            Normalized OHLCV bar
        """
        pass

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """
        Get the name of the data provider.

        Returns:
            Provider name (e.g., "tradier", "alpaca")
        """
        pass
