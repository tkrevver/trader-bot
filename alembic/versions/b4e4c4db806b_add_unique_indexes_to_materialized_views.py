"""add_unique_indexes_to_materialized_views

Revision ID: b4e4c4db806b
Revises: c6b6795c53bd
Create Date: 2025-11-08 22:37:16.445912

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b4e4c4db806b'
down_revision: Union[str, None] = 'c6b6795c53bd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Add unique indexes to materialized views to enable concurrent refresh.

    Concurrent refresh of materialized views requires a unique index with no WHERE clause.
    These indexes ensure data uniqueness and enable non-blocking refreshes.
    """
    # Create unique indexes for concurrent refresh support
    op.create_index(
        'ohlcv_5min_symbol_time_idx',
        'ohlcv_5min',
        ['symbol', 'time'],
        unique=True
    )

    op.create_index(
        'ohlcv_15min_symbol_time_idx',
        'ohlcv_15min',
        ['symbol', 'time'],
        unique=True
    )

    op.create_index(
        'ohlcv_30min_symbol_time_idx',
        'ohlcv_30min',
        ['symbol', 'time'],
        unique=True
    )

    op.create_index(
        'ohlcv_daily_symbol_time_idx',
        'ohlcv_daily',
        ['symbol', 'time'],
        unique=True
    )


def downgrade() -> None:
    """Remove unique indexes from materialized views."""
    op.drop_index('ohlcv_daily_symbol_time_idx', table_name='ohlcv_daily')
    op.drop_index('ohlcv_30min_symbol_time_idx', table_name='ohlcv_30min')
    op.drop_index('ohlcv_15min_symbol_time_idx', table_name='ohlcv_15min')
    op.drop_index('ohlcv_5min_symbol_time_idx', table_name='ohlcv_5min')
