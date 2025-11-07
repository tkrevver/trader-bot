"""create_indexes

Revision ID: 41a449542500
Revises: e103e4a38456
Create Date: 2025-11-06 22:52:05.301485

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '41a449542500'
down_revision: Union[str, None] = 'e103e4a38456'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create indexes for performance optimization."""

    # OHLCV 1min table indexes
    # BRIN index on time for efficient range scans (optimal for sequential time-series data)
    op.execute("CREATE INDEX idx_ohlcv_1min_time_brin ON ohlcv_1min USING BRIN (time)")

    # B-tree indexes for symbol lookups and combined symbol+time queries
    op.execute("CREATE INDEX idx_ohlcv_1min_symbol ON ohlcv_1min (symbol)")
    op.execute("CREATE INDEX idx_ohlcv_1min_symbol_time ON ohlcv_1min (symbol, time DESC)")

    # Materialized view indexes
    # 5-minute view
    op.execute("CREATE INDEX idx_ohlcv_5min_time ON ohlcv_5min (time DESC)")
    op.execute("CREATE INDEX idx_ohlcv_5min_symbol ON ohlcv_5min (symbol)")
    op.execute("CREATE INDEX idx_ohlcv_5min_symbol_time ON ohlcv_5min (symbol, time DESC)")

    # 15-minute view
    op.execute("CREATE INDEX idx_ohlcv_15min_time ON ohlcv_15min (time DESC)")
    op.execute("CREATE INDEX idx_ohlcv_15min_symbol ON ohlcv_15min (symbol)")
    op.execute("CREATE INDEX idx_ohlcv_15min_symbol_time ON ohlcv_15min (symbol, time DESC)")

    # 30-minute view
    op.execute("CREATE INDEX idx_ohlcv_30min_time ON ohlcv_30min (time DESC)")
    op.execute("CREATE INDEX idx_ohlcv_30min_symbol ON ohlcv_30min (symbol)")
    op.execute("CREATE INDEX idx_ohlcv_30min_symbol_time ON ohlcv_30min (symbol, time DESC)")

    # Daily view
    op.execute("CREATE INDEX idx_ohlcv_daily_time ON ohlcv_daily (time DESC)")
    op.execute("CREATE INDEX idx_ohlcv_daily_symbol ON ohlcv_daily (symbol)")
    op.execute("CREATE INDEX idx_ohlcv_daily_symbol_time ON ohlcv_daily (symbol, time DESC)")

    # Trades table indexes
    op.execute("CREATE INDEX idx_trades_timestamp ON trades (timestamp DESC)")
    op.execute("CREATE INDEX idx_trades_symbol ON trades (symbol)")
    op.execute("CREATE INDEX idx_trades_order_id ON trades (order_id)")
    op.execute("CREATE INDEX idx_trades_strategy ON trades (strategy_name)")

    # Orders table indexes
    op.execute("CREATE INDEX idx_orders_timestamp ON orders (timestamp DESC)")
    op.execute("CREATE INDEX idx_orders_symbol ON orders (symbol)")
    op.execute("CREATE INDEX idx_orders_status ON orders (status)")
    op.execute("CREATE INDEX idx_orders_broker_order_id ON orders (broker_order_id)")
    op.execute("CREATE INDEX idx_orders_strategy ON orders (strategy_name)")
    op.execute("CREATE INDEX idx_orders_signal_id ON orders (signal_id)")

    # Positions table indexes
    op.execute("CREATE INDEX idx_positions_symbol ON positions (symbol)")
    op.execute("CREATE INDEX idx_positions_status ON positions (status)")
    op.execute("CREATE INDEX idx_positions_strategy ON positions (strategy_name)")
    op.execute("CREATE INDEX idx_positions_opened_at ON positions (opened_at DESC)")

    # Signals table indexes
    op.execute("CREATE INDEX idx_signals_timestamp ON signals (timestamp DESC)")
    op.execute("CREATE INDEX idx_signals_symbol ON signals (symbol)")
    op.execute("CREATE INDEX idx_signals_strategy ON signals (strategy_name)")
    op.execute("CREATE INDEX idx_signals_approved ON signals (approved)")

    # Strategies table indexes
    op.execute("CREATE INDEX idx_strategies_name ON strategies (name)")
    op.execute("CREATE INDEX idx_strategies_active ON strategies (active)")

    # Account snapshots table indexes
    op.execute("CREATE INDEX idx_account_snapshots_timestamp ON account_snapshots (timestamp DESC)")
    op.execute("CREATE INDEX idx_account_snapshots_broker ON account_snapshots (broker)")


def downgrade() -> None:
    """Drop all indexes."""

    # OHLCV 1min indexes
    op.execute("DROP INDEX IF EXISTS idx_ohlcv_1min_time_brin")
    op.execute("DROP INDEX IF EXISTS idx_ohlcv_1min_symbol")
    op.execute("DROP INDEX IF EXISTS idx_ohlcv_1min_symbol_time")

    # Materialized view indexes
    op.execute("DROP INDEX IF EXISTS idx_ohlcv_5min_time")
    op.execute("DROP INDEX IF EXISTS idx_ohlcv_5min_symbol")
    op.execute("DROP INDEX IF EXISTS idx_ohlcv_5min_symbol_time")

    op.execute("DROP INDEX IF EXISTS idx_ohlcv_15min_time")
    op.execute("DROP INDEX IF EXISTS idx_ohlcv_15min_symbol")
    op.execute("DROP INDEX IF EXISTS idx_ohlcv_15min_symbol_time")

    op.execute("DROP INDEX IF EXISTS idx_ohlcv_30min_time")
    op.execute("DROP INDEX IF EXISTS idx_ohlcv_30min_symbol")
    op.execute("DROP INDEX IF EXISTS idx_ohlcv_30min_symbol_time")

    op.execute("DROP INDEX IF EXISTS idx_ohlcv_daily_time")
    op.execute("DROP INDEX IF EXISTS idx_ohlcv_daily_symbol")
    op.execute("DROP INDEX IF EXISTS idx_ohlcv_daily_symbol_time")

    # Trades table indexes
    op.execute("DROP INDEX IF EXISTS idx_trades_timestamp")
    op.execute("DROP INDEX IF EXISTS idx_trades_symbol")
    op.execute("DROP INDEX IF EXISTS idx_trades_order_id")
    op.execute("DROP INDEX IF EXISTS idx_trades_strategy")

    # Orders table indexes
    op.execute("DROP INDEX IF EXISTS idx_orders_timestamp")
    op.execute("DROP INDEX IF EXISTS idx_orders_symbol")
    op.execute("DROP INDEX IF EXISTS idx_orders_status")
    op.execute("DROP INDEX IF EXISTS idx_orders_broker_order_id")
    op.execute("DROP INDEX IF EXISTS idx_orders_strategy")
    op.execute("DROP INDEX IF EXISTS idx_orders_signal_id")

    # Positions table indexes
    op.execute("DROP INDEX IF EXISTS idx_positions_symbol")
    op.execute("DROP INDEX IF EXISTS idx_positions_status")
    op.execute("DROP INDEX IF EXISTS idx_positions_strategy")
    op.execute("DROP INDEX IF EXISTS idx_positions_opened_at")

    # Signals table indexes
    op.execute("DROP INDEX IF EXISTS idx_signals_timestamp")
    op.execute("DROP INDEX IF EXISTS idx_signals_symbol")
    op.execute("DROP INDEX IF EXISTS idx_signals_strategy")
    op.execute("DROP INDEX IF EXISTS idx_signals_approved")

    # Strategies table indexes
    op.execute("DROP INDEX IF EXISTS idx_strategies_name")
    op.execute("DROP INDEX IF EXISTS idx_strategies_active")

    # Account snapshots table indexes
    op.execute("DROP INDEX IF EXISTS idx_account_snapshots_timestamp")
    op.execute("DROP INDEX IF EXISTS idx_account_snapshots_broker")
