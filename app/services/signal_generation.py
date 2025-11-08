"""Signal generation service.

Orchestrates strategy execution and signal generation:
1. Load active strategies from database and strategy loader
2. Fetch latest market data for each strategy's symbols/timeframes
3. Call strategy.on_bar() to process data
4. Call strategy.generate_signals() to get trading signals
5. Store signals in database
"""

import logging
from datetime import datetime
from typing import Optional

from asyncpg.pool import Pool

from app.db.repositories.market_data import MarketDataRepository
from app.db.repositories.signals import SignalsRepository
from app.db.repositories.strategies import StrategyRepository
from app.models.signals import SignalCreate
from app.services.feature_engine import FeatureEngine
from app.strategies.loader import StrategyLoader
from app.utils.logger import get_logger
from app.utils.market_hours import MarketHours

logger = get_logger(__name__)


class SignalGenerationService:
    """Service for generating trading signals from strategies."""

    def __init__(self, db_pool: Pool):
        """Initialize signal generation service.

        Args:
            db_pool: Database connection pool
        """
        self.db_pool = db_pool
        self.feature_engine = FeatureEngine(db_pool)
        self.strategy_loader = StrategyLoader()
        self.strategy_repo = StrategyRepository(db_pool)
        self.signals_repo = SignalsRepository(db_pool)
        self.market_data_repo = MarketDataRepository(db_pool)
        self.market_hours = MarketHours()

    async def initialize(self) -> None:
        """Initialize the service by loading all strategies."""
        logger.info("Initializing signal generation service...")

        # Load all strategy files
        self.strategy_loader.load_all_strategies()

        # Get strategy metadata
        metadata_list = self.strategy_loader.get_all_strategy_metadata()
        logger.info(f"Discovered {len(metadata_list)} strategies")

        # Sync with database: create strategies that don't exist
        async with self.db_pool.acquire() as conn:
            for metadata in metadata_list:
                existing = await self.strategy_repo.get_strategy_by_name(
                    conn, metadata["name"]
                )

                if not existing:
                    # Create new strategy in database
                    from app.models.strategy import StrategyCreate

                    strategy_create = StrategyCreate(
                        name=metadata["name"],
                        description=metadata["description"],
                        version=metadata["version"],
                        author=metadata.get("author"),
                        is_active=False,  # Start inactive
                        symbols=metadata["symbols"],
                        timeframes=metadata["timeframes"],
                        config=metadata["parameters"],
                    )
                    await self.strategy_repo.create_strategy(conn, strategy_create)
                    logger.info(f"Created strategy in database: {metadata['name']}")
                else:
                    logger.info(
                        f"Strategy already exists in database: {metadata['name']}"
                    )

        logger.info("Signal generation service initialized")

    async def generate_signals_for_all_strategies(self) -> dict[str, list[SignalCreate]]:
        """Generate signals for all active strategies.

        Returns:
            Dictionary mapping strategy name to list of generated signals
        """
        # Get active strategies from database
        async with self.db_pool.acquire() as conn:
            active_strategies = await self.strategy_repo.get_active_strategies(conn)

        if not active_strategies:
            logger.info("No active strategies found")
            return {}

        logger.info(f"Generating signals for {len(active_strategies)} active strategies")

        all_signals = {}

        for strategy_db in active_strategies:
            signals = await self.generate_signals_for_strategy(strategy_db.name)
            if signals:
                all_signals[strategy_db.name] = signals

        return all_signals

    async def generate_signals_for_strategy(
        self, strategy_name: str
    ) -> list[SignalCreate]:
        """Generate signals for a specific strategy.

        Args:
            strategy_name: Name of the strategy

        Returns:
            List of generated signals
        """
        # Get strategy instance
        strategy = self.strategy_loader.get_strategy_instance(strategy_name)

        if not strategy:
            # Try to instantiate it
            async with self.db_pool.acquire() as conn:
                strategy_db = await self.strategy_repo.get_strategy_by_name(
                    conn, strategy_name
                )

            if not strategy_db:
                logger.error(f"Strategy not found in database: {strategy_name}")
                return []

            strategy = self.strategy_loader.instantiate_strategy(
                strategy_name, config=strategy_db.config
            )

            if not strategy:
                logger.error(f"Failed to instantiate strategy: {strategy_name}")
                return []

        # Get required symbols and timeframes
        symbols = strategy.get_symbols()
        timeframes = strategy.get_timeframes()

        all_signals = []

        # Process each symbol
        for symbol in symbols:
            # Process each timeframe
            for timeframe in timeframes:
                try:
                    # Fetch latest bars
                    bars = await self.feature_engine.get_bars(
                        symbol=symbol,
                        timeframe=timeframe,
                        lookback_bars=100,  # Default lookback
                    )

                    if bars.empty:
                        logger.warning(
                            f"No bars found for {symbol} {timeframe}, skipping"
                        )
                        continue

                    # Get latest bar
                    latest_bar = bars.iloc[-1]

                    # Call strategy.on_bar()
                    strategy.on_bar(symbol, timeframe, latest_bar, bars)

                except Exception as e:
                    logger.error(
                        f"Error processing {symbol} {timeframe} for {strategy_name}: {e}",
                        exc_info=True,
                    )
                    continue

            # After processing all timeframes, generate signals for this symbol
            try:
                signals = strategy.generate_signals(symbol)
                if signals:
                    logger.info(
                        f"Strategy {strategy_name} generated {len(signals)} signals for {symbol}"
                    )
                    all_signals.extend(signals)

                    # Store signals in database
                    async with self.db_pool.acquire() as conn:
                        for signal in signals:
                            await self.signals_repo.create_signal(conn, signal)

            except Exception as e:
                logger.error(
                    f"Error generating signals for {symbol} in {strategy_name}: {e}",
                    exc_info=True,
                )
                continue

        return all_signals

    async def run_signal_generation_cycle(self) -> dict[str, int]:
        """Run a complete signal generation cycle.

        This is the main entry point called by the scheduler.

        Returns:
            Dictionary with statistics (strategies_processed, signals_generated)
        """
        # Check if market is open
        if not self.market_hours.is_market_open(datetime.utcnow()):
            logger.info("Market is closed, skipping signal generation")
            return {"strategies_processed": 0, "signals_generated": 0}

        logger.info("Starting signal generation cycle")

        all_signals = await self.generate_signals_for_all_strategies()

        strategies_processed = len(all_signals)
        signals_generated = sum(len(signals) for signals in all_signals.values())

        logger.info(
            f"Signal generation cycle complete: {strategies_processed} strategies, "
            f"{signals_generated} signals generated"
        )

        return {
            "strategies_processed": strategies_processed,
            "signals_generated": signals_generated,
        }

    def get_loaded_strategies(self) -> list[dict]:
        """Get list of loaded strategies.

        Returns:
            List of strategy metadata
        """
        return self.strategy_loader.get_all_strategy_metadata()

    async def reload_strategy(self, module_name: str) -> bool:
        """Reload a strategy module.

        Args:
            module_name: Module name to reload

        Returns:
            True if successful, False otherwise
        """
        try:
            strategy_class = self.strategy_loader.reload_strategy(module_name)
            if strategy_class:
                logger.info(f"Reloaded strategy: {module_name}")
                return True
            return False
        except Exception as e:
            logger.error(f"Error reloading strategy {module_name}: {e}", exc_info=True)
            return False
