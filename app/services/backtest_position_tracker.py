"""Position tracker for backtesting.

Tracks positions, cash, and equity in memory during backtest execution.
Simulates trade execution with slippage and commission.
"""

from datetime import datetime
from decimal import Decimal
from typing import Optional

from app.models.backtest import BacktestTrade, EquityCurvePoint
from app.utils.logger import logger


class Position:
    """Represents an open position."""

    def __init__(
        self,
        symbol: str,
        side: str,
        quantity: int,
        entry_price: Decimal,
        entry_time: datetime,
    ):
        """Initialize position.

        Args:
            symbol: Trading symbol
            side: Position side ('LONG' or 'SHORT')
            quantity: Number of shares
            entry_price: Entry price per share
            entry_time: Entry timestamp
        """
        self.symbol = symbol
        self.side = side  # 'LONG' or 'SHORT'
        self.quantity = quantity
        self.entry_price = entry_price
        self.entry_time = entry_time

    @property
    def market_value(self) -> Decimal:
        """Calculate market value at entry price.

        Returns:
            Market value (quantity * entry_price)
        """
        return Decimal(str(self.quantity)) * self.entry_price

    def unrealized_pnl(self, current_price: Decimal) -> Decimal:
        """Calculate unrealized P&L.

        Args:
            current_price: Current market price

        Returns:
            Unrealized P&L for LONG or SHORT position
        """
        if self.side == "LONG":
            return (current_price - self.entry_price) * Decimal(str(self.quantity))
        else:  # SHORT
            return (self.entry_price - current_price) * Decimal(str(self.quantity))


class BacktestPositionTracker:
    """Track positions, cash, and equity during backtesting."""

    def __init__(
        self,
        initial_capital: Decimal,
        commission_per_share: Decimal = Decimal("0"),
        slippage_bps: int = 5,
    ):
        """Initialize position tracker.

        Args:
            initial_capital: Starting cash
            commission_per_share: Commission per share
            slippage_bps: Slippage in basis points (default: 5 bps)
        """
        self.initial_capital = initial_capital
        self.cash = initial_capital
        self.commission_per_share = commission_per_share
        self.slippage_bps = slippage_bps

        self.positions: dict[str, Position] = {}  # symbol -> Position
        self.trades: list[BacktestTrade] = []
        self.equity_curve: list[EquityCurvePoint] = []

        self.total_commission = Decimal("0")
        self.total_slippage = Decimal("0")

    def _calculate_slippage(self, price: Decimal, side: str) -> Decimal:
        """Calculate slippage amount.

        Args:
            price: Order price
            side: 'buy' or 'sell'

        Returns:
            Slippage amount per share
        """
        slippage_pct = Decimal(str(self.slippage_bps)) / Decimal("10000")

        if side == "buy":
            # Slippage increases buy price
            return price * slippage_pct
        else:
            # Slippage decreases sell price
            return -price * slippage_pct

    def execute_trade(
        self,
        backtest_id: int,
        symbol: str,
        side: str,
        quantity: int,
        price: Decimal,
        timestamp: datetime,
        position_intent: str = "LONG",
        metadata: Optional[dict] = None,
    ) -> Optional[BacktestTrade]:
        """Execute a simulated trade.

        Args:
            backtest_id: Backtest ID
            symbol: Trading symbol
            side: 'buy' or 'sell' (execution side, not position side)
            quantity: Number of shares
            price: Execution price (before slippage)
            timestamp: Execution timestamp
            position_intent: 'LONG' or 'SHORT' - indicates whether opening/closing a LONG or SHORT position
            metadata: Optional trade metadata

        Returns:
            BacktestTrade if executed, None if insufficient cash/shares

        Logic:
            - BUY + LONG intent = Open/add to LONG position
            - SELL + LONG intent = Close LONG position
            - SELL + SHORT intent = Open/add to SHORT position
            - BUY + SHORT intent = Close SHORT position
        """
        # Calculate slippage
        slippage_per_share = self._calculate_slippage(price, side)
        execution_price = price + slippage_per_share

        # Calculate commission
        commission = self.commission_per_share * Decimal(str(quantity))

        # Calculate costs
        total_slippage = abs(slippage_per_share) * Decimal(str(quantity))

        # Determine if opening or closing position
        existing_position = self.positions.get(symbol)
        is_opening = existing_position is None
        is_closing = existing_position is not None

        # OPENING A POSITION
        if is_opening:
            if side == "buy" and position_intent == "LONG":
                # Open LONG position with BUY
                cost = (execution_price * Decimal(str(quantity))) + commission
                if cost > self.cash:
                    logger.warning(f"Insufficient cash for LONG entry: need {cost}, have {self.cash}")
                    return None

                self.cash -= cost
                self.positions[symbol] = Position(
                    symbol=symbol,
                    side="LONG",
                    quantity=quantity,
                    entry_price=execution_price,
                    entry_time=timestamp,
                )
                pnl = None

            elif side == "sell" and position_intent == "SHORT":
                # Open SHORT position with SELL
                # For short selling, we receive cash (minus commission)
                proceeds = (execution_price * Decimal(str(quantity))) - commission
                self.cash += proceeds

                self.positions[symbol] = Position(
                    symbol=symbol,
                    side="SHORT",
                    quantity=quantity,
                    entry_price=execution_price,
                    entry_time=timestamp,
                )
                pnl = None

            else:
                logger.warning(
                    f"Invalid opening trade: side={side}, position_intent={position_intent}. "
                    "Use BUY+LONG or SELL+SHORT to open positions."
                )
                return None

        # CLOSING A POSITION
        else:
            pos = existing_position
            if pos.quantity < quantity:
                logger.warning(
                    f"Insufficient shares to close: need {quantity}, have {pos.quantity}"
                )
                return None

            if pos.side == "LONG" and side == "sell":
                # Close LONG position with SELL
                proceeds = (execution_price * Decimal(str(quantity))) - commission
                cost_basis = pos.entry_price * Decimal(str(quantity))
                pnl = (execution_price * Decimal(str(quantity))) - cost_basis - commission
                self.cash += proceeds

            elif pos.side == "SHORT" and side == "buy":
                # Close SHORT position with BUY (buy to cover)
                cost = (execution_price * Decimal(str(quantity))) + commission
                if cost > self.cash:
                    logger.warning(f"Insufficient cash to cover SHORT: need {cost}, have {self.cash}")
                    return None

                proceeds = pos.entry_price * Decimal(str(quantity))  # Original sale proceeds
                pnl = proceeds - (execution_price * Decimal(str(quantity))) - commission
                self.cash -= cost

            else:
                logger.warning(
                    f"Invalid closing trade: position.side={pos.side}, trade.side={side}. "
                    "Use SELL to close LONG, BUY to close SHORT."
                )
                return None

            # Update or close position
            if pos.quantity == quantity:
                del self.positions[symbol]
            else:
                pos.quantity -= quantity

        # Create trade record
        trade = BacktestTrade(
            backtest_id=backtest_id,
            symbol=symbol,
            side=side,
            quantity=quantity,
            price=execution_price,
            executed_at=timestamp,
            pnl=pnl,
            commission=commission,
            slippage=total_slippage,
            metadata=metadata,
        )

        # Track totals
        self.total_commission += commission
        self.total_slippage += total_slippage

        # Store trade
        self.trades.append(trade)

        logger.debug(
            f"Executed {side} {quantity} {symbol} @ {execution_price} "
            f"(slippage: {total_slippage}, commission: {commission})"
        )

        return trade

    def get_position(self, symbol: str) -> Optional[Position]:
        """Get current position for a symbol.

        Args:
            symbol: Trading symbol

        Returns:
            Position if exists, None otherwise
        """
        return self.positions.get(symbol)

    def has_position(self, symbol: str) -> bool:
        """Check if there's an open position for a symbol.

        Args:
            symbol: Trading symbol

        Returns:
            True if position exists
        """
        return symbol in self.positions

    def get_equity(self, current_prices: dict[str, Decimal]) -> Decimal:
        """Calculate current total equity.

        Args:
            current_prices: Current prices for each symbol

        Returns:
            Total equity (cash + positions value)
        """
        positions_value = Decimal("0")

        for symbol, pos in self.positions.items():
            if symbol in current_prices:
                positions_value += current_prices[symbol] * Decimal(str(pos.quantity))

        return self.cash + positions_value

    def get_positions_value(self, current_prices: dict[str, Decimal]) -> Decimal:
        """Calculate current positions market value.

        Args:
            current_prices: Current prices for each symbol

        Returns:
            Total positions value
        """
        positions_value = Decimal("0")

        for symbol, pos in self.positions.items():
            if symbol in current_prices:
                positions_value += current_prices[symbol] * Decimal(str(pos.quantity))

        return positions_value

    def record_equity_curve_point(
        self,
        backtest_id: int,
        timestamp: datetime,
        current_prices: dict[str, Decimal],
    ) -> EquityCurvePoint:
        """Record an equity curve point.

        Args:
            backtest_id: Backtest ID
            timestamp: Timestamp for this point
            current_prices: Current prices for each symbol

        Returns:
            Equity curve point
        """
        positions_value = self.get_positions_value(current_prices)
        equity = self.cash + positions_value

        point = EquityCurvePoint(
            backtest_id=backtest_id,
            timestamp=timestamp,
            equity=equity,
            cash=self.cash,
            positions_value=positions_value,
        )

        self.equity_curve.append(point)
        return point

    def get_summary(self) -> dict:
        """Get summary statistics.

        Returns:
            Dictionary with summary stats
        """
        return {
            "initial_capital": self.initial_capital,
            "current_cash": self.cash,
            "total_trades": len(self.trades),
            "open_positions": len(self.positions),
            "total_commission": self.total_commission,
            "total_slippage": self.total_slippage,
        }
