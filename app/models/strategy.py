"""Strategy models."""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class Strategy(BaseModel):
    """Strategy model."""

    id: Optional[int] = None
    name: str = Field(..., description="Unique strategy name")
    description: Optional[str] = Field(None, description="Strategy description")
    active: bool = Field(default=False, description="Whether strategy is active")
    config: Optional[dict] = Field(None, description="Strategy-specific configuration")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        """Pydantic config."""
        json_schema_extra = {
            "example": {
                "name": "momentum_strategy",
                "description": "Simple momentum strategy using RSI and MACD",
                "active": True,
                "config": {
                    "rsi_period": 14,
                    "rsi_oversold": 30,
                    "rsi_overbought": 70,
                    "macd_fast": 12,
                    "macd_slow": 26,
                    "macd_signal": 9
                },
                "created_at": "2025-01-15T09:00:00-05:00",
                "updated_at": "2025-01-15T09:00:00-05:00"
            }
        }


class StrategyCreate(BaseModel):
    """Model for creating a new strategy."""

    name: str
    description: Optional[str] = None
    active: bool = False
    config: Optional[dict] = None


class StrategyUpdate(BaseModel):
    """Model for updating a strategy."""

    description: Optional[str] = None
    active: Optional[bool] = None
    config: Optional[dict] = None


class StrategyConfig(BaseModel):
    """Strategy configuration model."""

    name: str
    parameters: dict = Field(..., description="Strategy parameters")

    class Config:
        """Pydantic config."""
        json_schema_extra = {
            "example": {
                "name": "momentum_strategy",
                "parameters": {
                    "rsi_period": 14,
                    "rsi_oversold": 30,
                    "rsi_overbought": 70
                }
            }
        }
