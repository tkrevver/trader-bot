"""Backtest runner - event-driven backtesting engine.

Runs backtests by:
1. Loading strategy from strategy loader
2. Fetching historical OHLCV data from database
3. Replaying bars chronologically (event-driven)
4. Calling strategy.on_bar() and strategy.generate_signals()
5. Executing simulated trades with slippage/commission
6. Tracking positions and equity
7. Calculating performance metrics
8. Storing results in database
"""

import asyncio
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional

import pandas as pd
import pytz
from asyncpg.pool import Pool

from app.db.repositories.backtest import BacktestRepository
from app.models.backtest import (
    Backtest,
    BacktestConfig,
    BacktestCreate,
    BacktestMetrics,
    BacktestResult,
    BacktestStatus,
    BacktestTrade,
)
from app.services.backtest_metrics import BacktestMetricsCalculator
from app.services.backtest_position_tracker import BacktestPositionTracker
from app.services.feature_engine import FeatureEngine
from app.strategies.base import Strategy
from app.strategies.loader import StrategyLoader
from app.utils.logger import logger


class BacktestRunner:
    """Event-driven backtest runner."""

    def __init__(self, db_pool: Pool):
        """Initialize backtest runner.

        Args:
            db_pool: Database connection pool
        """
        self.db_pool = db_pool
        self.backtest_repo = BacktestRepository(db_pool)
        self.feature_engine = FeatureEngine(db_pool)
        self.strategy_loader = StrategyLoader()

    async def run_backtest(self, config: BacktestConfig) -> BacktestResult:
        """Run a backtest.

        Args:
            config: Backtest configuration

        Returns:
            Backtest result with metrics

        Raises:
            Exception: If backtest fails
        """
        # Create backtest record
        async with self.db_pool.acquire() as conn:
            backtest_create = BacktestCreate(
                strategy_name=config.strategy_name,
                symbol=config.symbol,
                start_date=config.start_date,
                end_date=config.end_date,
                initial_capital=config.initial_capital,
                config=config.config,
            )
            backtest = await self.backtest_repo.create_backtest(conn, backtest_create)

        logger.info(
            f"Starting backtest {backtest.id}: {config.strategy_name} on {config.symbol} "
            f"from {config.start_date} to {config.end_date}"
        )

        try:
            # Update status to RUNNING
            async with self.db_pool.acquire() as conn:
                await self.backtest_repo.update_backtest_status(
                    conn, backtest.id, BacktestStatus.RUNNING
                )

            # Load strategy
            strategy = await self._load_strategy(config)

            # Initialize position tracker
            tracker = BacktestPositionTracker(
                initial_capital=config.initial_capital,
                commission_per_share=config.commission_per_share,
                slippage_bps=config.slippage_bps,
            )

            # Fetch historical data for all required timeframes
            historical_data = await self._fetch_historical_data(config, strategy)

            # Run event-driven backtest
            await self._run_event_loop(backtest.id, config, strategy, tracker, historical_data)

            # Calculate metrics
            metrics = BacktestMetricsCalculator.calculate_metrics(
                trades=tracker.trades,
                equity_curve=tracker.equity_curve,
                initial_capital=config.initial_capital,
                start_date=config.start_date,
                end_date=config.end_date,
            )

            # Save results to database
            async with self.db_pool.acquire() as conn:
                # Save metrics
                await self.backtest_repo.save_backtest_metrics(
                    conn, backtest.id, metrics
                )

                # Save trades
                for trade in tracker.trades:
                    await self.backtest_repo.save_backtest_trade(conn, trade)

                # Save equity curve
                for point in tracker.equity_curve:
                    await self.backtest_repo.save_equity_curve_point(conn, point)

                # Update status to COMPLETED
                backtest = await self.backtest_repo.update_backtest_status(
                    conn, backtest.id, BacktestStatus.COMPLETED
                )

            logger.info(
                f"Backtest {backtest.id} completed: "
                f"{metrics.total_trades} trades, "
                f"{metrics.total_return_pct:.2f}% return"
            )

            return BacktestResult(
                backtest=backtest,
                metrics=metrics,
                trades=tracker.trades,
                equity_curve=tracker.equity_curve,
            )

        except Exception as e:
            logger.error(f"Backtest {backtest.id} failed: {e}", exc_info=True)

            # Update status to FAILED
            async with self.db_pool.acquire() as conn:
                await self.backtest_repo.update_backtest_status(
                    conn, backtest.id, BacktestStatus.FAILED, error_message=str(e)
                )

            raise

    async def _load_strategy(self, config: BacktestConfig) -> Strategy:
        """Load and initialize strategy.

        Args:
            config: Backtest configuration

        Returns:
            Initialized strategy instance

        Raises:
            ValueError: If strategy not found
        """
        # Load all strategies
        self.strategy_loader.load_all_strategies()

        # Instantiate strategy
        strategy = self.strategy_loader.instantiate_strategy(
            config.strategy_name, config=config.config
        )

        if not strategy:
            raise ValueError(f"Strategy not found: {config.strategy_name}")

        return strategy

    async def _fetch_historical_data(
        self, config: BacktestConfig, strategy: Strategy
    ) -> dict[str, pd.DataFrame]:
        """Fetch historical data for all required timeframes.

        Args:
            config: Backtest configuration
            strategy: Strategy instance

        Returns:
            Dictionary mapping timeframe to DataFrame

        Raises:
            ValueError: If no data found
        """
        timeframes = strategy.get_timeframes()
        historical_data = {}

        for timeframe in timeframes:
            # Fetch bars for this timeframe
            bars = await self.feature_engine.get_bars(
                symbol=config.symbol,
                timeframe=timeframe,
                lookback_bars=100000,  # Get all available bars
                end_time=config.end_date,
            )

            if bars.empty:
                raise ValueError(
                    f"No historical data found for {config.symbol} {timeframe}"
                )

            # Filter to date range - ensure timezone awareness
            start_date = config.start_date
            end_date = config.end_date

            # Make dates timezone-aware if they aren't
            if start_date.tzinfo is None:
                start_date = pytz.utc.localize(start_date)
            if end_date.tzinfo is None:
                end_date = pytz.utc.localize(end_date)

            bars = bars[
                (bars.index >= start_date) & (bars.index <= end_date)
            ]

            if bars.empty:
                raise ValueError(
                    f"No bars in date range for {config.symbol} {timeframe}"
                )

            historical_data[timeframe] = bars
            logger.info(
                f"Loaded {len(bars)} bars for {timeframe} "
                f"from {bars.index.min()} to {bars.index.max()}"
            )

        return historical_data

    async def _run_event_loop(
        self,
        backtest_id: int,
        config: BacktestConfig,
        strategy: Strategy,
        tracker: BacktestPositionTracker,
        historical_data: dict[str, pd.DataFrame],
    ) -> None:
        """Run event-driven backtest loop.

        Args:
            backtest_id: Backtest ID
            config: Backtest configuration
            strategy: Strategy instance
            tracker: Position tracker
            historical_data: Historical data for all timeframes
        """
        # Get primary timeframe (first one, typically 1min)
        timeframes = strategy.get_timeframes()
        primary_timeframe = timeframes[0]
        primary_bars = historical_data[primary_timeframe]

        logger.info(f"Running backtest on {len(primary_bars)} primary bars ({primary_timeframe})")

        # Iterate through primary timeframe bars
        total_bars = len(primary_bars)
        for i, (timestamp, bar) in enumerate(primary_bars.iterrows()):
            # Log progress every 50 bars
            if i > 0 and i % 50 == 0:
                progress_pct = (i / total_bars) * 100
                logger.info(f"Backtest progress: {i}/{total_bars} bars ({progress_pct:.1f}%)")
            # Process this bar on all timeframes
            for timeframe in timeframes:
                tf_bars = historical_data[timeframe]

                # Get bars up to current timestamp
                current_bars = tf_bars[tf_bars.index <= timestamp]

                if current_bars.empty:
                    continue

                # Get latest bar for this timeframe
                latest_bar = current_bars.iloc[-1]

                # Call strategy.on_bar()
                strategy.on_bar(
                    symbol=config.symbol,
                    timeframe=timeframe,
                    bar=latest_bar,
                    bars=current_bars,
                )

            # After processing all timeframes, check for signals
            signals = strategy.generate_signals(config.symbol)

            # Execute signals
            for signal in signals:
                execution_price = Decimal(str(bar["close"]))

                # Check if we have an existing position
                existing_position = tracker.get_position(config.symbol)
                state = strategy.get_state(config.symbol)

                if signal.signal_type == "BUY":
                    if existing_position is None:
                        # Opening a new LONG position
                        quantity = signal.quantity if signal.quantity else 10

                        trade = tracker.execute_trade(
                            backtest_id=backtest_id,
                            symbol=config.symbol,
                            side="buy",
                            quantity=quantity,
                            price=execution_price,
                            timestamp=timestamp,
                            position_intent="LONG",
                            metadata=signal.metadata,
                        )

                        if trade:
                            # Update strategy state
                            state.in_position = True
                            state.position_side = "LONG"
                            state.entry_price = float(execution_price)
                            state.entry_time = timestamp
                            state.position_size = quantity

                    elif existing_position.side == "SHORT":
                        # Closing a SHORT position (buy to cover)
                        quantity = existing_position.quantity

                        trade = tracker.execute_trade(
                            backtest_id=backtest_id,
                            symbol=config.symbol,
                            side="buy",
                            quantity=quantity,
                            price=execution_price,
                            timestamp=timestamp,
                            position_intent="SHORT",  # Closing SHORT
                            metadata=signal.metadata,
                        )

                        if trade:
                            # Reset strategy state
                            state.reset()

                elif signal.signal_type == "SELL":
                    if existing_position is None:
                        # Opening a new SHORT position
                        quantity = signal.quantity if signal.quantity else 10

                        trade = tracker.execute_trade(
                            backtest_id=backtest_id,
                            symbol=config.symbol,
                            side="sell",
                            quantity=quantity,
                            price=execution_price,
                            timestamp=timestamp,
                            position_intent="SHORT",
                            metadata=signal.metadata,
                        )

                        if trade:
                            # Update strategy state
                            state.in_position = True
                            state.position_side = "SHORT"
                            state.entry_price = float(execution_price)
                            state.entry_time = timestamp
                            state.position_size = quantity

                    elif existing_position.side == "LONG":
                        # Closing a LONG position
                        quantity = existing_position.quantity

                        trade = tracker.execute_trade(
                            backtest_id=backtest_id,
                            symbol=config.symbol,
                            side="sell",
                            quantity=quantity,
                            price=execution_price,
                            timestamp=timestamp,
                            position_intent="LONG",  # Closing LONG
                            metadata=signal.metadata,
                        )

                        if trade:
                            # Reset strategy state
                            state.reset()

            # Record equity curve point (every 100 bars to reduce storage)
            if i % 100 == 0 or i == len(primary_bars) - 1:
                current_price = {config.symbol: Decimal(str(bar["close"]))}
                tracker.record_equity_curve_point(
                    backtest_id=backtest_id,
                    timestamp=timestamp,
                    current_prices=current_price,
                )

        # Final equity curve point
        final_bar = primary_bars.iloc[-1]
        final_price = {config.symbol: Decimal(str(final_bar["close"]))}
        tracker.record_equity_curve_point(
            backtest_id=backtest_id,
            timestamp=primary_bars.index[-1],
            current_prices=final_price,
        )

        logger.info(
            f"Event loop completed: {len(tracker.trades)} trades executed, "
            f"{len(tracker.equity_curve)} equity points recorded"
        )

    async def get_backtest_result(self, backtest_id: int) -> Optional[BacktestResult]:
        """Get backtest result by ID.

        Args:
            backtest_id: Backtest ID

        Returns:
            Backtest result if found, None otherwise
        """
        async with self.db_pool.acquire() as conn:
            backtest = await self.backtest_repo.get_backtest(conn, backtest_id)
            if not backtest:
                return None

            trades = await self.backtest_repo.get_backtest_trades(conn, backtest_id)
            equity_curve = await self.backtest_repo.get_equity_curve(conn, backtest_id)

            # Parse metrics from JSON
            metrics = (
                BacktestMetrics(**backtest.metrics) if backtest.metrics else BacktestMetrics()
            )

            return BacktestResult(
                backtest=backtest,
                metrics=metrics,
                trades=trades,
                equity_curve=equity_curve,
            )
