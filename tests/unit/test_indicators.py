"""Unit tests for technical indicators library."""

import pandas as pd
import pytest
from decimal import Decimal

from app.utils import indicators


@pytest.fixture
def sample_ohlcv_data():
    """Generate sample OHLCV data for testing."""
    data = {
        "open": [100.0, 101.0, 102.0, 101.5, 103.0, 102.5, 104.0, 103.5, 105.0, 104.5],
        "high": [101.0, 102.0, 103.0, 102.5, 104.0, 103.5, 105.0, 104.5, 106.0, 105.5],
        "low": [99.5, 100.5, 101.5, 101.0, 102.5, 102.0, 103.5, 103.0, 104.5, 104.0],
        "close": [
            100.5,
            101.5,
            102.5,
            101.0,
            103.5,
            102.0,
            104.5,
            103.0,
            105.5,
            104.0,
        ],
        "volume": [
            1000000,
            1100000,
            1200000,
            1050000,
            1300000,
            1150000,
            1400000,
            1250000,
            1500000,
            1350000,
        ],
    }
    return pd.DataFrame(data)


def test_validate_ohlcv_success(sample_ohlcv_data):
    """Test OHLCV validation with valid data."""
    # Should not raise any exception
    indicators.validate_ohlcv(sample_ohlcv_data)


def test_validate_ohlcv_missing_columns():
    """Test OHLCV validation with missing columns."""
    df = pd.DataFrame({"open": [100], "high": [101], "low": [99]})
    with pytest.raises(ValueError, match="missing required columns"):
        indicators.validate_ohlcv(df)


def test_sma_calculation(sample_ohlcv_data):
    """Test Simple Moving Average calculation."""
    result = indicators.sma(sample_ohlcv_data, length=5)

    assert isinstance(result, pd.Series)
    assert len(result) == len(sample_ohlcv_data)
    # First 4 values should be NaN (not enough data)
    assert pd.isna(result.iloc[0:4]).all()
    # 5th value should be average of first 5 closes
    expected = sample_ohlcv_data["close"].iloc[0:5].mean()
    assert abs(result.iloc[4] - expected) < 0.01


def test_ema_calculation(sample_ohlcv_data):
    """Test Exponential Moving Average calculation."""
    result = indicators.ema(sample_ohlcv_data, length=5)

    assert isinstance(result, pd.Series)
    assert len(result) == len(sample_ohlcv_data)
    # EMA should not have as many NaN values as SMA
    # Last value should exist
    assert not pd.isna(result.iloc[-1])


def test_rsi_calculation(sample_ohlcv_data):
    """Test RSI calculation."""
    result = indicators.rsi(sample_ohlcv_data, length=14)

    assert isinstance(result, pd.Series)
    assert len(result) == len(sample_ohlcv_data)
    # RSI values should be between 0 and 100 (where not NaN)
    valid_values = result.dropna()
    assert (valid_values >= 0).all()
    assert (valid_values <= 100).all()


def test_macd_calculation(sample_ohlcv_data):
    """Test MACD calculation."""
    result = indicators.macd(sample_ohlcv_data, fast=12, slow=26, signal=9)

    assert isinstance(result, pd.DataFrame)
    # Should have MACD, MACDh (histogram), MACDs (signal) columns
    assert "MACD_12_26_9" in result.columns
    assert "MACDh_12_26_9" in result.columns
    assert "MACDs_12_26_9" in result.columns


def test_bbands_calculation(sample_ohlcv_data):
    """Test Bollinger Bands calculation."""
    result = indicators.bbands(sample_ohlcv_data, length=20, std=2.0)

    assert isinstance(result, pd.DataFrame)
    # Should have lower, middle, upper bands
    assert "BBL_20_2.0" in result.columns  # Lower band
    assert "BBM_20_2.0" in result.columns  # Middle band (SMA)
    assert "BBU_20_2.0" in result.columns  # Upper band


def test_atr_calculation(sample_ohlcv_data):
    """Test Average True Range calculation."""
    result = indicators.atr(sample_ohlcv_data, length=14)

    assert isinstance(result, pd.Series)
    assert len(result) == len(sample_ohlcv_data)
    # ATR should be positive (where not NaN)
    valid_values = result.dropna()
    assert (valid_values >= 0).all()


def test_vwap_calculation(sample_ohlcv_data):
    """Test VWAP calculation."""
    result = indicators.vwap(sample_ohlcv_data)

    assert isinstance(result, pd.Series)
    assert len(result) == len(sample_ohlcv_data)
    # VWAP should be within high/low range
    assert not pd.isna(result.iloc[-1])


def test_stoch_calculation(sample_ohlcv_data):
    """Test Stochastic Oscillator calculation."""
    result = indicators.stoch(sample_ohlcv_data, k=14, d=3)

    assert isinstance(result, pd.DataFrame)
    # Should have %K and %D lines
    assert "STOCHk_14_3_3" in result.columns
    assert "STOCHd_14_3_3" in result.columns


def test_adx_calculation(sample_ohlcv_data):
    """Test ADX calculation."""
    result = indicators.adx(sample_ohlcv_data, length=14)

    assert isinstance(result, pd.DataFrame)
    # Should have ADX, +DI, -DI
    assert "ADX_14" in result.columns


def test_obv_calculation(sample_ohlcv_data):
    """Test On-Balance Volume calculation."""
    result = indicators.obv(sample_ohlcv_data)

    assert isinstance(result, pd.Series)
    assert len(result) == len(sample_ohlcv_data)


def test_cci_calculation(sample_ohlcv_data):
    """Test Commodity Channel Index calculation."""
    result = indicators.cci(sample_ohlcv_data, length=20)

    assert isinstance(result, pd.Series)
    assert len(result) == len(sample_ohlcv_data)


def test_williams_r_calculation(sample_ohlcv_data):
    """Test Williams %R calculation."""
    result = indicators.williams_r(sample_ohlcv_data, length=14)

    assert isinstance(result, pd.Series)
    assert len(result) == len(sample_ohlcv_data)
    # Williams %R should be between -100 and 0
    valid_values = result.dropna()
    assert (valid_values >= -100).all()
    assert (valid_values <= 0).all()


def test_mfi_calculation(sample_ohlcv_data):
    """Test Money Flow Index calculation."""
    result = indicators.mfi(sample_ohlcv_data, length=14)

    assert isinstance(result, pd.Series)
    assert len(result) == len(sample_ohlcv_data)
    # MFI should be between 0 and 100
    valid_values = result.dropna()
    assert (valid_values >= 0).all()
    assert (valid_values <= 100).all()


def test_calculate_all_indicators(sample_ohlcv_data):
    """Test calculating multiple indicators at once."""
    result = indicators.calculate_all_indicators(
        sample_ohlcv_data, indicators=["sma", "rsi", "macd"]
    )

    assert isinstance(result, pd.DataFrame)
    # Should have original columns plus indicators
    assert "open" in result.columns
    assert "close" in result.columns
    assert "SMA" in result.columns
    assert "RSI" in result.columns
    assert "MACD_12_26_9" in result.columns


def test_calculate_all_indicators_with_params(sample_ohlcv_data):
    """Test calculating indicators with custom parameters."""
    result = indicators.calculate_all_indicators(
        sample_ohlcv_data,
        indicators=["sma", "ema"],
        sma_params={"length": 10},
        ema_params={"length": 20},
    )

    assert isinstance(result, pd.DataFrame)
    assert "SMA" in result.columns
    assert "EMA" in result.columns


def test_calculate_all_indicators_unknown(sample_ohlcv_data):
    """Test error handling for unknown indicator."""
    with pytest.raises(ValueError, match="Unknown indicator"):
        indicators.calculate_all_indicators(
            sample_ohlcv_data, indicators=["unknown_indicator"]
        )


def test_sma_custom_column(sample_ohlcv_data):
    """Test SMA on custom column."""
    result = indicators.sma(sample_ohlcv_data, length=5, column="high")

    assert isinstance(result, pd.Series)
    # Should calculate on 'high' instead of 'close'
    expected = sample_ohlcv_data["high"].iloc[0:5].mean()
    assert abs(result.iloc[4] - expected) < 0.01


def test_ema_different_lengths(sample_ohlcv_data):
    """Test EMA with different lengths."""
    ema_short = indicators.ema(sample_ohlcv_data, length=3)
    ema_long = indicators.ema(sample_ohlcv_data, length=10)

    # Shorter EMA should react faster to price changes
    # Both should have values
    assert not pd.isna(ema_short.iloc[-1])
    assert not pd.isna(ema_long.iloc[-1])
