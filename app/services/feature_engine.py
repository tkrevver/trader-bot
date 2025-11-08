"""Feature engine for computing technical indicators with caching.

This service fetches OHLCV data from the database and computes technical
indicators using the indicators library. Results are cached to avoid
redundant calculations.
"""

import hashlib
import logging
from datetime import datetime, timedelta
from functools import lru_cache
from typing import Any, Optional

import pandas as pd
from asyncpg.pool import Pool

from app.db.repositories.market_data import MarketDataRepository
from app.utils import indicators
from app.utils.logger import logger



class FeatureEngine:
    """Compute and cache technical indicators for trading strategies."""

    def __init__(self, db_pool: Pool):
        """Initialize feature engine.

        Args:
            db_pool: Database connection pool
        """
        self.db_pool = db_pool
        self.market_data_repo = MarketDataRepository()
        self._cache: dict[str, tuple[datetime, pd.DataFrame]] = {}
        self._cache_ttl_seconds = 60  # Cache for 60 seconds

    async def get_bars(
        self,
        symbol: str,
        timeframe: str = "1min",
        lookback_bars: int = 100,
        end_time: Optional[datetime] = None,
    ) -> pd.DataFrame:
        """Fetch OHLCV bars from database.

        Args:
            symbol: Trading symbol
            timeframe: Timeframe ('1min', '5min', '15min', '30min', 'daily')
            lookback_bars: Number of bars to fetch
            end_time: End time for query (default: now)

        Returns:
            DataFrame with OHLCV data indexed by time
        """
        if end_time is None:
            end_time = datetime.utcnow()

        # Calculate start time based on lookback
        # Rough estimate: for market hours, 1 trading day ~= 390 minutes
        if timeframe == "1min":
            lookback_minutes = lookback_bars
        elif timeframe == "5min":
            lookback_minutes = lookback_bars * 5
        elif timeframe == "15min":
            lookback_minutes = lookback_bars * 15
        elif timeframe == "30min":
            lookback_minutes = lookback_bars * 30
        elif timeframe == "daily":
            lookback_minutes = lookback_bars * 390  # Trading minutes per day
        else:
            lookback_minutes = lookback_bars

        # Add buffer for weekends/holidays (2x)
        start_time = end_time - timedelta(minutes=lookback_minutes * 2)

        # Fetch from appropriate table
        bars = await self.market_data_repo.get_bars(
            symbol=symbol,
            start_time=start_time,
            end_time=end_time,
            timeframe=timeframe,
            limit=lookback_bars,
        )

        if not bars:
            logger.warning(
                f"No bars found for {symbol} {timeframe} from {start_time} to {end_time}"
            )
            return pd.DataFrame()

        # Convert to DataFrame
        df = pd.DataFrame(
            [
                {
                    "time": bar.time,
                    "open": float(bar.open),
                    "high": float(bar.high),
                    "low": float(bar.low),
                    "close": float(bar.close),
                    "volume": bar.volume,
                    "vwap": float(bar.vwap) if bar.vwap else None,
                    "trades": bar.trades,
                }
                for bar in bars
            ]
        )

        df = df.set_index("time")
        df = df.sort_index()

        return df

    def _get_cache_key(
        self,
        symbol: str,
        timeframe: str,
        indicator_name: str,
        params: dict[str, Any],
    ) -> str:
        """Generate cache key for indicator calculation.

        Args:
            symbol: Trading symbol
            timeframe: Timeframe
            indicator_name: Indicator name
            params: Indicator parameters

        Returns:
            Hash string for cache key
        """
        # Sort params for consistent hashing
        params_str = str(sorted(params.items()))
        key_string = f"{symbol}:{timeframe}:{indicator_name}:{params_str}"
        return hashlib.md5(key_string.encode()).hexdigest()

    def _is_cache_valid(self, cache_key: str) -> bool:
        """Check if cached data is still valid.

        Args:
            cache_key: Cache key to check

        Returns:
            True if cache is valid, False otherwise
        """
        if cache_key not in self._cache:
            return False

        cached_time, _ = self._cache[cache_key]
        age_seconds = (datetime.utcnow() - cached_time).total_seconds()
        return age_seconds < self._cache_ttl_seconds

    def _get_from_cache(self, cache_key: str) -> Optional[pd.DataFrame]:
        """Get indicator data from cache.

        Args:
            cache_key: Cache key

        Returns:
            Cached DataFrame or None if not found/expired
        """
        if not self._is_cache_valid(cache_key):
            return None

        _, cached_df = self._cache[cache_key]
        return cached_df.copy()

    def _save_to_cache(self, cache_key: str, df: pd.DataFrame) -> None:
        """Save indicator data to cache.

        Args:
            cache_key: Cache key
            df: DataFrame to cache
        """
        self._cache[cache_key] = (datetime.utcnow(), df.copy())

    async def compute_indicator(
        self,
        symbol: str,
        timeframe: str,
        indicator_name: str,
        lookback_bars: int = 100,
        use_cache: bool = True,
        **indicator_params,
    ) -> pd.DataFrame:
        """Compute a single indicator with caching.

        Args:
            symbol: Trading symbol
            timeframe: Timeframe
            indicator_name: Indicator name (e.g., 'sma', 'rsi', 'macd')
            lookback_bars: Number of bars to fetch
            use_cache: Whether to use caching
            **indicator_params: Parameters for the indicator

        Returns:
            DataFrame with OHLCV data and computed indicator columns
        """
        # Check cache
        cache_key = self._get_cache_key(
            symbol, timeframe, indicator_name, indicator_params
        )

        if use_cache:
            cached_result = self._get_from_cache(cache_key)
            if cached_result is not None:
                logger.debug(f"Cache hit for {symbol} {timeframe} {indicator_name}")
                return cached_result

        # Fetch bars
        df = await self.get_bars(
            symbol=symbol, timeframe=timeframe, lookback_bars=lookback_bars
        )

        if df.empty:
            return df

        # Compute indicator
        try:
            indicator_func = getattr(indicators, indicator_name)
            result = indicator_func(df, **indicator_params)

            # Add indicator to dataframe
            if isinstance(result, pd.Series):
                df[indicator_name.upper()] = result
            elif isinstance(result, pd.DataFrame):
                df = df.join(result)

            # Save to cache
            if use_cache:
                self._save_to_cache(cache_key, df)

            return df

        except AttributeError:
            raise ValueError(f"Unknown indicator: {indicator_name}")

    async def compute_multiple_indicators(
        self,
        symbol: str,
        timeframe: str,
        indicators_config: list[dict[str, Any]],
        lookback_bars: int = 100,
        use_cache: bool = True,
    ) -> pd.DataFrame:
        """Compute multiple indicators on the same dataset.

        Args:
            symbol: Trading symbol
            timeframe: Timeframe
            indicators_config: List of indicator configs, each with:
                - name: Indicator name
                - params: Indicator parameters (dict)
            lookback_bars: Number of bars to fetch
            use_cache: Whether to use caching

        Returns:
            DataFrame with OHLCV data and all computed indicators

        Example:
            >>> indicators_config = [
            ...     {"name": "sma", "params": {"length": 20}},
            ...     {"name": "rsi", "params": {"length": 14}},
            ...     {"name": "macd", "params": {}},
            ... ]
            >>> df = await feature_engine.compute_multiple_indicators(
            ...     "SPY", "5min", indicators_config
            ... )
        """
        # Fetch bars once
        df = await self.get_bars(
            symbol=symbol, timeframe=timeframe, lookback_bars=lookback_bars
        )

        if df.empty:
            return df

        # Compute each indicator
        for config in indicators_config:
            indicator_name = config["name"]
            indicator_params = config.get("params", {})

            try:
                indicator_func = getattr(indicators, indicator_name)
                result = indicator_func(df, **indicator_params)

                # Add indicator to dataframe
                if isinstance(result, pd.Series):
                    df[indicator_name.upper()] = result
                elif isinstance(result, pd.DataFrame):
                    df = df.join(result)

            except AttributeError:
                logger.error(f"Unknown indicator: {indicator_name}")
                continue

        return df

    def clear_cache(self) -> None:
        """Clear all cached indicator data."""
        self._cache.clear()
        logger.info("Feature engine cache cleared")

    def get_cache_stats(self) -> dict[str, Any]:
        """Get cache statistics.

        Returns:
            Dictionary with cache stats
        """
        valid_entries = sum(1 for key in self._cache if self._is_cache_valid(key))
        return {
            "total_entries": len(self._cache),
            "valid_entries": valid_entries,
            "expired_entries": len(self._cache) - valid_entries,
            "ttl_seconds": self._cache_ttl_seconds,
        }
