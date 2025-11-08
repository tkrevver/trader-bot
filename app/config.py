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

    # Broker
    broker: Literal["paper", "tastytrade", "tradier"] = Field(
        default="paper",
        description="Broker to use for trading"
    )

    # Tastytrade
    tastytrade_username: str = Field(default="", description="Tastytrade username")
    tastytrade_password: str = Field(default="", description="Tastytrade password")
    tastytrade_account_number: str = Field(default="", description="Tastytrade account number")

    # Tradier (Market Data & Brokerage)
    tradier_api_token: str = Field(default="", description="Tradier API token")
    tradier_api_url: str = Field(
        default="https://api.tradier.com",
        description="Tradier API base URL"
    )
    tradier_account_id: str = Field(default="", description="Tradier account ID (for trading)")

    # Alpaca (Market Data & Brokerage)
    alpaca_api_key: str = Field(default="", description="Alpaca API key ID")
    alpaca_api_secret: str = Field(default="", description="Alpaca API secret key")
    alpaca_data_api_url: str = Field(
        default="https://data.alpaca.markets",
        description="Alpaca Data API base URL"
    )
    alpaca_trading_api_url: str = Field(
        default="https://paper-api.alpaca.markets",
        description="Alpaca Trading API base URL (paper or live)"
    )

    # Market Data Provider Selection
    market_data_provider: Literal["tradier", "alpaca"] = Field(
        default="tradier",
        description="Market data provider to use (tradier or alpaca)"
    )

    # Trading
    initial_capital: float = Field(default=100000.0, description="Initial capital for paper trading")
    max_position_size_pct: float = Field(default=0.10, description="Max position size as % of portfolio")
    max_portfolio_exposure: float = Field(default=1.0, description="Max portfolio exposure (1.0 = 100%)")
    daily_loss_limit_pct: float = Field(default=0.02, description="Daily loss limit as % (0.02 = 2%)")
    default_slippage_bps: int = Field(default=5, description="Default slippage in basis points")

    # Market Hours
    enable_extended_hours: bool = Field(default=False, description="Enable extended hours trading (4 AM - 8 PM ET)")

    # Risk Management
    enable_trading: bool = Field(default=False, description="Enable trading (safety flag)")
    enable_live_trading: bool = Field(default=False, description="Enable live trading with real money")

    # Timezone
    timezone: str = Field(default="America/New_York", description="Trading timezone")

    # Server
    host: str = Field(default="0.0.0.0", description="Server host")
    port: int = Field(default=8000, description="Server port")

    @property
    def tradier_session_filter(self) -> str:
        """
        Get the appropriate Tradier session filter based on extended hours setting.

        Returns:
            "all" if extended hours enabled (4 AM - 8 PM ET), "open" otherwise (9:30 AM - 4 PM ET)
        """
        return "all" if self.enable_extended_hours else "open"


# Global settings instance
settings = Settings()
