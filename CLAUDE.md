# Trader Bot - Claude Context

This document provides comprehensive context about the implemented system for AI assistants.

## Project Overview

Automated trading bot for day/swing trading strategies. Currently focused on SPY (S&P 500 ETF) with plans to expand to other symbols.

**Current Status:** Week 2 (Data Infrastructure), Week 3 (Strategy Framework), and Week 6 (Backtesting Engine) completed. Real-time data ingestion working with Tradier API ($10/month for real-time market data).

## Technology Stack

- **Language:** Python 3.11+
- **Framework:** FastAPI
- **Database:** PostgreSQL with manual weekly partitioning (NOT TimescaleDB)
- **Scheduler:** APScheduler (AsyncIOScheduler)
- **Data Sources:**
  - **Tradier Brokerage API** (api.tradier.com) - Real-time data, $10/month
  - **Alpaca Markets API** (alpaca.markets) - 5+ years historical (FREE tier)
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

**backtests** - Backtest metadata and results
- Stores backtest configuration, status, and performance metrics
- Links to trades and equity curve via foreign keys

**backtest_trades** - Individual trades from backtests
- Stores entry/exit prices, P&L, commission, slippage
- Links to parent backtest

**backtest_equity_curve** - Equity snapshots over time
- Tracks cash, positions value, and total equity
- Used for calculating drawdowns and visualizing performance

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

## Timezone Handling

**Storage:** All timestamps are stored in the database as `TIMESTAMP WITH TIME ZONE` in UTC.

**Display:** API responses return timestamps in the configured timezone (default: `America/New_York`) via `TIMEZONE` environment variable.

**Conversion Pattern:**

The application uses Pydantic `@field_serializer` decorators to automatically convert UTC timestamps to the configured timezone when serializing API responses:

```python
@field_serializer("time")
def serialize_time(self, dt: datetime) -> str:
    """Serialize datetime to configured timezone."""
    tz = pytz.timezone(settings.timezone)
    if dt.tzinfo is None:
        dt = pytz.utc.localize(dt)
    dt_local = dt.astimezone(tz)
    return dt_local.isoformat()
```

**Models with Timezone Serialization:**

- `OHLCVBar` - Serializes `time` field
- `MarketDataGap` - Serializes `start_time`, `end_time`, `detected_at` fields
- `HealthCheckResponse` - Serializes `latest_bar_time` field
- `TradeDetail` - Serializes `entry_time`, `exit_time` fields
- `BacktestDetailedResponse` - Serializes `start_date`, `end_date` fields

**Important:** Service layer returns raw `datetime` objects. The API layer uses Pydantic response models (e.g., `LatestBarResponse`, `HealthCheckResponse`) which automatically trigger the field serializers. Never manually convert timestamps to strings in the service layer.

**Utility Function:**

`MarketHours.convert_to_local_tz(dt: datetime)` is available for manual conversion when needed outside of API responses.

## Project Structure

```
trader-bot/
├── app/
│   ├── api/                    # API endpoints (thin wrappers, delegate to services)
│   │   ├── backtest.py        # Backtest endpoints (run, results, detailed analysis)
│   │   ├── health.py          # Health check endpoints
│   │   ├── market_data.py     # Market data CRUD + backfill
│   │   ├── scheduler.py       # Scheduler management
│   │   └── tasks.py           # Admin tasks (partition management)
│   ├── db/
│   │   ├── connection.py      # Database pool management
│   │   ├── partition_manager.py  # Auto-create partitions
│   │   └── repositories/      # Data access layer
│   │       ├── backtest.py    # Backtest CRUD operations
│   │       ├── market_data.py # OHLCV operations + gap detection
│   │       ├── signals.py
│   │       ├── orders.py
│   │       ├── positions.py
│   │       └── trades.py
│   ├── models/                # Pydantic models
│   │   ├── backtest.py        # Backtest, BacktestTrade, EquityCurvePoint, BacktestMetrics
│   │   ├── market_data.py
│   │   ├── signals.py
│   │   ├── orders.py
│   │   ├── positions.py
│   │   └── strategy.py
│   ├── services/               # Business logic layer
│   │   ├── backtest_metrics.py   # Performance metrics calculator (25+ metrics)
│   │   ├── backtest_position_tracker.py  # Position/cash tracking with slippage
│   │   ├── backtest_runner.py    # Event-driven backtest orchestration
│   │   ├── base_market_data_client.py  # Abstract base class for data providers
│   │   ├── feature_engine.py     # Indicator caching and computation
│   │   ├── tradier_client.py  # Tradier REST API client
│   │   ├── alpaca_client.py   # Alpaca REST API client
│   │   ├── market_data_client_factory.py  # Provider factory/selector
│   │   ├── data_ingestion.py  # Data orchestration (fetching, backfill validation, stats)
│   │   └── materialized_view_refresh.py  # View refresh + validation
│   ├── strategies/             # Trading strategies (auto-loaded from this folder)
│   │   ├── base.py            # Abstract Strategy base class
│   │   └── loader.py          # Dynamic strategy loader
│   ├── tasks/
│   │   └── scheduler.py       # APScheduler job definitions
│   ├── utils/
│   │   ├── indicators.py      # pandas-ta wrapper (13+ indicators)
│   │   ├── logger.py          # Structured logging
│   │   └── market_hours.py    # US market hours/holidays
│   └── config.py              # Settings from environment
├── strategies/                 # Strategy implementations (outside app/)
│   └── opening_range_breakout.py  # Reference strategy implementation
├── tests/                     # Pytest test suite (88 tests, all passing)
│   ├── conftest.py            # Shared fixtures
│   ├── test_database.py       # Database tests
│   ├── test_tradier_client.py # Tradier API client tests
│   ├── test_alpaca_client.py  # Alpaca API client tests
│   ├── test_market_data_client_factory.py  # Factory pattern tests
│   ├── test_market_hours.py   # Market hours tests
│   ├── test_market_data_repository.py  # Repository tests
│   ├── test_data_ingestion.py # Ingestion + backfill validation + stats tests
│   ├── test_backfill.py       # Backfill tests
│   ├── test_gap_detection.py  # Gap detection tests
│   ├── test_materialized_view_refresh.py  # View refresh + validation tests
│   └── unit/                  # Unit tests for strategies and backtesting
│       ├── test_backtest_position_tracker.py  # Position tracking tests
│       ├── test_indicators.py  # Technical indicator tests
│       └── test_strategy_base.py  # Strategy base class tests
├── bruno/trader-bot/          # API request collection
│   ├── Backtest/              # Backtest API requests
│   │   ├── Run Backtest.bru
│   │   └── Get Detailed Results.bru
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
- `GET /api/v1/market-data/{symbol}/health` - Data quality metrics and gap detection
  - Query params: `days_back` (1-30) OR `hours_back` (1-720), defaults to 24 hours
  - Returns: bar_count, latest_bar_time, gap_count, gaps list, healthy status

### Market Data
- `GET /api/v1/market-data/{symbol}/latest` - Latest bar for timeframe
- `GET /api/v1/market-data/{symbol}/history` - Historical bars with time range
- `POST /api/v1/market-data/{symbol}/ingest-latest` - Trigger ingestion of latest bar (called by scheduler)
- `POST /api/v1/market-data/{symbol}/backfill` - Manual backfill from configured data provider
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
- `data_ingestion` - 1-minute data pulls (ACTIVE)
- `refresh_materialized_views` - Refresh aggregated views (ACTIVE)
- `data_health_check` - Data quality checks with gap detection (DISABLED - needs issue tracking)

### Admin Tasks
- `POST /api/v1/tasks/partitions/create?year=YYYY&table_name=ohlcv_1min` - Create partitions for a year
- `GET /api/v1/tasks/partitions/list?table_name=ohlcv_1min&year=YYYY` - List partitions (optional year filter)
- `DELETE /api/v1/tasks/partitions/drop-year?year=YYYY&table_name=ohlcv_1min&confirm=true` - Drop year partitions (requires confirm=true)

### Backtest
- `POST /api/v1/backtest` - Run a backtest
  - Request body: strategy_name, symbol, start_date, end_date, initial_capital, commission_per_share, slippage_bps, config
  - Returns: backtest_id, status, metrics, trades, equity_curve
- `GET /api/v1/backtest/{backtest_id}` - Get backtest status
- `GET /api/v1/backtest/{backtest_id}/results` - Get backtest metrics only
- `GET /api/v1/backtest/{backtest_id}/trades` - Get all trades
- `GET /api/v1/backtest/{backtest_id}/equity` - Get equity curve
- `GET /api/v1/backtest/{backtest_id}/detailed` - Get detailed trade analysis with entry/exit pairs
  - Returns: Detailed trade info with holding periods, win/loss classification, timezone-aware timestamps
- `GET /api/v1/backtest` - List all backtests (with optional filters)
- `DELETE /api/v1/backtest/{backtest_id}` - Delete a backtest

## Strategy Framework

The system uses a **modular, pluggable strategy architecture** that allows multiple strategies to run simultaneously.

### Strategy Base Class

All strategies inherit from `app.strategies.base.Strategy`:

```python
class Strategy(ABC):
    """Abstract base class for all trading strategies."""

    @abstractmethod
    def on_bar(self, symbol: str, timeframe: str, bar: pd.Series, bars: pd.DataFrame) -> None:
        """Process new market data bar."""
        pass

    @abstractmethod
    def generate_signals(self, symbol: str) -> list[SignalCreate]:
        """Generate trading signals based on current state."""
        pass

    @abstractmethod
    def get_metadata(self) -> StrategyMetadata:
        """Return strategy metadata (name, description, parameters)."""
        pass
```

### Key Concepts

1. **Multi-timeframe Support**: Strategies can process multiple timeframes (e.g., 1min and 5min bars)
2. **State Management**: Each symbol gets its own `StrategyState` for tracking positions and custom data
3. **Indicator Caching**: The `FeatureEngine` caches computed indicators (60-second TTL) to avoid redundant calculations
4. **Event-Driven**: Strategies react to market data bars and generate signals

### Creating a New Strategy

1. Create a new file in `strategies/` folder (e.g., `strategies/my_strategy.py`)
2. Inherit from `Strategy` base class
3. Implement required methods: `on_bar()`, `generate_signals()`, `get_metadata()`, `validate_parameters()`
4. Strategy will be auto-loaded on startup

### Reference Implementation: Opening Range Breakout

Located at `strategies/opening_range_breakout.py`

**Strategy Rules:**
- Trade during regular market hours only (no earlier than 10:00 AM ET)
- Calculate opening range: high/low from first 30 minutes (9:30-10:00 AM ET)
- **Entry**: Buy when price breaks above opening high on 1-min bars (if not in position)
- **Exit**: Sell when 5-min bar closes below EMA-10, then exit on next 1-min bar
- Fixed position size: 10 shares
- Allow multiple entries per day

**Technical Details:**
- Uses 1-min bars for entry signals
- Uses 5-min bars for exit signals (EMA-10 calculation)
- Tracks opening range and position state per day
- Prevents duplicate signals for same breakout using `last_buy_signal_price` tracking

## Backtesting Engine

Event-driven backtesting framework with realistic execution simulation.

### Architecture

1. **BacktestRunner** (`app/services/backtest_runner.py`) - Orchestrates backtest execution
   - Fetches historical data from database
   - Replays bars chronologically through strategy
   - Collects signals and executes trades via position tracker
   - Calculates final metrics and stores results

2. **BacktestPositionTracker** (`app/services/backtest_position_tracker.py`) - Simulates trade execution
   - Tracks cash, positions, and equity in memory
   - Applies realistic slippage (configurable basis points)
   - Applies commission (per-share or percentage)
   - Validates sufficient cash/shares before execution
   - Records equity curve points

3. **BacktestMetrics** (`app/services/backtest_metrics.py`) - Performance calculation
   - **25+ metrics** including:
     - Total return %, CAGR, Sharpe ratio, Sortino ratio
     - Max drawdown, max drawdown duration
     - Win rate, profit factor, average win/loss
     - Total trades, winning/losing trades
     - Average holding period, longest winning/losing streak

### Slippage Simulation

Realistic market impact modeling:

```python
slippage_pct = slippage_bps / 10000  # e.g., 5 bps = 0.05%

# Buy orders: slippage increases execution price
execution_price = price + (price * slippage_pct)

# Sell orders: slippage decreases execution price
execution_price = price - (price * slippage_pct)
```

### Running a Backtest

**Via Bruno API:**
```
POST /api/v1/backtest
{
  "strategy_name": "opening_range_breakout",
  "symbol": "SPY",
  "start_date": "2025-08-09T00:00:00",
  "end_date": "2025-11-07T23:59:59",
  "initial_capital": "10000",
  "commission_per_share": "0",
  "slippage_bps": 5,
  "config": {
    "opening_range_minutes": 30,
    "earliest_entry_time": "10:00",
    "position_size": 10
  }
}
```

**Response includes:**
- Backtest ID and status
- Performance metrics (total return, Sharpe, max drawdown, etc.)
- All executed trades
- Equity curve points

### Detailed Trade Analysis

The `/api/v1/backtest/{id}/detailed` endpoint pairs buy/sell trades and provides:

- Trade number (sequential)
- Entry/exit times (timezone-aware, in ET)
- Entry/exit prices
- P&L per trade
- Win/Loss classification
- Holding period in minutes
- Total commission and slippage per trade

**Example Output:**
```json
{
  "backtest_id": 15,
  "strategy_name": "opening_range_breakout",
  "symbol": "SPY",
  "total_trades": 46,
  "winning_trades": 10,
  "losing_trades": 36,
  "metrics": {
    "total_return_pct": -2.10,
    "sharpe_ratio": -0.15,
    "max_drawdown_pct": -3.45,
    "win_rate": 21.74
  },
  "trades": [
    {
      "trade_number": 1,
      "date": "2025-08-09",
      "entry_time": "2025-08-09T10:10:00-04:00",
      "exit_time": "2025-08-09T11:25:00-04:00",
      "side": "LONG",
      "quantity": 10,
      "entry_price": "532.45",
      "exit_price": "534.20",
      "pnl": "17.50",
      "win_loss": "WIN",
      "commission": "0",
      "slippage": "0.53",
      "holding_period_minutes": 75.0
    }
  ]
}
```

## Scheduled Jobs

APScheduler runs 2 active background jobs during market hours. **All jobs call API endpoints** (not services directly) to ensure consistent flow and proper database connection handling.

### Active Jobs:

1. **data_ingestion** - Every minute at :05 seconds
   - Calls `POST /api/v1/market-data/{symbol}/ingest-latest`
   - Fetches latest 1-minute bar from configured data provider (Tradier or Alpaca)
   - Prevents duplicates
   - Only runs during market hours (9:30 AM - 4:00 PM ET)

2. **refresh_materialized_views** - Every 5 minutes
   - Calls `POST /api/v1/market-data/views/refresh?concurrently=true`
   - Refreshes all 4 materialized views concurrently
   - Updates aggregated timeframe data

### Disabled Jobs (Require Issue Tracking System):

3. **data_health_check** - DISABLED (would run every 15 minutes)
   - Would call `GET /api/v1/market-data/{symbol}/health?days_back=7`
   - Includes gap detection and data quality checks
   - **Problem:** Logs same health failures repeatedly (96+ duplicate warnings/day)
   - **Solution needed:** Database-backed issue tracking with state change detection
   - **Alternative:** Manually call API endpoint when needed

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

## Alpaca API Integration

**Base URL:** `https://data.alpaca.markets`

**Authentication:** Headers `APCA-API-KEY-ID` and `APCA-API-SECRET-KEY`

**Cost:** FREE tier available (paid tiers for enhanced features)

### Stock Bars Endpoint
```
GET /v2/stocks/{symbol}/bars
```

**Parameters:**
- `symbol` - Stock symbol (e.g., SPY)
- `timeframe` - Bar interval (1Min, 5Min, 15Min, 30Min, 1Hour, 1Day)
- `start` - Start date/time (ISO 8601/RFC 3339 format)
- `end` - End date/time (ISO 8601/RFC 3339 format)
- `limit` - Max bars per request (default: 1000, max: 10000)
- `feed` - Data feed ("iex" for free tier, "sip" for paid)
- `page_token` - For pagination

**Historical Data:**
- **5+ years** of data available (since 2016)
- All timeframes: 1Min, 5Min, 15Min, 30Min, 1Hour, 1Day
- FREE tier limitations: IEX exchange only, 15-min delay for "historical" data

**Response Format:**
```json
{
  "bars": [
    {
      "t": "2023-09-29T04:00:00Z",
      "o": 172.015,
      "h": 173.06,
      "l": 170.36,
      "c": 171.29,
      "v": 923134,
      "n": 12630,
      "vw": 171.716432
    }
  ],
  "symbol": "AAPL",
  "next_page_token": "..."
}
```

**Key Advantages:**
- **5+ years** of historical data on FREE tier (vs Tradier's 20 days)
- **VWAP included** in every bar
- **Trade count** (number of trades) included
- **Automatic pagination** for large date ranges
- **No monthly cost** for free tier

## Market Data Provider Architecture

The system uses a **pluggable provider architecture** allowing easy switching between data sources:

### Provider Selection

Set via environment variable:
```bash
MARKET_DATA_PROVIDER=tradier  # or "alpaca"
```

### Architecture Components

1. **BaseMarketDataClient** - Abstract interface all providers implement
2. **TradierClient** - Tradier API implementation
3. **AlpacaClient** - Alpaca API implementation
4. **MarketDataClientFactory** - Returns configured provider instance

### Adding New Providers

To add a new data provider:
1. Create class inheriting from `BaseMarketDataClient`
2. Implement required methods: `fetch_timesales()`, `fetch_latest_bar()`, `parse_bar_to_ohlcv()`
3. Add provider to factory in `market_data_client_factory.py`
4. Update config with new provider option

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
│ MarketDataClientFactory  │
│ - Returns configured     │
│   provider instance      │
└──────┬───────────────────┘
       │
       ├─────────────────┬──────────────────┐
       v                 v                  v
┌─────────────┐   ┌─────────────┐   ┌──────────┐
│TradierClient│   │AlpacaClient │   │  Future  │
│- Real-time  │   │- 5+ years   │   │ Providers│
│- 20 days    │   │- FREE tier  │   │          │
│  historical │   │- VWAP data  │   │          │
└──────┬──────┘   └──────┬──────┘   └────┬─────┘
       │                 │                │
       └─────────────────┴────────────────┘
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

# Alpaca (Market Data & Brokerage)
ALPACA_API_KEY=your_api_key_here
ALPACA_API_SECRET=your_api_secret_here
ALPACA_DATA_API_URL=https://data.alpaca.markets
ALPACA_TRADING_API_URL=https://paper-api.alpaca.markets

# Market Data Provider Selection
MARKET_DATA_PROVIDER=tradier  # Options: "tradier" or "alpaca"

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
1. Health (3 requests - basic health, detailed health, data health with gap detection)
2. Market Data (5 requests - CRUD operations only)
3. Materialized Views (3 requests)
4. Scheduler (3 requests)
5. Admin Tasks (4 requests - partition management)

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
- Tradier: Max 20 days for 1min bars (API limitation)
- Alpaca: 5+ years available (FREE tier)
- Respects provider API rate limits
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
2. **Layered architecture:** API endpoints are thin wrappers that delegate to service layer for business logic
3. **Scheduler architecture:** All scheduled jobs call API endpoints (not services) for consistent DB connection handling
4. **Data Provider Selection:** Set `MARKET_DATA_PROVIDER` env var to switch between Tradier and Alpaca
5. **Tradier Cost:** $10/month Pro plan for real-time data, 20-day historical limit
6. **Alpaca Cost:** FREE tier with 5+ years historical data (IEX exchange only)
7. **TimescaleDB:** We're NOT using it - manual partitioning only
8. **Historical Limits:** Provider-dependent (Tradier: 20 days, Alpaca: 5+ years)
9. **Market hours:** Jobs only run 9:30 AM - 4:00 PM ET on trading days
10. **Partition auto-creation:** Happens on startup, not in migrations
11. **Materialized views:** Already exist from previous migration - don't recreate
12. **Concurrent refresh:** Requires unique index, which exists
13. **Gap detection vs backfill:** `/gaps` only detects and logs, `/backfill` actually fills gaps
14. **VWAP & Trade Count:** Only available with Alpaca (Tradier doesn't provide these)

## Next Steps (Not Yet Implemented)

### Data Quality & Monitoring:
- **Issue tracking system** - Database-backed tracking of data gaps and health failures
  - Store issues with first_seen, last_seen, resolved_at timestamps
  - Deduplication logic to prevent duplicate log spam
  - Admin UI to view/resolve unresolved issues
  - Re-enable gap_detection and data_health_check scheduled jobs
- Log aggregation (CloudWatch, Datadog, Elasticsearch)
- Alerting (email/Slack notifications for critical issues)
- Monitoring dashboard

### Trading Implementation (Live Trading):
- Order execution via broker APIs (Alpaca Trading API, Tradier, etc.)
- Position management (real-time tracking)
- Risk management (position sizing, stop losses, portfolio exposure limits)
- Signal-to-order translation layer
- Live strategy deployment

### Additional Strategies:
- RSI mean reversion
- MACD crossover
- Bollinger Band squeeze
- Moving average crossovers
- Volume-based strategies

### Infrastructure:
- Real-time WebSocket data feed (both Alpaca and Tradier support this)
- Additional data providers (Polygon.io, Interactive Brokers, etc.)
- Backtest optimization (parameter grid search)
- Walk-forward analysis

## Testing

**Test Framework:** Pytest with async support

**Test Structure:**
```
tests/
├── __init__.py
├── conftest.py                     # Shared fixtures and configuration
├── test_database.py                # Database connection and partitions
├── test_tradier_client.py          # Tradier API client
├── test_alpaca_client.py           # Alpaca API client
├── test_market_data_client_factory.py  # Provider factory pattern
├── test_market_hours.py            # Market hours utilities
├── test_market_data_repository.py  # Repository CRUD operations
├── test_data_ingestion.py          # Data ingestion service (provider-agnostic)
├── test_backfill.py                # Historical backfill
├── test_gap_detection.py           # Gap detection and filling
├── test_materialized_view_refresh.py  # View refresh + validation
└── unit/                           # Unit tests
    ├── test_backtest_position_tracker.py  # Position tracking, slippage, commission
    ├── test_indicators.py          # Technical indicators (20 tests)
    └── test_strategy_base.py       # Strategy base class and state management
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

**Coverage (88 tests total):**
- Database connectivity and connection pooling
- Automatic partition creation and management
- Market data provider implementations (Tradier and Alpaca)
- Provider factory pattern and selection
- Market data repository CRUD operations
- Data ingestion (market hours aware, extended hours support, provider-agnostic)
- Historical data backfill (works with any provider)
- Gap detection and automatic filling
- Market hours validation (open/closed, holidays, extended hours)
- Bar parsing and normalization (OHLCV format with VWAP and trade count)
- Materialized view refresh and validation
- **Strategy framework** (base class, state management, multi-timeframe support)
- **Backtest position tracker** (trade execution, slippage, commission, equity tracking)
- **Technical indicators** (SMA, EMA, RSI, MACD, BBands, ATR, VWAP, Stochastic, ADX, etc.)

**Notes:**
- Tests use async fixtures for database connection
- Some tests are conditional based on market hours
- Data ingestion tests may show warnings due to delayed API data (expected behavior)
- Indicator tests use 50 rows of synthetic data to ensure sufficient calculation periods
