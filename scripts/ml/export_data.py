"""Export historical OHLCV data from database to Parquet files for ML training."""

import asyncio
import pandas as pd
from datetime import datetime
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.db.connection import db_pool
from app.config import settings


async def export_ohlcv_data(
    symbol: str = 'SPY',
    start_date: str = '2023-01-01',
    end_date: str = '2025-11-07',
    output_dir: str = 'data/processed'
):
    """
    Export historical OHLCV data from all timeframes to Parquet files.

    Args:
        symbol: Stock symbol to export
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
        output_dir: Output directory for Parquet files
    """
    print(f"Exporting {symbol} data from {start_date} to {end_date}...")

    # Ensure output directory exists
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    # Connect to database
    await db_pool.connect()

    try:
        # Convert dates to datetime objects with UTC timezone
        import pytz
        start_dt = pd.to_datetime(start_date).tz_localize('UTC')
        end_dt = pd.to_datetime(end_date).tz_localize('UTC')

        # Export 1-minute data
        print("\n1. Exporting 1-minute data...")
        query_1min = """
            SELECT time, symbol, open, high, low, close, volume, vwap, trades
            FROM ohlcv_1min
            WHERE symbol = $1
              AND time >= $2
              AND time <= $3
            ORDER BY time
        """
        rows_1min = await db_pool.fetch(query_1min, symbol, start_dt, end_dt)
        df_1min = pd.DataFrame(rows_1min, columns=['time', 'symbol', 'open', 'high', 'low', 'close', 'volume', 'vwap', 'trades'])

        output_file_1min = f"{output_dir}/{symbol}_1min_ohlcv.parquet"
        df_1min.to_parquet(output_file_1min, index=False)
        print(f"   ✓ Exported {len(df_1min):,} rows to {output_file_1min}")

        # Export 5-minute data
        print("\n2. Exporting 5-minute data...")
        query_5min = """
            SELECT time, symbol, open, high, low, close, volume, vwap, trades
            FROM ohlcv_5min
            WHERE symbol = $1
              AND time >= $2
              AND time <= $3
            ORDER BY time
        """
        rows_5min = await db_pool.fetch(query_5min, symbol, start_dt, end_dt)
        df_5min = pd.DataFrame(rows_5min, columns=['time', 'symbol', 'open', 'high', 'low', 'close', 'volume', 'vwap', 'trades'])

        output_file_5min = f"{output_dir}/{symbol}_5min_ohlcv.parquet"
        df_5min.to_parquet(output_file_5min, index=False)
        print(f"   ✓ Exported {len(df_5min):,} rows to {output_file_5min}")

        # Export 15-minute data
        print("\n3. Exporting 15-minute data...")
        query_15min = """
            SELECT time, symbol, open, high, low, close, volume, vwap, trades
            FROM ohlcv_15min
            WHERE symbol = $1
              AND time >= $2
              AND time <= $3
            ORDER BY time
        """
        rows_15min = await db_pool.fetch(query_15min, symbol, start_dt, end_dt)
        df_15min = pd.DataFrame(rows_15min, columns=['time', 'symbol', 'open', 'high', 'low', 'close', 'volume', 'vwap', 'trades'])

        output_file_15min = f"{output_dir}/{symbol}_15min_ohlcv.parquet"
        df_15min.to_parquet(output_file_15min, index=False)
        print(f"   ✓ Exported {len(df_15min):,} rows to {output_file_15min}")

        # Export 30-minute data
        print("\n4. Exporting 30-minute data...")
        query_30min = """
            SELECT time, symbol, open, high, low, close, volume, vwap, trades
            FROM ohlcv_30min
            WHERE symbol = $1
              AND time >= $2
              AND time <= $3
            ORDER BY time
        """
        rows_30min = await db_pool.fetch(query_30min, symbol, start_dt, end_dt)
        df_30min = pd.DataFrame(rows_30min, columns=['time', 'symbol', 'open', 'high', 'low', 'close', 'volume', 'vwap', 'trades'])

        output_file_30min = f"{output_dir}/{symbol}_30min_ohlcv.parquet"
        df_30min.to_parquet(output_file_30min, index=False)
        print(f"   ✓ Exported {len(df_30min):,} rows to {output_file_30min}")

        # Summary
        print("\n" + "="*70)
        print("EXPORT SUMMARY")
        print("="*70)
        print(f"Symbol: {symbol}")
        print(f"Date Range: {start_date} to {end_date}")
        print(f"\n1-minute bars: {len(df_1min):,}")
        print(f"  Date range: {df_1min['time'].min()} to {df_1min['time'].max()}")
        print(f"\n5-minute bars: {len(df_5min):,}")
        print(f"  Date range: {df_5min['time'].min()} to {df_5min['time'].max()}")
        print(f"\n15-minute bars: {len(df_15min):,}")
        print(f"  Date range: {df_15min['time'].min()} to {df_15min['time'].max()}")
        print(f"\n30-minute bars: {len(df_30min):,}")
        print(f"  Date range: {df_30min['time'].min()} to {df_30min['time'].max()}")

        # Basic statistics
        print(f"\nPrice Statistics (1-min data):")
        print(f"  Open: ${df_1min['open'].iloc[0]:.2f} → Close: ${df_1min['close'].iloc[-1]:.2f}")
        print(f"  Min: ${df_1min['low'].min():.2f}, Max: ${df_1min['high'].max():.2f}")
        print(f"  Avg Volume: {df_1min['volume'].mean():,.0f}")

        print("\n✓ Export complete!")

    finally:
        await db_pool.disconnect()


if __name__ == '__main__':
    # Export 2 years of SPY data
    asyncio.run(export_ohlcv_data(
        symbol='SPY',
        start_date='2023-11-01',  # ~2 years from Nov 2025
        end_date='2025-11-07'
    ))
