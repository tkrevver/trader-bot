"""Application configuration using Pydantic settings."""

from typing import Literal
from pydantic import Field, PostgresDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )

    # Application
    app_name: str = Field(default="trader-bot", description="Application name")
    environment: Literal["development", "staging", "production"] = Field(
        default="development",
        description="Environment name"
    )
    log_level: str = Field(default="INFO", description="Logging level")
    debug: bool = Field(default=False, description="Debug mode")

    # Database
    database_url: PostgresDsn = Field(
        default="postgresql://thanh.khuu@localhost:5432/trader_bot_dev",
        description="PostgreSQL connection URL"
    )
    database_pool_size: int = Field(default=10, description="Database connection pool size")
    database_max_overflow: int = Field(default=20, description="Database max overflow connections")

    # Polygon.io (Massive)
    polygon_api_key: str = Field(default="", description="Polygon.io API key")
    polygon_websocket_url: str = Field(
        default="wss://socket.polygon.io/stocks",
        description="Polygon.io WebSocket URL"
    )
    polygon_rest_url: str = Field(
        default="https://api.polygon.io",
        description="Polygon.io REST API URL"
    )

    # Broker
    broker: Literal["paper", "tastytrade", "tradier"] = Field(
        default="paper",
        description="Broker to use for trading"
    )

    # Tastytrade
    tastytrade_username: str = Field(default="", description="Tastytrade username")
    tastytrade_password: str = Field(default="", description="Tastytrade password")
    tastytrade_account_number: str = Field(default="", description="Tastytrade account number")

    # Tradier
    tradier_access_token: str = Field(default="", description="Tradier access token")
    tradier_account_id: str = Field(default="", description="Tradier account ID")
    tradier_base_url: str = Field(
        default="https://api.tradier.com/v1",
        description="Tradier API base URL"
    )

    # Trading
    initial_capital: float = Field(default=100000.0, description="Initial capital for paper trading")
    max_position_size_pct: float = Field(default=0.10, description="Max position size as % of portfolio")
    max_portfolio_exposure: float = Field(default=1.0, description="Max portfolio exposure (1.0 = 100%)")
    daily_loss_limit_pct: float = Field(default=0.02, description="Daily loss limit as % (0.02 = 2%)")
    default_slippage_bps: int = Field(default=5, description="Default slippage in basis points")

    # Risk Management
    enable_trading: bool = Field(default=False, description="Enable trading (safety flag)")
    enable_live_trading: bool = Field(default=False, description="Enable live trading with real money")

    # Timezone
    timezone: str = Field(default="America/New_York", description="Trading timezone")

    # Server
    host: str = Field(default="0.0.0.0", description="Server host")
    port: int = Field(default=8000, description="Server port")


# Global settings instance
settings = Settings()
