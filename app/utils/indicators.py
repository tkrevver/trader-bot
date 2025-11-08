"""Technical indicators library using pandas-ta.

This module provides a clean interface to common technical indicators
used in trading strategies. All functions accept pandas DataFrames with
OHLCV data and return pandas Series or DataFrames.
"""

import pandas as pd
import pandas_ta as ta
from typing import Optional


def validate_ohlcv(df: pd.DataFrame) -> None:
    """Validate that DataFrame contains required OHLCV columns.

    Args:
        df: DataFrame to validate

    Raises:
        ValueError: If required columns are missing
    """
    required_cols = ["open", "high", "low", "close", "volume"]
    missing = [col for col in required_cols if col not in df.columns]
    if missing:
        raise ValueError(f"DataFrame missing required columns: {missing}")


def sma(df: pd.DataFrame, length: int = 20, column: str = "close") -> pd.Series:
    """Calculate Simple Moving Average.

    Args:
        df: OHLCV DataFrame
        length: Lookback period (default: 20)
        column: Column to use for calculation (default: 'close')

    Returns:
        pandas Series with SMA values
    """
    validate_ohlcv(df)
    return ta.sma(df[column], length=length)


def ema(df: pd.DataFrame, length: int = 20, column: str = "close") -> pd.Series:
    """Calculate Exponential Moving Average.

    Args:
        df: OHLCV DataFrame
        length: Lookback period (default: 20)
        column: Column to use for calculation (default: 'close')

    Returns:
        pandas Series with EMA values
    """
    validate_ohlcv(df)
    return ta.ema(df[column], length=length)


def rsi(df: pd.DataFrame, length: int = 14, column: str = "close") -> pd.Series:
    """Calculate Relative Strength Index.

    Args:
        df: OHLCV DataFrame
        length: Lookback period (default: 14)
        column: Column to use for calculation (default: 'close')

    Returns:
        pandas Series with RSI values (0-100)
    """
    validate_ohlcv(df)
    result = ta.rsi(df[column], length=length)
    # pandas-ta may return None for insufficient data
    if result is None:
        return pd.Series(index=df.index, dtype=float)
    return result


def macd(
    df: pd.DataFrame,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
    column: str = "close",
) -> pd.DataFrame:
    """Calculate MACD (Moving Average Convergence Divergence).

    Args:
        df: OHLCV DataFrame
        fast: Fast EMA period (default: 12)
        slow: Slow EMA period (default: 26)
        signal: Signal line period (default: 9)
        column: Column to use for calculation (default: 'close')

    Returns:
        DataFrame with columns: MACD, MACDh (histogram), MACDs (signal)
    """
    validate_ohlcv(df)
    result = ta.macd(df[column], fast=fast, slow=slow, signal=signal)
    if result is None:
        return pd.DataFrame(index=df.index)
    return result


def bbands(
    df: pd.DataFrame, length: int = 20, std: float = 2.0, column: str = "close"
) -> pd.DataFrame:
    """Calculate Bollinger Bands.

    Args:
        df: OHLCV DataFrame
        length: Moving average period (default: 20)
        std: Standard deviation multiplier (default: 2.0)
        column: Column to use for calculation (default: 'close')

    Returns:
        DataFrame with columns: BBL (lower), BBM (middle), BBU (upper), BBB (bandwidth), BBP (percent)
    """
    validate_ohlcv(df)
    result = ta.bbands(df[column], length=length, std=std)
    if result is None:
        return pd.DataFrame(index=df.index)
    return result


def atr(df: pd.DataFrame, length: int = 14) -> pd.Series:
    """Calculate Average True Range.

    Args:
        df: OHLCV DataFrame
        length: Lookback period (default: 14)

    Returns:
        pandas Series with ATR values
    """
    validate_ohlcv(df)
    result = ta.atr(df["high"], df["low"], df["close"], length=length)
    if result is None:
        return pd.Series(index=df.index, dtype=float)
    return result


def vwap(df: pd.DataFrame) -> pd.Series:
    """Calculate Volume Weighted Average Price.

    Note: VWAP should be calculated from daily data (resets each day).
    This calculates cumulative VWAP for the provided DataFrame.

    Args:
        df: OHLCV DataFrame

    Returns:
        pandas Series with VWAP values
    """
    validate_ohlcv(df)
    result = ta.vwap(df["high"], df["low"], df["close"], df["volume"])
    if result is None:
        return pd.Series(index=df.index, dtype=float)
    return result


def stoch(
    df: pd.DataFrame,
    k: int = 14,
    d: int = 3,
    smooth_k: int = 3,
) -> pd.DataFrame:
    """Calculate Stochastic Oscillator.

    Args:
        df: OHLCV DataFrame
        k: %K period (default: 14)
        d: %D period (default: 3)
        smooth_k: Smoothing period for %K (default: 3)

    Returns:
        DataFrame with columns: STOCHk, STOCHd
    """
    validate_ohlcv(df)
    result = ta.stoch(
        df["high"], df["low"], df["close"], k=k, d=d, smooth_k=smooth_k
    )
    if result is None:
        return pd.DataFrame(index=df.index)
    return result


def adx(df: pd.DataFrame, length: int = 14) -> pd.DataFrame:
    """Calculate Average Directional Index (trend strength).

    Args:
        df: OHLCV DataFrame
        length: Lookback period (default: 14)

    Returns:
        DataFrame with columns: ADX, DMP (+DI), DMN (-DI)
    """
    validate_ohlcv(df)
    result = ta.adx(df["high"], df["low"], df["close"], length=length)
    if result is None:
        return pd.DataFrame(index=df.index)
    return result


def obv(df: pd.DataFrame) -> pd.Series:
    """Calculate On-Balance Volume.

    Args:
        df: OHLCV DataFrame

    Returns:
        pandas Series with OBV values
    """
    validate_ohlcv(df)
    return ta.obv(df["close"], df["volume"])


def cci(df: pd.DataFrame, length: int = 20) -> pd.Series:
    """Calculate Commodity Channel Index.

    Args:
        df: OHLCV DataFrame
        length: Lookback period (default: 20)

    Returns:
        pandas Series with CCI values
    """
    validate_ohlcv(df)
    result = ta.cci(df["high"], df["low"], df["close"], length=length)
    if result is None:
        return pd.Series(index=df.index, dtype=float)
    return result


def williams_r(df: pd.DataFrame, length: int = 14) -> pd.Series:
    """Calculate Williams %R.

    Args:
        df: OHLCV DataFrame
        length: Lookback period (default: 14)

    Returns:
        pandas Series with Williams %R values (-100 to 0)
    """
    validate_ohlcv(df)
    result = ta.willr(df["high"], df["low"], df["close"], length=length)
    if result is None:
        return pd.Series(index=df.index, dtype=float)
    return result


def mfi(df: pd.DataFrame, length: int = 14) -> pd.Series:
    """Calculate Money Flow Index.

    Args:
        df: OHLCV DataFrame
        length: Lookback period (default: 14)

    Returns:
        pandas Series with MFI values (0-100)
    """
    validate_ohlcv(df)
    result = ta.mfi(df["high"], df["low"], df["close"], df["volume"], length=length)
    if result is None:
        return pd.Series(index=df.index, dtype=float)
    return result


def calculate_all_indicators(
    df: pd.DataFrame,
    indicators: Optional[list[str]] = None,
    **kwargs,
) -> pd.DataFrame:
    """Calculate multiple indicators and add them as columns to the DataFrame.

    Args:
        df: OHLCV DataFrame
        indicators: List of indicator names to calculate (default: all common ones)
        **kwargs: Additional parameters for specific indicators

    Returns:
        DataFrame with original data plus indicator columns

    Example:
        >>> df_with_indicators = calculate_all_indicators(
        ...     df,
        ...     indicators=['sma', 'rsi', 'macd'],
        ...     sma_length=20,
        ...     rsi_length=14
        ... )
    """
    validate_ohlcv(df)
    result = df.copy()

    if indicators is None:
        indicators = ["sma", "ema", "rsi", "macd", "bbands", "atr"]

    indicator_map = {
        "sma": lambda: sma(result, **kwargs.get("sma_params", {})),
        "ema": lambda: ema(result, **kwargs.get("ema_params", {})),
        "rsi": lambda: rsi(result, **kwargs.get("rsi_params", {})),
        "macd": lambda: macd(result, **kwargs.get("macd_params", {})),
        "bbands": lambda: bbands(result, **kwargs.get("bbands_params", {})),
        "atr": lambda: atr(result, **kwargs.get("atr_params", {})),
        "vwap": lambda: vwap(result),
        "stoch": lambda: stoch(result, **kwargs.get("stoch_params", {})),
        "adx": lambda: adx(result, **kwargs.get("adx_params", {})),
        "obv": lambda: obv(result),
        "cci": lambda: cci(result, **kwargs.get("cci_params", {})),
        "williams_r": lambda: williams_r(result, **kwargs.get("williams_r_params", {})),
        "mfi": lambda: mfi(result, **kwargs.get("mfi_params", {})),
    }

    for indicator_name in indicators:
        if indicator_name not in indicator_map:
            raise ValueError(f"Unknown indicator: {indicator_name}")

        indicator_result = indicator_map[indicator_name]()

        # Handle both Series and DataFrame returns
        if isinstance(indicator_result, pd.Series):
            result[indicator_name.upper()] = indicator_result
        elif isinstance(indicator_result, pd.DataFrame):
            # Merge indicator columns into result
            result = result.join(indicator_result)

    return result
