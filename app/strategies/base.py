"""Abstract base class for trading strategies.

All trading strategies must inherit from this base class and implement
the required methods. This ensures consistent interface across all strategies
for signal generation, backtesting, and live trading.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Optional

import pandas as pd
from pydantic import BaseModel, Field

from app.models.signals import SignalCreate


class StrategyMetadata(BaseModel):
    """Metadata describing a strategy."""

    name: str = Field(..., description="Unique strategy name")
    description: str = Field(..., description="Strategy description")
    version: str = Field(default="1.0.0", description="Strategy version")
    author: Optional[str] = Field(None, description="Strategy author")
    symbols: list[str] = Field(default_factory=list, description="Supported symbols")
    timeframes: list[str] = Field(
        default_factory=list, description="Required timeframes (e.g., ['1min', '5min'])"
    )
    parameters: dict[str, Any] = Field(
        default_factory=dict, description="Strategy parameters"
    )


class StrategyState(BaseModel):
    """Strategy runtime state (position tracking, internal variables)."""

    symbol: str = Field(..., description="Symbol being traded")
    in_position: bool = Field(default=False, description="Currently in a position")
    position_side: Optional[str] = Field(None, description="Position side: 'LONG' or 'SHORT'")
    entry_price: Optional[float] = Field(None, description="Entry price if in position")
    entry_time: Optional[datetime] = Field(None, description="Entry timestamp")
    position_size: int = Field(default=0, description="Current position size (shares)")
    custom_state: dict[str, Any] = Field(
        default_factory=dict, description="Strategy-specific state variables"
    )

    def reset(self) -> None:
        """Reset position state (called after exit)."""
        self.in_position = False
        self.position_side = None
        self.entry_price = None
        self.entry_time = None
        self.position_size = 0


class Strategy(ABC):
    """Abstract base class for all trading strategies.

    Strategies must implement:
    - get_metadata(): Return strategy information
    - on_bar(): Process new market data bar
    - generate_signals(): Generate trading signals based on current state

    Optional methods to override:
    - on_start(): Called when strategy is initialized
    - on_end(): Called when strategy is stopped
    - validate_parameters(): Validate strategy configuration
    """

    def __init__(self, config: Optional[dict[str, Any]] = None):
        """Initialize strategy with configuration.

        Args:
            config: Strategy configuration parameters
        """
        self.config = config or {}
        self.state: dict[str, StrategyState] = {}  # symbol -> StrategyState
        self._metadata: Optional[StrategyMetadata] = None
        self._is_initialized = False

    def initialize(self) -> None:
        """Initialize the strategy (called before first bar)."""
        if self._is_initialized:
            return

        self._metadata = self.get_metadata()
        self.validate_parameters()
        self.on_start()
        self._is_initialized = True

    def get_state(self, symbol: str) -> StrategyState:
        """Get or create state for a symbol.

        Args:
            symbol: Trading symbol

        Returns:
            StrategyState for the symbol
        """
        if symbol not in self.state:
            self.state[symbol] = StrategyState(symbol=symbol)
        return self.state[symbol]

    @abstractmethod
    def get_metadata(self) -> StrategyMetadata:
        """Return strategy metadata.

        Returns:
            StrategyMetadata with name, description, version, etc.
        """
        pass

    @abstractmethod
    def on_bar(
        self,
        symbol: str,
        timeframe: str,
        bar: pd.Series,
        bars: pd.DataFrame,
    ) -> None:
        """Process a new market data bar.

        This method is called for each new bar on each subscribed timeframe.
        Update internal state, calculate indicators, check conditions, etc.

        Args:
            symbol: Trading symbol
            timeframe: Bar timeframe (e.g., '1min', '5min')
            bar: Current bar as pandas Series (latest row)
            bars: Historical bars including current bar as DataFrame
        """
        pass

    @abstractmethod
    def generate_signals(self, symbol: str) -> list[SignalCreate]:
        """Generate trading signals based on current state.

        This method is called after on_bar() to check if any signals should
        be generated. Return empty list if no signals.

        Args:
            symbol: Trading symbol

        Returns:
            List of SignalCreate objects (entry/exit signals)
        """
        pass

    def on_start(self) -> None:
        """Called when strategy is started (before first bar).

        Override to perform initialization tasks like loading data,
        setting up indicators, etc.
        """
        pass

    def on_end(self) -> None:
        """Called when strategy is stopped.

        Override to perform cleanup tasks like closing positions,
        saving state, etc.
        """
        pass

    def validate_parameters(self) -> None:
        """Validate strategy configuration parameters.

        Override to add custom parameter validation.

        Raises:
            ValueError: If parameters are invalid
        """
        pass

    def get_symbols(self) -> list[str]:
        """Get list of symbols this strategy trades.

        Returns:
            List of trading symbols
        """
        if not self._metadata:
            self._metadata = self.get_metadata()
        return self._metadata.symbols

    def get_timeframes(self) -> list[str]:
        """Get list of timeframes this strategy requires.

        Returns:
            List of timeframe strings (e.g., ['1min', '5min'])
        """
        if not self._metadata:
            self._metadata = self.get_metadata()
        return self._metadata.timeframes

    def reset_state(self, symbol: str) -> None:
        """Reset strategy state for a symbol.

        Args:
            symbol: Trading symbol
        """
        if symbol in self.state:
            self.state[symbol].reset()

    def reset_all_states(self) -> None:
        """Reset strategy state for all symbols."""
        for state in self.state.values():
            state.reset()

    def __repr__(self) -> str:
        """String representation of strategy."""
        if not self._metadata:
            self._metadata = self.get_metadata()
        return f"<Strategy: {self._metadata.name} v{self._metadata.version}>"
