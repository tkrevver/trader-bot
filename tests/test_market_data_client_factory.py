"""Tests for market data client factory."""

import pytest
from app.services.market_data_client_factory import (
    get_market_data_client,
    get_all_supported_providers
)
from app.services.tradier_client import TradierClient
from app.services.alpaca_client import AlpacaClient
from app.config import settings


def test_get_tradier_client(monkeypatch):
    """Test factory returns TradierClient when configured."""
    monkeypatch.setattr(settings, "market_data_provider", "tradier")

    client = get_market_data_client()

    assert isinstance(client, TradierClient)
    assert client.provider_name == "tradier"


def test_get_alpaca_client(monkeypatch):
    """Test factory returns AlpacaClient when configured."""
    monkeypatch.setattr(settings, "market_data_provider", "alpaca")

    client = get_market_data_client()

    assert isinstance(client, AlpacaClient)
    assert client.provider_name == "alpaca"


def test_invalid_provider(monkeypatch):
    """Test factory raises error for unsupported provider."""
    monkeypatch.setattr(settings, "market_data_provider", "invalid")

    with pytest.raises(ValueError) as exc_info:
        get_market_data_client()

    assert "Unsupported market data provider" in str(exc_info.value)
    assert "invalid" in str(exc_info.value)


def test_get_all_supported_providers():
    """Test getting list of all supported providers."""
    providers = get_all_supported_providers()

    assert isinstance(providers, list)
    assert "tradier" in providers
    assert "alpaca" in providers
    assert len(providers) == 2
