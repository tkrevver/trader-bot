"""Labeling strategies for supervised learning."""

import pandas as pd
import numpy as np
from typing import Optional


class Labeler:
    """Create labels for supervised learning from OHLCV data."""

    @staticmethod
    def triple_barrier(
        df: pd.DataFrame,
        profit_target_pct: float = 0.5,
        stop_loss_pct: float = 0.3,
        time_limit_bars: int = 30
    ) -> pd.Series:
        """
        Triple Barrier Method labeling.

        Labels each bar based on which barrier is hit first:
        - Upper barrier (profit target): BUY (1)
        - Lower barrier (stop loss): SELL (-1)
        - Time limit expired: HOLD (0)

        This prevents look-ahead bias and mimics realistic trading with
        profit targets and stop losses.

        Args:
            df: DataFrame with OHLCV data
            profit_target_pct: Profit target as percentage (e.g., 0.5 = 0.5%)
            stop_loss_pct: Stop loss as percentage (e.g., 0.3 = 0.3%)
            time_limit_bars: Maximum number of bars to wait

        Returns:
            Series with labels: 1 (BUY), 0 (HOLD), -1 (SELL)

        Example:
            If entry at $100:
            - Upper barrier: $100.50 (0.5% profit)
            - Lower barrier: $99.70 (0.3% loss)
            - Time limit: 30 bars (30 minutes for 1-min data)
        """
        labels = []

        for i in range(len(df) - time_limit_bars):
            entry_price = df['close'].iloc[i]
            upper = entry_price * (1 + profit_target_pct / 100)
            lower = entry_price * (1 - stop_loss_pct / 100)

            # Look ahead up to time_limit_bars
            future_highs = df['high'].iloc[i+1:i+1+time_limit_bars]
            future_lows = df['low'].iloc[i+1:i+1+time_limit_bars]

            # Find first bar that hits each barrier
            hit_upper_idx = None
            hit_lower_idx = None

            for j, (high, low) in enumerate(zip(future_highs, future_lows)):
                if hit_upper_idx is None and high >= upper:
                    hit_upper_idx = j
                if hit_lower_idx is None and low <= lower:
                    hit_lower_idx = j

                # Stop if both hit (rare but possible)
                if hit_upper_idx is not None and hit_lower_idx is not None:
                    break

            # Determine label based on which barrier hit first
            if hit_upper_idx is not None and (hit_lower_idx is None or hit_upper_idx < hit_lower_idx):
                labels.append(1)  # BUY - profit target hit first
            elif hit_lower_idx is not None and (hit_upper_idx is None or hit_lower_idx < hit_upper_idx):
                labels.append(-1)  # SELL - stop loss hit first
            else:
                labels.append(0)  # HOLD - neither barrier hit within time limit

        # Pad with NaN for last time_limit_bars (can't look ahead)
        labels.extend([np.nan] * time_limit_bars)

        return pd.Series(labels, index=df.index, name='label')

    @staticmethod
    def forward_returns(
        df: pd.DataFrame,
        periods: int = 30,
        quantiles: int = 3
    ) -> pd.Series:
        """
        Label based on forward returns quantiles.

        Simpler than Triple Barrier but doesn't account for risk.

        Args:
            df: DataFrame with OHLCV data
            periods: Number of bars to look ahead (e.g., 30 = next 30 minutes)
            quantiles: Number of quantiles to split into (3 = terciles)

        Returns:
            Series with labels based on quantile ranking

        Example (quantiles=3):
            Bottom 33%: -1 (SELL)
            Middle 33%: 0 (HOLD)
            Top 33%: 1 (BUY)
        """
        # Calculate forward returns
        forward_return = (df['close'].shift(-periods) - df['close']) / df['close']

        # Label based on quantiles
        try:
            labels = pd.qcut(
                forward_return,
                q=quantiles,
                labels=list(range(-(quantiles//2), quantiles//2 + 1)),
                duplicates='drop'
            )
        except ValueError:
            # If not enough unique values for quantiles, use simple thresholds
            labels = pd.cut(
                forward_return,
                bins=[-np.inf, -0.001, 0.001, np.inf],
                labels=[-1, 0, 1]
            )

        return labels

    @staticmethod
    def trend_following(
        df: pd.DataFrame,
        ema_period: int = 20,
        threshold_pct: float = 0.2
    ) -> pd.Series:
        """
        Label based on trend following using EMA.

        Args:
            df: DataFrame with OHLCV data
            ema_period: Period for EMA calculation
            threshold_pct: Percentage above/below EMA for signal

        Returns:
            Series with labels: 1 (uptrend), 0 (sideways), -1 (downtrend)
        """
        ema = df['close'].ewm(span=ema_period, adjust=False).mean()
        threshold = threshold_pct / 100

        labels = np.where(
            df['close'] > ema * (1 + threshold),
            1,  # BUY (uptrend)
            np.where(
                df['close'] < ema * (1 - threshold),
                -1,  # SELL (downtrend)
                0  # HOLD (sideways)
            )
        )

        return pd.Series(labels, index=df.index, name='label')

    @staticmethod
    def trend_following_labels(
        df: pd.DataFrame,
        ema_period: int = 20,
        min_profit_pct: float = 0.1
    ) -> pd.Series:
        """
        Label based on trend-following with EMA exits (NO entry criteria).

        Labels every bar based on forward trend profitability:
        - Look forward to find when price crosses EMA20
        - LONG: If going up is profitable (price rises ≥min_profit_pct before crossing below EMA20)
        - SHORT: If going down is profitable (price falls ≥min_profit_pct before crossing above EMA20)
        - HOLD: If neither direction is profitable

        This creates MORE training data by not filtering on entry conditions.
        Entry criteria (bar reclaim, alignment, VWAP) are handled in the STRATEGY, not labels.

        Exit detection:
        - LONG exit: Close below EMA20
        - SHORT exit: Close above EMA20

        Args:
            df: DataFrame with OHLCV data (only 'close' required)
            ema_period: EMA period for entry/exit (default: 20)
            min_profit_pct: Minimum profit to label as BUY/SELL (default: 0.1%)

        Returns:
            Series with labels: 1 (BUY), -1 (SELL), 0 (HOLD)
        """
        from app.utils.indicators import ema

        labels = []

        # Calculate EMA20 for exit detection
        ema20 = ema(df, length=ema_period, column='close')

        # Check required columns
        if 'close' not in df.columns:
            raise ValueError("Missing required column: 'close'")

        for i in range(len(df) - 1):  # -1 because we need at least 1 forward bar
            entry_price = df['close'].iloc[i]
            current_ema20 = ema20.iloc[i]

            # Look forward to find both potential exits
            long_exit_price = None
            short_exit_price = None

            # Look ahead (up to 100 bars or end of data)
            max_lookback = min(100, len(df) - i - 1)

            for j in range(1, max_lookback + 1):
                future_close = df['close'].iloc[i + j]
                future_ema20 = ema20.iloc[i + j]

                # LONG exit: First time close below EMA20
                if long_exit_price is None and future_close < future_ema20:
                    long_exit_price = future_close

                # SHORT exit: First time close above EMA20
                if short_exit_price is None and future_close > future_ema20:
                    short_exit_price = future_close

                # Stop if both exits found
                if long_exit_price is not None and short_exit_price is not None:
                    break

            # Calculate potential P&L for both directions
            long_pnl_pct = ((long_exit_price - entry_price) / entry_price * 100) if long_exit_price else -999
            short_pnl_pct = ((entry_price - short_exit_price) / entry_price * 100) if short_exit_price else -999

            # Label based on which direction is profitable
            if long_pnl_pct >= min_profit_pct and long_pnl_pct > short_pnl_pct:
                labels.append(1)  # BUY - long is profitable
            elif short_pnl_pct >= min_profit_pct and short_pnl_pct > long_pnl_pct:
                labels.append(-1)  # SELL - short is profitable
            else:
                labels.append(0)  # HOLD - neither is profitable enough

        # Pad last bar with HOLD (can't look ahead)
        labels.append(0)

        return pd.Series(labels, index=df.index, name='label')

    @staticmethod
    def analyze_label_distribution(labels: pd.Series) -> dict:
        """
        Analyze label distribution to check for class imbalance.

        Args:
            labels: Series of labels

        Returns:
            Dictionary with distribution statistics
        """
        # Remove NaN
        valid_labels = labels.dropna()

        # Count each class
        counts = valid_labels.value_counts().sort_index()
        percentages = (counts / len(valid_labels) * 100).round(2)

        # Calculate imbalance ratio
        max_count = counts.max()
        min_count = counts.min()
        imbalance_ratio = max_count / min_count if min_count > 0 else np.inf

        return {
            'total_samples': len(valid_labels),
            'counts': counts.to_dict(),
            'percentages': percentages.to_dict(),
            'imbalance_ratio': imbalance_ratio,
            'is_balanced': imbalance_ratio < 2.0  # Considered balanced if ratio < 2:1
        }

    @staticmethod
    def get_recommended_class_weights(labels: pd.Series) -> dict:
        """
        Calculate recommended class weights for imbalanced datasets.

        Uses sklearn's balanced weighting formula:
        weight = n_samples / (n_classes * n_samples_per_class)

        Args:
            labels: Series of labels

        Returns:
            Dictionary mapping class labels to weights
        """
        valid_labels = labels.dropna()
        counts = valid_labels.value_counts()

        n_samples = len(valid_labels)
        n_classes = len(counts)

        weights = {}
        for label, count in counts.items():
            weights[int(label)] = n_samples / (n_classes * count)

        return weights
