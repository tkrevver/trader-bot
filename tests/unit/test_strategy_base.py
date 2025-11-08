"""Unit tests for strategy base class."""

import pandas as pd
import pytest
from datetime import datetime

from app.strategies.base import Strategy, StrategyMetadata, StrategyState
from app.models.signals import SignalCreate


class MockStrategy(Strategy):
    """Mock strategy for testing."""

    def get_metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            name="mock_strategy",
            description="Test strategy",
            version="1.0.0",
            symbols=["SPY"],
            timeframes=["1min", "5min"],
            parameters={"test_param": 42},
        )

    def on_bar(
        self, symbol: str, timeframe: str, bar: pd.Series, bars: pd.DataFrame
    ) -> None:
        # Simple implementation: track if we've seen a bar
        state = self.get_state(symbol)
        state.custom_state["bar_count"] = state.custom_state.get("bar_count", 0) + 1

    def generate_signals(self, symbol: str) -> list[SignalCreate]:
        state = self.get_state(symbol)
        # Generate a buy signal if we've seen 5 bars
        if state.custom_state.get("bar_count", 0) >= 5 and not state.in_position:
            return [
                SignalCreate(
                    strategy_name="mock_strategy",
                    symbol=symbol,
                    signal_type="BUY",
                )
            ]
        return []


def test_strategy_initialization():
    """Test strategy initialization."""
    strategy = MockStrategy(config={"test_param": 100})

    assert strategy.config == {"test_param": 100}
    assert not strategy._is_initialized
    assert strategy.state == {}


def test_strategy_initialize():
    """Test strategy initialization process."""
    strategy = MockStrategy()
    strategy.initialize()

    assert strategy._is_initialized
    assert strategy._metadata is not None
    assert strategy._metadata.name == "mock_strategy"


def test_strategy_get_state():
    """Test getting state for a symbol."""
    strategy = MockStrategy()

    # First access should create state
    state = strategy.get_state("SPY")
    assert isinstance(state, StrategyState)
    assert state.symbol == "SPY"
    assert not state.in_position

    # Second access should return same state
    state2 = strategy.get_state("SPY")
    assert state is state2


def test_strategy_metadata():
    """Test strategy metadata."""
    strategy = MockStrategy()
    metadata = strategy.get_metadata()

    assert metadata.name == "mock_strategy"
    assert metadata.description == "Test strategy"
    assert metadata.version == "1.0.0"
    assert metadata.symbols == ["SPY"]
    assert metadata.timeframes == ["1min", "5min"]
    assert metadata.parameters == {"test_param": 42}


def test_strategy_get_symbols():
    """Test getting strategy symbols."""
    strategy = MockStrategy()
    symbols = strategy.get_symbols()

    assert symbols == ["SPY"]


def test_strategy_get_timeframes():
    """Test getting strategy timeframes."""
    strategy = MockStrategy()
    timeframes = strategy.get_timeframes()

    assert timeframes == ["1min", "5min"]


def test_strategy_on_bar():
    """Test on_bar method."""
    strategy = MockStrategy()
    strategy.initialize()

    # Create sample bar
    bar = pd.Series(
        {
            "time": datetime(2025, 1, 1, 10, 0),
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.5,
            "volume": 1000000,
        }
    )
    bars = pd.DataFrame([bar])

    # Process bar
    strategy.on_bar("SPY", "1min", bar, bars)

    # Check state was updated
    state = strategy.get_state("SPY")
    assert state.custom_state["bar_count"] == 1


def test_strategy_generate_signals():
    """Test signal generation."""
    strategy = MockStrategy()
    strategy.initialize()

    # Create sample bars
    bar = pd.Series(
        {
            "time": datetime(2025, 1, 1, 10, 0),
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.5,
            "volume": 1000000,
        }
    )
    bars = pd.DataFrame([bar])

    # Process 5 bars to trigger signal
    for i in range(5):
        strategy.on_bar("SPY", "1min", bar, bars)

    # Generate signals
    signals = strategy.generate_signals("SPY")

    assert len(signals) == 1
    assert signals[0].strategy_name == "mock_strategy"
    assert signals[0].symbol == "SPY"
    assert signals[0].signal_type == "BUY"


def test_strategy_state_reset():
    """Test resetting strategy state."""
    strategy = MockStrategy()
    state = strategy.get_state("SPY")

    # Set some state
    state.in_position = True
    state.entry_price = 100.0
    state.position_size = 10

    # Reset
    strategy.reset_state("SPY")

    # State should be reset
    assert not state.in_position
    assert state.entry_price is None
    assert state.position_size == 0


def test_strategy_state_reset_all():
    """Test resetting all strategy states."""
    strategy = MockStrategy()

    # Create states for multiple symbols
    spy_state = strategy.get_state("SPY")
    qqq_state = strategy.get_state("QQQ")

    spy_state.in_position = True
    qqq_state.in_position = True

    # Reset all
    strategy.reset_all_states()

    assert not spy_state.in_position
    assert not qqq_state.in_position


def test_strategy_state_model():
    """Test StrategyState model."""
    state = StrategyState(symbol="SPY")

    assert state.symbol == "SPY"
    assert not state.in_position
    assert state.entry_price is None
    assert state.position_size == 0
    assert state.custom_state == {}


def test_strategy_state_reset_method():
    """Test StrategyState reset method."""
    state = StrategyState(symbol="SPY")

    # Set some values
    state.in_position = True
    state.entry_price = 100.0
    state.entry_time = datetime(2025, 1, 1, 10, 0)
    state.position_size = 10

    # Reset
    state.reset()

    assert not state.in_position
    assert state.entry_price is None
    assert state.entry_time is None
    assert state.position_size == 0


def test_strategy_repr():
    """Test strategy string representation."""
    strategy = MockStrategy()
    strategy.initialize()

    repr_str = repr(strategy)
    assert "mock_strategy" in repr_str
    assert "1.0.0" in repr_str


def test_strategy_on_start_on_end():
    """Test on_start and on_end lifecycle methods."""

    class LifecycleStrategy(MockStrategy):
        def on_start(self):
            self.started = True

        def on_end(self):
            self.ended = True

    strategy = LifecycleStrategy()
    strategy.initialize()

    assert hasattr(strategy, "started")
    assert strategy.started is True

    strategy.on_end()
    assert hasattr(strategy, "ended")
    assert strategy.ended is True


def test_strategy_validate_parameters():
    """Test parameter validation."""

    class ValidatedStrategy(MockStrategy):
        def validate_parameters(self):
            if "required_param" not in self.config:
                raise ValueError("required_param is missing")

    # Should raise error
    strategy = ValidatedStrategy(config={})
    with pytest.raises(ValueError, match="required_param is missing"):
        strategy.initialize()

    # Should succeed
    strategy2 = ValidatedStrategy(config={"required_param": "value"})
    strategy2.initialize()  # Should not raise


def test_strategy_double_initialize():
    """Test that initialize can be called multiple times safely."""
    strategy = MockStrategy()

    strategy.initialize()
    assert strategy._is_initialized

    # Second call should be safe
    strategy.initialize()
    assert strategy._is_initialized
