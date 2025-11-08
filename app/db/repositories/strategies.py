"""Strategy repository for database operations."""

from datetime import datetime
from typing import Optional
from asyncpg import Connection
from asyncpg.pool import Pool

from app.models.strategy import Strategy, StrategyCreate, StrategyUpdate
from app.utils.logger import logger



class StrategyRepository:
    """Repository for strategy database operations."""

    def __init__(self, db_pool: Pool):
        """Initialize repository with database pool.

        Args:
            db_pool: Database connection pool
        """
        self.db_pool = db_pool

    async def create_strategy(
        self, conn: Connection, strategy: StrategyCreate
    ) -> Strategy:
        """Create a new strategy.

        Args:
            conn: Database connection
            strategy: Strategy creation data

        Returns:
            Created strategy

        Raises:
            Exception: If strategy name already exists
        """
        query = """
            INSERT INTO strategies (
                name, description, version, author, is_active,
                symbols, timeframes, config, created_at, updated_at
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            RETURNING id, name, description, version, author, is_active,
                      symbols, timeframes, config, created_at, updated_at
        """

        now = datetime.utcnow()
        row = await conn.fetchrow(
            query,
            strategy.name,
            strategy.description,
            strategy.version,
            strategy.author,
            strategy.is_active,
            strategy.symbols,
            strategy.timeframes,
            strategy.config,
            now,
            now,
        )

        logger.info(f"Created strategy: {strategy.name}")
        return Strategy(**dict(row))

    async def get_strategy(self, conn: Connection, strategy_id: int) -> Optional[Strategy]:
        """Get strategy by ID.

        Args:
            conn: Database connection
            strategy_id: Strategy ID

        Returns:
            Strategy if found, None otherwise
        """
        query = """
            SELECT id, name, description, version, author, is_active,
                   symbols, timeframes, config, created_at, updated_at
            FROM strategies
            WHERE id = $1
        """

        row = await conn.fetchrow(query, strategy_id)
        if row:
            return Strategy(**dict(row))
        return None

    async def get_strategy_by_name(
        self, conn: Connection, name: str
    ) -> Optional[Strategy]:
        """Get strategy by name.

        Args:
            conn: Database connection
            name: Strategy name

        Returns:
            Strategy if found, None otherwise
        """
        query = """
            SELECT id, name, description, version, author, is_active,
                   symbols, timeframes, config, created_at, updated_at
            FROM strategies
            WHERE name = $1
        """

        row = await conn.fetchrow(query, name)
        if row:
            return Strategy(**dict(row))
        return None

    async def get_all_strategies(
        self, conn: Connection, active_only: bool = False
    ) -> list[Strategy]:
        """Get all strategies.

        Args:
            conn: Database connection
            active_only: If True, return only active strategies

        Returns:
            List of strategies
        """
        if active_only:
            query = """
                SELECT id, name, description, version, author, is_active,
                       symbols, timeframes, config, created_at, updated_at
                FROM strategies
                WHERE is_active = TRUE
                ORDER BY name
            """
        else:
            query = """
                SELECT id, name, description, version, author, is_active,
                       symbols, timeframes, config, created_at, updated_at
                FROM strategies
                ORDER BY name
            """

        rows = await conn.fetch(query)
        return [Strategy(**dict(row)) for row in rows]

    async def update_strategy(
        self, conn: Connection, strategy_id: int, update: StrategyUpdate
    ) -> Optional[Strategy]:
        """Update strategy.

        Args:
            conn: Database connection
            strategy_id: Strategy ID
            update: Strategy update data

        Returns:
            Updated strategy if found, None otherwise
        """
        # Build dynamic UPDATE query based on provided fields
        update_fields = []
        params = []
        param_idx = 1

        update_dict = update.model_dump(exclude_unset=True)
        for field, value in update_dict.items():
            update_fields.append(f"{field} = ${param_idx}")
            params.append(value)
            param_idx += 1

        if not update_fields:
            # No fields to update
            return await self.get_strategy(conn, strategy_id)

        # Add updated_at
        update_fields.append(f"updated_at = ${param_idx}")
        params.append(datetime.utcnow())
        param_idx += 1

        # Add strategy_id as last parameter
        params.append(strategy_id)

        query = f"""
            UPDATE strategies
            SET {', '.join(update_fields)}
            WHERE id = ${param_idx}
            RETURNING id, name, description, version, author, is_active,
                      symbols, timeframes, config, created_at, updated_at
        """

        row = await conn.fetchrow(query, *params)
        if row:
            logger.info(f"Updated strategy ID {strategy_id}")
            return Strategy(**dict(row))
        return None

    async def delete_strategy(self, conn: Connection, strategy_id: int) -> bool:
        """Delete strategy.

        Args:
            conn: Database connection
            strategy_id: Strategy ID

        Returns:
            True if deleted, False if not found
        """
        query = "DELETE FROM strategies WHERE id = $1"
        result = await conn.execute(query, strategy_id)

        # Check if any rows were deleted
        deleted = result.split()[-1] == "1"
        if deleted:
            logger.info(f"Deleted strategy ID {strategy_id}")
        return deleted

    async def activate_strategy(
        self, conn: Connection, strategy_id: int
    ) -> Optional[Strategy]:
        """Activate a strategy.

        Args:
            conn: Database connection
            strategy_id: Strategy ID

        Returns:
            Updated strategy if found, None otherwise
        """
        return await self.update_strategy(
            conn, strategy_id, StrategyUpdate(is_active=True)
        )

    async def deactivate_strategy(
        self, conn: Connection, strategy_id: int
    ) -> Optional[Strategy]:
        """Deactivate a strategy.

        Args:
            conn: Database connection
            strategy_id: Strategy ID

        Returns:
            Updated strategy if found, None otherwise
        """
        return await self.update_strategy(
            conn, strategy_id, StrategyUpdate(is_active=False)
        )

    async def get_active_strategies(self, conn: Connection) -> list[Strategy]:
        """Get all active strategies.

        Args:
            conn: Database connection

        Returns:
            List of active strategies
        """
        return await self.get_all_strategies(conn, active_only=True)
