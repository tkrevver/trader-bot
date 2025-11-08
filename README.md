# Trader Bot - Automated Trading Platform

An automated day/swing trading bot built with FastAPI, PostgreSQL, and Python. Designed for SPY (S&P 500 ETF) trading with minute-level data ingestion and multi-timeframe analysis.

## Features

### Data Infrastructure
- **Multiple Data Providers**: Pluggable architecture supporting Tradier and Alpaca Markets
  - **Tradier**: Real-time data, $10/month (20 days historical)
  - **Alpaca**: FREE tier with 5+ years historical data + VWAP
- **Extended Hours Trading**: Support for pre-market and after-hours data (4 AM - 8 PM ET)
- **Multi-Timeframe Analysis**: Automatic aggregations (1min, 5min, 15min, 30min, daily) via materialized views
- **Partitioned Storage**: PostgreSQL native partitioning for efficient time-series data management
- **Scheduled Data Collection**: APScheduler for automated data ingestion every minute during market hours
- **Gap Detection**: Automatic detection and backfilling of missing data
- **Timezone-Aware**: All timestamps in configured timezone (Eastern Time for US markets)

### Strategy Framework
- **Modular Strategy Architecture**: Pluggable strategies loaded from `strategies/` folder
- **Multi-Timeframe Support**: Process multiple timeframes (e.g., 1min and 5min) simultaneously
- **State Management**: Per-symbol position and custom state tracking
- **13+ Technical Indicators**: SMA, EMA, RSI, MACD, Bollinger Bands, ATR, VWAP, Stochastic, ADX, and more
- **Indicator Caching**: 60-second TTL cache to avoid redundant calculations
- **Reference Strategy**: Opening Range Breakout implementation included

### Backtesting Engine
- **Event-Driven Backtesting**: Bar-by-bar historical replay with realistic execution
- **Realistic Slippage**: Configurable basis points slippage simulation
- **Commission Support**: Per-share or percentage-based commission
- **25+ Performance Metrics**: Total return, CAGR, Sharpe ratio, Sortino ratio, max drawdown, win rate, profit factor, etc.
- **Detailed Trade Analysis**: Entry/exit pairing, holding periods, win/loss classification
- **Equity Curve Tracking**: Cash and positions value snapshots over time

### Infrastructure
- **Broker Agnostic**: Supports Tastytrade, Tradier, and paper trading (live trading not yet implemented)
- **REST API**: FastAPI-based API with automatic documentation
- **Testing**: Comprehensive pytest test suite with 88 passing tests

## Project Status

**Weeks 1-2 (Data Infrastructure)** ✓
- ✅ Database setup (PostgreSQL with native partitioning)
- ✅ Project structure
- ✅ Configuration management
- ✅ Database migrations (Alembic)
- ✅ FastAPI application with health endpoints
- ✅ Structured logging
- ✅ **Multi-provider data architecture** (Tradier + Alpaca)
- ✅ Real-time/near-real-time data ingestion (1-minute bars)
- ✅ Automated scheduled ingestion
- ✅ Gap detection and backfilling
- ✅ Materialized views for multi-timeframe aggregation
- ✅ Extended hours support
- ✅ Market hours validation
- ✅ **5+ years historical data access** (via Alpaca FREE tier)

**Week 3 (Strategy Framework)** ✓
- ✅ Abstract strategy base class with multi-timeframe support
- ✅ Dynamic strategy loader from `strategies/` folder
- ✅ Per-symbol state management
- ✅ Opening Range Breakout reference implementation
- ✅ 13+ technical indicators via pandas-ta
- ✅ Feature engine with indicator caching (60s TTL)

**Week 6 (Backtesting Engine)** ✓
- ✅ Event-driven backtest orchestration
- ✅ Position tracking with realistic slippage and commission
- ✅ 25+ performance metrics calculator
- ✅ Detailed trade analysis with entry/exit pairing
- ✅ REST API endpoints for running and analyzing backtests
- ✅ Comprehensive test suite (88 tests passing)

**Next Steps** (Weeks 4-5, 7-8)
- Week 4: Signal generation and database storage
- Week 5: Risk management framework
- Week 7: Order execution via broker APIs
- Week 8: Live trading deployment with paper trading validation

## Architecture

### Database

- **Primary**: PostgreSQL 18 with native partitioning
- **Partitioning**: Weekly partitions for OHLCV data (optimized for time-series)
- **Indexes**: BRIN indexes for time columns, B-tree for symbol lookups
- **Aggregations**: Materialized views for multi-timeframe data

### Technology Stack

- **FastAPI**: Modern async web framework
- **PostgreSQL**: Time-series optimized with partitioning
- **asyncpg**: Async PostgreSQL driver
- **Alembic**: Database migrations
- **APScheduler**: Background task scheduling
- **Pydantic**: Data validation and settings
- **pandas-ta**: Technical indicators

## Setup

### Prerequisites

- Python 3.13+
- PostgreSQL 18+ (via Postgres.app or Homebrew)
- **Market Data Provider** (choose one or both):
  - **Alpaca** (recommended for backtesting): FREE account at https://alpaca.markets
  - **Tradier**: $10/month account at https://tradier.com

### Installation

1. **Clone the repository** (if applicable)

2. **Activate virtual environment:**
   ```bash
   source .venv/bin/activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment variables:**
   ```bash
   cp .env.example .env
   # Edit .env with your settings
   ```

5. **Run database migrations:**
   ```bash
   alembic upgrade head
   ```

## Running the Application

### Development Mode (with auto-reload)

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

**Note:** The main FastAPI app is in `main.py` at the project root, NOT `app/main.py`.

### Production Mode

```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

## API Documentation

Once the server is running:

- **Interactive API docs (Swagger UI):** http://localhost:8000/docs
- **Alternative API docs (ReDoc):** http://localhost:8000/redoc
- **Root endpoint:** http://localhost:8000/

## API Endpoints

### Health & Status

- `GET /` - Root endpoint with API information
- `GET /health` - Basic health check
- `GET /health/detailed` - Detailed component health status (database, scheduler, tradier)

### Market Data

- `GET /api/v1/market-data/{symbol}/latest` - Latest bar for a timeframe
- `GET /api/v1/market-data/{symbol}/history` - Historical bars with time range
- `GET /api/v1/market-data/{symbol}/gaps` - Detect missing data gaps
- `POST /api/v1/market-data/{symbol}/ingest-latest` - Trigger manual ingestion (used by scheduler)
- `POST /api/v1/market-data/{symbol}/backfill` - Manual backfill historical data
- `GET /api/v1/market-data/{symbol}/health` - Data quality and coverage metrics
- `GET /api/v1/market-data/{symbol}/stats` - Statistics about available data

### Materialized Views

- `POST /api/v1/market-data/views/refresh` - Refresh all aggregated views
- `POST /api/v1/market-data/views/refresh?view_name=ohlcv_5min` - Refresh specific view
- `GET /api/v1/market-data/views/stats` - View row counts and sizes

### Scheduler

- `GET /api/v1/scheduler/status` - Scheduler status and job information
- `POST /api/v1/scheduler/jobs/{job_id}/pause` - Pause a scheduled job
- `POST /api/v1/scheduler/jobs/{job_id}/resume` - Resume a paused job

### Backtesting

- `POST /api/v1/backtest` - Run a backtest with configuration
- `GET /api/v1/backtest/{backtest_id}` - Get backtest status
- `GET /api/v1/backtest/{backtest_id}/results` - Get performance metrics
- `GET /api/v1/backtest/{backtest_id}/trades` - Get all trades
- `GET /api/v1/backtest/{backtest_id}/equity` - Get equity curve
- `GET /api/v1/backtest/{backtest_id}/detailed` - Get detailed trade analysis (entry/exit pairs, holding periods, win/loss)
- `GET /api/v1/backtest` - List all backtests with optional filters
- `DELETE /api/v1/backtest/{backtest_id}` - Delete a backtest

### Coming Soon

- Trading control (start/stop)
- Position management (live trading)
- Order execution via broker APIs
- Signal generation and storage
- Risk management enforcement

## Database Schema

### Core Tables

- **ohlcv_1min** - Partitioned table for minute-level OHLCV data (with volume, VWAP, trade count)
- **backtests** - Backtest metadata, configuration, status, and performance metrics
- **backtest_trades** - Individual trades from backtests (entry/exit prices, P&L, commission, slippage)
- **backtest_equity_curve** - Equity snapshots over time for drawdown calculations
- **trades** - Executed trades log (live trading - not yet implemented)
- **orders** - Order history (live trading - not yet implemented)
- **positions** - Current and historical positions (live trading - not yet implemented)
- **signals** - Strategy signals (not yet implemented)
- **strategies** - Strategy configurations (not yet implemented)
- **account_snapshots** - Daily account snapshots (live trading - not yet implemented)

### Materialized Views

- **ohlcv_5min** - 5-minute aggregated data
- **ohlcv_15min** - 15-minute aggregated data
- **ohlcv_30min** - 30-minute aggregated data
- **ohlcv_daily** - Daily aggregated data

## Database Management

### View Migrations

```bash
# View migration status
alembic current

# View migration history
alembic history

# Upgrade to latest
alembic upgrade head

# Downgrade one version
alembic downgrade -1

# Downgrade to specific version
alembic downgrade <revision_id>
```

### Create New Migration

```bash
alembic revision -m "description_of_change"
```

## Configuration

Configuration is managed via environment variables in the `.env` file:

- **Database**: PostgreSQL connection settings
- **Market Data Provider**: Choose between `tradier` or `alpaca`
  - **Tradier**: API token for real-time data and brokerage
  - **Alpaca**: API key/secret for FREE 5+ years historical data
- **Broker**: Tastytrade, Tradier, or paper trading
- **Trading**: Risk management parameters (position sizing, loss limits)
- **Market Hours**: Extended hours support (pre-market and after-hours)
- **Timezone**: Market timezone (America/New_York for US markets)
- **Safety**: Enable trading flags (ENABLE_TRADING, ENABLE_LIVE_TRADING)

### Switching Data Providers

Simply change one environment variable in `.env`:

```bash
# Use Tradier (real-time, $10/month, 20 days historical)
MARKET_DATA_PROVIDER=tradier

# OR use Alpaca (FREE, 5+ years historical + VWAP)
MARKET_DATA_PROVIDER=alpaca
```

See `.env.example` for all available options.

## Development

### Project Structure

```
trader-bot/
├── app/                    # Application code
│   ├── api/               # REST API endpoints
│   │   ├── backtest.py   # Backtest endpoints
│   │   ├── health.py     # Health check endpoints
│   │   ├── market_data.py # Market data endpoints
│   │   ├── scheduler.py  # Scheduler management
│   │   └── tasks.py      # Admin tasks
│   ├── brokers/           # Broker integrations (not yet implemented)
│   ├── db/                # Database layer
│   │   ├── repositories/ # Data access layer
│   │   │   ├── backtest.py # Backtest CRUD
│   │   │   └── market_data.py # OHLCV operations
│   │   └── partition_manager.py # Auto partition creation
│   ├── models/            # Pydantic models
│   │   ├── backtest.py   # Backtest models
│   │   └── market_data.py # OHLCV models
│   ├── services/          # Business logic
│   │   ├── backtest_metrics.py # 25+ performance metrics
│   │   ├── backtest_position_tracker.py # Trade execution simulation
│   │   ├── backtest_runner.py # Event-driven backtest orchestration
│   │   ├── base_market_data_client.py  # Abstract provider interface
│   │   ├── tradier_client.py           # Tradier implementation
│   │   ├── alpaca_client.py            # Alpaca implementation
│   │   ├── market_data_client_factory.py  # Provider selector
│   │   ├── data_ingestion.py           # Data orchestration
│   │   └── feature_engine.py           # Indicator caching
│   ├── strategies/        # Strategy framework
│   │   ├── base.py       # Abstract Strategy base class
│   │   └── loader.py     # Dynamic strategy loader
│   ├── tasks/             # Background tasks
│   ├── utils/             # Utilities
│   │   ├── indicators.py # 13+ technical indicators
│   │   ├── logger.py     # Structured logging
│   │   └── market_hours.py # Market hours utilities
│   ├── websockets/        # WebSocket endpoints (not yet implemented)
│   └── config.py          # Configuration
├── main.py                # FastAPI app (ROOT, not app/)
├── alembic/               # Database migrations
├── strategies/            # User-defined strategies
│   └── opening_range_breakout.py # Reference implementation
├── tests/                 # Tests (88 passing)
│   ├── test_*.py         # Integration tests
│   └── unit/             # Unit tests
│       ├── test_backtest_position_tracker.py
│       ├── test_indicators.py
│       └── test_strategy_base.py
├── bruno/trader-bot/      # API request collection
│   ├── Backtest/         # Backtest API requests
│   ├── Market Data/      # Market data requests
│   └── ...
├── scripts/               # Utility scripts
├── .env                   # Environment config
├── requirements.txt       # Dependencies
├── ALPACA_INTEGRATION.md  # Alpaca integration docs
├── CLAUDE.md              # AI assistant context
├── IMPLEMENTATION_PLAN.md # Detailed plan
└── README.md             # This file
```

### Adding Strategies

Create a new strategy in the `strategies/` directory:

1. Create a Python file (e.g., `strategies/my_strategy.py`)
2. Inherit from `app.strategies.base.Strategy`
3. Implement required methods:
   - `get_metadata()` - Strategy name, description, parameters
   - `validate_parameters()` - Parameter validation
   - `on_bar()` - Process market data bars
   - `generate_signals()` - Generate buy/sell signals

See `strategies/opening_range_breakout.py` for a complete example.

### Running Tests

```bash
pytest
```

With coverage:

```bash
pytest --cov=app --cov-report=html
```

## Deployment

### Local Development

The application is designed to run locally with zero cloud costs:

- PostgreSQL on local machine
- FastAPI server on localhost
- Can execute live trades during market hours

### Cloud Deployment (Future)

When strategies prove profitable, deploy to:

- **GCP Cloud Run**: Serverless FastAPI hosting
- **Timescale Cloud**: Managed TimescaleDB (~$48/month)
- **OR**: GCP Compute Engine with self-hosted PostgreSQL (~$67/month)

## Safety Features

- **Double Enable Flags**: Both `ENABLE_TRADING` and `ENABLE_LIVE_TRADING` must be true
- **Paper Trading Default**: Always defaults to paper broker
- **Daily Loss Limits**: Automatic halt on excessive losses
- **Position Size Limits**: Prevent over-concentration
- **End-of-Day Closure**: Mandatory position closure for day trading

## Documentation

- **Implementation Plan**: See `IMPLEMENTATION_PLAN.md` for detailed architecture and roadmap
- **AI Context**: See `CLAUDE.md` for comprehensive system documentation
- **API Docs**: Available at `/docs` when server is running
- **Database Schema**: See Alembic migrations in `alembic/versions/`

## License

[Add your license here]

## Support

For questions or issues, please refer to the `IMPLEMENTATION_PLAN.md` or open an issue.

---

**Version**: 3.0.0 (Strategy Framework + Backtesting Engine)
**Last Updated**: 2025-11-07

## Recent Updates

### v3.0.0 - Strategy Framework + Backtesting Engine (Week 3 & 6)
- ✨ Modular strategy framework with multi-timeframe support
- 📈 13+ technical indicators (SMA, EMA, RSI, MACD, BBands, ATR, VWAP, etc.)
- 🔄 Event-driven backtesting engine with realistic slippage and commission
- 📊 25+ performance metrics (Sharpe ratio, max drawdown, win rate, etc.)
- 🎯 Opening Range Breakout reference strategy implementation
- 🧪 Comprehensive test suite (88 tests passing)
- 🔍 Detailed trade analysis with entry/exit pairing and holding periods
- 💾 Backtest persistence and retrieval via REST API

### v2.1.0 - Multi-Provider Data Architecture (Week 1-2)
- ✨ Added Alpaca Markets integration (FREE 5+ years historical data)
- 🏗️ Implemented pluggable data provider architecture
- 📊 VWAP and trade count support (Alpaca)
- 🔧 Easy provider switching via environment variable
- ✅ Comprehensive test suite for both providers
