"""create_core_schema_with_partitioning

Revision ID: 89ddd9683855
Revises:
Create Date: 2025-11-06 22:47:05.301485

"""
from typing import Sequence, Union
from datetime import datetime, timedelta

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '89ddd9683855'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create core schema with partitioned tables."""

    # 1. Create partitioned OHLCV table
    op.execute("""
        CREATE TABLE ohlcv_1min (
            time TIMESTAMPTZ NOT NULL,
            symbol TEXT NOT NULL,
            open NUMERIC(10, 2) NOT NULL,
            high NUMERIC(10, 2) NOT NULL,
            low NUMERIC(10, 2) NOT NULL,
            close NUMERIC(10, 2) NOT NULL,
            volume BIGINT NOT NULL,
            vwap NUMERIC(10, 2),
            trades INTEGER,
            PRIMARY KEY (time, symbol)
        ) PARTITION BY RANGE (time);
    """)

    # Create initial partitions (weekly) for current year
    # Starting from 2025-01-01 for first 12 weeks
    start_date = datetime(2025, 1, 1)
    for week in range(52):  # Create partitions for full year
        week_start = start_date + timedelta(weeks=week)
        week_end = week_start + timedelta(weeks=1)
        partition_name = f"ohlcv_1min_{week_start.year}_w{week+1:02d}"

        op.execute(f"""
            CREATE TABLE {partition_name} PARTITION OF ohlcv_1min
            FOR VALUES FROM ('{week_start.isoformat()}') TO ('{week_end.isoformat()}');
        """)

    # 2. Create trades table
    op.execute("""
        CREATE TABLE trades (
            id SERIAL PRIMARY KEY,
            timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            symbol TEXT NOT NULL,
            side TEXT NOT NULL CHECK (side IN ('BUY', 'SELL')),
            quantity NUMERIC(10, 4) NOT NULL,
            price NUMERIC(10, 2) NOT NULL,
            commission NUMERIC(10, 2) DEFAULT 0,
            order_id INTEGER,
            pnl NUMERIC(10, 2),
            strategy_name TEXT,
            broker TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
    """)

    # 3. Create orders table
    op.execute("""
        CREATE TABLE orders (
            id SERIAL PRIMARY KEY,
            timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            symbol TEXT NOT NULL,
            side TEXT NOT NULL CHECK (side IN ('BUY', 'SELL')),
            quantity NUMERIC(10, 4) NOT NULL,
            order_type TEXT NOT NULL CHECK (order_type IN ('MARKET', 'LIMIT', 'STOP', 'STOP_LIMIT')),
            limit_price NUMERIC(10, 2),
            stop_price NUMERIC(10, 2),
            status TEXT NOT NULL CHECK (status IN ('PENDING', 'SUBMITTED', 'FILLED', 'PARTIALLY_FILLED', 'CANCELED', 'REJECTED')),
            filled_quantity NUMERIC(10, 4) DEFAULT 0,
            filled_price NUMERIC(10, 2),
            broker_order_id TEXT,
            strategy_name TEXT,
            signal_id INTEGER,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
    """)

    # 4. Create positions table
    op.execute("""
        CREATE TABLE positions (
            id SERIAL PRIMARY KEY,
            symbol TEXT NOT NULL,
            quantity NUMERIC(10, 4) NOT NULL,
            avg_entry_price NUMERIC(10, 2) NOT NULL,
            current_price NUMERIC(10, 2),
            unrealized_pnl NUMERIC(10, 2),
            realized_pnl NUMERIC(10, 2) DEFAULT 0,
            opened_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            closed_at TIMESTAMPTZ,
            status TEXT NOT NULL CHECK (status IN ('OPEN', 'CLOSED')),
            strategy_name TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
    """)

    # 5. Create signals table
    op.execute("""
        CREATE TABLE signals (
            id SERIAL PRIMARY KEY,
            timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            symbol TEXT NOT NULL,
            signal_type TEXT NOT NULL CHECK (signal_type IN ('BUY', 'SELL', 'HOLD')),
            confidence NUMERIC(3, 2) CHECK (confidence >= 0 AND confidence <= 1),
            strategy_name TEXT NOT NULL,
            timeframe TEXT,
            metadata JSONB,
            approved BOOLEAN DEFAULT FALSE,
            rejection_reason TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
    """)

    # 6. Create strategies table
    op.execute("""
        CREATE TABLE strategies (
            id SERIAL PRIMARY KEY,
            name TEXT UNIQUE NOT NULL,
            description TEXT,
            active BOOLEAN DEFAULT FALSE,
            config JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
    """)

    # 7. Create account_snapshots table
    op.execute("""
        CREATE TABLE account_snapshots (
            id SERIAL PRIMARY KEY,
            timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            cash NUMERIC(12, 2) NOT NULL,
            equity NUMERIC(12, 2) NOT NULL,
            buying_power NUMERIC(12, 2),
            daily_pnl NUMERIC(10, 2),
            total_pnl NUMERIC(10, 2),
            broker TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
    """)

    # Add comment for future reference
    op.execute("COMMENT ON TABLE ohlcv_1min IS 'Partitioned table storing minute-level OHLCV data'")


def downgrade() -> None:
    """Drop all tables."""
    op.execute("DROP TABLE IF EXISTS account_snapshots CASCADE")
    op.execute("DROP TABLE IF EXISTS strategies CASCADE")
    op.execute("DROP TABLE IF EXISTS signals CASCADE")
    op.execute("DROP TABLE IF EXISTS positions CASCADE")
    op.execute("DROP TABLE IF EXISTS orders CASCADE")
    op.execute("DROP TABLE IF EXISTS trades CASCADE")
    op.execute("DROP TABLE IF EXISTS ohlcv_1min CASCADE")
