"""Orders repository for database operations."""

from datetime import datetime
from typing import List, Optional

from app.db.connection import db_pool
from app.models.orders import Order, OrderStatus
from app.utils.logger import logger


class OrdersRepository:
    """Repository for order operations."""

    @staticmethod
    async def create_order(order: Order) -> Optional[int]:
        """
        Create a new order.

        Args:
            order: Order to create

        Returns:
            Optional[int]: Order ID if created, None otherwise
        """
        try:
            query = """
                INSERT INTO orders (
                    timestamp, symbol, side, quantity, order_type, limit_price, stop_price,
                    status, filled_quantity, filled_price, broker_order_id,
                    strategy_name, signal_id, updated_at
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
                RETURNING id
            """

            order_id = await db_pool.fetchval(
                query,
                order.timestamp,
                order.symbol,
                order.side,
                order.quantity,
                order.order_type,
                order.limit_price,
                order.stop_price,
                order.status,
                order.filled_quantity,
                order.filled_price,
                order.broker_order_id,
                order.strategy_name,
                order.signal_id,
                order.updated_at
            )

            logger.info(
                "Created order",
                extra={
                    "order_id": order_id,
                    "symbol": order.symbol,
                    "side": order.side,
                    "quantity": str(order.quantity),
                    "type": order.order_type
                }
            )

            return order_id

        except Exception as e:
            logger.error(
                "Error creating order",
                extra={"symbol": order.symbol, "error": str(e)}
            )
            return None

    @staticmethod
    async def get_order(order_id: int) -> Optional[Order]:
        """
        Get an order by ID.

        Args:
            order_id: Order ID

        Returns:
            Optional[Order]: Order if found, None otherwise
        """
        try:
            query = """
                SELECT id, timestamp, symbol, side, quantity, order_type, limit_price, stop_price,
                       status, filled_quantity, filled_price, broker_order_id,
                       strategy_name, signal_id, updated_at
                FROM orders
                WHERE id = $1
            """

            row = await db_pool.fetchrow(query, order_id)

            if row:
                return Order(**dict(row))

            return None

        except Exception as e:
            logger.error(
                "Error getting order",
                extra={"order_id": order_id, "error": str(e)}
            )
            return None

    @staticmethod
    async def update_order(order_id: int, **updates) -> bool:
        """
        Update an order.

        Args:
            order_id: Order ID
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

            # Add order_id as last parameter
            params.append(order_id)

            query = f"""
                UPDATE orders
                SET {", ".join(set_clauses)}
                WHERE id = ${param_idx}
            """

            await db_pool.execute(query, *params)

            logger.info(
                "Updated order",
                extra={"order_id": order_id, "updates": updates}
            )

            return True

        except Exception as e:
            logger.error(
                "Error updating order",
                extra={"order_id": order_id, "error": str(e)}
            )
            return False

    @staticmethod
    async def get_orders(
        symbol: Optional[str] = None,
        status: Optional[str] = None,
        strategy_name: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100
    ) -> List[Order]:
        """
        Get orders with optional filters.

        Args:
            symbol: Filter by symbol
            status: Filter by status
            strategy_name: Filter by strategy
            start_time: Filter by start time
            end_time: Filter by end time
            limit: Maximum number of orders to return

        Returns:
            List[Order]: List of orders
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
                SELECT id, timestamp, symbol, side, quantity, order_type, limit_price, stop_price,
                       status, filled_quantity, filled_price, broker_order_id,
                       strategy_name, signal_id, updated_at
                FROM orders
                WHERE {where_clause}
                ORDER BY timestamp DESC
                LIMIT {limit}
            """

            rows = await db_pool.fetch(query, *params)

            return [Order(**dict(row)) for row in rows]

        except Exception as e:
            logger.error("Error getting orders", extra={"error": str(e)})
            return []

    @staticmethod
    async def get_pending_orders() -> List[Order]:
        """
        Get all pending/submitted orders.

        Returns:
            List[Order]: List of pending orders
        """
        try:
            query = """
                SELECT id, timestamp, symbol, side, quantity, order_type, limit_price, stop_price,
                       status, filled_quantity, filled_price, broker_order_id,
                       strategy_name, signal_id, updated_at
                FROM orders
                WHERE status IN ('PENDING', 'SUBMITTED', 'PARTIALLY_FILLED')
                ORDER BY timestamp ASC
            """

            rows = await db_pool.fetch(query)

            return [Order(**dict(row)) for row in rows]

        except Exception as e:
            logger.error("Error getting pending orders", extra={"error": str(e)})
            return []
