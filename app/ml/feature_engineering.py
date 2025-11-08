"""Feature engineering for ML models with multi-timeframe support."""

import pandas as pd
import numpy as np
from app.utils import indicators


class FeatureEngineer:
    """
    Create features for ML models from OHLCV data.

    Supports multi-timeframe feature engineering:
    - 1-min indicators for fast signals
    - 5-min indicators for medium-term momentum
    - 15-min indicators for trend context
    - 30-min indicators for broader market structure
    """

    def __init__(self, df_1min: pd.DataFrame, df_5min: pd.DataFrame = None,
                 df_15min: pd.DataFrame = None, df_30min: pd.DataFrame = None):
        """
        Initialize with OHLCV dataframes for different timeframes.

        Args:
            df_1min: 1-minute OHLCV bars (required)
            df_5min: 5-minute OHLCV bars (optional)
            df_15min: 15-minute OHLCV bars (optional)
            df_30min: 30-minute OHLCV bars (optional)
        """
        self.df_1min = df_1min.copy()
        self.df_5min = df_5min.copy() if df_5min is not None else None
        self.df_15min = df_15min.copy() if df_15min is not None else None
        self.df_30min = df_30min.copy() if df_30min is not None else None

    def create_all_features(self) -> pd.DataFrame:
        """
        Create all features from all available timeframes.

        Returns:
            DataFrame with 1-minute bars and all computed features
        """
        # Start with 1-min data
        result = self.df_1min.copy()

        # Add 1-min features
        result = self._add_timeframe_features(result, self.df_1min, suffix='_1min')

        # Add 5-min features (aligned to 1-min timestamps)
        if self.df_5min is not None:
            result = self._align_and_merge(result, self.df_5min, suffix='_5min')

        # Add 15-min features
        if self.df_15min is not None:
            result = self._align_and_merge(result, self.df_15min, suffix='_15min')

        # Add 30-min features
        if self.df_30min is not None:
            result = self._align_and_merge(result, self.df_30min, suffix='_30min')

        # Add time-based features
        result = self._add_time_features(result)

        # Add derived features
        result = self._add_derived_features(result)

        return result

    def _add_timeframe_features(self, df: pd.DataFrame, source_df: pd.DataFrame,
                                 suffix: str) -> pd.DataFrame:
        """
        Add technical indicators for a specific timeframe.

        Args:
            df: Target dataframe to add features to
            source_df: Source dataframe to compute indicators from
            suffix: Suffix to add to feature names (e.g., '_1min')
        """
        # Create a copy with only numeric OHLCV columns for indicator calculation
        # This avoids numba issues with datetime columns
        ohlcv_df = source_df[['open', 'high', 'low', 'close', 'volume']].copy()

        # Ensure all columns are numeric (float64) to avoid numba/pandas-ta issues
        for col in ohlcv_df.columns:
            ohlcv_df[col] = pd.to_numeric(ohlcv_df[col], errors='coerce')

        # Trend indicators
        df[f'sma_10{suffix}'] = indicators.sma(ohlcv_df, length=10)
        df[f'sma_20{suffix}'] = indicators.sma(ohlcv_df, length=20)
        df[f'sma_50{suffix}'] = indicators.sma(ohlcv_df, length=50)
        df[f'ema_10{suffix}'] = indicators.ema(ohlcv_df, length=10)
        df[f'ema_20{suffix}'] = indicators.ema(ohlcv_df, length=20)
        df[f'ema_50{suffix}'] = indicators.ema(ohlcv_df, length=50)

        # MACD
        macd_result = indicators.macd(ohlcv_df)
        if macd_result is not None and not macd_result.empty:
            df[f'macd{suffix}'] = macd_result['MACD_12_26_9']
            df[f'macd_signal{suffix}'] = macd_result['MACDs_12_26_9']
            df[f'macd_hist{suffix}'] = macd_result['MACDh_12_26_9']
        else:
            df[f'macd{suffix}'] = 0
            df[f'macd_signal{suffix}'] = 0
            df[f'macd_hist{suffix}'] = 0

        # Momentum indicators
        df[f'rsi_14{suffix}'] = indicators.rsi(ohlcv_df, length=14)
        df[f'rsi_21{suffix}'] = indicators.rsi(ohlcv_df, length=21)

        stoch = indicators.stoch(ohlcv_df)
        if stoch is not None and not stoch.empty:
            df[f'stoch_k{suffix}'] = stoch['STOCHk_14_3_3']
            df[f'stoch_d{suffix}'] = stoch['STOCHd_14_3_3']
        else:
            df[f'stoch_k{suffix}'] = 50
            df[f'stoch_d{suffix}'] = 50

        df[f'williams_r{suffix}'] = indicators.williams_r(ohlcv_df, length=14)

        # Volatility indicators
        df[f'atr_14{suffix}'] = indicators.atr(ohlcv_df, length=14)
        df[f'atr_20{suffix}'] = indicators.atr(ohlcv_df, length=20)

        bbands = indicators.bbands(ohlcv_df)
        if bbands is not None and not bbands.empty:
            df[f'bbands_upper{suffix}'] = bbands['BBU_20_2.0_2.0']
            df[f'bbands_middle{suffix}'] = bbands['BBM_20_2.0_2.0']
            df[f'bbands_lower{suffix}'] = bbands['BBL_20_2.0_2.0']
            df[f'bbands_width{suffix}'] = bbands['BBB_20_2.0_2.0']  # Bandwidth is already calculated
            df[f'bbands_pct_b{suffix}'] = bbands['BBP_20_2.0_2.0']  # %B is already calculated
        else:
            # Set to neutral values if indicator fails
            df[f'bbands_upper{suffix}'] = ohlcv_df['close']
            df[f'bbands_middle{suffix}'] = ohlcv_df['close']
            df[f'bbands_lower{suffix}'] = ohlcv_df['close']
            df[f'bbands_width{suffix}'] = 0
            df[f'bbands_pct_b{suffix}'] = 0.5

        # Volume indicators
        df[f'volume_sma_20{suffix}'] = ohlcv_df['volume'].rolling(20).mean()
        df[f'volume_ratio{suffix}'] = ohlcv_df['volume'] / df[f'volume_sma_20{suffix}']

        # Price-based features
        df[f'returns{suffix}'] = ohlcv_df['close'].pct_change()
        df[f'log_returns{suffix}'] = np.log(ohlcv_df['close'] / ohlcv_df['close'].shift(1))
        df[f'high_low_ratio{suffix}'] = ohlcv_df['high'] / ohlcv_df['low']
        df[f'close_open_ratio{suffix}'] = ohlcv_df['close'] / ohlcv_df['open']

        # Price to indicator ratios
        df[f'price_to_sma20{suffix}'] = ohlcv_df['close'] / df[f'sma_20{suffix}']

        if 'vwap' in source_df.columns:
            df[f'price_to_vwap{suffix}'] = source_df['close'] / source_df['vwap']

        # Trend strength (ADX)
        adx_result = indicators.adx(ohlcv_df)
        if adx_result is not None and not adx_result.empty and 'ADX_14' in adx_result.columns:
            df[f'adx{suffix}'] = adx_result['ADX_14']
        else:
            df[f'adx{suffix}'] = 25

        return df

    def _align_and_merge(self, df_1min: pd.DataFrame, df_higher: pd.DataFrame,
                         suffix: str) -> pd.DataFrame:
        """
        Align higher timeframe features to 1-minute bars and merge.

        Uses forward-fill to propagate higher timeframe values to 1-min bars.

        Args:
            df_1min: 1-minute dataframe
            df_higher: Higher timeframe dataframe (5min, 15min, 30min)
            suffix: Suffix for feature names
        """
        # Compute features for higher timeframe
        # Start with time column from df_higher
        df_features = df_higher[['time']].copy()
        df_features = self._add_timeframe_features(df_features, df_higher, suffix)

        # Merge with 1-min data using forward-fill (asof merge)
        # This ensures each 1-min bar has the most recent higher timeframe values
        df_1min = df_1min.sort_values('time')
        df_features = df_features.sort_values('time')

        # Merge on time, forward-filling higher timeframe values
        merged = pd.merge_asof(
            df_1min,
            df_features,
            on='time',
            direction='backward'  # Use most recent higher timeframe value
        )

        return merged

    def _add_time_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add time-based features."""
        df['hour'] = df['time'].dt.hour
        df['minute'] = df['time'].dt.minute
        df['day_of_week'] = df['time'].dt.dayofweek

        # Binary flags for market periods
        df['is_first_30min'] = ((df['hour'] == 9) & (df['minute'] < 60)).astype(int)
        df['is_first_hour'] = (df['hour'] == 9).astype(int)
        df['is_last_hour'] = (df['hour'] == 15).astype(int)
        df['is_last_30min'] = ((df['hour'] == 15) & (df['minute'] >= 30)).astype(int)

        df['is_monday'] = (df['day_of_week'] == 0).astype(int)
        df['is_friday'] = (df['day_of_week'] == 4).astype(int)

        # Minutes since market open (9:30 AM)
        market_open_minutes = 9 * 60 + 30
        df['minutes_since_open'] = df['hour'] * 60 + df['minute'] - market_open_minutes

        return df

    def _add_derived_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Add derived features (interactions, lags, etc.).

        These are features derived from the base indicators.
        """
        # Lagged features (1-min timeframe only to keep feature count manageable)
        if 'close' in df.columns:
            df['close_lag_1'] = df['close'].shift(1)
            df['close_lag_5'] = df['close'].shift(5)

        if 'rsi_14_1min' in df.columns:
            df['rsi_14_1min_lag_1'] = df['rsi_14_1min'].shift(1)
            df['rsi_14_1min_diff'] = df['rsi_14_1min'] - df['rsi_14_1min_lag_1']

        if 'volume' in df.columns:
            df['volume_lag_1'] = df['volume'].shift(1)

        # Statistical features (1-min)
        if 'close' in df.columns:
            df['rolling_mean_30'] = df['close'].rolling(30).mean()
            df['rolling_std_30'] = df['close'].rolling(30).std()
            df['zscore_30'] = (df['close'] - df['rolling_mean_30']) / df['rolling_std_30']

        # Interaction features (examples)
        if 'rsi_14_1min' in df.columns and 'volume_ratio_1min' in df.columns:
            df['rsi_volume_interaction'] = df['rsi_14_1min'] * df['volume_ratio_1min']

        # Trend alignment across timeframes
        if all(col in df.columns for col in ['price_to_sma20_1min', 'price_to_sma20_5min', 'price_to_sma20_15min']):
            df['trend_alignment'] = (
                (df['price_to_sma20_1min'] > 1) &
                (df['price_to_sma20_5min'] > 1) &
                (df['price_to_sma20_15min'] > 1)
            ).astype(int)

        return df

    def get_feature_columns(self, exclude_ohlcv: bool = True) -> list:
        """
        Get list of feature column names.

        Args:
            exclude_ohlcv: If True, exclude raw OHLCV columns

        Returns:
            List of feature column names
        """
        exclude_cols = ['time', 'symbol', 'label']

        if exclude_ohlcv:
            exclude_cols.extend(['open', 'high', 'low', 'close', 'volume', 'vwap', 'trades'])

        # Get all columns except excluded ones
        df = self.create_all_features()
        feature_cols = [col for col in df.columns if col not in exclude_cols]

        return feature_cols
