"""Opening Range Breakout Strategy.

Strategy Rules:
1. During regular market hours only
2. Calculate opening range: high/low from first 30 minutes (9:30-10:00 AM ET)
3. No trading before 10:00 AM ET
4. Entry: Buy when price breaks above opening high (if not in position)
5. Exit: Sell when price breaks below previous 5-min bar close (checked on 1-min bars)
6. Position sizing: Fixed 10 shares
7. Allow multiple entries per day

Technical Details:
- Uses 1-min bars for entry signals
- Uses 5-min bars for exit signals
- Tracks opening range and position state per day
"""

from datetime import datetime, time
from typing import Any, Optional

import pandas as pd
import pytz

from app.models.signals import SignalCreate
from app.strategies.base import Strategy, StrategyMetadata
from app.utils import indicators


class OpeningRangeBreakoutStrategy(Strategy):
    """Opening range breakout strategy implementation."""

    def get_metadata(self) -> StrategyMetadata:
        """Return strategy metadata."""
        return StrategyMetadata(
            name="opening_range_breakout",
            description=(
                "Opening range breakout strategy: "
                "Buy on break above opening range high (9:30-10:00 AM), "
                "exit when price breaks below previous 5-min bar close"
            ),
            version="1.0.0",
            author="Trader Bot",
            symbols=["SPY"],
            timeframes=["1min", "5min"],
            parameters={
                "opening_range_minutes": 30,
                "earliest_entry_time": "10:00",
                "position_size": 10,  # Fixed shares
            },
        )

    def validate_parameters(self) -> None:
        """Validate configuration parameters."""
        if "opening_range_minutes" in self.config:
            if self.config["opening_range_minutes"] <= 0:
                raise ValueError("opening_range_minutes must be positive")

        if "position_size" in self.config:
            if self.config["position_size"] <= 0:
                raise ValueError("position_size must be positive")

    def _get_config_value(self, key: str, default: Any) -> Any:
        """Get configuration value with fallback to metadata default."""
        metadata = self.get_metadata()
        return self.config.get(key, metadata.parameters.get(key, default))

    def _get_market_time(self, timestamp: datetime) -> datetime:
        """Convert timestamp to ET timezone.

        Args:
            timestamp: UTC timestamp

        Returns:
            Timestamp in ET timezone
        """
        et_tz = pytz.timezone("America/New_York")
        if timestamp.tzinfo is None:
            timestamp = pytz.utc.localize(timestamp)
        return timestamp.astimezone(et_tz)

    def _is_new_day(self, timestamp: datetime, symbol: str) -> bool:
        """Check if this is a new trading day.

        Args:
            timestamp: Current timestamp
            symbol: Trading symbol

        Returns:
            True if new day, False otherwise
        """
        state = self.get_state(symbol)
        last_date = state.custom_state.get("last_date")

        current_date = self._get_market_time(timestamp).date()

        if last_date is None or current_date > last_date:
            state.custom_state["last_date"] = current_date
            return True

        return False

    def _reset_daily_state(self, symbol: str) -> None:
        """Reset state for a new trading day.

        Args:
            symbol: Trading symbol
        """
        state = self.get_state(symbol)
        state.custom_state["opening_high"] = None
        state.custom_state["opening_low"] = None
        state.custom_state["opening_range_set"] = False
        state.custom_state["last_buy_signal_price"] = None
        state.custom_state["exit_signal_triggered"] = False
        state.custom_state["exit_trigger_price"] = None
        state.custom_state["exit_trigger_ema"] = None

    def _update_opening_range(self, symbol: str, bar: pd.Series) -> None:
        """Update opening range with current bar.

        Args:
            symbol: Trading symbol
            bar: Current 1-minute bar
        """
        state = self.get_state(symbol)

        current_high = state.custom_state.get("opening_high")
        current_low = state.custom_state.get("opening_low")

        # Update high/low
        if current_high is None or bar["high"] > current_high:
            state.custom_state["opening_high"] = float(bar["high"])

        if current_low is None or bar["low"] < current_low:
            state.custom_state["opening_low"] = float(bar["low"])

    def _is_opening_range_period(self, timestamp: datetime) -> bool:
        """Check if timestamp is within opening range period (9:30-10:00 AM ET).

        Args:
            timestamp: Timestamp to check

        Returns:
            True if within opening range period
        """
        market_time = self._get_market_time(timestamp)
        opening_range_minutes = self._get_config_value("opening_range_minutes", 30)

        # Opening range: 9:30-10:00 AM ET (default 30 minutes)
        market_open = time(9, 30)

        # Calculate opening range end time properly
        total_minutes = 9 * 60 + 30 + opening_range_minutes
        end_hour = total_minutes // 60
        end_minute = total_minutes % 60
        opening_range_end = time(end_hour, end_minute)

        return market_open <= market_time.time() < opening_range_end

    def _can_enter_trade(self, timestamp: datetime) -> bool:
        """Check if current time allows entering trades.

        Args:
            timestamp: Current timestamp

        Returns:
            True if can enter trades
        """
        market_time = self._get_market_time(timestamp)
        earliest_entry = self._get_config_value("earliest_entry_time", "10:00")

        # Parse earliest entry time
        hour, minute = map(int, earliest_entry.split(":"))
        earliest_time = time(hour, minute)

        return market_time.time() >= earliest_time

    def on_bar(
        self, symbol: str, timeframe: str, bar: pd.Series, bars: pd.DataFrame
    ) -> None:
        """Process new market data bar.

        Args:
            symbol: Trading symbol
            timeframe: Bar timeframe
            bar: Current bar
            bars: Historical bars including current
        """
        state = self.get_state(symbol)

        # Get bar timestamp
        if "time" in bar.index:
            bar_time = bar["time"]
        else:
            bar_time = bar.name  # index is timestamp

        if not isinstance(bar_time, datetime):
            return

        # Check if new day - reset daily state
        if self._is_new_day(bar_time, symbol):
            self._reset_daily_state(symbol)

        # Process 1-minute bars for opening range and entry signals
        if timeframe == "1min":
            # Update opening range during opening period
            if self._is_opening_range_period(bar_time):
                self._update_opening_range(symbol, bar)
            elif not state.custom_state.get("opening_range_set"):
                # Mark opening range as complete
                state.custom_state["opening_range_set"] = True

            # Store current price for signal generation
            current_price = float(bar["close"])
            state.custom_state["current_price"] = current_price
            state.custom_state["current_time"] = bar_time

        # Process 5-minute bars for exit signal
        elif timeframe == "5min":
            # Calculate EMA-10 on 5-min bars
            if len(bars) >= 10:
                # Get EMA-10
                from app.utils.indicators import ema
                ema_series = ema(bars, length=10)

                if not ema_series.empty:
                    current_ema10 = float(ema_series.iloc[-1])
                    current_5min_close = float(bar["close"])

                    # Check if 5-min bar closed below EMA-10
                    if current_5min_close < current_ema10:
                        # Set flag to exit on next 1-min bar
                        state.custom_state["exit_signal_triggered"] = True
                        state.custom_state["exit_trigger_price"] = current_5min_close
                        state.custom_state["exit_trigger_ema"] = current_ema10
                    else:
                        # Clear exit signal if price back above EMA
                        state.custom_state["exit_signal_triggered"] = False

    def generate_signals(self, symbol: str) -> list[SignalCreate]:
        """Generate trading signals.

        Args:
            symbol: Trading symbol

        Returns:
            List of signals (entry or exit)
        """
        state = self.get_state(symbol)
        signals = []

        # Check if opening range is set
        if not state.custom_state.get("opening_range_set"):
            return signals

        opening_high = state.custom_state.get("opening_high")
        opening_low = state.custom_state.get("opening_low")

        if opening_high is None or opening_low is None:
            return signals

        # Get current price from latest bar
        current_price = state.custom_state.get("current_price")
        current_time = state.custom_state.get("current_time")

        if current_price is None or current_time is None:
            return signals

        # ENTRY SIGNAL: Break above opening high (only if not in position)
        if not state.in_position:
            # Check if price breaks above opening high
            if current_price > opening_high:
                # Check if we haven't already signaled entry for this breakout
                # Track the last price where we generated a signal
                last_signal_price = state.custom_state.get("last_buy_signal_price")

                # Only generate signal if this is a NEW breakout (haven't signaled yet, or re-entry after exit)
                if last_signal_price is None or last_signal_price < opening_high:
                    # Check if we can enter (not too early)
                    if self._can_enter_trade(current_time):
                        position_size = self._get_config_value("position_size", 10)

                        # Mark the price at which we generated this signal
                        state.custom_state["last_buy_signal_price"] = current_price

                        signals.append(
                            SignalCreate(
                                symbol=symbol,
                                signal_type="BUY",
                                strategy_name=self.get_metadata().name,
                                timeframe="1min",
                                metadata={
                                    "opening_high": opening_high,
                                    "opening_low": opening_low,
                                    "position_size": position_size,
                                    "current_price": current_price,
                                    "reason": f"Price {current_price:.2f} broke above opening high {opening_high:.2f}",
                                },
                            )
                        )

        # EXIT SIGNAL: 5-min bar closed below EMA-10
        elif state.in_position:
            exit_triggered = state.custom_state.get("exit_signal_triggered", False)

            if exit_triggered:
                # Generate SELL signal on next 1-min bar
                exit_trigger_price = state.custom_state.get("exit_trigger_price")
                exit_trigger_ema = state.custom_state.get("exit_trigger_ema")

                signals.append(
                    SignalCreate(
                        symbol=symbol,
                        signal_type="SELL",
                        strategy_name=self.get_metadata().name,
                        timeframe="1min",
                        metadata={
                            "exit_trigger": "5min_close_below_ema10",
                            "current_price": current_price,
                            "trigger_5min_close": exit_trigger_price,
                            "trigger_ema10": exit_trigger_ema,
                            "reason": f"5-min bar closed at {exit_trigger_price:.2f} below EMA-10 {exit_trigger_ema:.2f}",
                        },
                    )
                )

                # Clear the exit signal flag after generating signal
                state.custom_state["exit_signal_triggered"] = False

        return signals
