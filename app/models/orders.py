"""Order models."""

from datetime import datetime
from typing import Optional, Literal
from pydantic import BaseModel, Field
from decimal import Decimal


class OrderStatus:
    """Order status constants."""
    PENDING = "PENDING"
    SUBMITTED = "SUBMITTED"
    FILLED = "FILLED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    CANCELED = "CANCELED"
    REJECTED = "REJECTED"


class OrderType:
    """Order type constants."""
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"
    STOP_LIMIT = "STOP_LIMIT"


class Order(BaseModel):
    """Order model."""

    id: Optional[int] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    symbol: str = Field(..., description="Trading symbol")
    side: Literal["BUY", "SELL"] = Field(..., description="Order side")
    quantity: Decimal = Field(..., description="Order quantity", gt=0)
    order_type: Literal["MARKET", "LIMIT", "STOP", "STOP_LIMIT"] = Field(
        ...,
        description="Order type"
    )
    limit_price: Optional[Decimal] = Field(None, description="Limit price (for limit orders)", ge=0)
    stop_price: Optional[Decimal] = Field(None, description="Stop price (for stop orders)", ge=0)
    status: Literal[
        "PENDING", "SUBMITTED", "FILLED", "PARTIALLY_FILLED", "CANCELED", "REJECTED"
    ] = Field(default=OrderStatus.PENDING, description="Order status")
    filled_quantity: Decimal = Field(default=Decimal(0), description="Filled quantity", ge=0)
    filled_price: Optional[Decimal] = Field(None, description="Average fill price", ge=0)
    broker_order_id: Optional[str] = Field(None, description="Broker's order ID")
    strategy_name: Optional[str] = Field(None, description="Strategy that placed the order")
    signal_id: Optional[int] = Field(None, description="Signal ID that triggered the order")
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        """Pydantic config."""
        json_schema_extra = {
            "example": {
                "timestamp": "2025-01-15T09:35:00-05:00",
                "symbol": "SPY",
                "side": "BUY",
                "quantity": "10",
                "order_type": "MARKET",
                "limit_price": None,
                "stop_price": None,
                "status": "FILLED",
                "filled_quantity": "10",
                "filled_price": "450.50",
                "broker_order_id": "ORD123456",
                "strategy_name": "momentum_strategy",
                "signal_id": 42
            }
        }


class OrderCreate(BaseModel):
    """Model for creating a new order."""

    symbol: str
    side: Literal["BUY", "SELL"]
    quantity: Decimal = Field(..., gt=0)
    order_type: Literal["MARKET", "LIMIT", "STOP", "STOP_LIMIT"]
    limit_price: Optional[Decimal] = Field(None, ge=0)
    stop_price: Optional[Decimal] = Field(None, ge=0)
    strategy_name: Optional[str] = None
    signal_id: Optional[int] = None


class OrderUpdate(BaseModel):
    """Model for updating an order."""

    status: Optional[Literal[
        "PENDING", "SUBMITTED", "FILLED", "PARTIALLY_FILLED", "CANCELED", "REJECTED"
    ]] = None
    filled_quantity: Optional[Decimal] = Field(None, ge=0)
    filled_price: Optional[Decimal] = Field(None, ge=0)
    broker_order_id: Optional[str] = None


class OrderResponse(BaseModel):
    """Response model for order queries."""

    order: Order
    message: Optional[str] = None
