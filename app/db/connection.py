"""Database connection pool management using asyncpg."""

import asyncpg
from typing import Optional
from app.config import settings
from app.utils.logger import logger


class DatabasePool:
    """Manages PostgreSQL connection pool using asyncpg."""

    def __init__(self):
        self._pool: Optional[asyncpg.Pool] = None

    async def connect(self) -> None:
        """Create database connection pool."""
        if self._pool is not None:
            logger.warning("Database pool already connected")
            return

        try:
            # Parse the PostgreSQL URL
            db_url = str(settings.database_url)

            self._pool = await asyncpg.create_pool(
                db_url,
                min_size=1,
                max_size=settings.database_pool_size,
                max_inactive_connection_lifetime=300,
                command_timeout=60,
            )

            logger.info(
                "Database connection pool created",
                extra={"pool_size": settings.database_pool_size}
            )

        except Exception as e:
            logger.error("Failed to create database pool", extra={"error": str(e)})
            raise

    async def disconnect(self) -> None:
        """Close database connection pool."""
        if self._pool is None:
            logger.warning("Database pool not connected")
            return

        try:
            await self._pool.close()
            self._pool = None
            logger.info("Database connection pool closed")

        except Exception as e:
            logger.error("Failed to close database pool", extra={"error": str(e)})
            raise

    async def execute(self, query: str, *args) -> str:
        """
        Execute a SQL command.

        Args:
            query: SQL query string
            *args: Query parameters

        Returns:
            str: Command result
        """
        if self._pool is None:
            raise RuntimeError("Database pool not connected")

        async with self._pool.acquire() as connection:
            return await connection.execute(query, *args)

    async def fetch(self, query: str, *args) -> list:
        """
        Fetch multiple rows.

        Args:
            query: SQL query string
            *args: Query parameters

        Returns:
            list: Query results
        """
        if self._pool is None:
            raise RuntimeError("Database pool not connected")

        async with self._pool.acquire() as connection:
            return await connection.fetch(query, *args)

    async def fetchrow(self, query: str, *args) -> Optional[asyncpg.Record]:
        """
        Fetch a single row.

        Args:
            query: SQL query string
            *args: Query parameters

        Returns:
            Optional[asyncpg.Record]: Query result or None
        """
        if self._pool is None:
            raise RuntimeError("Database pool not connected")

        async with self._pool.acquire() as connection:
            return await connection.fetchrow(query, *args)

    async def fetchval(self, query: str, *args):
        """
        Fetch a single value.

        Args:
            query: SQL query string
            *args: Query parameters

        Returns:
            Any: Query result value
        """
        if self._pool is None:
            raise RuntimeError("Database pool not connected")

        async with self._pool.acquire() as connection:
            return await connection.fetchval(query, *args)

    @property
    def pool(self) -> asyncpg.Pool:
        """Get the connection pool."""
        if self._pool is None:
            raise RuntimeError("Database pool not connected")
        return self._pool


# Global database pool instance
db_pool = DatabasePool()
