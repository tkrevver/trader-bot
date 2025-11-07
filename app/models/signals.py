"""Signal models."""

from datetime import datetime
from typing import Optional, Literal
from pydantic import BaseModel, Field
from decimal import Decimal


class Signal(BaseModel):
    """Trading signal model."""

    id: Optional[int] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    symbol: str = Field(..., description="Trading symbol")
    signal_type: Literal["BUY", "SELL", "HOLD"] = Field(..., description="Signal type")
    confidence: Optional[Decimal] = Field(
        None,
        description="Signal confidence (0.0 to 1.0)",
        ge=0,
        le=1
    )
    strategy_name: str = Field(..., description="Strategy that generated the signal")
    timeframe: Optional[str] = Field(None, description="Timeframe used for signal generation")
    metadata: Optional[dict] = Field(None, description="Strategy-specific metadata")
    approved: bool = Field(default=False, description="Whether signal was approved by risk manager")
    rejection_reason: Optional[str] = Field(None, description="Reason for rejection (if not approved)")

    class Config:
        """Pydantic config."""
        json_schema_extra = {
            "example": {
                "timestamp": "2025-01-15T09:35:00-05:00",
                "symbol": "SPY",
                "signal_type": "BUY",
                "confidence": "0.85",
                "strategy_name": "momentum_strategy",
                "timeframe": "15min",
                "metadata": {
                    "rsi": 35.5,
                    "macd": 1.25,
                    "reason": "RSI oversold + MACD bullish crossover"
                },
                "approved": True,
                "rejection_reason": None
            }
        }


class SignalCreate(BaseModel):
    """Model for creating a new signal."""

    symbol: str
    signal_type: Literal["BUY", "SELL", "HOLD"]
    confidence: Optional[Decimal] = Field(None, ge=0, le=1)
    strategy_name: str
    timeframe: Optional[str] = None
    metadata: Optional[dict] = None


class SignalApproval(BaseModel):
    """Model for signal approval/rejection."""

    signal_id: int
    approved: bool
    rejection_reason: Optional[str] = None
