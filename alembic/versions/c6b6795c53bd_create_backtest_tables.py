"""create_backtest_tables

Revision ID: c6b6795c53bd
Revises: 41a449542500
Create Date: 2025-11-07 21:34:21.163603

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c6b6795c53bd'
down_revision: Union[str, None] = '41a449542500'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create backtests table
    op.create_table(
        'backtests',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('strategy_name', sa.String(100), nullable=False),
        sa.Column('symbol', sa.String(10), nullable=False),
        sa.Column('start_date', sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column('end_date', sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column('initial_capital', sa.Numeric(12, 2), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, server_default='PENDING'),
        sa.Column('config', sa.JSON(), nullable=True),
        sa.Column('metrics', sa.JSON(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('started_at', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('completed_at', sa.TIMESTAMP(timezone=True), nullable=True),
    )

    # Create index on strategy_name and status for filtering
    op.create_index('ix_backtests_strategy_name', 'backtests', ['strategy_name'])
    op.create_index('ix_backtests_status', 'backtests', ['status'])

    # Create backtest_trades table
    op.create_table(
        'backtest_trades',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('backtest_id', sa.Integer(), nullable=False),
        sa.Column('symbol', sa.String(10), nullable=False),
        sa.Column('side', sa.String(10), nullable=False),
        sa.Column('quantity', sa.Integer(), nullable=False),
        sa.Column('price', sa.Numeric(12, 4), nullable=False),
        sa.Column('executed_at', sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column('pnl', sa.Numeric(12, 2), nullable=True),
        sa.Column('commission', sa.Numeric(12, 2), nullable=False, server_default='0'),
        sa.Column('slippage', sa.Numeric(12, 4), nullable=False, server_default='0'),
        sa.Column('metadata', sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(['backtest_id'], ['backtests.id'], ondelete='CASCADE'),
    )

    # Create index on backtest_id for fast lookups
    op.create_index('ix_backtest_trades_backtest_id', 'backtest_trades', ['backtest_id'])

    # Create backtest_equity_curve table
    op.create_table(
        'backtest_equity_curve',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('backtest_id', sa.Integer(), nullable=False),
        sa.Column('timestamp', sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column('equity', sa.Numeric(12, 2), nullable=False),
        sa.Column('cash', sa.Numeric(12, 2), nullable=False),
        sa.Column('positions_value', sa.Numeric(12, 2), nullable=False),
        sa.ForeignKeyConstraint(['backtest_id'], ['backtests.id'], ondelete='CASCADE'),
    )

    # Create index on backtest_id and timestamp
    op.create_index('ix_backtest_equity_curve_backtest_id', 'backtest_equity_curve', ['backtest_id'])
    op.create_index('ix_backtest_equity_curve_timestamp', 'backtest_equity_curve', ['timestamp'])


def downgrade() -> None:
    op.drop_index('ix_backtest_equity_curve_timestamp', table_name='backtest_equity_curve')
    op.drop_index('ix_backtest_equity_curve_backtest_id', table_name='backtest_equity_curve')
    op.drop_table('backtest_equity_curve')

    op.drop_index('ix_backtest_trades_backtest_id', table_name='backtest_trades')
    op.drop_table('backtest_trades')

    op.drop_index('ix_backtests_status', table_name='backtests')
    op.drop_index('ix_backtests_strategy_name', table_name='backtests')
    op.drop_table('backtests')
