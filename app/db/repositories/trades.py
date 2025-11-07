"""Trades repository for database operations."""

from datetime import datetime
from typing import List, Optional
from decimal import Decimal

from app.db.connection import db_pool
from app.utils.logger import logger


class Trade:
    """Trade model (simplified for repository)."""

    def __init__(
        self,
        id: Optional[int] = None,
        timestamp: datetime = None,
        symbol: str = "",
        side: str = "",
        quantity: Decimal = Decimal(0),
        price: Decimal = Decimal(0),
        commission: Decimal = Decimal(0),
        order_id: Optional[int] = None,
        pnl: Optional[Decimal] = None,
        strategy_name: Optional[str] = None,
        broker: Optional[str] = None
    ):
        self.id = id
        self.timestamp = timestamp or datetime.utcnow()
        self.symbol = symbol
        self.side = side
        self.quantity = quantity
        self.price = price
        self.commission = commission
        self.order_id = order_id
        self.pnl = pnl
        self.strategy_name = strategy_name
        self.broker = broker


class TradesRepository:
    """Repository for trade operations."""

    @staticmethod
    async def create_trade(trade: Trade) -> Optional[int]:
        """
        Create a new trade.

        Args:
            trade: Trade to create

        Returns:
            Optional[int]: Trade ID if created, None otherwise
        """
        try:
            query = """
                INSERT INTO trades (
                    timestamp, symbol, side, quantity, price, commission,
                    order_id, pnl, strategy_name, broker
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                RETURNING id
            """

            trade_id = await db_pool.fetchval(
                query,
                trade.timestamp,
                trade.symbol,
                trade.side,
                trade.quantity,
                trade.price,
                trade.commission,
                trade.order_id,
                trade.pnl,
                trade.strategy_name,
                trade.broker
            )

            logger.info(
                "Created trade",
                extra={
                    "trade_id": trade_id,
                    "symbol": trade.symbol,
                    "side": trade.side,
                    "quantity": str(trade.quantity),
                    "price": str(trade.price)
                }
            )

            return trade_id

        except Exception as e:
            logger.error(
                "Error creating trade",
                extra={"symbol": trade.symbol, "error": str(e)}
            )
            return None

    @staticmethod
    async def get_trade(trade_id: int) -> Optional[Trade]:
        """
        Get a trade by ID.

        Args:
            trade_id: Trade ID

        Returns:
            Optional[Trade]: Trade if found, None otherwise
        """
        try:
            query = """
                SELECT id, timestamp, symbol, side, quantity, price, commission,
                       order_id, pnl, strategy_name, broker
                FROM trades
                WHERE id = $1
            """

            row = await db_pool.fetchrow(query, trade_id)

            if row:
                return Trade(**dict(row))

            return None

        except Exception as e:
            logger.error(
                "Error getting trade",
                extra={"trade_id": trade_id, "error": str(e)}
            )
            return None

    @staticmethod
    async def get_trades(
        symbol: Optional[str] = None,
        side: Optional[str] = None,
        strategy_name: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100
    ) -> List[Trade]:
        """
        Get trades with optional filters.

        Args:
            symbol: Filter by symbol
            side: Filter by side (BUY/SELL)
            strategy_name: Filter by strategy
            start_time: Filter by start time
            end_time: Filter by end time
            limit: Maximum number of trades to return

        Returns:
            List[Trade]: List of trades
        """
        try:
            conditions = []
            params = []
            param_idx = 1

            if symbol:
                conditions.append(f"symbol = ${param_idx}")
                params.append(symbol)
                param_idx += 1

            if side:
                conditions.append(f"side = ${param_idx}")
                params.append(side)
                param_idx += 1

            if strategy_name:
                conditions.append(f"strategy_name = ${param_idx}")
                params.append(strategy_name)
                param_idx += 1

            if start_time:
                conditions.append(f"timestamp >= ${param_idx}")
                params.append(start_time)
                param_idx += 1

            if end_time:
                conditions.append(f"timestamp <= ${param_idx}")
                params.append(end_time)
                param_idx += 1

            where_clause = " AND ".join(conditions) if conditions else "1=1"

            query = f"""
                SELECT id, timestamp, symbol, side, quantity, price, commission,
                       order_id, pnl, strategy_name, broker
                FROM trades
                WHERE {where_clause}
                ORDER BY timestamp DESC
                LIMIT {limit}
            """

            rows = await db_pool.fetch(query, *params)

            return [Trade(**dict(row)) for row in rows]

        except Exception as e:
            logger.error("Error getting trades", extra={"error": str(e)})
            return []

    @staticmethod
    async def get_total_pnl(
        symbol: Optional[str] = None,
        strategy_name: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> Decimal:
        """
        Get total P&L from trades.

        Args:
            symbol: Filter by symbol
            strategy_name: Filter by strategy
            start_time: Filter by start time
            end_time: Filter by end time

        Returns:
            Decimal: Total P&L
        """
        try:
            conditions = []
            params = []
            param_idx = 1

            if symbol:
                conditions.append(f"symbol = ${param_idx}")
                params.append(symbol)
                param_idx += 1

            if strategy_name:
                conditions.append(f"strategy_name = ${param_idx}")
                params.append(strategy_name)
                param_idx += 1

            if start_time:
                conditions.append(f"timestamp >= ${param_idx}")
                params.append(start_time)
                param_idx += 1

            if end_time:
                conditions.append(f"timestamp <= ${param_idx}")
                params.append(end_time)
                param_idx += 1

            where_clause = " AND ".join(conditions) if conditions else "1=1"

            query = f"""
                SELECT COALESCE(SUM(pnl), 0) AS total_pnl
                FROM trades
                WHERE {where_clause}
                AND pnl IS NOT NULL
            """

            total = await db_pool.fetchval(query, *params)

            return Decimal(str(total)) if total else Decimal(0)

        except Exception as e:
            logger.error("Error getting total P&L", extra={"error": str(e)})
            return Decimal(0)

    @staticmethod
    async def get_trade_count(
        symbol: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> int:
        """
        Get count of trades.

        Args:
            symbol: Filter by symbol
            start_time: Filter by start time
            end_time: Filter by end time

        Returns:
            int: Number of trades
        """
        try:
            conditions = []
            params = []
            param_idx = 1

            if symbol:
                conditions.append(f"symbol = ${param_idx}")
                params.append(symbol)
                param_idx += 1

            if start_time:
                conditions.append(f"timestamp >= ${param_idx}")
                params.append(start_time)
                param_idx += 1

            if end_time:
                conditions.append(f"timestamp <= ${param_idx}")
                params.append(end_time)
                param_idx += 1

            where_clause = " AND ".join(conditions) if conditions else "1=1"

            query = f"""
                SELECT COUNT(*) FROM trades
                WHERE {where_clause}
            """

            count = await db_pool.fetchval(query, *params)

            return count or 0

        except Exception as e:
            logger.error("Error getting trade count", extra={"error": str(e)})
            return 0
