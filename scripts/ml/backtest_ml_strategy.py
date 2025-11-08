"""Run backtest for ML strategy.

This script:
1. Loads the trained XGBoost model
2. Runs backtest on test period (Aug-Nov 2025)
3. Evaluates trading performance metrics
4. Compares to buy-and-hold baseline
"""

import asyncio
import sys
from datetime import datetime
from pathlib import Path

import pytz

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from decimal import Decimal

from app.db.connection import db_pool
from app.models.backtest import BacktestConfig
from app.services.backtest_runner import BacktestRunner
from strategies.ml_strategy import MLStrategy


async def main():
    """Run ML strategy backtest."""
    print("="*70)
    print("ML STRATEGY BACKTEST")
    print("="*70)
    print()

    # Initialize database connection
    await db_pool.connect()

    try:
        # Strategy configuration
        strategy_config = {
            "model_path": "models/xgboost_spy_latest.pkl",
            "position_size": 10,
            "confidence_threshold": 0.65,  # Only take high-confidence signals
            "require_all_timeframes": True,
            "max_bars_buffer": 200,  # Increase buffer for indicator calculation
        }

        # Test period (same as model's test set)
        # From training output: Test period is 2025-08-05 13:41:00+00:00 to 2025-11-06 20:38:00+00:00
        start_date = datetime(2025, 8, 5, 13, 41, 0, tzinfo=pytz.UTC)
        end_date = datetime(2025, 11, 6, 20, 38, 0, tzinfo=pytz.UTC)

        print(f"Test Period: {start_date} to {end_date}")
        print(f"Symbol: SPY")
        print(f"Position Size: {strategy_config['position_size']} shares")
        print(f"Confidence Threshold: {strategy_config['confidence_threshold']}")
        print()

        # Initialize backtest runner
        backtest_runner = BacktestRunner(db_pool.pool)

        print("Running backtest...")
        print()

        # Create backtest configuration
        backtest_config = BacktestConfig(
            strategy_name="ml_strategy",
            symbol="SPY",
            start_date=start_date,
            end_date=end_date,
            initial_capital=Decimal("10000"),
            commission_per_share=Decimal("0.005"),
            slippage_bps=5,
            config=strategy_config,
        )

        # Run backtest
        results = await backtest_runner.run_backtest(backtest_config)

        # Print results
        print("="*70)
        print("BACKTEST RESULTS")
        print("="*70)
        print()

        print(f"Backtest ID: {results.backtest.id}")
        print(f"Status: {results.backtest.status}")
        print()

        print("-"*70)
        print("PERFORMANCE METRICS")
        print("-"*70)
        metrics = results.metrics

        print(f"\nTotal Return: {metrics.total_return_pct or 0:.2f}%")
        print(f"Total P&L: ${metrics.total_pnl:.2f}")
        print(f"CAGR: {metrics.cagr or 0:.2f}%")
        print()

        print(f"Sharpe Ratio: {metrics.sharpe_ratio or 0:.2f}")
        print(f"Sortino Ratio: {metrics.sortino_ratio or 0:.2f}")
        print(f"Max Drawdown: {metrics.max_drawdown_pct or 0:.2f}%")
        print(f"Max Drawdown Duration (days): {metrics.max_drawdown_duration_days or 0}")
        print()

        print(f"Total Trades: {metrics.total_trades}")
        print(f"Winning Trades: {metrics.winning_trades}")
        print(f"Losing Trades: {metrics.losing_trades}")
        print(f"Win Rate: {metrics.win_rate or 0:.2f}%")
        print()

        print(f"Profit Factor: {metrics.profit_factor or 0:.2f}")
        print(f"Average Win: ${metrics.average_win or 0:.2f}")
        print(f"Average Loss: ${metrics.average_loss or 0:.2f}")
        print(f"Largest Win: ${metrics.largest_win or 0:.2f}")
        print(f"Largest Loss: ${metrics.largest_loss or 0:.2f}")
        print()

        print(f"Average Holding Period (minutes): {metrics.average_holding_period_minutes or 0:.1f}")
        print(f"Max Consecutive Wins: {metrics.max_consecutive_wins or 0}")
        print(f"Max Consecutive Losses: {metrics.max_consecutive_losses or 0}")
        print()

        # Success criteria check
        print("-"*70)
        print("SUCCESS CRITERIA CHECK")
        print("-"*70)
        print()

        target_sharpe = 1.0
        target_win_rate = 55.0
        target_max_dd = -10.0

        sharpe_ok = metrics.sharpe_ratio >= target_sharpe
        win_rate_ok = metrics.win_rate >= target_win_rate
        dd_ok = metrics.max_drawdown_pct >= target_max_dd

        print(f"Sharpe Ratio > {target_sharpe}: {metrics.sharpe_ratio:.2f} {'✓' if sharpe_ok else '✗'}")
        print(f"Win Rate > {target_win_rate}%: {metrics.win_rate:.2f}% {'✓' if win_rate_ok else '✗'}")
        print(f"Max Drawdown > {target_max_dd}%: {metrics.max_drawdown_pct:.2f}% {'✓' if dd_ok else '✗'}")
        print()

        if sharpe_ok and win_rate_ok and dd_ok:
            print("✓ ALL SUCCESS CRITERIA MET - Ready for paper trading!")
        else:
            print("✗ Some criteria not met - Consider:")
            if not sharpe_ok:
                print("  - Increase confidence threshold to filter weak signals")
                print("  - Try different labeling parameters (profit target, stop loss)")
            if not win_rate_ok:
                print("  - Add more features or feature engineering")
                print("  - Try different model hyperparameters")
            if not dd_ok:
                print("  - Implement dynamic position sizing")
                print("  - Add stop-loss rules")

        print()
        print("-"*70)
        print("TRADE SAMPLE (First 5 Trades)")
        print("-"*70)
        print()

        if results.trades:
            for i, trade in enumerate(results.trades[:5], 1):
                print(f"Trade {i}:")
                print(f"  {trade.type.upper()} at {trade.price:.2f} ({trade.quantity} shares)")
                print(f"  Time: {trade.timestamp}")
                print(f"  P&L: ${trade.pnl:.2f}")
                print()

            if len(results.trades) > 5:
                print(f"... and {len(results.trades) - 5} more trades")
                print()

        print("="*70)
        print()

        print(f"View detailed results:")
        print(f"  GET /api/v1/backtest/{results.backtest.id}/detailed")
        print()

    finally:
        # Close database connection
        await db_pool.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
