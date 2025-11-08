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
- **Data Source:** Tradier Brokerage API (api.tradier.com)
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
│   │   ├── tradier_client.py  # Tradier REST API client
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
│   ├── test_tradier_client.py # Tradier API client tests
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
- `GET /health/detailed` - Component status (database, scheduler, tradier, broker)

### Market Data
- `GET /api/v1/market-data/{symbol}/latest` - Latest bar for timeframe
- `GET /api/v1/market-data/{symbol}/history` - Historical bars with time range
- `GET /api/v1/market-data/{symbol}/gaps` - Detect missing data gaps
- `POST /api/v1/market-data/{symbol}/ingest-latest` - Trigger ingestion of latest bar (called by scheduler)
- `POST /api/v1/market-data/{symbol}/backfill` - Manual backfill from Tradier API
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

APScheduler runs 4 background jobs during market hours. **All jobs call API endpoints** (not services directly) to ensure consistent flow and proper database connection handling.

1. **data_ingestion** - Every minute at :05 seconds
   - Calls `POST /api/v1/market-data/{symbol}/ingest-latest`
   - Fetches latest 1-minute bar from Tradier API
   - Prevents duplicates
   - Only runs during market hours (9:30 AM - 4:00 PM ET)

2. **gap_detection** - Every hour at :10 past the hour
   - Calls `GET /api/v1/market-data/{symbol}/gaps?days_back=7`
   - Scans for missing bars in the last 7 days
   - Logs gaps for investigation (does NOT auto-fill)

3. **data_health_check** - Every 15 minutes
   - Calls `GET /api/v1/market-data/{symbol}/health?hours_back=24`
   - Checks data freshness and quality
   - Logs warnings if data is unhealthy

4. **refresh_materialized_views** - Every 5 minutes
   - Calls `POST /api/v1/market-data/views/refresh?concurrently=true`
   - Refreshes all 4 materialized views concurrently
   - Updates aggregated timeframe data

**Market Hours:**
- Open: 9:30 AM ET
- Close: 4:00 PM ET
- Holidays: US market holidays for 2025 hardcoded in `app/utils/market_hours.py`

## Tradier API Integration

**Base URL:** `https://api.tradier.com`

**Authentication:** Bearer token via `TRADIER_API_TOKEN` environment variable

**Cost:** $10/month (Tradier Pro plan) - includes real-time market data + brokerage

### Timesales Endpoint (OHLCV Bars)
```
GET /v1/markets/timesales
```

**Parameters:**
- `symbol` - Stock symbol (e.g., SPY)
- `interval` - Bar interval (1min, 5min, 15min, tick)
- `start` - Start date/time (YYYY-MM-DD HH:MM format)
- `end` - End date/time (YYYY-MM-DD HH:MM format)
- `session_filter` - "open" for market hours only, "all" for extended hours

**Historical Data Limits:**
- 1min: 20 days (market hours), 10 days (all hours)
- 5min: 40 days (market hours), 18 days (all hours)
- 15min: 40 days (market hours), 18 days (all hours)

**Response Format:**
```json
{
  "series": {
    "data": [
      {
        "time": "2025-11-07 09:31:00",
        "timestamp": 1730984460,
        "open": 583.45,
        "high": 583.98,
        "low": 583.40,
        "close": 583.75,
        "volume": 125000
      }
    ]
  }
}
```

### Real-Time Data

**Advantage:** Tradier provides **real-time market data** to all brokerage account holders (no 15-min delay).

- Data is current during market hours (9:30 AM - 4:00 PM ET)
- No timestamp verification needed - data is fresh
- 1-minute bars available within seconds of completion

## Data Ingestion Flow

```
┌─────────────┐
│  Scheduler  │ (Every minute at :05 seconds)
└──────┬──────┘
       │
       │ POST /api/v1/market-data/{symbol}/ingest-latest
       v
┌──────────────────────────┐
│ API Endpoint             │
│ - Check market status    │
│ - Return clear messages  │
└──────┬───────────────────┘
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
│ TradierClient            │
│ - Fetch latest bar       │
│ - Real-time data (no     │
│   timestamp verification │
│   needed)                │
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
# Application
APP_NAME=trader-bot
ENVIRONMENT=development
LOG_LEVEL=INFO
DEBUG=false

# Database
DATABASE_URL=postgresql://user@localhost:5432/trader_bot_dev
DATABASE_POOL_SIZE=10
DATABASE_MAX_OVERFLOW=20

# Tradier (Market Data & Brokerage)
TRADIER_API_TOKEN=your_api_token_here
TRADIER_API_URL=https://api.tradier.com
TRADIER_ACCOUNT_ID=

# Broker
BROKER=paper

# Trading
INITIAL_CAPITAL=100000
MAX_POSITION_SIZE_PCT=0.10
MAX_PORTFOLIO_EXPOSURE=1.0
DAILY_LOSS_LIMIT_PCT=0.02
DEFAULT_SLIPPAGE_BPS=5

# Market Hours
ENABLE_EXTENDED_HOURS=false

# Risk Management (Safety Flags)
ENABLE_TRADING=false
ENABLE_LIVE_TRADING=false

# Timezone
TIMEZONE=America/New_York

# Server
HOST=0.0.0.0
PORT=8000
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
- Respects Tradier API rate limits
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
2. **Scheduler architecture:** All scheduled jobs call API endpoints (not services) for consistent DB connection handling
3. **Tradier Cost:** $10/month Pro plan required for real-time data
4. **TimescaleDB:** We're NOT using it - manual partitioning only
5. **Historical Limits:** Tradier provides 20 days of 1-minute data (grows over time)
6. **Market hours:** Jobs only run 9:30 AM - 4:00 PM ET on trading days
7. **Partition auto-creation:** Happens on startup, not in migrations
8. **Materialized views:** Already exist from previous migration - don't recreate
9. **Concurrent refresh:** Requires unique index, which exists
10. **Gap detection vs backfill:** `/gaps` only detects and logs, `/backfill` actually fills gaps

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
├── test_tradier_client.py          # Tradier API client
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
- Tradier API integration
- Market data repository CRUD operations
- Data ingestion (market hours aware, extended hours support)
- Historical data backfill
- Gap detection and automatic filling
- Market hours validation (open/closed, holidays, extended hours)

**Notes:**
- Tests use async fixtures for database connection
- Some tests are conditional based on market hours
- Data ingestion tests may show warnings due to delayed API data (expected behavior)
