"""Market data models."""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, field_validator
from decimal import Decimal


class OHLCVBar(BaseModel):
    """OHLCV bar data model."""

    time: datetime = Field(..., description="Timestamp of the bar")
    symbol: str = Field(..., description="Trading symbol (e.g., 'SPY')")
    open: Decimal = Field(..., description="Opening price", ge=0)
    high: Decimal = Field(..., description="Highest price", ge=0)
    low: Decimal = Field(..., description="Lowest price", ge=0)
    close: Decimal = Field(..., description="Closing price", ge=0)
    volume: int = Field(..., description="Trading volume", ge=0)
    vwap: Optional[Decimal] = Field(None, description="Volume-weighted average price")
    trades: Optional[int] = Field(None, description="Number of trades", ge=0)

    @field_validator("high")
    @classmethod
    def validate_high(cls, v: Decimal, info) -> Decimal:
        """Validate that high >= open, close, low."""
        values = info.data
        if "low" in values and v < values["low"]:
            raise ValueError("high must be >= low")
        if "open" in values and v < values["open"]:
            raise ValueError("high must be >= open")
        if "close" in values and v < values["close"]:
            raise ValueError("high must be >= close")
        return v

    @field_validator("low")
    @classmethod
    def validate_low(cls, v: Decimal, info) -> Decimal:
        """Validate that low <= open, close, high."""
        values = info.data
        if "open" in values and v > values["open"]:
            raise ValueError("low must be <= open")
        if "close" in values and v > values["close"]:
            raise ValueError("low must be <= close")
        return v

    class Config:
        """Pydantic config."""
        json_schema_extra = {
            "example": {
                "time": "2025-01-15T09:30:00-05:00",
                "symbol": "SPY",
                "open": "450.25",
                "high": "451.50",
                "low": "449.75",
                "close": "451.00",
                "volume": 1250000,
                "vwap": "450.75",
                "trades": 1523
            }
        }


class Tick(BaseModel):
    """Single tick/trade data model."""

    timestamp: datetime = Field(..., description="Timestamp of the tick")
    symbol: str = Field(..., description="Trading symbol")
    price: Decimal = Field(..., description="Trade price", ge=0)
    size: int = Field(..., description="Trade size", ge=0)
    exchange: Optional[str] = Field(None, description="Exchange code")
    conditions: Optional[list[str]] = Field(None, description="Trade conditions")

    class Config:
        """Pydantic config."""
        json_schema_extra = {
            "example": {
                "timestamp": "2025-01-15T09:30:05.123456-05:00",
                "symbol": "SPY",
                "price": "450.50",
                "size": 100,
                "exchange": "Q",
                "conditions": ["@"]
            }
        }


class BarResponse(BaseModel):
    """Response model for bar queries."""

    symbol: str
    timeframe: str = Field(..., description="Timeframe (1min, 5min, 15min, 30min, daily)")
    bars: list[OHLCVBar]
    count: int = Field(..., description="Number of bars returned")

    class Config:
        """Pydantic config."""
        json_schema_extra = {
            "example": {
                "symbol": "SPY",
                "timeframe": "1min",
                "bars": [],
                "count": 0
            }
        }


class LatestBarResponse(BaseModel):
    """Response model for latest bar query."""

    symbol: str
    timeframe: str
    bar: Optional[OHLCVBar] = None

    class Config:
        """Pydantic config."""
        json_schema_extra = {
            "example": {
                "symbol": "SPY",
                "timeframe": "1min",
                "bar": None
            }
        }


class MarketDataGap(BaseModel):
    """Model representing a gap in market data."""

    symbol: str
    timeframe: str
    start_time: datetime = Field(..., description="Start of gap")
    end_time: datetime = Field(..., description="End of gap")
    missing_bars: int = Field(..., description="Number of missing bars")
    detected_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        """Pydantic config."""
        json_schema_extra = {
            "example": {
                "symbol": "SPY",
                "timeframe": "1min",
                "start_time": "2025-01-15T10:00:00-05:00",
                "end_time": "2025-01-15T10:05:00-05:00",
                "missing_bars": 5,
                "detected_at": "2025-01-15T10:10:00-05:00"
            }
        }
