"""Backtest models."""

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, ConfigDict


class BacktestStatus(str, Enum):
    """Backtest status enum."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class BacktestConfig(BaseModel):
    """Configuration for running a backtest."""

    strategy_name: str = Field(..., description="Strategy name to backtest")
    symbol: str = Field(..., description="Symbol to trade")
    start_date: datetime = Field(..., description="Backtest start date")
    end_date: datetime = Field(..., description="Backtest end date")
    initial_capital: Decimal = Field(..., gt=0, description="Starting capital")
    commission_per_share: Decimal = Field(
        default=Decimal("0"), ge=0, description="Commission per share"
    )
    slippage_bps: int = Field(
        default=5, ge=0, description="Slippage in basis points"
    )
    config: Optional[dict[str, Any]] = Field(
        None, description="Strategy-specific configuration"
    )


class BacktestTrade(BaseModel):
    """Backtest trade record."""

    model_config = ConfigDict(from_attributes=True)

    id: Optional[int] = None
    backtest_id: int
    symbol: str
    side: str  # 'buy' or 'sell'
    quantity: int
    price: Decimal
    executed_at: datetime
    pnl: Optional[Decimal] = None
    commission: Decimal = Decimal("0")
    slippage: Decimal = Decimal("0")
    metadata: Optional[dict[str, Any]] = None


class EquityCurvePoint(BaseModel):
    """Single point on the equity curve."""

    model_config = ConfigDict(from_attributes=True)

    id: Optional[int] = None
    backtest_id: int
    timestamp: datetime
    equity: Decimal
    cash: Decimal
    positions_value: Decimal


class BacktestMetrics(BaseModel):
    """Comprehensive backtest performance metrics."""

    # Returns
    total_return_pct: Optional[float] = Field(None, description="Total return %")
    cagr: Optional[float] = Field(None, description="Compound annual growth rate %")
    total_pnl: Decimal = Field(Decimal("0"), description="Total P&L")

    # Risk metrics
    max_drawdown_pct: Optional[float] = Field(None, description="Maximum drawdown %")
    max_drawdown_duration_days: Optional[int] = Field(
        None, description="Max drawdown duration in days"
    )
    sharpe_ratio: Optional[float] = Field(None, description="Sharpe ratio")
    sortino_ratio: Optional[float] = Field(None, description="Sortino ratio")
    volatility: Optional[float] = Field(None, description="Annualized volatility %")

    # Trade statistics
    total_trades: int = Field(0, description="Total number of trades")
    winning_trades: int = Field(0, description="Number of winning trades")
    losing_trades: int = Field(0, description="Number of losing trades")
    win_rate: Optional[float] = Field(None, description="Win rate %")
    profit_factor: Optional[float] = Field(None, description="Profit factor")

    average_win: Optional[Decimal] = Field(None, description="Average winning trade")
    average_loss: Optional[Decimal] = Field(None, description="Average losing trade")
    largest_win: Optional[Decimal] = Field(None, description="Largest winning trade")
    largest_loss: Optional[Decimal] = Field(None, description="Largest losing trade")

    average_holding_period_minutes: Optional[float] = Field(
        None, description="Average holding period in minutes"
    )
    average_bars_in_trade: Optional[float] = Field(
        None, description="Average bars per trade"
    )

    # Position metrics
    exposure_time_pct: Optional[float] = Field(
        None, description="% of time in market"
    )

    # Daily statistics
    best_day_pct: Optional[float] = Field(None, description="Best daily return %")
    worst_day_pct: Optional[float] = Field(None, description="Worst daily return %")
    average_daily_return_pct: Optional[float] = Field(
        None, description="Average daily return %"
    )
    positive_days_pct: Optional[float] = Field(None, description="% of positive days")

    # Execution quality
    total_commission: Decimal = Field(Decimal("0"), description="Total commissions paid")
    total_slippage: Decimal = Field(Decimal("0"), description="Total slippage cost")


class Backtest(BaseModel):
    """Backtest database model."""

    model_config = ConfigDict(from_attributes=True)

    id: Optional[int] = None
    strategy_name: str
    symbol: str
    start_date: datetime
    end_date: datetime
    initial_capital: Decimal
    status: BacktestStatus = BacktestStatus.PENDING
    config: Optional[dict[str, Any]] = None
    metrics: Optional[dict[str, Any]] = None
    error_message: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class BacktestResult(BaseModel):
    """Complete backtest result with metrics, trades, and equity curve."""

    backtest: Backtest
    metrics: BacktestMetrics
    trades: list[BacktestTrade] = []
    equity_curve: list[EquityCurvePoint] = []


class BacktestCreate(BaseModel):
    """Model for creating a new backtest."""

    strategy_name: str
    symbol: str
    start_date: datetime
    end_date: datetime
    initial_capital: Decimal
    config: Optional[dict[str, Any]] = None


class BacktestSummary(BaseModel):
    """Summary of a backtest (without full trades/equity curve)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    strategy_name: str
    symbol: str
    start_date: datetime
    end_date: datetime
    initial_capital: Decimal
    status: BacktestStatus
    metrics: Optional[BacktestMetrics] = None
    created_at: datetime
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None
