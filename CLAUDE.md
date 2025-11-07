# Trader Bot - Claude Context

This document provides comprehensive context about the implemented system for AI assistants.

## Project Overview

Automated trading bot for day/swing trading strategies. Currently focused on SPY (S&P 500 ETF) with plans to expand to other symbols.

**Current Status:** Week 2 (Data Infrastructure) completed. Real-time data ingestion not working due to API tier limitations (delayed data).

## Technology Stack

- **Language:** Python 3.11+
- **Framework:** FastAPI
- **Database:** PostgreSQL with manual weekly partitioning (NOT TimescaleDB)
- **Scheduler:** APScheduler (AsyncIOScheduler)
- **Data Source:** Polygon.io REST API (api.massive.com)
- **API Testing:** Bruno
- **Migrations:** Alembic

## Database Architecture

### Tables

**ohlcv_1min** (partitioned table)
- Stores 1-minute OHLCV bars
- Partitioned by week using ISO week numbers
- Partition naming: `ohlcv_1min_YYYY_wWW` (e.g., `ohlcv_1min_2025_w45`)
- Auto-creates partitions 4 weeks in advance on startup
- Primary key: `(symbol, time)`

**Schema:**
```sql
CREATE TABLE ohlcv_1min (
    time TIMESTAMP WITH TIME ZONE NOT NULL,
    symbol VARCHAR(10) NOT NULL,
    open DECIMAL(12,4) NOT NULL,
    high DECIMAL(12,4) NOT NULL,
    low DECIMAL(12,4) NOT NULL,
    close DECIMAL(12,4) NOT NULL,
    volume BIGINT NOT NULL,
    vwap DECIMAL(12,4),
    trades INTEGER,
    PRIMARY KEY (symbol, time)
) PARTITION BY RANGE (time);
```

### Materialized Views

Four materialized views aggregate 1-minute data into larger timeframes:

1. **ohlcv_5min** - 5-minute bars
2. **ohlcv_15min** - 15-minute bars
3. **ohlcv_30min** - 30-minute bars
4. **ohlcv_daily** - Daily bars

**Refresh Strategy:**
- Uses `REFRESH MATERIALIZED VIEW CONCURRENTLY` to avoid blocking queries
- Requires unique index on (symbol, time) for concurrent refresh
- Auto-refreshes every 5 minutes via scheduler
- Can be manually refreshed via API

## Project Structure

```
trader-bot/
├── app/
│   ├── api/                    # API endpoints
│   │   ├── health.py          # Health check endpoints
│   │   ├── market_data.py     # Market data CRUD + backfill
│   │   └── scheduler.py       # Scheduler management
│   ├── db/
│   │   ├── connection.py      # Database pool management
│   │   ├── partition_manager.py  # Auto-create partitions
│   │   └── repositories/      # Data access layer
│   │       ├── market_data.py # OHLCV operations + gap detection
│   │       ├── signals.py
│   │       ├── orders.py
│   │       ├── positions.py
│   │       └── trades.py
│   ├── models/                # Pydantic models
│   │   ├── market_data.py
│   │   ├── signals.py
│   │   ├── orders.py
│   │   ├── positions.py
│   │   └── strategy.py
│   ├── services/
│   │   ├── polygon_client.py  # REST API client with retry logic
│   │   ├── data_ingestion.py  # Orchestrates data fetching
│   │   └── materialized_view_refresh.py
│   ├── tasks/
│   │   └── scheduler.py       # APScheduler job definitions
│   ├── utils/
│   │   ├── logger.py          # Structured logging
│   │   └── market_hours.py    # US market hours/holidays
│   └── config.py              # Settings from environment
├── tests/                     # Pytest test suite
│   ├── conftest.py            # Shared fixtures
│   ├── test_database.py       # Database tests
│   ├── test_polygon_client.py # API client tests
│   ├── test_market_hours.py   # Market hours tests
│   ├── test_market_data_repository.py  # Repository tests
│   ├── test_data_ingestion.py # Ingestion tests
│   ├── test_backfill.py       # Backfill tests
│   └── test_gap_detection.py  # Gap detection tests
├── bruno/trader-bot/          # API request collection
├── alembic/                   # Database migrations
├── main.py                    # FastAPI app entry point (ROOT, not app/)
├── pytest.ini                 # Pytest configuration
└── .env                       # Environment variables
```

## API Endpoints

Base URL: `http://localhost:8000`

### Health
- `GET /health` - Basic health check
- `GET /health/detailed` - Component status (database, scheduler, polygon, broker)

### Market Data
- `GET /api/v1/market-data/{symbol}/latest` - Latest bar for timeframe
- `GET /api/v1/market-data/{symbol}/history` - Historical bars with time range
- `GET /api/v1/market-data/{symbol}/gaps` - Detect missing data gaps
- `POST /api/v1/market-data/{symbol}/backfill` - Manual backfill from Polygon API
- `GET /api/v1/market-data/{symbol}/health` - Data quality metrics
- `GET /api/v1/market-data/{symbol}/stats` - Coverage statistics

### Materialized Views
- `POST /api/v1/market-data/views/refresh` - Refresh all views
- `POST /api/v1/market-data/views/refresh?view_name=ohlcv_5min` - Refresh specific view
- `GET /api/v1/market-data/views/stats` - View row counts and sizes

### Scheduler
- `GET /api/v1/scheduler/status` - Scheduler status and job info
- `POST /api/v1/scheduler/jobs/{job_id}/pause` - Pause job
- `POST /api/v1/scheduler/jobs/{job_id}/resume` - Resume job

**Valid Job IDs:**
- `data_ingestion` - 1-minute data pulls
- `gap_detection` - Detect missing data
- `data_health_check` - Data quality checks
- `refresh_materialized_views` - Refresh aggregated views

## Scheduled Jobs

APScheduler runs 4 background jobs during market hours:

1. **data_ingestion** - Every minute at :05 seconds
   - Fetches latest 1-minute bar from Polygon API
   - Validates timestamp matches expected time
   - Prevents duplicates
   - Only runs during market hours (9:30 AM - 4:00 PM ET)

2. **gap_detection** - Every hour at :10 past the hour
   - Scans for missing bars in the last 7 days
   - Logs gaps for investigation

3. **data_health_check** - Every 15 minutes
   - Checks data freshness
   - Validates data quality

4. **refresh_materialized_views** - Every 5 minutes
   - Refreshes all 4 materialized views concurrently
   - Updates aggregated timeframe data

**Market Hours:**
- Open: 9:30 AM ET
- Close: 4:00 PM ET
- Holidays: US market holidays for 2025 hardcoded in `app/utils/market_hours.py`

## Polygon.io API Integration

**Base URL:** `https://api.massive.com` (Polygon rebranded to Massive)

**Authentication:** API key via `POLYGON_API_KEY` environment variable

### Aggregates Endpoint
```
GET /v2/aggs/ticker/{symbol}/range/1/minute/{from_date}/{to_date}
```

**Parameters:**
- `limit=1` - Only fetch most recent bar
- `sort=desc` - Sort by timestamp descending

**Date Range for 1-min pulls:**
- `from_date` = yesterday (UTC)
- `to_date` = today (UTC)
- Returns most recent bar in that range

### Retry Logic

The `PolygonClient` implements 3-attempt retry for timestamp verification:
1. First attempt: Immediate fetch
2. Second attempt: Wait 2 seconds if stale data
3. Third attempt: Wait 5 seconds if still stale
4. Fourth attempt: Wait 10 seconds if still stale

**Timestamp Verification:**
- Checks if returned timestamp matches expected time (previous minute)
- Rejects bars that are too old (>2 minutes behind expected)

### Known Issue: Delayed Data

**Problem:** Polygon API returns data with "DELAYED" status on the current tier.

**Symptoms:**
- When requesting November 7 data, API returns November 6 data
- Delay is 15+ minutes
- Our timestamp verification correctly rejects this stale data
- Result: No data flows into database during live trading

**Root Cause:** Current API subscription is on a delayed data tier

**Solution:**
- Use backfill endpoint for historical data: `POST /api/v1/market-data/SPY/backfill`
- Upgrade to Developer tier ($200/mo) for real-time data when ready for live trading

## Data Ingestion Flow

```
┌─────────────┐
│  Scheduler  │ (Every minute at :05 seconds)
└──────┬──────┘
       │
       v
┌──────────────────────────┐
│ DataIngestionService     │
│ - Check market hours     │
│ - Calculate expected time│
│ - Check for duplicates   │
└──────┬───────────────────┘
       │
       v
┌──────────────────────────┐
│ PolygonClient            │
│ - Fetch from API         │
│ - Verify timestamp       │
│ - Retry if stale (3x)    │
└──────┬───────────────────┘
       │
       v
┌──────────────────────────┐
│ MarketDataRepository     │
│ - Insert into ohlcv_1min │
│ - Handle duplicates      │
└──────────────────────────┘
```

## Environment Variables

Required in `.env`:

```bash
# Database
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/trader_bot

# Polygon.io API
POLYGON_API_KEY=your_api_key_here
POLYGON_REST_URL=https://api.massive.com

# Application
APP_NAME=trader-bot
ENVIRONMENT=development
DEBUG=true
HOST=0.0.0.0
PORT=8000
LOG_LEVEL=INFO
```

## Running the Application

**Start the server:**
```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

**Important:** The main FastAPI app is in `main.py` at the project root, NOT `app/main.py`.

**On startup, the app:**
1. Connects to database
2. Creates partitions for current + next 4 weeks
3. Starts APScheduler with 4 jobs
4. Registers API routers

**On shutdown, the app:**
1. Stops scheduler gracefully
2. Closes database connections

## Testing with Bruno

Bruno collection location: `bruno/trader-bot/`

**Environment:** Local
- `baseUrl`: http://localhost:8000
- `symbol`: SPY

**Request folders:**
1. Health (2 requests)
2. Market Data (6 requests)
3. Materialized Views (3 requests)
4. Scheduler (3 requests)

## Database Migrations

**Run migrations:**
```bash
alembic upgrade head
```

**Key migrations:**
1. `afe0cd1f9b6e_create_ohlcv_1min_table.py` - Creates partitioned table
2. `e103e4a38456_create_materialized_views_for_timeframes.py` - Creates 4 materialized views

**Note:** Partitions are NOT created by migrations. They're auto-created on app startup by `partition_manager.py`.

## Backfilling Historical Data

**Via API:**

The backfill endpoint automatically detects and fills gaps to ensure data completeness.

Two ways to specify date range:

1. **Days parameter (easier):**
```bash
POST /api/v1/market-data/SPY/backfill?days=7
```

2. **Explicit dates:**
```bash
POST /api/v1/market-data/SPY/backfill?start_date=2025-11-01T00:00:00&end_date=2025-11-07T23:59:59
```

**Parameters:**
- `days` - Number of days to backfill from today (1-30)
- `start_date` - Explicit start date (alternative to days)
- `end_date` - Explicit end date (alternative to days)

**Constraints:**
- Max 30 days per request (API limitation)
- Respects Polygon API rate limits
- Checks for duplicates before inserting
- Always detects and fills gaps automatically

**Response:**
```json
{
  "symbol": "SPY",
  "start_date": "2025-11-01T00:00:00",
  "end_date": "2025-11-07T23:59:59",
  "bars_inserted": 2340,
  "gaps_found": 2,
  "gaps": [
    {
      "start_time": "2025-11-02T14:30:00",
      "end_time": "2025-11-02T14:45:00",
      "missing_bars": 15
    }
  ],
  "success": true
}
```

## Logging

Structured JSON logging via `app/utils/logger.py`

**Log levels:** DEBUG, INFO, WARNING, ERROR, CRITICAL

**Key log events:**
- Database connections
- Partition creation
- Scheduler job execution
- Data ingestion success/failure
- API errors

## Important Quirks & Gotchas

1. **Main app location:** `main.py` is in project root, NOT `app/main.py`
2. **Polygon URL:** Use `https://api.massive.com` NOT `https://api.polygon.io`
3. **TimescaleDB:** We're NOT using it - manual partitioning only
4. **Delayed data:** Current Polygon tier has 15+ min delay
5. **Market hours:** Jobs only run 9:30 AM - 4:00 PM ET on trading days
6. **Partition auto-creation:** Happens on startup, not in migrations
7. **Materialized views:** Already exist from previous migration - don't recreate
8. **Concurrent refresh:** Requires unique index, which exists

## Next Steps (Not Yet Implemented)

- Trading strategies (RSI, MACD, etc.)
- Signal generation
- Order execution
- Position management
- Risk management
- Broker integration (Alpaca)
- Real-time WebSocket data feed
- Backtesting framework
- Performance analytics

## Testing

**Test Framework:** Pytest with async support

**Test Structure:**
```
tests/
├── __init__.py
├── conftest.py                     # Shared fixtures and configuration
├── test_database.py                # Database connection and partitions
├── test_polygon_client.py          # Polygon.io API client
├── test_market_hours.py            # Market hours utilities
├── test_market_data_repository.py  # Repository CRUD operations
├── test_data_ingestion.py          # Data ingestion service
├── test_backfill.py                # Historical backfill
└── test_gap_detection.py           # Gap detection and filling
```

**Run all tests:**
```bash
pytest
```

**Run specific test file:**
```bash
pytest tests/test_database.py
```

**Run with verbose output:**
```bash
pytest -v
```

**Coverage:**
- Database connectivity and connection pooling
- Automatic partition creation and management
- Polygon.io API integration with retry logic
- Market data repository CRUD operations
- Data ingestion (market hours aware)
- Historical data backfill
- Gap detection and automatic filling
- Market hours validation (open/closed, holidays)

**Notes:**
- Tests use async fixtures for database connection
- Some tests are conditional based on market hours
- Data ingestion tests may show warnings due to delayed API data (expected behavior)
