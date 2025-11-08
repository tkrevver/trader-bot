"""Machine Learning Strategy using XGBoost classifier.

Strategy Rules:
1. Load pre-trained XGBoost model
2. Compute multi-timeframe features on every 1-minute bar
3. Make predictions: BUY (1), HOLD (0), SELL (-1)
4. Generate trading signals based on predictions
5. Optional: Apply confidence threshold to filter weak signals

Technical Details:
- Uses 1-min, 5-min, 15-min, 30-min bars for feature computation
- Requires all 4 timeframes to be available
- Features must match training data exactly (140 features)
- Model outputs class probabilities for confidence filtering
"""

import json
import pickle
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import pandas as pd
import numpy as np

from app.models.signals import SignalCreate
from app.strategies.base import Strategy, StrategyMetadata
from app.ml.feature_engineering import FeatureEngineer


class MLStrategy(Strategy):
    """ML-based trading strategy using XGBoost."""

    def __init__(self, config: Optional[dict[str, Any]] = None):
        """Initialize ML strategy.

        Args:
            config: Strategy configuration with keys:
                - model_path: Path to trained model file (default: models/xgboost_spy_latest.pkl)
                - position_size: Number of shares to trade (default: 10)
                - confidence_threshold: Min probability to take signal (default: 0.6)
                - require_all_timeframes: Require all 4 timeframes (default: True)
        """
        super().__init__(config)
        self.model = None
        self.feature_columns = None
        self.feature_engineer = None

        # Buffers to store recent bars for each timeframe
        self.bars_1min = {}  # symbol -> DataFrame
        self.bars_5min = {}
        self.bars_15min = {}
        self.bars_30min = {}

    def get_metadata(self) -> StrategyMetadata:
        """Return strategy metadata."""
        return StrategyMetadata(
            name="ml_strategy",
            description=(
                "Machine learning strategy using XGBoost classifier. "
                "Predicts BUY/SELL/HOLD signals using multi-timeframe features. "
                "Trained on Triple Barrier Method labels."
            ),
            version="1.0.0",
            author="Trader Bot ML",
            symbols=["SPY"],
            timeframes=["1min", "5min", "15min", "30min"],
            parameters={
                "model_path": "models/xgboost_spy_latest.pkl",
                "position_size": 10,
                "confidence_threshold": 0.6,
                "require_all_timeframes": True,
                "max_bars_buffer": 100,  # Keep last N bars for feature computation
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

    def on_start(self) -> None:
        """Load model and feature columns on strategy start."""
        model_path = self._get_config_value("model_path", "models/xgboost_spy_latest.pkl")

        # Load model
        model_file = Path(model_path)
        if not model_file.exists():
            raise FileNotFoundError(f"Model file not found: {model_path}")

        with open(model_file, "rb") as f:
            self.model = pickle.load(f)

        print(f"✓ Loaded XGBoost model from {model_path}")

        # Load feature columns
        feature_cols_file = Path("models/feature_columns.json")
        if not feature_cols_file.exists():
            raise FileNotFoundError("Feature columns file not found: models/feature_columns.json")

        with open(feature_cols_file, "r") as f:
            data = json.load(f)
            # Handle both list format and dict format with 'features' key
            if isinstance(data, dict) and 'features' in data:
                self.feature_columns = data['features']
            elif isinstance(data, list):
                self.feature_columns = data
            else:
                raise ValueError(f"Unexpected format in feature_columns.json: {type(data)}")

        print(f"✓ Loaded {len(self.feature_columns)} feature columns")

    def _get_config_value(self, key: str, default: Any) -> Any:
        """Get configuration value with fallback to metadata default."""
        metadata = self.get_metadata()
        return self.config.get(key, metadata.parameters.get(key, default))

    def on_bar(
        self,
        symbol: str,
        timeframe: str,
        bar: pd.Series,
        bars: pd.DataFrame,
    ) -> None:
        """Process new market data bar.

        Args:
            symbol: Trading symbol
            timeframe: Bar timeframe (1min, 5min, 15min, 30min)
            bar: Current bar
            bars: Historical bars including current
        """
        # Store bars in appropriate buffer
        max_buffer = self._get_config_value("max_bars_buffer", 100)

        # Make a copy and ensure 'time' is a column, not index
        bars_copy = bars.tail(max_buffer).copy()
        if 'time' not in bars_copy.columns and bars_copy.index.name == 'time':
            bars_copy = bars_copy.reset_index()

        if timeframe == "1min":
            self.bars_1min[symbol] = bars_copy
        elif timeframe == "5min":
            self.bars_5min[symbol] = bars_copy
        elif timeframe == "15min":
            self.bars_15min[symbol] = bars_copy
        elif timeframe == "30min":
            self.bars_30min[symbol] = bars_copy

    def generate_signals(self, symbol: str) -> list[SignalCreate]:
        """Generate trading signals based on ML predictions.

        Args:
            symbol: Trading symbol

        Returns:
            List of SignalCreate objects (entry/exit signals)
        """
        signals = []
        state = self.get_state(symbol)

        # Check for end-of-day exit first
        if symbol in self.bars_1min:
            df_1min = self.bars_1min[symbol]
            if len(df_1min) > 0:
                current_time = df_1min.iloc[-1]['time']
                current_price = df_1min.iloc[-1]['close']

                # Exit at 3:55 PM ET (15 minutes before close)
                if current_time.hour == 15 and current_time.minute >= 55:
                    if state.in_position:
                        # Force exit at end of day
                        signals.append(
                            SignalCreate(
                                symbol=symbol,
                                signal_type="SELL",
                                confidence=1.0,  # 100% confidence for EOD exit
                                strategy_name=self.get_metadata().name,
                                metadata={
                                    "prediction": "EOD_EXIT",
                                    "price": float(current_price),
                                    "quantity": state.position_size,
                                    "reason": "End-of-day exit",
                                    "entry_price": state.entry_price,
                                    "pnl": float((current_price - state.entry_price) * state.position_size),
                                },
                            )
                        )
                        state.reset()
                        return signals  # Return immediately after EOD exit

        # Check if we have all required timeframes
        require_all = self._get_config_value("require_all_timeframes", True)

        if require_all:
            if not all([
                symbol in self.bars_1min,
                symbol in self.bars_5min,
                symbol in self.bars_15min,
                symbol in self.bars_30min,
            ]):
                return []  # Not enough data yet
        else:
            if symbol not in self.bars_1min:
                return []  # At minimum need 1-min bars

        # Get latest bars for each timeframe
        df_1min = self.bars_1min.get(symbol)
        df_5min = self.bars_5min.get(symbol) if symbol in self.bars_5min else None
        df_15min = self.bars_15min.get(symbol) if symbol in self.bars_15min else None
        df_30min = self.bars_30min.get(symbol) if symbol in self.bars_30min else None

        if df_1min is None or len(df_1min) < 60:
            return []  # Need at least 60 bars for indicators

        # Convert decimal columns to float (same as training)
        for df in [df_1min, df_5min, df_15min, df_30min]:
            if df is not None:
                for col in ['open', 'high', 'low', 'close', 'vwap']:
                    if col in df.columns:
                        df[col] = df[col].astype(float)

        # Compute features using FeatureEngineer
        try:
            engineer = FeatureEngineer(
                df_1min=df_1min,
                df_5min=df_5min,
                df_15min=df_15min,
                df_30min=df_30min,
            )

            df_features = engineer.create_all_features()

            # Get latest row (most recent 1-min bar)
            latest_features = df_features.iloc[-1]

            # Extract feature values in correct order
            X = latest_features[self.feature_columns].values.reshape(1, -1)

            # Handle any remaining NaN values (forward-fill, back-fill, then zero)
            X = pd.DataFrame(X, columns=self.feature_columns)
            X = X.ffill(axis=1).bfill(axis=1).fillna(0)
            X = X.values

            # Make prediction
            prediction = self.model.predict(X)[0]  # -1, 0, or 1

            # Get prediction probabilities for confidence filtering
            probabilities = self.model.predict_proba(X)[0]  # [p_sell, p_hold, p_buy]
            max_prob = probabilities.max()

            confidence_threshold = self._get_config_value("confidence_threshold", 0.6)

            # Only act if confidence exceeds threshold
            if max_prob < confidence_threshold:
                return []

            position_size = self._get_config_value("position_size", 10)
            current_time = df_1min.iloc[-1]['time']
            current_price = df_1min.iloc[-1]['close']

            # Generate signals based on prediction
            if prediction == 1 and not state.in_position:
                # BUY signal
                signals.append(
                    SignalCreate(
                        symbol=symbol,
                        signal_type="BUY",
                        confidence=float(max_prob),
                        strategy_name=self.get_metadata().name,
                        metadata={
                            "prediction": "BUY",
                            "price": float(current_price),
                            "quantity": position_size,
                            "probabilities": {
                                "sell": float(probabilities[0]),
                                "hold": float(probabilities[1]),
                                "buy": float(probabilities[2]),
                            },
                        },
                    )
                )

                # Update state
                state.in_position = True
                state.entry_price = float(current_price)
                state.entry_time = current_time
                state.position_size = position_size

            elif prediction == -1 and state.in_position:
                # SELL signal (exit)
                signals.append(
                    SignalCreate(
                        symbol=symbol,
                        signal_type="SELL",
                        confidence=float(max_prob),
                        strategy_name=self.get_metadata().name,
                        metadata={
                            "prediction": "SELL",
                            "price": float(current_price),
                            "quantity": state.position_size,
                            "probabilities": {
                                "sell": float(probabilities[0]),
                                "hold": float(probabilities[1]),
                                "buy": float(probabilities[2]),
                            },
                            "entry_price": state.entry_price,
                            "pnl": float((current_price - state.entry_price) * state.position_size),
                        },
                    )
                )

                # Reset state
                state.reset()

        except Exception as e:
            import traceback
            print(f"Error generating ML signals for {symbol} at {df_1min.iloc[-1]['time']}: {e}")
            print(f"Traceback: {traceback.format_exc()}")
            return []

        return signals
