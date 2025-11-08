"""Tests for backtest position tracker."""

from decimal import Decimal
from datetime import datetime

import pytest

from app.services.backtest_position_tracker import BacktestPositionTracker


def test_initial_state():
    """Test initial tracker state."""
    tracker = BacktestPositionTracker(
        initial_capital=Decimal("10000"),
        commission_per_share=Decimal("0.01"),
        slippage_bps=5,
    )

    assert tracker.cash == Decimal("10000")
    assert tracker.get_equity({}) == Decimal("10000")  # No positions = cash only
    assert len(tracker.positions) == 0
    assert len(tracker.trades) == 0


def test_execute_buy_trade():
    """Test executing a buy trade."""
    tracker = BacktestPositionTracker(
        initial_capital=Decimal("10000"),
        commission_per_share=Decimal("0"),
        slippage_bps=5,
    )

    trade = tracker.execute_trade(
        backtest_id=1,
        symbol="SPY",
        side="buy",
        quantity=10,
        price=Decimal("100"),
        timestamp=datetime(2025, 1, 1, 10, 0),
    )

    assert trade is not None
    assert trade.side == "buy"
    assert trade.quantity == 10
    # Price should include slippage (5 bps = 0.05%)
    assert trade.price > Decimal("100")

    # Check position created
    assert tracker.has_position("SPY")
    position = tracker.get_position("SPY")
    assert position.quantity == 10


def test_execute_sell_trade_with_profit():
    """Test executing a sell trade with profit."""
    tracker = BacktestPositionTracker(
        initial_capital=Decimal("10000"),
        commission_per_share=Decimal("0"),
        slippage_bps=5,
    )

    # Buy at 100
    tracker.execute_trade(
        backtest_id=1,
        symbol="SPY",
        side="buy",
        quantity=10,
        price=Decimal("100"),
        timestamp=datetime(2025, 1, 1, 10, 0),
    )

    # Sell at 110 (profit)
    sell_trade = tracker.execute_trade(
        backtest_id=1,
        symbol="SPY",
        side="sell",
        quantity=10,
        price=Decimal("110"),
        timestamp=datetime(2025, 1, 1, 11, 0),
    )

    assert sell_trade is not None
    assert sell_trade.pnl is not None
    assert sell_trade.pnl > 0  # Should be profitable
    assert not tracker.has_position("SPY")  # Position closed


def test_insufficient_cash():
    """Test trade rejected due to insufficient cash."""
    tracker = BacktestPositionTracker(
        initial_capital=Decimal("100"),  # Only $100
        commission_per_share=Decimal("0"),
        slippage_bps=5,
    )

    # Try to buy $1000 worth
    trade = tracker.execute_trade(
        backtest_id=1,
        symbol="SPY",
        side="buy",
        quantity=10,
        price=Decimal("100"),
        timestamp=datetime(2025, 1, 1, 10, 0),
    )

    assert trade is None  # Should be rejected
    assert tracker.cash == Decimal("100")  # Cash unchanged


def test_equity_curve_tracking():
    """Test equity curve point recording."""
    tracker = BacktestPositionTracker(
        initial_capital=Decimal("10000"),
        commission_per_share=Decimal("0"),
        slippage_bps=5,
    )

    # Buy some shares
    tracker.execute_trade(
        backtest_id=1,
        symbol="SPY",
        side="buy",
        quantity=10,
        price=Decimal("100"),
        timestamp=datetime(2025, 1, 1, 10, 0),
    )

    # Record equity point
    tracker.record_equity_curve_point(
        backtest_id=1,
        timestamp=datetime(2025, 1, 1, 12, 0),
        current_prices={"SPY": Decimal("105")},
    )

    assert len(tracker.equity_curve) == 1
    point = tracker.equity_curve[0]
    assert point.equity > Decimal("10000")  # Position appreciated


def test_slippage_calculation():
    """Test slippage is applied correctly."""
    tracker = BacktestPositionTracker(
        initial_capital=Decimal("10000"),
        commission_per_share=Decimal("0"),
        slippage_bps=10,  # 10 bps = 0.1%
    )

    # Buy trade
    buy_trade = tracker.execute_trade(
        backtest_id=1,
        symbol="SPY",
        side="buy",
        quantity=10,
        price=Decimal("100"),
        timestamp=datetime(2025, 1, 1, 10, 0),
    )

    # Slippage should be positive (adds to buy price)
    # 10 bps = 0.1% = 0.001 * $100 = $0.10 per share
    # Total slippage for 10 shares = $0.10 * 10 = $1.00
    expected_slippage = Decimal("100") * Decimal("0.001") * Decimal("10")
    assert buy_trade.slippage > 0
    assert abs(buy_trade.slippage - expected_slippage) < Decimal("0.01")


def test_commission_calculation():
    """Test commission is applied correctly."""
    tracker = BacktestPositionTracker(
        initial_capital=Decimal("10000"),
        commission_per_share=Decimal("0.50"),  # $0.50 per share
        slippage_bps=0,
    )

    trade = tracker.execute_trade(
        backtest_id=1,
        symbol="SPY",
        side="buy",
        quantity=10,
        price=Decimal("100"),
        timestamp=datetime(2025, 1, 1, 10, 0),
    )

    # Commission = 10 shares * $0.50 = $5.00
    assert trade.commission == Decimal("5.00")
