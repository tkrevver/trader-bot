"""Trend-Following ML Strategy using XGBoost classifier.

Strategy Rules:
1. Load pre-trained XGBoost trend-following model
2. Compute focused trend-following features on every 5-minute bar
3. Make predictions: BUY (1), HOLD (0), SELL (-1)
4. Enter LONG when model predicts BUY and all entry criteria met
5. Enter SHORT when model predicts SELL and all entry criteria met
6. Exit LONG when price closes below EMA20 OR EOD (3:55 PM)
7. Exit SHORT when price closes above EMA20 OR EOD (3:55 PM)

Entry Criteria:
- LONG: Bullish EMA alignment + strong slope + reclaim EMA20 + price > VWAP
- SHORT: Bearish EMA alignment + strong slope + break EMA20 + price < VWAP

Technical Details:
- Executes on 5-min timeframe
- Uses 1-min, 5-min, 15-min, 30-min bars for multi-timeframe slope features
- Features: ~28 focused trend-following features (vs 140 in original ML strategy)
- Model trained with trend-following labels (not Triple Barrier)
"""

import json
import pickle
from datetime import datetime, time
from pathlib import Path
from typing import Any, Optional

import pandas as pd
import numpy as np
import pytz

from app.models.signals import SignalCreate
from app.strategies.base import Strategy, StrategyMetadata
from app.ml.trend_following_features import TrendFollowingFeatureEngineer
from app.utils import indicators
from app.config import settings


class TrendFollowingMLStrategy(Strategy):
    """Trend-following ML-based trading strategy using XGBoost."""

    def __init__(self, config: Optional[dict[str, Any]] = None):
        """Initialize trend-following ML strategy.

        Args:
            config: Strategy configuration with keys:
                - model_path: Path to trained model file (default: models/xgboost_spy_trend_following.pkl)
                - position_size: Number of shares to trade (default: 10)
                - confidence_threshold: Min probability to take signal (default: 0.6)
                - require_all_timeframes: Require all 4 timeframes (default: True)
                - max_bars_buffer: Max bars to keep in memory (default: 200)
        """
        super().__init__(config)
        self.model = None
        self.feature_columns = None
        self.feature_engineer = None

        # Buffers to store recent bars for each timeframe
        self.bars_5min = {}  # symbol -> DataFrame (primary)
        self.bars_1min = {}
        self.bars_15min = {}
        self.bars_30min = {}

    def get_metadata(self) -> StrategyMetadata:
        """Return strategy metadata."""
        return StrategyMetadata(
            name="trend_following_ml_strategy",
            description=(
                "Trend-following ML strategy using XGBoost classifier. "
                "Predicts BUY/SELL/HOLD based on EMA slopes, alignment, and trend strength. "
                "Exits when price crosses EMA20 in opposite direction. "
                "Executes on 5-min timeframe with multi-timeframe features."
            ),
            version="1.0.0",
            author="Trader Bot ML",
            symbols=["SPY"],
            timeframes=["1min", "5min", "15min", "30min"],
            parameters={
                "model_path": "models/xgboost_spy_trend_following.pkl",
                "position_size": 10,
                "confidence_threshold": 0.6,
                "require_all_timeframes": True,
                "max_bars_buffer": 200,
            },
        )

    def validate_parameters(self) -> None:
        """Validate configuration parameters."""
        if "position_size" in self.config:
            if self.config["position_size"] <= 0:
                raise ValueError("position_size must be positive")

        if "confidence_threshold" in self.config:
            threshold = self.config["confidence_threshold"]
            if not (0.0 <= threshold <= 1.0):
                raise ValueError("confidence_threshold must be between 0 and 1")

    def _get_config_value(self, key: str, default: Any) -> Any:
        """Get configuration value with fallback to metadata default."""
        metadata = self.get_metadata()
        return self.config.get(key, metadata.parameters.get(key, default))

    def on_start(self) -> None:
        """Load model and feature columns on strategy start."""
        model_path = self._get_config_value("model_path", "models/xgboost_spy_trend_following.pkl")

        # Load model
        model_file = Path(model_path)
        if not model_file.exists():
            raise FileNotFoundError(f"Model file not found: {model_path}")

        with open(model_file, "rb") as f:
            self.model = pickle.load(f)

        print(f"✓ Loaded XGBoost trend-following model from {model_path}")

        # Load feature columns
        feature_cols_path = Path(model_path).parent / "trend_following_feature_columns.json"
        if not feature_cols_path.exists():
            raise FileNotFoundError(f"Feature columns file not found: {feature_cols_path}")

        with open(feature_cols_path, "r") as f:
            data = json.load(f)
            # Handle both dict and list formats
            if isinstance(data, dict) and 'features' in data:
                self.feature_columns = data['features']
            elif isinstance(data, list):
                self.feature_columns = data
            else:
                raise ValueError(f"Unexpected feature columns format: {type(data)}")

        print(f"✓ Loaded {len(self.feature_columns)} feature columns")
        print(f"  Expected features: {len(self.feature_columns)}")

    def on_bar(self, symbol: str, timeframe: str, bar: pd.Series, bars: pd.DataFrame) -> None:
        """Process new market data bar.

        Args:
            symbol: Trading symbol
            timeframe: Bar timeframe (1min, 5min, 15min, or 30min)
            bar: Latest bar data
            bars: Historical bars including the latest
        """
        max_bars = self._get_config_value("max_bars_buffer", 200)

        # Store bars in appropriate buffer (keep last N bars)
        if timeframe == "5min":
            self.bars_5min[symbol] = bars.tail(max_bars).copy()
        elif timeframe == "1min":
            self.bars_1min[symbol] = bars.tail(max_bars).copy()
        elif timeframe == "15min":
            self.bars_15min[symbol] = bars.tail(max_bars).copy()
        elif timeframe == "30min":
            self.bars_30min[symbol] = bars.tail(max_bars).copy()

    def generate_signals(self, symbol: str) -> list[SignalCreate]:
        """Generate trading signals based on ML model predictions.

        Args:
            symbol: Trading symbol

        Returns:
            List of trading signals
        """
        signals = []
        state = self.get_state(symbol)

        # Check if we have all required timeframes
        require_all = self._get_config_value("require_all_timeframes", True)
        if require_all:
            if (symbol not in self.bars_5min or
                symbol not in self.bars_1min or
                symbol not in self.bars_15min or
                symbol not in self.bars_30min):
                return signals

        # Get 5-min bars (primary timeframe)
        if symbol not in self.bars_5min or len(self.bars_5min[symbol]) == 0:
            return signals

        bars_5min = self.bars_5min[symbol]
        current_bar = bars_5min.iloc[-1]
        current_time = current_bar.get('time', bars_5min.index[-1])
        if isinstance(current_time, str):
            current_time = pd.to_datetime(current_time)

        # Convert to ET timezone
        if current_time.tzinfo is None:
            current_time = pytz.utc.localize(current_time)
        et_tz = pytz.timezone(settings.timezone)
        current_time = current_time.astimezone(et_tz)

        # Check for EOD exit (3:55 PM ET)
        if current_time.hour == 15 and current_time.minute >= 55:
            if state.in_position:
                signals.append(
                    SignalCreate(
                        strategy_name=self.get_metadata().name,
                        symbol=symbol,
                        signal_type="SELL",
                        price=float(current_bar['close']),
                        quantity=state.position_size,
                        confidence=1.0,
                        metadata={"reason": "EOD exit (3:55 PM)"}
                    )
                )
            return signals

        # Check for EMA20 exit
        if state.in_position:
            # Calculate EMA20 on 5-min bars
            ohlcv_5min = bars_5min[['open', 'high', 'low', 'close', 'volume']].copy()
            for col in ohlcv_5min.columns:
                ohlcv_5min[col] = pd.to_numeric(ohlcv_5min[col], errors='coerce')

            ema20 = indicators.ema(ohlcv_5min, length=20)
            current_close = float(current_bar['close'])
            current_ema20 = float(ema20.iloc[-1])

            # LONG exit: Close below EMA20
            if state.position_side == "LONG" and current_close < current_ema20:
                signals.append(
                    SignalCreate(
                        strategy_name=self.get_metadata().name,
                        symbol=symbol,
                        signal_type="SELL",
                        price=current_close,
                        quantity=state.position_size,
                        confidence=1.0,
                        metadata={"reason": "LONG exit: price below EMA20"}
                    )
                )
                return signals

            # SHORT exit: Close above EMA20
            if state.position_side == "SHORT" and current_close > current_ema20:
                signals.append(
                    SignalCreate(
                        strategy_name=self.get_metadata().name,
                        symbol=symbol,
                        signal_type="BUY",  # Cover short
                        price=current_close,
                        quantity=state.position_size,
                        confidence=1.0,
                        metadata={"reason": "SHORT exit: price above EMA20"}
                    )
                )
                return signals

        # Don't enter new positions if already in one
        if state.in_position:
            return signals

        # Compute features
        try:
            df_5min = self.bars_5min.get(symbol)
            df_1min = self.bars_1min.get(symbol) if require_all else None
            df_15min = self.bars_15min.get(symbol) if require_all else None
            df_30min = self.bars_30min.get(symbol) if require_all else None

            # Create feature engineer
            engineer = TrendFollowingFeatureEngineer(
                df_5min=df_5min,
                df_1min=df_1min,
                df_15min=df_15min,
                df_30min=df_30min
            )

            # Generate features
            df_features = engineer.create_all_features()

            # Get latest features
            if len(df_features) == 0:
                return signals

            latest_features = df_features.iloc[-1]

            # PRE-FILTER: Only trade on bar reclaim/break (entry requirement)
            # bar_reclaim: 1 = reclaim up, -1 = break down, 0 = neither
            bar_reclaim = latest_features.get('bar_reclaim', 0)
            if bar_reclaim == 0:
                # No bar reclaim or break - skip this bar
                return signals

            # Extract feature values in correct order
            X = []
            for col in self.feature_columns:
                if col in latest_features:
                    X.append(float(latest_features[col]))
                else:
                    # Missing feature - use 0 as default
                    X.append(0.0)

            X = np.array(X).reshape(1, -1)

            # Make prediction
            prediction = self.model.predict(X)[0] - 1  # Convert from 0,1,2 to -1,0,1
            probabilities = self.model.predict_proba(X)[0]
            max_prob = probabilities.max()

            # Apply confidence threshold
            confidence_threshold = self._get_config_value("confidence_threshold", 0.6)
            if max_prob < confidence_threshold:
                return signals

            # ENTRY FILTER: Only enter if bar_reclaim matches model prediction
            # This enforces: reclaim up (1) must have BUY prediction (1)
            #                break down (-1) must have SELL prediction (-1)
            if bar_reclaim == 1 and prediction != 1:
                return signals  # Reclaim up but model doesn't predict BUY
            if bar_reclaim == -1 and prediction != -1:
                return signals  # Break down but model doesn't predict SELL

            # Generate signals (bar_reclaim matches prediction)
            position_size = self._get_config_value("position_size", 10)
            current_price = float(current_bar['close'])

            if prediction == 1 and bar_reclaim == 1:  # BUY signal + reclaim up
                signals.append(
                    SignalCreate(
                        strategy_name=self.get_metadata().name,
                        symbol=symbol,
                        signal_type="BUY",
                        price=current_price,
                        quantity=position_size,
                        confidence=float(max_prob),
                        metadata={
                            "prediction": "BUY",
                            "probability": float(max_prob),
                            "model": "trend_following_xgboost"
                        }
                    )
                )
            elif prediction == -1 and bar_reclaim == -1:  # SELL signal + break down
                signals.append(
                    SignalCreate(
                        strategy_name=self.get_metadata().name,
                        symbol=symbol,
                        signal_type="SELL",
                        price=current_price,
                        quantity=position_size,
                        confidence=float(max_prob),
                        metadata={
                            "prediction": "SELL",
                            "probability": float(max_prob),
                            "model": "trend_following_xgboost",
                            "bar_reclaim": "break_down"
                        }
                    )
                )

        except Exception as e:
            print(f"Error generating signals: {e}")
            import traceback
            traceback.print_exc()

        return signals
