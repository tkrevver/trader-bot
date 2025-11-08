"""Backtest repository for database operations."""

import json
from datetime import datetime
from decimal import Decimal
from typing import Optional

from asyncpg import Connection
from asyncpg.pool import Pool

from app.models.backtest import (
    Backtest,
    BacktestCreate,
    BacktestStatus,
    BacktestTrade,
    EquityCurvePoint,
    BacktestMetrics,
)
from app.utils.logger import logger


class BacktestRepository:
    """Repository for backtest database operations."""

    def __init__(self, db_pool: Pool):
        """Initialize repository with database pool.

        Args:
            db_pool: Database connection pool
        """
        self.db_pool = db_pool

    @staticmethod
    def _parse_json_fields(row_dict: dict) -> dict:
        """Parse JSON string fields to dicts.

        Args:
            row_dict: Row dictionary from database

        Returns:
            Row dictionary with parsed JSON fields
        """
        if row_dict.get('config') and isinstance(row_dict['config'], str):
            row_dict['config'] = json.loads(row_dict['config'])
        if row_dict.get('metrics') and isinstance(row_dict['metrics'], str):
            row_dict['metrics'] = json.loads(row_dict['metrics'])
        if row_dict.get('metadata') and isinstance(row_dict['metadata'], str):
            row_dict['metadata'] = json.loads(row_dict['metadata'])
        return row_dict

    async def create_backtest(
        self, conn: Connection, backtest_create: BacktestCreate
    ) -> Backtest:
        """Create a new backtest.

        Args:
            conn: Database connection
            backtest_create: Backtest creation data

        Returns:
            Created backtest
        """
        query = """
            INSERT INTO backtests (
                strategy_name, symbol, start_date, end_date,
                initial_capital, config, created_at
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            RETURNING id, strategy_name, symbol, start_date, end_date,
                      initial_capital, status, config, metrics, error_message,
                      created_at, started_at, completed_at
        """

        now = datetime.utcnow()
        row = await conn.fetchrow(
            query,
            backtest_create.strategy_name,
            backtest_create.symbol,
            backtest_create.start_date,
            backtest_create.end_date,
            backtest_create.initial_capital,
            json.dumps(backtest_create.config) if backtest_create.config else None,
            now,
        )

        logger.info(
            f"Created backtest {row['id']} for {backtest_create.strategy_name}"
        )
        return Backtest(**self._parse_json_fields(dict(row)))

    async def get_backtest(
        self, conn: Connection, backtest_id: int
    ) -> Optional[Backtest]:
        """Get backtest by ID.

        Args:
            conn: Database connection
            backtest_id: Backtest ID

        Returns:
            Backtest if found, None otherwise
        """
        query = """
            SELECT id, strategy_name, symbol, start_date, end_date,
                   initial_capital, status, config, metrics, error_message,
                   created_at, started_at, completed_at
            FROM backtests
            WHERE id = $1
        """

        row = await conn.fetchrow(query, backtest_id)
        if row:
            return Backtest(**self._parse_json_fields(dict(row)))
        return None

    async def update_backtest_status(
        self,
        conn: Connection,
        backtest_id: int,
        status: BacktestStatus,
        error_message: Optional[str] = None,
    ) -> Optional[Backtest]:
        """Update backtest status.

        Args:
            conn: Database connection
            backtest_id: Backtest ID
            status: New status
            error_message: Error message if failed

        Returns:
            Updated backtest if found, None otherwise
        """
        now = datetime.utcnow()

        # Set started_at if moving to RUNNING
        # Set completed_at if moving to COMPLETED or FAILED
        if status == BacktestStatus.RUNNING:
            query = """
                UPDATE backtests
                SET status = $1, started_at = $2
                WHERE id = $3
                RETURNING id, strategy_name, symbol, start_date, end_date,
                          initial_capital, status, config, metrics, error_message,
                          created_at, started_at, completed_at
            """
            row = await conn.fetchrow(query, status.value, now, backtest_id)
        elif status in (BacktestStatus.COMPLETED, BacktestStatus.FAILED):
            query = """
                UPDATE backtests
                SET status = $1, completed_at = $2, error_message = $3
                WHERE id = $4
                RETURNING id, strategy_name, symbol, start_date, end_date,
                          initial_capital, status, config, metrics, error_message,
                          created_at, started_at, completed_at
            """
            row = await conn.fetchrow(query, status.value, now, error_message, backtest_id)
        else:
            query = """
                UPDATE backtests
                SET status = $1
                WHERE id = $2
                RETURNING id, strategy_name, symbol, start_date, end_date,
                          initial_capital, status, config, metrics, error_message,
                          created_at, started_at, completed_at
            """
            row = await conn.fetchrow(query, status.value, backtest_id)

        if row:
            return Backtest(**self._parse_json_fields(dict(row)))
        return None

    async def save_backtest_metrics(
        self, conn: Connection, backtest_id: int, metrics: BacktestMetrics
    ) -> Optional[Backtest]:
        """Save backtest metrics.

        Args:
            conn: Database connection
            backtest_id: Backtest ID
            metrics: Backtest metrics

        Returns:
            Updated backtest if found, None otherwise
        """
        query = """
            UPDATE backtests
            SET metrics = $1
            WHERE id = $2
            RETURNING id, strategy_name, symbol, start_date, end_date,
                      initial_capital, status, config, metrics, error_message,
                      created_at, started_at, completed_at
        """

        # Convert model to dict and handle Decimal serialization
        metrics_dict = metrics.model_dump()

        # Convert Decimal to float for JSON serialization
        def decimal_default(obj):
            if isinstance(obj, Decimal):
                return float(obj)
            raise TypeError

        row = await conn.fetchrow(query, json.dumps(metrics_dict, default=decimal_default), backtest_id)

        if row:
            return Backtest(**self._parse_json_fields(dict(row)))
        return None

    async def save_backtest_trade(
        self, conn: Connection, trade: BacktestTrade
    ) -> BacktestTrade:
        """Save a backtest trade.

        Args:
            conn: Database connection
            trade: Backtest trade

        Returns:
            Saved trade with ID
        """
        query = """
            INSERT INTO backtest_trades (
                backtest_id, symbol, side, quantity, price, executed_at,
                pnl, commission, slippage, metadata
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            RETURNING id, backtest_id, symbol, side, quantity, price, executed_at,
                      pnl, commission, slippage, metadata
        """

        row = await conn.fetchrow(
            query,
            trade.backtest_id,
            trade.symbol,
            trade.side,
            trade.quantity,
            trade.price,
            trade.executed_at,
            trade.pnl,
            trade.commission,
            trade.slippage,
            json.dumps(trade.metadata) if trade.metadata else None,
        )

        return BacktestTrade(**self._parse_json_fields(dict(row)))

    async def get_backtest_trades(
        self, conn: Connection, backtest_id: int
    ) -> list[BacktestTrade]:
        """Get all trades for a backtest.

        Args:
            conn: Database connection
            backtest_id: Backtest ID

        Returns:
            List of trades
        """
        query = """
            SELECT id, backtest_id, symbol, side, quantity, price, executed_at,
                   pnl, commission, slippage, metadata
            FROM backtest_trades
            WHERE backtest_id = $1
            ORDER BY executed_at
        """

        rows = await conn.fetch(query, backtest_id)
        return [BacktestTrade(**self._parse_json_fields(dict(row))) for row in rows]

    async def save_equity_curve_point(
        self, conn: Connection, point: EquityCurvePoint
    ) -> EquityCurvePoint:
        """Save an equity curve point.

        Args:
            conn: Database connection
            point: Equity curve point

        Returns:
            Saved point with ID
        """
        query = """
            INSERT INTO backtest_equity_curve (
                backtest_id, timestamp, equity, cash, positions_value
            )
            VALUES ($1, $2, $3, $4, $5)
            RETURNING id, backtest_id, timestamp, equity, cash, positions_value
        """

        row = await conn.fetchrow(
            query,
            point.backtest_id,
            point.timestamp,
            point.equity,
            point.cash,
            point.positions_value,
        )

        return EquityCurvePoint(**dict(row))

    async def get_equity_curve(
        self, conn: Connection, backtest_id: int
    ) -> list[EquityCurvePoint]:
        """Get equity curve for a backtest.

        Args:
            conn: Database connection
            backtest_id: Backtest ID

        Returns:
            List of equity curve points
        """
        query = """
            SELECT id, backtest_id, timestamp, equity, cash, positions_value
            FROM backtest_equity_curve
            WHERE backtest_id = $1
            ORDER BY timestamp
        """

        rows = await conn.fetch(query, backtest_id)
        return [EquityCurvePoint(**dict(row)) for row in rows]

    async def get_all_backtests(
        self,
        conn: Connection,
        strategy_name: Optional[str] = None,
        status: Optional[BacktestStatus] = None,
        limit: int = 100,
    ) -> list[Backtest]:
        """Get all backtests with optional filters.

        Args:
            conn: Database connection
            strategy_name: Filter by strategy name
            status: Filter by status
            limit: Maximum number of results

        Returns:
            List of backtests
        """
        query_parts = [
            """
            SELECT id, strategy_name, symbol, start_date, end_date,
                   initial_capital, status, config, metrics, error_message,
                   created_at, started_at, completed_at
            FROM backtests
            WHERE 1=1
            """
        ]
        params = []
        param_idx = 1

        if strategy_name:
            query_parts.append(f"AND strategy_name = ${param_idx}")
            params.append(strategy_name)
            param_idx += 1

        if status:
            query_parts.append(f"AND status = ${param_idx}")
            params.append(status.value)
            param_idx += 1

        query_parts.append(f"ORDER BY created_at DESC LIMIT ${param_idx}")
        params.append(limit)

        query = " ".join(query_parts)
        rows = await conn.fetch(query, *params)

        return [Backtest(**self._parse_json_fields(dict(row))) for row in rows]

    async def delete_backtest(self, conn: Connection, backtest_id: int) -> bool:
        """Delete a backtest (cascades to trades and equity curve).

        Args:
            conn: Database connection
            backtest_id: Backtest ID

        Returns:
            True if deleted, False if not found
        """
        query = "DELETE FROM backtests WHERE id = $1"
        result = await conn.execute(query, backtest_id)

        deleted = result.split()[-1] == "1"
        if deleted:
            logger.info(f"Deleted backtest {backtest_id}")
        return deleted
