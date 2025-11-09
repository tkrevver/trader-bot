"""Feature engineering for trend-following ML strategy.

Focused feature set (25 features) based on:
- EMA slopes across multiple timeframes
- ADX trend strength
- EMA alignment
- Bar reclaim patterns
- Price vs VWAP
"""

import warnings
import pandas as pd
import numpy as np
from app.utils import indicators

# Suppress FutureWarnings about pandas downcasting behavior
warnings.filterwarnings('ignore', category=FutureWarning, message='.*Downcasting object dtype.*')


class TrendFollowingFeatureEngineer:
    """
    Create focused trend-following features for ML models.

    Uses 5-min bars as primary timeframe with multi-timeframe slope indicators.
    Total: ~28 features (down from 140).
    """

    def __init__(
        self,
        df_5min: pd.DataFrame,
        df_1min: pd.DataFrame = None,
        df_15min: pd.DataFrame = None,
        df_30min: pd.DataFrame = None
    ):
        """
        Initialize with OHLCV dataframes for different timeframes.

        Args:
            df_5min: 5-minute OHLCV bars (primary execution timeframe)
            df_1min: 1-minute OHLCV bars (optional, for short-term slopes)
            df_15min: 15-minute OHLCV bars (optional, for medium-term slopes)
            df_30min: 30-minute OHLCV bars (optional, for long-term slopes)
        """
        self.df_5min = df_5min.copy()
        self.df_1min = df_1min.copy() if df_1min is not None else None
        self.df_15min = df_15min.copy() if df_15min is not None else None
        self.df_30min = df_30min.copy() if df_30min is not None else None

    def create_all_features(self) -> pd.DataFrame:
        """
        Create all trend-following features.

        Returns:
            DataFrame with 5-minute bars and all computed features
        """
        # Start with 5-min data (primary timeframe)
        result = self.df_5min.copy()

        # Ensure numeric columns for indicator calculation
        ohlcv_df = result[['open', 'high', 'low', 'close', 'volume']].copy()
        for col in ohlcv_df.columns:
            ohlcv_df[col] = pd.to_numeric(ohlcv_df[col], errors='coerce')

        # 1. EMA Slopes (16 features: 4 EMAs × 4 timeframes)
        result = self._add_ema_slopes(result)

        # 2. ADX Trend Strength (4 features: 4 timeframes)
        result = self._add_adx_features(result)

        # 3. EMA Alignment (4 features: 4 timeframes)
        result = self._add_ema_alignment_features(result)

        # 4. Bar Reclaim/Break Patterns (1 feature)
        result = self._add_bar_patterns(result)

        # 5. Price vs VWAP (1 feature)
        result = self._add_vwap_features(result)

        # 6. Time Features (2 features)
        result = self._add_time_features(result)

        return result

    def _add_ema_slopes(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Add EMA slope features for all timeframes.

        16 features: EMA2, EMA5, EMA10, EMA20 slopes for each timeframe
        """
        # 5-min timeframe slopes (primary)
        ohlcv_5min = self.df_5min[['open', 'high', 'low', 'close', 'volume']].copy()
        for col in ohlcv_5min.columns:
            ohlcv_5min[col] = pd.to_numeric(ohlcv_5min[col], errors='coerce')

        for ema_len in [2, 5, 10, 20]:
            # Calculate EMA first
            ema_series = indicators.ema(ohlcv_5min, length=ema_len)

            # Create temp df with EMA as 'close' column for slope calculation
            temp_df = pd.DataFrame({
                'open': ema_series,
                'high': ema_series,
                'low': ema_series,
                'close': ema_series,
                'volume': ohlcv_5min['volume']
            }, index=ohlcv_5min.index)

            # Fill NaN values before slope calculation (forward fill, then back fill for any remaining)
            temp_df = temp_df.infer_objects(copy=False).ffill().bfill().fillna(0)

            # Calculate slope of EMA (angle in degrees)
            df[f'ema{ema_len}_slope_5min'] = indicators.slope(temp_df, length=10, as_angle=True)

        # 1-min timeframe slopes (if available)
        if self.df_1min is not None:
            ohlcv_1min = self.df_1min[['open', 'high', 'low', 'close', 'volume']].copy()
            for col in ohlcv_1min.columns:
                ohlcv_1min[col] = pd.to_numeric(ohlcv_1min[col], errors='coerce')

            for ema_len in [2, 5, 10, 20]:
                ema_series = indicators.ema(ohlcv_1min, length=ema_len)
                temp_df = pd.DataFrame({
                    'open': ema_series,
                    'high': ema_series,
                    'low': ema_series,
                    'close': ema_series,
                    'volume': ohlcv_1min['volume']
                }, index=ohlcv_1min.index)

                # Fill NaN values before slope calculation
                temp_df = temp_df.infer_objects(copy=False).ffill().bfill().fillna(0)

                slope_1min = indicators.slope(temp_df, length=10, as_angle=True)

                # Align to 5-min bars (forward fill)
                df[f'ema{ema_len}_slope_1min'] = self._align_to_5min(slope_1min)
        else:
            # Fill with zeros if 1-min data not available
            for ema_len in [2, 5, 10, 20]:
                df[f'ema{ema_len}_slope_1min'] = 0

        # 15-min timeframe slopes (if available)
        if self.df_15min is not None:
            ohlcv_15min = self.df_15min[['open', 'high', 'low', 'close', 'volume']].copy()
            for col in ohlcv_15min.columns:
                ohlcv_15min[col] = pd.to_numeric(ohlcv_15min[col], errors='coerce')

            for ema_len in [2, 5, 10, 20]:
                ema_series = indicators.ema(ohlcv_15min, length=ema_len)
                temp_df = pd.DataFrame({
                    'open': ema_series,
                    'high': ema_series,
                    'low': ema_series,
                    'close': ema_series,
                    'volume': ohlcv_15min['volume']
                }, index=ohlcv_15min.index)

                # Fill NaN values before slope calculation
                temp_df = temp_df.infer_objects(copy=False).ffill().bfill().fillna(0)

                slope_15min = indicators.slope(temp_df, length=10, as_angle=True)

                # Align to 5-min bars (forward fill)
                df[f'ema{ema_len}_slope_15min'] = self._align_to_5min(slope_15min)
        else:
            for ema_len in [2, 5, 10, 20]:
                df[f'ema{ema_len}_slope_15min'] = 0

        # 30-min timeframe slopes (if available)
        if self.df_30min is not None:
            ohlcv_30min = self.df_30min[['open', 'high', 'low', 'close', 'volume']].copy()
            for col in ohlcv_30min.columns:
                ohlcv_30min[col] = pd.to_numeric(ohlcv_30min[col], errors='coerce')

            for ema_len in [2, 5, 10, 20]:
                ema_series = indicators.ema(ohlcv_30min, length=ema_len)
                temp_df = pd.DataFrame({
                    'open': ema_series,
                    'high': ema_series,
                    'low': ema_series,
                    'close': ema_series,
                    'volume': ohlcv_30min['volume']
                }, index=ohlcv_30min.index)

                # Fill NaN values before slope calculation
                temp_df = temp_df.infer_objects(copy=False).ffill().bfill().fillna(0)

                slope_30min = indicators.slope(temp_df, length=10, as_angle=True)

                # Align to 5-min bars (forward fill)
                df[f'ema{ema_len}_slope_30min'] = self._align_to_5min(slope_30min)
        else:
            for ema_len in [2, 5, 10, 20]:
                df[f'ema{ema_len}_slope_30min'] = 0

        return df

    def _add_adx_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Add ADX trend strength features for all timeframes.

        4 features: ADX value for each timeframe
        """
        # 5-min ADX
        ohlcv_5min = self.df_5min[['open', 'high', 'low', 'close', 'volume']].copy()
        for col in ohlcv_5min.columns:
            ohlcv_5min[col] = pd.to_numeric(ohlcv_5min[col], errors='coerce')

        adx_result = indicators.adx_trend_filter(ohlcv_5min, length=14, adx_threshold=25.0)
        df['adx_5min'] = adx_result['ADX'].fillna(25.0)

        # 1-min ADX
        if self.df_1min is not None:
            ohlcv_1min = self.df_1min[['open', 'high', 'low', 'close', 'volume']].copy()
            for col in ohlcv_1min.columns:
                ohlcv_1min[col] = pd.to_numeric(ohlcv_1min[col], errors='coerce')

            adx_result = indicators.adx_trend_filter(ohlcv_1min, length=14, adx_threshold=25.0)
            adx_1min = adx_result['ADX'].fillna(25.0)
            df['adx_1min'] = self._align_to_5min(adx_1min)
        else:
            df['adx_1min'] = 25.0

        # 15-min ADX
        if self.df_15min is not None:
            ohlcv_15min = self.df_15min[['open', 'high', 'low', 'close', 'volume']].copy()
            for col in ohlcv_15min.columns:
                ohlcv_15min[col] = pd.to_numeric(ohlcv_15min[col], errors='coerce')

            adx_result = indicators.adx_trend_filter(ohlcv_15min, length=14, adx_threshold=25.0)
            adx_15min = adx_result['ADX'].fillna(25.0)
            df['adx_15min'] = self._align_to_5min(adx_15min)
        else:
            df['adx_15min'] = 25.0

        # 30-min ADX
        if self.df_30min is not None:
            ohlcv_30min = self.df_30min[['open', 'high', 'low', 'close', 'volume']].copy()
            for col in ohlcv_30min.columns:
                ohlcv_30min[col] = pd.to_numeric(ohlcv_30min[col], errors='coerce')

            adx_result = indicators.adx_trend_filter(ohlcv_30min, length=14, adx_threshold=25.0)
            adx_30min = adx_result['ADX'].fillna(25.0)
            df['adx_30min'] = self._align_to_5min(adx_30min)
        else:
            df['adx_30min'] = 25.0

        return df

    def _add_ema_alignment_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Add EMA alignment strength features for all timeframes.

        4 features: alignment_strength for each timeframe
        """
        # 5-min alignment
        ohlcv_5min = self.df_5min[['open', 'high', 'low', 'close', 'volume']].copy()
        for col in ohlcv_5min.columns:
            ohlcv_5min[col] = pd.to_numeric(ohlcv_5min[col], errors='coerce')

        align_result = indicators.ema_alignment(ohlcv_5min, ema_lengths=[2, 5, 10, 20])
        df['is_bullish_aligned'] = align_result['is_bullish_aligned']
        df['is_bearish_aligned'] = align_result['is_bearish_aligned']
        df['alignment_strength_5min'] = align_result['alignment_strength'].fillna(0)

        # 1-min alignment
        if self.df_1min is not None:
            ohlcv_1min = self.df_1min[['open', 'high', 'low', 'close', 'volume']].copy()
            for col in ohlcv_1min.columns:
                ohlcv_1min[col] = pd.to_numeric(ohlcv_1min[col], errors='coerce')

            align_result = indicators.ema_alignment(ohlcv_1min, ema_lengths=[2, 5, 10, 20])
            alignment_1min = align_result['alignment_strength'].fillna(0)
            df['alignment_strength_1min'] = self._align_to_5min(alignment_1min)
        else:
            df['alignment_strength_1min'] = 0

        # 15-min alignment
        if self.df_15min is not None:
            ohlcv_15min = self.df_15min[['open', 'high', 'low', 'close', 'volume']].copy()
            for col in ohlcv_15min.columns:
                ohlcv_15min[col] = pd.to_numeric(ohlcv_15min[col], errors='coerce')

            align_result = indicators.ema_alignment(ohlcv_15min, ema_lengths=[2, 5, 10, 20])
            alignment_15min = align_result['alignment_strength'].fillna(0)
            df['alignment_strength_15min'] = self._align_to_5min(alignment_15min)
        else:
            df['alignment_strength_15min'] = 0

        # 30-min alignment
        if self.df_30min is not None:
            ohlcv_30min = self.df_30min[['open', 'high', 'low', 'close', 'volume']].copy()
            for col in ohlcv_30min.columns:
                ohlcv_30min[col] = pd.to_numeric(ohlcv_30min[col], errors='coerce')

            align_result = indicators.ema_alignment(ohlcv_30min, ema_lengths=[2, 5, 10, 20])
            alignment_30min = align_result['alignment_strength'].fillna(0)
            df['alignment_strength_30min'] = self._align_to_5min(alignment_30min)
        else:
            df['alignment_strength_30min'] = 0

        return df

    def _add_bar_patterns(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Add bar reclaim/break pattern features.

        1 feature: bar_reclaim (1 if reclaim up, -1 if break down, 0 otherwise)
        """
        # Calculate EMA20 for 5-min bars
        ohlcv_5min = self.df_5min[['open', 'high', 'low', 'close', 'volume']].copy()
        for col in ohlcv_5min.columns:
            ohlcv_5min[col] = pd.to_numeric(ohlcv_5min[col], errors='coerce')

        ema20 = indicators.ema(ohlcv_5min, length=20)

        # Bar reclaim: opens below EMA20, closes above
        reclaims_up = (df['open'] < ema20) & (df['close'] > ema20)

        # Bar break: opens above EMA20, closes below
        breaks_down = (df['open'] > ema20) & (df['close'] < ema20)

        df['bar_reclaim'] = 0
        df.loc[reclaims_up, 'bar_reclaim'] = 1
        df.loc[breaks_down, 'bar_reclaim'] = -1

        return df

    def _add_vwap_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Add VWAP-based features.

        1 feature: price_vs_vwap (percentage above/below VWAP)
        """
        # Use VWAP from source data if available, otherwise calculate it
        if 'vwap' in self.df_5min.columns:
            vwap_series = self.df_5min['vwap']
        else:
            ohlcv_5min = self.df_5min[['open', 'high', 'low', 'close', 'volume']].copy()
            for col in ohlcv_5min.columns:
                ohlcv_5min[col] = pd.to_numeric(ohlcv_5min[col], errors='coerce')

            # Set index to time if available for VWAP calculation
            if 'time' in self.df_5min.columns:
                ohlcv_5min.index = pd.to_datetime(self.df_5min['time'])

            vwap_series = indicators.vwap(ohlcv_5min)

        # Calculate percentage distance from VWAP
        df['vwap'] = vwap_series
        df['price_vs_vwap'] = ((df['close'] - vwap_series) / vwap_series * 100).fillna(0)

        return df

    def _add_time_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Add time-based features.

        2 features: hour, minutes_since_open
        """
        # Ensure time column is datetime
        if 'time' in df.columns:
            time_col = pd.to_datetime(df['time'])
        else:
            time_col = df.index
            # Ensure index is DatetimeIndex
            if not isinstance(time_col, pd.DatetimeIndex):
                time_col = pd.to_datetime(time_col)

        # Extract hour and minute (DatetimeIndex doesn't need .dt accessor)
        if isinstance(time_col, pd.DatetimeIndex):
            df['hour'] = time_col.hour
            hours = time_col.hour
            minutes = time_col.minute
        else:
            # Series needs .dt accessor
            df['hour'] = time_col.dt.hour
            hours = time_col.dt.hour
            minutes = time_col.dt.minute

        # Minutes since market open (9:30 AM ET = 570 minutes from midnight)
        market_open_minutes = 9 * 60 + 30
        df['minutes_since_open'] = hours * 60 + minutes - market_open_minutes
        df['minutes_since_open'] = df['minutes_since_open'].clip(lower=0)

        return df

    def _align_to_5min(self, series: pd.Series) -> pd.Series:
        """
        Align a series from another timeframe to 5-min bars using forward fill.

        Args:
            series: Series with datetime index

        Returns:
            Series aligned to 5-min bars
        """
        # Reindex to 5-min bars and forward fill
        aligned = series.reindex(self.df_5min.index, method='ffill')
        return aligned.fillna(0)

    def get_feature_names(self) -> list[str]:
        """
        Get list of all feature column names.

        Returns:
            List of feature column names (for X matrix)
        """
        features = []

        # EMA slopes (16 features)
        for timeframe in ['1min', '5min', '15min', '30min']:
            for ema_len in [2, 5, 10, 20]:
                features.append(f'ema{ema_len}_slope_{timeframe}')

        # ADX (4 features)
        for timeframe in ['1min', '5min', '15min', '30min']:
            features.append(f'adx_{timeframe}')

        # EMA alignment (4 features)
        for timeframe in ['1min', '5min', '15min', '30min']:
            features.append(f'alignment_strength_{timeframe}')

        # Bar pattern (1 feature)
        features.append('bar_reclaim')

        # VWAP (1 feature)
        features.append('price_vs_vwap')

        # Time (2 features)
        features.append('hour')
        features.append('minutes_since_open')

        return features
