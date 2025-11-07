"""Positions repository for database operations."""

from datetime import datetime
from typing import List, Optional
from decimal import Decimal

from app.db.connection import db_pool
from app.models.positions import Position
from app.utils.logger import logger


class PositionsRepository:
    """Repository for position operations."""

    @staticmethod
    async def create_position(position: Position) -> Optional[int]:
        """
        Create a new position.

        Args:
            position: Position to create

        Returns:
            Optional[int]: Position ID if created, None otherwise
        """
        try:
            query = """
                INSERT INTO positions (
                    symbol, quantity, avg_entry_price, current_price, unrealized_pnl,
                    realized_pnl, opened_at, closed_at, status, strategy_name
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                RETURNING id
            """

            position_id = await db_pool.fetchval(
                query,
                position.symbol,
                position.quantity,
                position.avg_entry_price,
                position.current_price,
                position.unrealized_pnl,
                position.realized_pnl,
                position.opened_at,
                position.closed_at,
                position.status,
                position.strategy_name
            )

            logger.info(
                "Created position",
                extra={
                    "position_id": position_id,
                    "symbol": position.symbol,
                    "quantity": str(position.quantity),
                    "entry_price": str(position.avg_entry_price)
                }
            )

            return position_id

        except Exception as e:
            logger.error(
                "Error creating position",
                extra={"symbol": position.symbol, "error": str(e)}
            )
            return None

    @staticmethod
    async def get_position(position_id: int) -> Optional[Position]:
        """
        Get a position by ID.

        Args:
            position_id: Position ID

        Returns:
            Optional[Position]: Position if found, None otherwise
        """
        try:
            query = """
                SELECT id, symbol, quantity, avg_entry_price, current_price, unrealized_pnl,
                       realized_pnl, opened_at, closed_at, status, strategy_name
                FROM positions
                WHERE id = $1
            """

            row = await db_pool.fetchrow(query, position_id)

            if row:
                return Position(**dict(row))

            return None

        except Exception as e:
            logger.error(
                "Error getting position",
                extra={"position_id": position_id, "error": str(e)}
            )
            return None

    @staticmethod
    async def get_open_position(symbol: str, strategy_name: Optional[str] = None) -> Optional[Position]:
        """
        Get open position for a symbol.

        Args:
            symbol: Trading symbol
            strategy_name: Optional strategy name filter

        Returns:
            Optional[Position]: Open position if found, None otherwise
        """
        try:
            if strategy_name:
                query = """
                    SELECT id, symbol, quantity, avg_entry_price, current_price, unrealized_pnl,
                           realized_pnl, opened_at, closed_at, status, strategy_name
                    FROM positions
                    WHERE symbol = $1 AND strategy_name = $2 AND status = 'OPEN'
                    ORDER BY opened_at DESC
                    LIMIT 1
                """
                row = await db_pool.fetchrow(query, symbol, strategy_name)
            else:
                query = """
                    SELECT id, symbol, quantity, avg_entry_price, current_price, unrealized_pnl,
                           realized_pnl, opened_at, closed_at, status, strategy_name
                    FROM positions
                    WHERE symbol = $1 AND status = 'OPEN'
                    ORDER BY opened_at DESC
                    LIMIT 1
                """
                row = await db_pool.fetchrow(query, symbol)

            if row:
                return Position(**dict(row))

            return None

        except Exception as e:
            logger.error(
                "Error getting open position",
                extra={"symbol": symbol, "error": str(e)}
            )
            return None

    @staticmethod
    async def get_open_positions() -> List[Position]:
        """
        Get all open positions.

        Returns:
            List[Position]: List of open positions
        """
        try:
            query = """
                SELECT id, symbol, quantity, avg_entry_price, current_price, unrealized_pnl,
                       realized_pnl, opened_at, closed_at, status, strategy_name
                FROM positions
                WHERE status = 'OPEN'
                ORDER BY opened_at DESC
            """

            rows = await db_pool.fetch(query)

            return [Position(**dict(row)) for row in rows]

        except Exception as e:
            logger.error("Error getting open positions", extra={"error": str(e)})
            return []

    @staticmethod
    async def update_position(position_id: int, **updates) -> bool:
        """
        Update a position.

        Args:
            position_id: Position ID
            **updates: Fields to update

        Returns:
            bool: True if updated, False otherwise
        """
        try:
            # Build SET clause dynamically
            set_clauses = []
            params = []
            param_idx = 1

            for key, value in updates.items():
                if key != "id":  # Don't update ID
                    set_clauses.append(f"{key} = ${param_idx}")
                    params.append(value)
                    param_idx += 1

            # Always update updated_at
            set_clauses.append(f"updated_at = ${param_idx}")
            params.append(datetime.utcnow())
            param_idx += 1

            # Add position_id as last parameter
            params.append(position_id)

            query = f"""
                UPDATE positions
                SET {", ".join(set_clauses)}
                WHERE id = ${param_idx}
            """

            await db_pool.execute(query, *params)

            logger.info(
                "Updated position",
                extra={"position_id": position_id, "updates": updates}
            )

            return True

        except Exception as e:
            logger.error(
                "Error updating position",
                extra={"position_id": position_id, "error": str(e)}
            )
            return False

    @staticmethod
    async def close_position(
        position_id: int,
        realized_pnl: Decimal,
        closed_at: Optional[datetime] = None
    ) -> bool:
        """
        Close a position.

        Args:
            position_id: Position ID
            realized_pnl: Realized P&L
            closed_at: Close timestamp (defaults to now)

        Returns:
            bool: True if closed, False otherwise
        """
        try:
            if closed_at is None:
                closed_at = datetime.utcnow()

            query = """
                UPDATE positions
                SET status = 'CLOSED',
                    closed_at = $1,
                    realized_pnl = $2,
                    unrealized_pnl = 0,
                    updated_at = $3
                WHERE id = $4
            """

            await db_pool.execute(query, closed_at, realized_pnl, datetime.utcnow(), position_id)

            logger.info(
                "Closed position",
                extra={
                    "position_id": position_id,
                    "realized_pnl": str(realized_pnl),
                    "closed_at": closed_at.isoformat()
                }
            )

            return True

        except Exception as e:
            logger.error(
                "Error closing position",
                extra={"position_id": position_id, "error": str(e)}
            )
            return False

    @staticmethod
    async def get_positions(
        symbol: Optional[str] = None,
        status: Optional[str] = None,
        strategy_name: Optional[str] = None,
        limit: int = 100
    ) -> List[Position]:
        """
        Get positions with optional filters.

        Args:
            symbol: Filter by symbol
            status: Filter by status (OPEN/CLOSED)
            strategy_name: Filter by strategy
            limit: Maximum number of positions to return

        Returns:
            List[Position]: List of positions
        """
        try:
            conditions = []
            params = []
            param_idx = 1

            if symbol:
                conditions.append(f"symbol = ${param_idx}")
                params.append(symbol)
                param_idx += 1

            if status:
                conditions.append(f"status = ${param_idx}")
                params.append(status)
                param_idx += 1

            if strategy_name:
                conditions.append(f"strategy_name = ${param_idx}")
                params.append(strategy_name)
                param_idx += 1

            where_clause = " AND ".join(conditions) if conditions else "1=1"

            query = f"""
                SELECT id, symbol, quantity, avg_entry_price, current_price, unrealized_pnl,
                       realized_pnl, opened_at, closed_at, status, strategy_name
                FROM positions
                WHERE {where_clause}
                ORDER BY opened_at DESC
                LIMIT {limit}
            """

            rows = await db_pool.fetch(query, *params)

            return [Position(**dict(row)) for row in rows]

        except Exception as e:
            logger.error("Error getting positions", extra={"error": str(e)})
            return []

    @staticmethod
    async def get_total_pnl() -> dict:
        """
        Get total realized and unrealized P&L across all positions.

        Returns:
            dict: Dictionary with total_realized_pnl and total_unrealized_pnl
        """
        try:
            query = """
                SELECT
                    COALESCE(SUM(realized_pnl), 0) AS total_realized,
                    COALESCE(SUM(CASE WHEN status = 'OPEN' THEN unrealized_pnl ELSE 0 END), 0) AS total_unrealized
                FROM positions
            """

            row = await db_pool.fetchrow(query)

            return {
                "total_realized_pnl": Decimal(str(row["total_realized"])),
                "total_unrealized_pnl": Decimal(str(row["total_unrealized"]))
            }

        except Exception as e:
            logger.error("Error getting total P&L", extra={"error": str(e)})
            return {
                "total_realized_pnl": Decimal(0),
                "total_unrealized_pnl": Decimal(0)
            }
