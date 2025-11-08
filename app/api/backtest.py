"""Backtest API endpoints."""

from datetime import datetime, date
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_serializer
import pytz

from app.config import settings
from app.db.connection import db_pool
from app.models.backtest import (
    BacktestConfig,
    BacktestMetrics,
    BacktestResult,
    BacktestStatus,
    BacktestSummary,
    BacktestTrade,
    EquityCurvePoint,
)
from app.services.backtest_runner import BacktestRunner
from app.utils.logger import logger

router = APIRouter(prefix="/api/v1/backtest", tags=["backtest"])


class TradeDetail(BaseModel):
    """Detailed trade information for analysis."""

    trade_number: int
    date: str  # YYYY-MM-DD format
    entry_time: datetime
    exit_time: Optional[datetime] = None
    side: str
    quantity: int
    entry_price: Decimal
    exit_price: Optional[Decimal] = None
    pnl: Optional[Decimal] = None
    win_loss: Optional[str] = None  # "WIN", "LOSS", or "OPEN"
    commission: Decimal
    slippage: Decimal
    holding_period_minutes: Optional[float] = None

    @field_serializer("entry_time")
    def serialize_entry_time(self, dt: datetime) -> str:
        """Serialize entry_time to configured timezone."""
        tz = pytz.timezone(settings.timezone)
        if dt.tzinfo is None:
            dt = pytz.utc.localize(dt)
        dt_local = dt.astimezone(tz)
        return dt_local.isoformat()

    @field_serializer("exit_time")
    def serialize_exit_time(self, dt: Optional[datetime]) -> Optional[str]:
        """Serialize exit_time to configured timezone."""
        if dt is None:
            return None
        tz = pytz.timezone(settings.timezone)
        if dt.tzinfo is None:
            dt = pytz.utc.localize(dt)
        dt_local = dt.astimezone(tz)
        return dt_local.isoformat()


class BacktestDetailedResponse(BaseModel):
    """Detailed backtest response with all trades."""

    backtest_id: int
    strategy_name: str
    symbol: str
    start_date: datetime
    end_date: datetime
    initial_capital: Decimal
    status: BacktestStatus
    metrics: Optional[BacktestMetrics] = None
    trades: list[TradeDetail] = []
    total_trades: int
    winning_trades: int
    losing_trades: int

    @field_serializer("start_date", "end_date")
    def serialize_datetime(self, dt: datetime) -> str:
        """Serialize datetime to configured timezone."""
        tz = pytz.timezone(settings.timezone)
        if dt.tzinfo is None:
            dt = pytz.utc.localize(dt)
        dt_local = dt.astimezone(tz)
        return dt_local.isoformat()


class BacktestRequest(BaseModel):
    """Request to run a backtest."""

    strategy_name: str = Field(..., description="Strategy name")
    symbol: str = Field(..., description="Trading symbol")
    start_date: datetime = Field(..., description="Start date")
    end_date: datetime = Field(..., description="End date")
    initial_capital: Decimal = Field(default=Decimal("10000"), gt=0)
    commission_per_share: Decimal = Field(default=Decimal("0"), ge=0)
    slippage_bps: int = Field(default=5, ge=0)
    config: Optional[dict] = None


class BacktestStatusResponse(BaseModel):
    """Backtest status response."""

    id: int
    strategy_name: str
    symbol: str
    start_date: datetime
    end_date: datetime
    status: BacktestStatus
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None


@router.post("", response_model=BacktestResult, status_code=201)
async def run_backtest(
    request: BacktestRequest,
):
    """Run a backtest.

    Args:
        request: Backtest configuration

    Returns:
        Backtest result with metrics
    """
    logger.info(
        f"Received backtest request: {request.strategy_name} on {request.symbol}"
    )

    config = BacktestConfig(
        strategy_name=request.strategy_name,
        symbol=request.symbol,
        start_date=request.start_date,
        end_date=request.end_date,
        initial_capital=request.initial_capital,
        commission_per_share=request.commission_per_share,
        slippage_bps=request.slippage_bps,
        config=request.config,
    )

    runner = BacktestRunner(db_pool.pool)

    try:
        result = await runner.run_backtest(config)
        return result
    except Exception as e:
        logger.error(f"Backtest failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{backtest_id}", response_model=BacktestStatusResponse)
async def get_backtest_status(
    backtest_id: int,
):
    """Get backtest status.

    Args:
        backtest_id: Backtest ID

    Returns:
        Backtest status
    """
    from app.db.repositories.backtest import BacktestRepository

    repo = BacktestRepository(db_pool.pool)

    async with db_pool.pool.acquire() as conn:
        backtest = await repo.get_backtest(conn, backtest_id)

    if not backtest:
        raise HTTPException(status_code=404, detail="Backtest not found")

    return BacktestStatusResponse(
        id=backtest.id,
        strategy_name=backtest.strategy_name,
        symbol=backtest.symbol,
        start_date=backtest.start_date,
        end_date=backtest.end_date,
        status=backtest.status,
        created_at=backtest.created_at,
        started_at=backtest.started_at,
        completed_at=backtest.completed_at,
        error_message=backtest.error_message,
    )


@router.get("/{backtest_id}/results", response_model=BacktestMetrics)
async def get_backtest_results(
    backtest_id: int,
):
    """Get backtest results (metrics).

    Args:
        backtest_id: Backtest ID

    Returns:
        Backtest metrics
    """
    from app.db.repositories.backtest import BacktestRepository

    repo = BacktestRepository(db_pool.pool)

    async with db_pool.pool.acquire() as conn:
        backtest = await repo.get_backtest(conn, backtest_id)

    if not backtest:
        raise HTTPException(status_code=404, detail="Backtest not found")

    if backtest.status != BacktestStatus.COMPLETED:
        raise HTTPException(
            status_code=400,
            detail=f"Backtest not completed yet (status: {backtest.status})",
        )

    if not backtest.metrics:
        raise HTTPException(status_code=404, detail="No metrics available")

    return BacktestMetrics(**backtest.metrics)


@router.get("/{backtest_id}/trades", response_model=list[BacktestTrade])
async def get_backtest_trades(
    backtest_id: int,
):
    """Get backtest trades.

    Args:
        backtest_id: Backtest ID

    Returns:
        List of trades
    """
    from app.db.repositories.backtest import BacktestRepository

    repo = BacktestRepository(db_pool.pool)

    async with db_pool.pool.acquire() as conn:
        backtest = await repo.get_backtest(conn, backtest_id)
        if not backtest:
            raise HTTPException(status_code=404, detail="Backtest not found")

        trades = await repo.get_backtest_trades(conn, backtest_id)

    return trades


@router.get("/{backtest_id}/equity", response_model=list[EquityCurvePoint])
async def get_backtest_equity_curve(
    backtest_id: int,
):
    """Get backtest equity curve.

    Args:
        backtest_id: Backtest ID

    Returns:
        List of equity curve points
    """
    from app.db.repositories.backtest import BacktestRepository

    repo = BacktestRepository(db_pool.pool)

    async with db_pool.pool.acquire() as conn:
        backtest = await repo.get_backtest(conn, backtest_id)
        if not backtest:
            raise HTTPException(status_code=404, detail="Backtest not found")

        equity_curve = await repo.get_equity_curve(conn, backtest_id)

    return equity_curve


@router.get("", response_model=list[BacktestSummary])
async def list_backtests(
    strategy_name: Optional[str] = Query(None, description="Filter by strategy name"),
    status: Optional[BacktestStatus] = Query(None, description="Filter by status"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum results"),
):
    """List backtests with optional filters.

    Args:
        strategy_name: Filter by strategy name
        status: Filter by status
        limit: Maximum results

    Returns:
        List of backtest summaries
    """
    from app.db.repositories.backtest import BacktestRepository

    repo = BacktestRepository(db_pool.pool)

    async with db_pool.pool.acquire() as conn:
        backtests = await repo.get_all_backtests(
            conn, strategy_name=strategy_name, status=status, limit=limit
        )

    summaries = []
    for backtest in backtests:
        duration_seconds = None
        if backtest.started_at and backtest.completed_at:
            duration_seconds = (
                backtest.completed_at - backtest.started_at
            ).total_seconds()

        metrics = (
            BacktestMetrics(**backtest.metrics) if backtest.metrics else None
        )

        summaries.append(
            BacktestSummary(
                id=backtest.id,
                strategy_name=backtest.strategy_name,
                symbol=backtest.symbol,
                start_date=backtest.start_date,
                end_date=backtest.end_date,
                initial_capital=backtest.initial_capital,
                status=backtest.status,
                metrics=metrics,
                created_at=backtest.created_at,
                completed_at=backtest.completed_at,
                duration_seconds=duration_seconds,
            )
        )

    return summaries


@router.delete("/{backtest_id}", status_code=204)
async def delete_backtest(
    backtest_id: int,
):
    """Delete a backtest.

    Args:
        backtest_id: Backtest ID
    """
    from app.db.repositories.backtest import BacktestRepository

    repo = BacktestRepository(db_pool.pool)

    async with db_pool.pool.acquire() as conn:
        deleted = await repo.delete_backtest(conn, backtest_id)

    if not deleted:
        raise HTTPException(status_code=404, detail="Backtest not found")

    return None


@router.get("/{backtest_id}/detailed", response_model=BacktestDetailedResponse)
async def get_backtest_detailed(
    backtest_id: int,
):
    """Get detailed backtest results with all trade information.

    Args:
        backtest_id: Backtest ID

    Returns:
        Detailed backtest results including all trades with entry/exit times and P&L
    """
    from app.db.repositories.backtest import BacktestRepository

    repo = BacktestRepository(db_pool.pool)

    async with db_pool.pool.acquire() as conn:
        backtest = await repo.get_backtest(conn, backtest_id)

        if not backtest:
            raise HTTPException(status_code=404, detail="Backtest not found")

        # Get all trades
        trades_raw = await repo.get_backtest_trades(conn, backtest_id)

    # Parse metrics
    metrics = None
    if backtest.metrics:
        metrics = BacktestMetrics(**backtest.metrics)

    # Group trades into pairs (entry + exit)
    trade_details = []
    trade_num = 0
    i = 0

    while i < len(trades_raw):
        trade = trades_raw[i]

        # If this is a BUY, look for the corresponding SELL
        if trade.side.lower() == "buy":
            trade_num += 1
            entry = trade
            exit_trade = None

            # Look for matching SELL
            if i + 1 < len(trades_raw) and trades_raw[i + 1].side.lower() == "sell":
                exit_trade = trades_raw[i + 1]
                i += 2  # Skip both trades
            else:
                i += 1  # Only skip entry

            # Calculate holding period
            holding_period = None
            if exit_trade:
                time_diff = exit_trade.executed_at - entry.executed_at
                holding_period = time_diff.total_seconds() / 60.0

            # Determine win/loss
            win_loss = None
            if exit_trade and exit_trade.pnl is not None:
                win_loss = "WIN" if exit_trade.pnl > 0 else "LOSS"
            elif exit_trade:
                win_loss = "OPEN"

            trade_details.append(
                TradeDetail(
                    trade_number=trade_num,
                    date=entry.executed_at.strftime("%Y-%m-%d"),
                    entry_time=entry.executed_at,
                    exit_time=exit_trade.executed_at if exit_trade else None,
                    side="LONG",
                    quantity=entry.quantity,
                    entry_price=entry.price,
                    exit_price=exit_trade.price if exit_trade else None,
                    pnl=exit_trade.pnl if exit_trade else None,
                    win_loss=win_loss,
                    commission=(entry.commission + (exit_trade.commission if exit_trade else Decimal("0"))),
                    slippage=(entry.slippage + (exit_trade.slippage if exit_trade else Decimal("0"))),
                    holding_period_minutes=holding_period,
                )
            )
        else:
            # Skip orphaned SELL orders
            i += 1

    # Count wins/losses
    winning_trades = sum(1 for t in trade_details if t.win_loss == "WIN")
    losing_trades = sum(1 for t in trade_details if t.win_loss == "LOSS")

    return BacktestDetailedResponse(
        backtest_id=backtest.id,
        strategy_name=backtest.strategy_name,
        symbol=backtest.symbol,
        start_date=backtest.start_date,
        end_date=backtest.end_date,
        initial_capital=backtest.initial_capital,
        status=backtest.status,
        metrics=metrics,
        trades=trade_details,
        total_trades=len(trade_details),
        winning_trades=winning_trades,
        losing_trades=losing_trades,
    )
