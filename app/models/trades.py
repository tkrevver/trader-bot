"""Trade models for recording executed trades."""

from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field, ConfigDict


class TradeBase(BaseModel):
    """Base trade model with common fields."""

    position_id: int = Field(..., description="Associated position ID")
    order_id: int = Field(..., description="Order that created this trade")
    symbol: str = Field(..., max_length=10, description="Trading symbol")
    side: str = Field(..., description="Trade side: 'buy' or 'sell'")
    quantity: int = Field(..., gt=0, description="Number of shares traded")
    price: Decimal = Field(..., gt=0, description="Execution price per share")
    commission: Decimal = Field(default=Decimal("0"), ge=0, description="Commission paid")
    slippage: Decimal = Field(default=Decimal("0"), description="Estimated slippage")


class TradeCreate(TradeBase):
    """Model for creating a new trade."""

    executed_at: Optional[datetime] = Field(
        default=None, description="Execution timestamp (defaults to now)"
    )


class Trade(TradeBase):
    """Complete trade model with database fields."""

    model_config = ConfigDict(from_attributes=True)

    id: int = Field(..., description="Trade ID")
    executed_at: datetime = Field(..., description="Execution timestamp")
    pnl: Optional[Decimal] = Field(None, description="Realized P&L (for closing trades)")
    created_at: datetime = Field(..., description="Record creation timestamp")

    @property
    def total_value(self) -> Decimal:
        """Calculate total trade value including commission."""
        return (self.price * self.quantity) + self.commission

    @property
    def net_proceeds(self) -> Decimal:
        """Calculate net proceeds (for sells) or cost (for buys)."""
        if self.side == "sell":
            return (self.price * self.quantity) - self.commission
        else:
            return -((self.price * self.quantity) + self.commission)


class TradeResponse(Trade):
    """API response model for trades."""

    pass


class TradeSummary(BaseModel):
    """Summary statistics for trades."""

    model_config = ConfigDict(from_attributes=True)

    total_trades: int = Field(..., description="Total number of trades")
    buy_trades: int = Field(..., description="Number of buy trades")
    sell_trades: int = Field(..., description="Number of sell trades")
    total_volume: int = Field(..., description="Total shares traded")
    total_commission: Decimal = Field(..., description="Total commission paid")
    total_pnl: Decimal = Field(..., description="Total realized P&L")
    gross_profit: Decimal = Field(..., description="Sum of winning trades")
    gross_loss: Decimal = Field(..., description="Sum of losing trades")
    win_rate: Optional[float] = Field(None, description="Percentage of winning trades")
    profit_factor: Optional[float] = Field(
        None, description="Gross profit / gross loss"
    )
    average_win: Optional[Decimal] = Field(None, description="Average winning trade")
    average_loss: Optional[Decimal] = Field(None, description="Average losing trade")
