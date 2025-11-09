"""Backtest metrics calculator.

Calculates comprehensive performance metrics from backtest results including:
- Returns (total return, CAGR)
- Risk metrics (Sharpe, Sortino, max drawdown, volatility)
- Trade statistics (win rate, profit factor, avg win/loss)
- Position metrics (holding period, exposure)
- Daily statistics (best/worst days, positive days %)
"""

import math
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional

import pandas as pd

from app.models.backtest import BacktestMetrics, BacktestTrade, EquityCurvePoint
from app.utils.logger import logger


class BacktestMetricsCalculator:
    """Calculate backtest performance metrics."""

    @staticmethod
    def calculate_metrics(
        trades: list[BacktestTrade],
        equity_curve: list[EquityCurvePoint],
        initial_capital: Decimal,
        start_date: datetime,
        end_date: datetime,
    ) -> BacktestMetrics:
        """Calculate all backtest metrics.

        Args:
            trades: List of backtest trades
            equity_curve: Equity curve points
            initial_capital: Starting capital
            start_date: Backtest start date
            end_date: Backtest end date

        Returns:
            Complete backtest metrics
        """
        metrics = BacktestMetrics()

        if not equity_curve:
            logger.warning("No equity curve data, returning empty metrics")
            return metrics

        # Convert to DataFrame for easier calculations
        equity_df = pd.DataFrame(
            [
                {
                    "timestamp": point.timestamp,
                    "equity": float(point.equity),
                    "cash": float(point.cash),
                    "positions_value": float(point.positions_value),
                }
                for point in equity_curve
            ]
        )
        equity_df = equity_df.set_index("timestamp")

        # Calculate returns metrics
        final_equity = equity_curve[-1].equity
        total_pnl = final_equity - initial_capital
        metrics.total_pnl = total_pnl

        if initial_capital > 0:
            metrics.total_return_pct = float(
                (total_pnl / initial_capital) * Decimal("100")
            )

            # CAGR (compound annual growth rate)
            days = (end_date - start_date).days
            if days > 0:
                years = days / 365.0
                if final_equity > 0:
                    metrics.cagr = (
                        (float(final_equity / initial_capital) ** (1 / years) - 1) * 100
                    )

        # Calculate drawdown metrics
        drawdown_metrics = BacktestMetricsCalculator._calculate_drawdown_metrics(
            equity_df
        )
        metrics.max_drawdown_pct = drawdown_metrics["max_drawdown_pct"]
        metrics.max_drawdown_duration_days = drawdown_metrics[
            "max_drawdown_duration_days"
        ]

        # Calculate risk metrics (Sharpe, Sortino, volatility)
        risk_metrics = BacktestMetricsCalculator._calculate_risk_metrics(equity_df)
        metrics.sharpe_ratio = risk_metrics["sharpe_ratio"]
        metrics.sortino_ratio = risk_metrics["sortino_ratio"]
        metrics.volatility = risk_metrics["volatility"]

        # Calculate trade statistics
        if trades:
            trade_stats = BacktestMetricsCalculator._calculate_trade_statistics(trades)
            metrics.total_trades = trade_stats["total_trades"]
            metrics.winning_trades = trade_stats["winning_trades"]
            metrics.losing_trades = trade_stats["losing_trades"]
            metrics.win_rate = trade_stats["win_rate"]
            metrics.profit_factor = trade_stats["profit_factor"]
            metrics.average_win = trade_stats["average_win"]
            metrics.average_loss = trade_stats["average_loss"]
            metrics.largest_win = trade_stats["largest_win"]
            metrics.largest_loss = trade_stats["largest_loss"]
            metrics.average_holding_period_minutes = trade_stats[
                "average_holding_period_minutes"
            ]
            metrics.total_commission = trade_stats["total_commission"]
            metrics.total_slippage = trade_stats["total_slippage"]

        # Calculate exposure time
        metrics.exposure_time_pct = BacktestMetricsCalculator._calculate_exposure_time(
            equity_df
        )

        # Calculate daily statistics
        daily_stats = BacktestMetricsCalculator._calculate_daily_statistics(equity_df)
        metrics.best_day_pct = daily_stats["best_day_pct"]
        metrics.worst_day_pct = daily_stats["worst_day_pct"]
        metrics.average_daily_return_pct = daily_stats["average_daily_return_pct"]
        metrics.positive_days_pct = daily_stats["positive_days_pct"]

        return metrics

    @staticmethod
    def _calculate_drawdown_metrics(equity_df: pd.DataFrame) -> dict:
        """Calculate drawdown metrics.

        Args:
            equity_df: Equity curve DataFrame

        Returns:
            Dictionary with drawdown metrics
        """
        equity = equity_df["equity"]

        # Calculate running maximum
        running_max = equity.cummax()

        # Calculate drawdown
        drawdown = (equity - running_max) / running_max * 100

        max_drawdown_pct = abs(drawdown.min()) if len(drawdown) > 0 else None

        # Calculate max drawdown duration
        max_dd_duration_days = None
        if len(drawdown) > 0:
            # Find periods where we're in drawdown
            in_drawdown = drawdown < 0

            if in_drawdown.any():
                # Label consecutive drawdown periods
                drawdown_periods = (in_drawdown != in_drawdown.shift()).cumsum()

                # For each drawdown period, calculate duration
                durations = []
                for period in drawdown_periods[in_drawdown].unique():
                    period_dates = equity_df.index[drawdown_periods == period]
                    if len(period_dates) > 1:
                        duration = (period_dates[-1] - period_dates[0]).days
                        durations.append(duration)

                if durations:
                    max_dd_duration_days = max(durations)

        return {
            "max_drawdown_pct": max_drawdown_pct,
            "max_drawdown_duration_days": max_dd_duration_days,
        }

    @staticmethod
    def _calculate_risk_metrics(equity_df: pd.DataFrame) -> dict:
        """Calculate risk-adjusted metrics.

        Args:
            equity_df: Equity curve DataFrame

        Returns:
            Dictionary with risk metrics
        """
        equity = equity_df["equity"]

        # Calculate returns
        returns = equity.pct_change().dropna()

        if len(returns) == 0:
            return {
                "sharpe_ratio": None,
                "sortino_ratio": None,
                "volatility": None,
            }

        # Annualized volatility
        volatility = float(returns.std() * math.sqrt(252) * 100)  # Assume 252 trading days

        # Sharpe ratio (assuming 0% risk-free rate)
        mean_return = returns.mean()
        if returns.std() > 0:
            sharpe_ratio = float((mean_return / returns.std()) * math.sqrt(252))
        else:
            sharpe_ratio = None

        # Sortino ratio (downside deviation)
        downside_returns = returns[returns < 0]
        if len(downside_returns) > 0 and downside_returns.std() > 0:
            sortino_ratio = float(
                (mean_return / downside_returns.std()) * math.sqrt(252)
            )
        else:
            sortino_ratio = None

        return {
            "sharpe_ratio": sharpe_ratio,
            "sortino_ratio": sortino_ratio,
            "volatility": volatility,
        }

    @staticmethod
    def _calculate_trade_statistics(trades: list[BacktestTrade]) -> dict:
        """Calculate trade statistics.

        Args:
            trades: List of backtest trades

        Returns:
            Dictionary with trade statistics
        """
        # Filter for exit trades (any trade with P&L is a closing trade)
        # - LONG positions: SELL with pnl
        # - SHORT positions: BUY with pnl
        exit_trades = [t for t in trades if t.pnl is not None]

        if not exit_trades:
            return {
                "total_trades": 0,
                "winning_trades": 0,
                "losing_trades": 0,
                "win_rate": None,
                "profit_factor": None,
                "average_win": None,
                "average_loss": None,
                "largest_win": None,
                "largest_loss": None,
                "average_holding_period_minutes": None,
                "total_commission": Decimal("0"),
                "total_slippage": Decimal("0"),
            }

        winning_trades = [t for t in exit_trades if t.pnl > 0]
        losing_trades = [t for t in exit_trades if t.pnl < 0]

        total_trades = len(exit_trades)
        win_count = len(winning_trades)
        loss_count = len(losing_trades)

        win_rate = (win_count / total_trades * 100) if total_trades > 0 else None

        # Profit factor
        gross_profit = sum(t.pnl for t in winning_trades) if winning_trades else Decimal("0")
        gross_loss = abs(sum(t.pnl for t in losing_trades)) if losing_trades else Decimal("0")
        profit_factor = float(gross_profit / gross_loss) if gross_loss > 0 else None

        # Average win/loss
        average_win = (
            sum(t.pnl for t in winning_trades) / len(winning_trades)
            if winning_trades
            else None
        )
        average_loss = (
            sum(t.pnl for t in losing_trades) / len(losing_trades)
            if losing_trades
            else None
        )

        # Largest win/loss
        largest_win = max((t.pnl for t in winning_trades), default=None)
        largest_loss = min((t.pnl for t in losing_trades), default=None)

        # Calculate holding period (need to match entry/exit trades)
        # Entry trades have pnl=None, exit trades have pnl set
        holding_periods = []
        entry_trades = [t for t in trades if t.pnl is None]

        for exit_trade in exit_trades:
            # Find corresponding entry trade (most recent entry before this exit)
            matching_entries = [
                t for t in entry_trades if t.executed_at < exit_trade.executed_at
            ]
            if matching_entries:
                entry_trade = matching_entries[-1]  # Most recent
                holding_period = (
                    exit_trade.executed_at - entry_trade.executed_at
                ).total_seconds() / 60
                holding_periods.append(holding_period)

        average_holding_period_minutes = (
            sum(holding_periods) / len(holding_periods) if holding_periods else None
        )

        # Total commission and slippage
        total_commission = sum(t.commission for t in trades)
        total_slippage = sum(t.slippage for t in trades)

        return {
            "total_trades": total_trades,
            "winning_trades": win_count,
            "losing_trades": loss_count,
            "win_rate": win_rate,
            "profit_factor": profit_factor,
            "average_win": average_win,
            "average_loss": average_loss,
            "largest_win": largest_win,
            "largest_loss": largest_loss,
            "average_holding_period_minutes": average_holding_period_minutes,
            "total_commission": total_commission,
            "total_slippage": total_slippage,
        }

    @staticmethod
    def _calculate_exposure_time(equity_df: pd.DataFrame) -> Optional[float]:
        """Calculate percentage of time in market.

        Args:
            equity_df: Equity curve DataFrame

        Returns:
            Exposure time percentage
        """
        if len(equity_df) == 0:
            return None

        # Count bars where positions_value > 0
        in_market = equity_df["positions_value"] > 0
        exposure_pct = (in_market.sum() / len(equity_df)) * 100

        return float(exposure_pct)

    @staticmethod
    def _calculate_daily_statistics(equity_df: pd.DataFrame) -> dict:
        """Calculate daily return statistics.

        Args:
            equity_df: Equity curve DataFrame

        Returns:
            Dictionary with daily statistics
        """
        if len(equity_df) == 0:
            return {
                "best_day_pct": None,
                "worst_day_pct": None,
                "average_daily_return_pct": None,
                "positive_days_pct": None,
            }

        # Resample to daily (last value of each day)
        daily_equity = equity_df["equity"].resample("D").last().dropna()

        if len(daily_equity) < 2:
            return {
                "best_day_pct": None,
                "worst_day_pct": None,
                "average_daily_return_pct": None,
                "positive_days_pct": None,
            }

        # Calculate daily returns
        daily_returns = daily_equity.pct_change().dropna() * 100

        best_day_pct = float(daily_returns.max()) if len(daily_returns) > 0 else None
        worst_day_pct = float(daily_returns.min()) if len(daily_returns) > 0 else None
        average_daily_return_pct = float(daily_returns.mean()) if len(daily_returns) > 0 else None

        positive_days = (daily_returns > 0).sum()
        positive_days_pct = (
            (positive_days / len(daily_returns)) * 100 if len(daily_returns) > 0 else None
        )

        return {
            "best_day_pct": best_day_pct,
            "worst_day_pct": worst_day_pct,
            "average_daily_return_pct": average_daily_return_pct,
            "positive_days_pct": positive_days_pct,
        }
