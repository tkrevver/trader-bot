"""Position models."""

from datetime import datetime
from typing import Optional, Literal
from pydantic import BaseModel, Field
from decimal import Decimal


class Position(BaseModel):
    """Position model."""

    id: Optional[int] = None
    symbol: str = Field(..., description="Trading symbol")
    quantity: Decimal = Field(..., description="Position quantity (positive for long, negative for short)")
    avg_entry_price: Decimal = Field(..., description="Average entry price", ge=0)
    current_price: Optional[Decimal] = Field(None, description="Current market price", ge=0)
    unrealized_pnl: Optional[Decimal] = Field(None, description="Unrealized P&L")
    realized_pnl: Decimal = Field(default=Decimal(0), description="Realized P&L")
    opened_at: datetime = Field(default_factory=datetime.utcnow, description="Position open time")
    closed_at: Optional[datetime] = Field(None, description="Position close time")
    status: Literal["OPEN", "CLOSED"] = Field(default="OPEN", description="Position status")
    strategy_name: Optional[str] = Field(None, description="Strategy that opened the position")

    @property
    def market_value(self) -> Optional[Decimal]:
        """Calculate current market value of the position."""
        if self.current_price is not None:
            return self.quantity * self.current_price
        return None

    @property
    def cost_basis(self) -> Decimal:
        """Calculate cost basis of the position."""
        return abs(self.quantity) * self.avg_entry_price

    class Config:
        """Pydantic config."""
        json_schema_extra = {
            "example": {
                "symbol": "SPY",
                "quantity": "10",
                "avg_entry_price": "450.50",
                "current_price": "452.00",
                "unrealized_pnl": "15.00",
                "realized_pnl": "0",
                "opened_at": "2025-01-15T09:35:00-05:00",
                "closed_at": None,
                "status": "OPEN",
                "strategy_name": "momentum_strategy"
            }
        }


class PositionCreate(BaseModel):
    """Model for creating a new position."""

    symbol: str
    quantity: Decimal
    avg_entry_price: Decimal = Field(..., ge=0)
    strategy_name: Optional[str] = None


class PositionUpdate(BaseModel):
    """Model for updating a position."""

    quantity: Optional[Decimal] = None
    avg_entry_price: Optional[Decimal] = Field(None, ge=0)
    current_price: Optional[Decimal] = Field(None, ge=0)
    unrealized_pnl: Optional[Decimal] = None
    realized_pnl: Optional[Decimal] = None
    status: Optional[Literal["OPEN", "CLOSED"]] = None
    closed_at: Optional[datetime] = None


class PositionSummary(BaseModel):
    """Summary of all positions."""

    total_positions: int
    open_positions: int
    closed_positions: int
    total_market_value: Decimal
    total_unrealized_pnl: Decimal
    total_realized_pnl: Decimal
    positions: list[Position]

    class Config:
        """Pydantic config."""
        json_schema_extra = {
            "example": {
                "total_positions": 5,
                "open_positions": 2,
                "closed_positions": 3,
                "total_market_value": "9040.00",
                "total_unrealized_pnl": "40.00",
                "total_realized_pnl": "125.00",
                "positions": []
            }
        }
