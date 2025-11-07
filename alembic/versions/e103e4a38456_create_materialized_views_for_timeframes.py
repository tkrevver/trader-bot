"""create_materialized_views_for_timeframes

Revision ID: e103e4a38456
Revises: 89ddd9683855
Create Date: 2025-11-06 22:50:05.301485

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e103e4a38456'
down_revision: Union[str, None] = '89ddd9683855'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create materialized views for multi-timeframe aggregations."""

    # 1. Create 5-minute OHLCV materialized view
    op.execute("""
        CREATE MATERIALIZED VIEW ohlcv_5min AS
        SELECT
            date_trunc('hour', time) +
                (floor(extract(minute FROM time) / 5) * interval '5 minutes') AS time,
            symbol,
            (array_agg(open ORDER BY time))[1] AS open,
            MAX(high) AS high,
            MIN(low) AS low,
            (array_agg(close ORDER BY time DESC))[1] AS close,
            SUM(volume) AS volume,
            CASE
                WHEN SUM(volume) > 0 THEN SUM(volume * vwap) / SUM(volume)
                ELSE NULL
            END AS vwap,
            SUM(trades) AS trades
        FROM ohlcv_1min
        GROUP BY 1, symbol
        ORDER BY time DESC, symbol;
    """)

    # 2. Create 15-minute OHLCV materialized view
    op.execute("""
        CREATE MATERIALIZED VIEW ohlcv_15min AS
        SELECT
            date_trunc('hour', time) +
                (floor(extract(minute FROM time) / 15) * interval '15 minutes') AS time,
            symbol,
            (array_agg(open ORDER BY time))[1] AS open,
            MAX(high) AS high,
            MIN(low) AS low,
            (array_agg(close ORDER BY time DESC))[1] AS close,
            SUM(volume) AS volume,
            CASE
                WHEN SUM(volume) > 0 THEN SUM(volume * vwap) / SUM(volume)
                ELSE NULL
            END AS vwap,
            SUM(trades) AS trades
        FROM ohlcv_1min
        GROUP BY 1, symbol
        ORDER BY time DESC, symbol;
    """)

    # 3. Create 30-minute OHLCV materialized view
    op.execute("""
        CREATE MATERIALIZED VIEW ohlcv_30min AS
        SELECT
            date_trunc('hour', time) +
                (floor(extract(minute FROM time) / 30) * interval '30 minutes') AS time,
            symbol,
            (array_agg(open ORDER BY time))[1] AS open,
            MAX(high) AS high,
            MIN(low) AS low,
            (array_agg(close ORDER BY time DESC))[1] AS close,
            SUM(volume) AS volume,
            CASE
                WHEN SUM(volume) > 0 THEN SUM(volume * vwap) / SUM(volume)
                ELSE NULL
            END AS vwap,
            SUM(trades) AS trades
        FROM ohlcv_1min
        GROUP BY 1, symbol
        ORDER BY time DESC, symbol;
    """)

    # 4. Create daily OHLCV materialized view
    op.execute("""
        CREATE MATERIALIZED VIEW ohlcv_daily AS
        SELECT
            date_trunc('day', time) AS time,
            symbol,
            (array_agg(open ORDER BY time))[1] AS open,
            MAX(high) AS high,
            MIN(low) AS low,
            (array_agg(close ORDER BY time DESC))[1] AS close,
            SUM(volume) AS volume,
            CASE
                WHEN SUM(volume) > 0 THEN SUM(volume * vwap) / SUM(volume)
                ELSE NULL
            END AS vwap,
            SUM(trades) AS trades
        FROM ohlcv_1min
        GROUP BY 1, symbol
        ORDER BY time DESC, symbol;
    """)

    # Add comments
    op.execute("COMMENT ON MATERIALIZED VIEW ohlcv_5min IS '5-minute aggregated OHLCV data'")
    op.execute("COMMENT ON MATERIALIZED VIEW ohlcv_15min IS '15-minute aggregated OHLCV data'")
    op.execute("COMMENT ON MATERIALIZED VIEW ohlcv_30min IS '30-minute aggregated OHLCV data'")
    op.execute("COMMENT ON MATERIALIZED VIEW ohlcv_daily IS 'Daily aggregated OHLCV data'")


def downgrade() -> None:
    """Drop materialized views."""
    op.execute("DROP MATERIALIZED VIEW IF EXISTS ohlcv_daily CASCADE")
    op.execute("DROP MATERIALIZED VIEW IF EXISTS ohlcv_30min CASCADE")
    op.execute("DROP MATERIALIZED VIEW IF EXISTS ohlcv_15min CASCADE")
    op.execute("DROP MATERIALIZED VIEW IF EXISTS ohlcv_5min CASCADE")
