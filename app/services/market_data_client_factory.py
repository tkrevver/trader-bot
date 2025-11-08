"""Factory for creating market data clients based on configuration."""

from app.services.base_market_data_client import BaseMarketDataClient
from app.services.tradier_client import TradierClient
from app.services.alpaca_client import AlpacaClient
from app.config import settings
from app.utils.logger import logger


def get_market_data_client() -> BaseMarketDataClient:
    """
    Get the configured market data client.

    Returns the appropriate market data client based on the
    MARKET_DATA_PROVIDER environment variable setting.

    Returns:
        BaseMarketDataClient: Configured market data client (Tradier or Alpaca)

    Raises:
        ValueError: If the configured provider is not supported
    """
    provider = settings.market_data_provider.lower()

    if provider == "tradier":
        logger.info(
            "Using Tradier as market data provider",
            extra={"provider": "tradier"}
        )
        return TradierClient()
    elif provider == "alpaca":
        logger.info(
            "Using Alpaca as market data provider",
            extra={"provider": "alpaca"}
        )
        return AlpacaClient()
    else:
        raise ValueError(
            f"Unsupported market data provider: {provider}. "
            f"Supported providers: tradier, alpaca"
        )


def get_all_supported_providers() -> list[str]:
    """
    Get list of all supported market data providers.

    Returns:
        list[str]: List of supported provider names
    """
    return ["tradier", "alpaca"]
