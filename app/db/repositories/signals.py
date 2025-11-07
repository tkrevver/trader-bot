"""Signals repository for database operations."""

from datetime import datetime
from typing import List, Optional

from app.db.connection import db_pool
from app.models.signals import Signal
from app.utils.logger import logger


class SignalsRepository:
    """Repository for signal operations."""

    @staticmethod
    async def create_signal(signal: Signal) -> Optional[int]:
        """
        Create a new signal.

        Args:
            signal: Signal to create

        Returns:
            Optional[int]: Signal ID if created, None otherwise
        """
        try:
            query = """
                INSERT INTO signals (
                    timestamp, symbol, signal_type, confidence, strategy_name,
                    timeframe, metadata, approved, rejection_reason
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                RETURNING id
            """

            signal_id = await db_pool.fetchval(
                query,
                signal.timestamp,
                signal.symbol,
                signal.signal_type,
                signal.confidence,
                signal.strategy_name,
                signal.timeframe,
                signal.metadata,
                signal.approved,
                signal.rejection_reason
            )

            logger.info(
                "Created signal",
                extra={
                    "signal_id": signal_id,
                    "symbol": signal.symbol,
                    "type": signal.signal_type,
                    "strategy": signal.strategy_name
                }
            )

            return signal_id

        except Exception as e:
            logger.error(
                "Error creating signal",
                extra={"symbol": signal.symbol, "error": str(e)}
            )
            return None

    @staticmethod
    async def get_signal(signal_id: int) -> Optional[Signal]:
        """
        Get a signal by ID.

        Args:
            signal_id: Signal ID

        Returns:
            Optional[Signal]: Signal if found, None otherwise
        """
        try:
            query = """
                SELECT id, timestamp, symbol, signal_type, confidence, strategy_name,
                       timeframe, metadata, approved, rejection_reason
                FROM signals
                WHERE id = $1
            """

            row = await db_pool.fetchrow(query, signal_id)

            if row:
                return Signal(**dict(row))

            return None

        except Exception as e:
            logger.error(
                "Error getting signal",
                extra={"signal_id": signal_id, "error": str(e)}
            )
            return None

    @staticmethod
    async def get_signals(
        symbol: Optional[str] = None,
        strategy_name: Optional[str] = None,
        approved: Optional[bool] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100
    ) -> List[Signal]:
        """
        Get signals with optional filters.

        Args:
            symbol: Filter by symbol
            strategy_name: Filter by strategy
            approved: Filter by approval status
            start_time: Filter by start time
            end_time: Filter by end time
            limit: Maximum number of signals to return

        Returns:
            List[Signal]: List of signals
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

            if approved is not None:
                conditions.append(f"approved = ${param_idx}")
                params.append(approved)
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
                SELECT id, timestamp, symbol, signal_type, confidence, strategy_name,
                       timeframe, metadata, approved, rejection_reason
                FROM signals
                WHERE {where_clause}
                ORDER BY timestamp DESC
                LIMIT {limit}
            """

            rows = await db_pool.fetch(query, *params)

            return [Signal(**dict(row)) for row in rows]

        except Exception as e:
            logger.error("Error getting signals", extra={"error": str(e)})
            return []

    @staticmethod
    async def update_signal_approval(
        signal_id: int,
        approved: bool,
        rejection_reason: Optional[str] = None
    ) -> bool:
        """
        Update signal approval status.

        Args:
            signal_id: Signal ID
            approved: Approval status
            rejection_reason: Reason for rejection (if not approved)

        Returns:
            bool: True if updated, False otherwise
        """
        try:
            query = """
                UPDATE signals
                SET approved = $1, rejection_reason = $2
                WHERE id = $3
            """

            await db_pool.execute(query, approved, rejection_reason, signal_id)

            logger.info(
                "Updated signal approval",
                extra={
                    "signal_id": signal_id,
                    "approved": approved,
                    "rejection_reason": rejection_reason
                }
            )

            return True

        except Exception as e:
            logger.error(
                "Error updating signal approval",
                extra={"signal_id": signal_id, "error": str(e)}
            )
            return False

    @staticmethod
    async def get_recent_signals(strategy_name: str, minutes: int = 60) -> List[Signal]:
        """
        Get recent signals for a strategy.

        Args:
            strategy_name: Strategy name
            minutes: Number of minutes to look back

        Returns:
            List[Signal]: List of recent signals
        """
        try:
            query = """
                SELECT id, timestamp, symbol, signal_type, confidence, strategy_name,
                       timeframe, metadata, approved, rejection_reason
                FROM signals
                WHERE strategy_name = $1
                AND timestamp >= NOW() - INTERVAL '1 minute' * $2
                ORDER BY timestamp DESC
            """

            rows = await db_pool.fetch(query, strategy_name, minutes)

            return [Signal(**dict(row)) for row in rows]

        except Exception as e:
            logger.error(
                "Error getting recent signals",
                extra={"strategy_name": strategy_name, "error": str(e)}
            )
            return []
