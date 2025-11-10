# ML Trading Strategy Runbook

Complete guide for developing, training, and backtesting machine learning trading strategies.

---

## Table of Contents

1. [Overview](#overview)
2. [Data Preparation](#data-preparation)
3. [Feature Engineering](#feature-engineering)
4. [Labeling Strategy](#labeling-strategy)
5. [Training Process](#training-process)
6. [Backtesting](#backtesting)
7. [Model Iteration](#model-iteration)
8. [Troubleshooting](#troubleshooting)

---

## Overview

The ML trading pipeline consists of:

1. **Data Export** - Export OHLCV data from database to Parquet files
2. **Feature Engineering** - Compute technical indicators across multiple timeframes
3. **Labeling** - Apply Triple Barrier Method to generate BUY/SELL/HOLD labels
4. **Training** - Train XGBoost classifier with proper train/val/test splits
5. **Backtesting** - Evaluate strategy performance on historical data

**Tech Stack:**
- XGBoost for classification
- pandas/numpy for data manipulation
- pandas-ta for technical indicators
- Triple Barrier Method for labeling

---

## Data Preparation

### Step 0: macOS Setup

**macOS users only:** Install OpenMP library required by XGBoost:

```bash
brew install libomp
```

This is not required on Linux or Windows.

---

### Step 1: Export Data from Database

Export OHLCV bars from PostgreSQL to Parquet files for efficient ML processing.

**Script:** `scripts/ml/export_data.py`

```python
"""
Exports multi-timeframe OHLCV data to Parquet files.

Creates:
- data/spy_ohlcv_1min.parquet
- data/spy_ohlcv_5min.parquet
- data/spy_ohlcv_15min.parquet
- data/spy_ohlcv_30min.parquet
"""
```

**Usage:**

```bash
python scripts/ml/export_data.py
```

**What it does:**
1. Connects to PostgreSQL database
2. Queries OHLCV data for specified date range (default: 2 years)
3. Exports to compressed Parquet files in `data/` folder
4. Prints row counts and date ranges

**Configuration:**

Edit `export_data.py` to change:
```python
SYMBOL = "SPY"
START_DATE = "2023-11-17"  # Adjust lookback period
END_DATE = "2025-11-06"
```

**Output:**
```
data/
├── spy_ohlcv_1min.parquet   # ~124,000 rows (1 bar per minute)
├── spy_ohlcv_5min.parquet   # ~26,000 rows
├── spy_ohlcv_15min.parquet  # ~9,000 rows
└── spy_ohlcv_30min.parquet  # ~4,500 rows
```

**File Format:**

Parquet files contain columns:
- `time` (datetime with timezone)
- `open`, `high`, `low`, `close` (OHLC prices)
- `volume` (trading volume)
- `vwap` (volume-weighted average price)

---

## Feature Engineering

### Overview

The `FeatureEngineer` class computes 140+ features from multi-timeframe OHLCV data.

**File:** `app/ml/feature_engineering.py`

**Supported Timeframes:**
- 1-minute (fast signals)
- 5-minute (medium-term momentum)
- 15-minute (trend context)
- 30-minute (market structure)

### Feature Categories

**1. Trend Indicators**
- SMA (10, 20, 50 periods)
- EMA (10, 20, 50 periods)
- Price-to-SMA ratios

**2. Momentum Indicators**
- RSI (14, 21 periods)
- Stochastic Oscillator (K, D)
- Williams %R (14 periods)
- MACD (12, 26, 9)

**3. Volatility Indicators**
- ATR (14, 20 periods)
- Bollinger Bands (upper, middle, lower, width, %B)

**4. Volume Indicators**
- Volume SMA (20 periods)
- Volume ratio (current / SMA)
- Price-to-VWAP ratio

**5. Trend Strength**
- ADX (14 periods)

**6. Time-Based Features**
- Hour, minute, day of week
- Market period flags (first 30min, last hour, etc.)
- Monday/Friday flags
- Minutes since market open

**7. Derived Features**
- Lagged prices (1, 5 bars)
- Lagged RSI and differences
- Rolling mean/std (30 bars)
- Z-score (30 bars)
- RSI × Volume interaction
- Trend alignment across timeframes

### Adding New Features

**Step 1:** Add indicator to `_add_timeframe_features()` method

```python
# Example: Add CCI indicator
from app.utils import indicators

def _add_timeframe_features(self, df, source_df, suffix):
    # ... existing features ...

    # Add CCI (Commodity Channel Index)
    cci = indicators.cci(ohlcv_df, length=20)
    if cci is not None and not cci.empty:
        df[f'cci_20{suffix}'] = cci['CCI_20_0.015']
    else:
        df[f'cci_20{suffix}'] = 0  # Neutral value

    return df
```

**Step 2:** Add to `_add_derived_features()` for interactions

```python
def _add_derived_features(self, df):
    # ... existing features ...

    # Add CCI momentum (change in CCI)
    if 'cci_20_1min' in df.columns:
        df['cci_momentum'] = df['cci_20_1min'].diff()

    return df
```

**Step 3:** Update feature count in docstrings

### Removing Features

**Option 1: Comment out in code**

```python
def _add_timeframe_features(self, df, source_df, suffix):
    # ... other features ...

    # Disable Williams %R (not useful)
    # df[f'williams_r{suffix}'] = indicators.williams_r(ohlcv_df, length=14)
```

**Option 2: Filter during training**

In `train_xgboost.py`:
```python
# Remove low-importance features
features_to_remove = ['williams_r_1min', 'williams_r_5min', 'stoch_k_30min']
feature_cols = [col for col in feature_cols if col not in features_to_remove]
```

### Testing Feature Engineering

```python
from app.ml.feature_engineering import FeatureEngineer
import pandas as pd

# Load data
df_1min = pd.read_parquet('data/spy_ohlcv_1min.parquet')
df_5min = pd.read_parquet('data/spy_ohlcv_5min.parquet')
df_15min = pd.read_parquet('data/spy_ohlcv_15min.parquet')
df_30min = pd.read_parquet('data/spy_ohlcv_30min.parquet')

# Create features
engineer = FeatureEngineer(df_1min, df_5min, df_15min, df_30min)
df_features = engineer.create_all_features()

print(f"Features created: {len(df_features.columns)}")
print(f"Rows: {len(df_features)}")
print(f"Null counts:\n{df_features.isnull().sum()}")
```

---

## Labeling Strategy

### Triple Barrier Method

The Triple Barrier Method creates 3-class labels (BUY/HOLD/SELL) based on which of 3 barriers is hit first:

1. **Profit Target** - Upper barrier (e.g., +0.5%)
2. **Stop Loss** - Lower barrier (e.g., -0.3%)
3. **Time Limit** - Maximum holding period (e.g., 30 bars)

**File:** `app/ml/labeling.py`

### Configuration

```python
from app.ml.labeling import TripleBarrierLabeler

labeler = TripleBarrierLabeler(
    profit_target_pct=0.005,  # 0.5% profit target
    stop_loss_pct=0.003,      # 0.3% stop loss
    time_limit_bars=30        # 30-minute max holding
)
```

### Label Classes

- **BUY (+1)** - Profit target hit first → profitable long opportunity
- **HOLD (0)** - Time limit hit first → no clear direction
- **SELL (-1)** - Stop loss hit first → losing long opportunity

### Adjusting Labels for Better Balance

**Problem:** Default settings create severe class imbalance (79% HOLD).

**Solution 1: More Aggressive Targets**
```python
labeler = TripleBarrierLabeler(
    profit_target_pct=0.003,  # Lower to 0.3% (easier to hit)
    stop_loss_pct=0.002,      # Lower to 0.2% (tighter stop)
    time_limit_bars=20        # Shorter time limit
)
```

**Solution 2: Asymmetric Barriers**
```python
labeler = TripleBarrierLabeler(
    profit_target_pct=0.004,  # 0.4% profit
    stop_loss_pct=0.004,      # 0.4% stop (symmetric)
    time_limit_bars=25
)
```

**Solution 3: Time-of-Day Specific Labels**
```python
# Higher targets during volatile market open
# Lower targets during midday chop
morning_labeler = TripleBarrierLabeler(0.007, 0.005, 30)
midday_labeler = TripleBarrierLabeler(0.003, 0.002, 20)
```

### Label Metadata

The labeler tracks metadata per label:
- `exit_reason`: Which barrier was hit (profit/loss/time)
- `holding_period`: Bars until exit
- `pnl_pct`: Actual P&L at exit

Use this to analyze labeling quality:
```python
df_labeled = labeler.label(df)

# Check label distribution
print(df_labeled['label'].value_counts(normalize=True))

# Analyze holding periods
print(df_labeled.groupby('label')['holding_period'].mean())

# Check P&L by label
print(df_labeled.groupby('label')['pnl_pct'].mean())
```

---

## Training Process

### Overview

Train XGBoost classifier on labeled multi-timeframe features.

**Script:** `scripts/ml/train_xgboost.py`

### Data Splits

**Temporal Split (Critical for Time Series):**

```
|------------------------|----------|----------|
     Training (70%)        Val (15%)  Test (15%)
   2023-11-17 to          2025-02-13  2025-08-05
     2025-02-13           to          to
                         2025-08-05  2025-11-06
```

**Why temporal?** Prevents look-ahead bias. Model must predict future, not explain past.

### Training Configuration

**Default Hyperparameters:**
```python
model = XGBClassifier(
    n_estimators=100,       # Number of boosting rounds
    max_depth=6,            # Tree depth
    learning_rate=0.1,      # Step size shrinkage
    subsample=0.8,          # Row sampling per tree
    colsample_bytree=0.8,   # Feature sampling per tree
    objective='multi:softmax',  # 3-class classification
    num_class=3,            # BUY/HOLD/SELL
    eval_metric='mlogloss', # Multi-class log loss
    random_state=42,
    scale_pos_weight=None,  # Auto-compute class weights
)
```

### Running Training

**Basic training:**
```bash
python scripts/ml/train_xgboost.py
```

**What it does:**
1. Loads Parquet files from `data/`
2. Creates features using `FeatureEngineer`
3. Applies Triple Barrier labeling
4. Splits into train/val/test (70/15/15)
5. Handles class imbalance with `scale_pos_weight`
6. Trains XGBoost classifier
7. Evaluates on validation and test sets
8. Saves model and feature columns
9. Prints feature importance

**Output Files:**
```
models/
├── xgboost_spy_latest.pkl    # Trained model
├── feature_columns.json       # List of 140 features (order matters!)
└── training_metrics.json      # Accuracy, confusion matrix, etc.
```

### Handling Class Imbalance

**Method 1: Class Weights (Current)**
```python
from sklearn.utils.class_weight import compute_class_weight

class_weights = compute_class_weight(
    'balanced',
    classes=np.array([-1, 0, 1]),
    y=y_train
)
# XGBoost uses scale_pos_weight internally
```

**Method 2: Undersampling HOLD Labels**
```python
from imblearn.under_sampling import RandomUnderSampler

rus = RandomUnderSampler(
    sampling_strategy={-1: 10000, 0: 30000, 1: 10000},
    random_state=42
)
X_resampled, y_resampled = rus.fit_resample(X_train, y_train)
```

**Method 3: Oversampling BUY/SELL (SMOTE)**
```python
from imblearn.over_sampling import SMOTE

smote = SMOTE(
    sampling_strategy={-1: 30000, 0: 30000, 1: 30000},
    random_state=42
)
X_resampled, y_resampled = smote.fit_resample(X_train, y_train)
```

### Hyperparameter Tuning

**Manual Grid Search:**
```python
param_grid = {
    'n_estimators': [50, 100, 200],
    'max_depth': [3, 6, 9],
    'learning_rate': [0.01, 0.1, 0.3],
    'subsample': [0.6, 0.8, 1.0],
}

best_score = 0
best_params = None

for n_est in param_grid['n_estimators']:
    for depth in param_grid['max_depth']:
        for lr in param_grid['learning_rate']:
            model = XGBClassifier(
                n_estimators=n_est,
                max_depth=depth,
                learning_rate=lr,
                ...
            )
            model.fit(X_train, y_train)
            score = model.score(X_val, y_val)

            if score > best_score:
                best_score = score
                best_params = {'n_estimators': n_est, 'max_depth': depth, 'learning_rate': lr}
```

**sklearn GridSearchCV:**
```python
from sklearn.model_selection import TimeSeriesSplit
from sklearn.model_selection import GridSearchCV

tscv = TimeSeriesSplit(n_splits=5)

grid = GridSearchCV(
    XGBClassifier(random_state=42),
    param_grid=param_grid,
    cv=tscv,
    scoring='accuracy',
    verbose=2,
    n_jobs=-1
)

grid.fit(X_train, y_train)
print(f"Best params: {grid.best_params_}")
print(f"Best score: {grid.best_score_}")
```

### Feature Importance Analysis

After training, analyze feature importance:

```python
import matplotlib.pyplot as plt

# Get feature importance
importance = model.feature_importances_
feature_importance = pd.DataFrame({
    'feature': feature_cols,
    'importance': importance
}).sort_values('importance', ascending=False)

# Plot top 20
top_features = feature_importance.head(20)
plt.figure(figsize=(10, 8))
plt.barh(top_features['feature'], top_features['importance'])
plt.xlabel('Importance')
plt.title('Top 20 Features')
plt.tight_layout()
plt.savefig('models/feature_importance.png')

# Remove low-importance features (<1%)
threshold = 0.01
important_features = feature_importance[
    feature_importance['importance'] > threshold
]['feature'].tolist()

print(f"Features above {threshold}: {len(important_features)}")
```

### Training Best Practices

1. **Always use temporal splits** - Never shuffle time series data
2. **Monitor validation accuracy** - Should be close to training (within 5%)
3. **Check confusion matrix** - Ensure model predicts all 3 classes
4. **Review label distribution** - Aim for 20-40% BUY/SELL combined
5. **Save training logs** - Track experiments and hyperparameters
6. **Version models** - Use timestamps: `xgboost_spy_2025_11_08.pkl`

---

## Backtesting

### Overview

Evaluate trained ML strategy on historical out-of-sample data.

**Script:** `scripts/ml/backtest_ml_strategy.py`

### Configuration

```python
config = {
    "model_path": "models/xgboost_spy_latest.pkl",
    "position_size": 10,              # Shares per trade
    "confidence_threshold": 0.65,     # Min probability to act
    "require_all_timeframes": True,   # Need 1/5/15/30min data
    "max_bars_buffer": 200,           # Bars kept in memory
}

backtest_config = {
    "symbol": "SPY",
    "start_date": "2025-08-05",       # Test period start
    "end_date": "2025-11-06",         # Test period end
    "initial_capital": 10000,         # Starting cash
    "commission_per_share": 0,        # Zero for now
    "slippage_bps": 5,                # 5 basis points (0.05%)
}
```

### Running Backtest

**Command line:**
```bash
python scripts/ml/backtest_ml_strategy.py
```

**Via Bruno API:**
1. Open Bruno
2. Go to `Backtest > Strategy: ML XGBoost`
3. Adjust config if needed (confidence, position size, dates)
4. Click "Send"

**Expected runtime:** 10-15 minutes for 3 months of 1-minute data

### Performance Metrics

The backtest calculates 25+ metrics:

**Returns:**
- Total Return %
- CAGR (annualized return)
- Daily returns mean/std

**Risk-Adjusted:**
- Sharpe Ratio (return / volatility)
- Sortino Ratio (return / downside volatility)
- Calmar Ratio (return / max drawdown)

**Drawdown:**
- Max Drawdown % (peak-to-trough decline)
- Max Drawdown Duration (days)
- Current Drawdown %

**Trade Statistics:**
- Total Trades
- Win Rate %
- Profit Factor (gross profit / gross loss)
- Average Win/Loss
- Best/Worst Trade
- Average Holding Period

**Streaks:**
- Longest Winning Streak
- Longest Losing Streak

### Interpreting Results

**Good Performance:**
```
Total Return: +15%
Sharpe Ratio: > 1.5
Win Rate: > 45%
Profit Factor: > 1.5
Max Drawdown: < 10%
```

**Poor Performance (Current Model):**
```
Total Return: -6.57%
Sharpe Ratio: -1.74
Win Rate: 17.54%
Profit Factor: 0.59
Max Drawdown: 7.34%
```

**Red Flags:**
- Win rate < 30% → Model is guessing wrong
- Profit Factor < 1.0 → Losses exceed wins
- Negative Sharpe → Returns don't justify risk
- Max Drawdown > 20% → Too risky

### Adjusting Strategy Parameters

**1. Confidence Threshold**

Lower threshold → more trades (but lower quality):
```python
config["confidence_threshold"] = 0.55  # Down from 0.65
```

Higher threshold → fewer trades (but higher quality):
```python
config["confidence_threshold"] = 0.75  # Up from 0.65
```

**2. Position Size**

More aggressive:
```python
config["position_size"] = 20  # 2x risk
```

More conservative:
```python
config["position_size"] = 5  # 0.5x risk
```

**3. Commission/Slippage**

Realistic costs:
```python
backtest_config["commission_per_share"] = 0.005  # $0.005/share
backtest_config["slippage_bps"] = 10             # 10 bps
```

### Walk-Forward Analysis

Test model robustness across different periods:

```python
periods = [
    ("2025-08-05", "2025-09-05"),  # August
    ("2025-09-06", "2025-10-06"),  # September
    ("2025-10-07", "2025-11-06"),  # October
]

for start, end in periods:
    backtest_config["start_date"] = start
    backtest_config["end_date"] = end
    # Run backtest
    # Record metrics
    # Compare consistency
```

Good models should have similar Sharpe ratios across periods.

### Detailed Trade Analysis

Get trade-by-trade breakdown:

```bash
# Via API
GET /api/v1/backtest/{backtest_id}/detailed
```

**Response includes:**
- Entry/exit times (timezone-aware)
- Entry/exit prices
- P&L per trade
- Win/Loss classification
- Holding period (minutes)
- Commission and slippage per trade

Use this to:
- Identify winning patterns (time of day, market conditions)
- Spot losing patterns (avoid certain setups)
- Calculate risk/reward per trade
- Analyze holding time distribution

---

## Model Iteration

### Workflow for Improving Models

**Iteration Cycle:**

1. **Analyze Current Performance** → Identify weaknesses
2. **Adjust Labeling OR Features** → Target specific issues
3. **Retrain Model** → With new configuration
4. **Backtest** → Evaluate improvement
5. **Repeat** → Until satisfactory or diminishing returns

### Common Improvement Strategies

**Problem: Low Win Rate (< 30%)**

Causes:
- Labels don't match market dynamics
- Profit/stop targets too tight/loose
- Features lack predictive power

Solutions:
- Adjust Triple Barrier parameters
- Add regime-specific features (volatility, trend strength)
- Filter training data (remove choppy periods)

**Problem: Few Trades Generated**

Causes:
- Model predicts mostly HOLD
- Confidence threshold too high
- Class imbalance in training

Solutions:
- Retrain with balanced classes (undersample HOLD)
- Lower confidence threshold
- Use more aggressive labeling

**Problem: Model Overfitting (High Train, Low Test Accuracy)**

Causes:
- Too many features
- Too deep trees (max_depth too high)
- Not enough data

Solutions:
- Feature selection (remove low-importance)
- Regularization (lower max_depth, higher learning_rate)
- Add more training data
- Use early stopping

**Problem: High Drawdowns**

Causes:
- No stop losses in strategy
- Position sizing too aggressive
- Model doesn't predict volatility

Solutions:
- Add stop-loss logic to strategy
- Dynamic position sizing based on volatility
- Train separate model for position sizing
- Filter trades during high volatility

### Experiment Tracking

Keep a log of experiments:

```
experiments.csv:
date,model_version,labeling_config,train_acc,test_acc,sharpe,win_rate,notes
2025-11-08,v1,0.5/0.3/30,84.4,89.5,-1.74,17.5,Baseline - too conservative
2025-11-09,v2,0.3/0.2/20,76.2,78.1,0.45,38.2,More balanced labels - better
2025-11-10,v3,0.3/0.2/20+SMOTE,71.5,73.8,0.62,41.5,SMOTE oversampling - best so far
```

### Versioning Models

Use timestamps and metadata:

```python
import datetime

timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
model_path = f"models/xgboost_spy_{timestamp}.pkl"

# Save with metadata
import json
metadata = {
    "timestamp": timestamp,
    "profit_target_pct": 0.003,
    "stop_loss_pct": 0.002,
    "time_limit_bars": 20,
    "train_accuracy": 76.2,
    "test_accuracy": 78.1,
    "features_count": 140,
    "label_distribution": {"BUY": 0.35, "HOLD": 0.30, "SELL": 0.35}
}

with open(model_path.replace('.pkl', '_metadata.json'), 'w') as f:
    json.dump(metadata, f, indent=2)
```

---

## Troubleshooting

### Data Issues

**Problem: Missing bars in exported data**

```bash
# Check for gaps
python -c "
import pandas as pd
df = pd.read_parquet('data/spy_ohlcv_1min.parquet')
df['time_diff'] = df['time'].diff()
gaps = df[df['time_diff'] > pd.Timedelta('2 minutes')]
print(f'Gaps found: {len(gaps)}')
print(gaps[['time', 'time_diff']])
"
```

**Problem: NaN values in features**

```python
# Check nulls
df_features = engineer.create_all_features()
null_cols = df_features.columns[df_features.isnull().any()].tolist()
print(f"Columns with nulls: {null_cols}")

# Forward-fill then drop remaining
df_features = df_features.ffill().dropna()
```

**Problem: Feature values are inf/-inf**

```python
# Replace inf with large finite numbers
df_features = df_features.replace([np.inf, -np.inf], np.nan)
df_features = df_features.ffill().bfill().fillna(0)
```

### Training Issues

**Problem: "ValueError: Feature columns mismatch"**

Cause: Features changed but using old model

Solution:
```bash
# Retrain from scratch
rm models/xgboost_spy_latest.pkl
rm models/feature_columns.json
python scripts/ml/train_xgboost.py
```

**Problem: Very slow training (> 30 minutes)**

Causes:
- Too many features (> 500)
- Too many estimators (> 500)
- Too much data (> 1M rows)

Solutions:
```python
# Reduce estimators
model = XGBClassifier(n_estimators=50)  # Down from 100

# Feature selection
from sklearn.feature_selection import SelectKBest, f_classif
selector = SelectKBest(f_classif, k=50)  # Keep top 50
X_train_selected = selector.fit_transform(X_train, y_train)

# Sample data
df_sampled = df.sample(frac=0.5, random_state=42)  # Use 50%
```

**Problem: Model predicts only one class**

Check class weights:
```python
print(f"Label distribution:\n{y_train.value_counts()}")

# Force balanced training
from imblearn.under_sampling import RandomUnderSampler
rus = RandomUnderSampler(random_state=42)
X_resampled, y_resampled = rus.fit_resample(X_train, y_train)
```

### Backtest Issues

**Problem: 0 trades generated**

Causes:
- Model predicts all HOLD
- Confidence threshold too high
- Missing timeframe data

Debug:
```python
# Check predictions
from strategies.ml_strategy import MLStrategy
strategy = MLStrategy(config)
strategy.on_start()

# Feed some bars and check raw predictions
probabilities = model.predict_proba(X_test[:10])
predictions = model.predict(X_test[:10])
print(f"Predictions: {predictions}")
print(f"Max probabilities: {probabilities.max(axis=1)}")
```

**Problem: Backtest fails with KeyError**

Check strategy code for proper feature column handling:
```python
# In MLStrategy.generate_signals()
try:
    X = latest_features[self.feature_columns].values.reshape(1, -1)
except KeyError as e:
    print(f"Missing feature: {e}")
    print(f"Available features: {latest_features.columns.tolist()}")
    return []
```

**Problem: Performance warnings during backtest**

Ignore pandas PerformanceWarnings about fragmentation - they don't affect results:
```python
import warnings
warnings.filterwarnings('ignore', category=pd.errors.PerformanceWarning)
```

### Model Performance Issues

**Problem: Good accuracy but poor trading performance**

Cause: Model optimizes for accuracy, not profit

Solutions:
- Use custom loss function (profit-based)
- Weight classes by profitability, not frequency
- Train separate model for profit prediction (regression)
- Use accuracy as filter, profitability for ranking

**Problem: Works in backtest but fails in paper trading**

Causes:
- Look-ahead bias in features
- Overfitting to backtest period
- Market regime changed

Solutions:
- Check feature engineering for future data leakage
- Walk-forward test on multiple periods
- Retrain on recent data
- Add regime detection

---

## Quick Reference

### File Locations

```
trader-bot/
├── app/ml/
│   ├── feature_engineering.py    # FeatureEngineer class
│   └── labeling.py                # TripleBarrierLabeler class
├── strategies/
│   └── ml_strategy.py             # MLStrategy implementation
├── scripts/ml/
│   ├── export_data.py             # Export to Parquet
│   ├── train_xgboost.py           # Training script
│   └── backtest_ml_strategy.py    # Backtest script
├── data/
│   └── spy_ohlcv_*.parquet        # Training data
├── models/
│   ├── xgboost_spy_latest.pkl     # Trained model
│   └── feature_columns.json       # Feature list
└── bruno/trader-bot/Backtest/
    └── Strategy- ML XGBoost.bru   # API request
```

### Command Cheat Sheet

```bash
# 1. Export data
python scripts/ml/export_data.py

# 2. Train model
python scripts/ml/train_xgboost.py

# 3. Backtest
python scripts/ml/backtest_ml_strategy.py

# 4. Check data quality
python -c "import pandas as pd; df = pd.read_parquet('data/spy_ohlcv_1min.parquet'); print(f'Rows: {len(df)}, Date range: {df.time.min()} to {df.time.max()}')"

# 5. Inspect model
python -c "import pickle; model = pickle.load(open('models/xgboost_spy_latest.pkl', 'rb')); print(model.get_params())"

# 6. Clean up
rm -rf data/*.parquet models/*.pkl models/*.json
```

### Key Metrics Targets

| Metric | Good | Acceptable | Poor |
|--------|------|------------|------|
| Sharpe Ratio | > 1.5 | > 1.0 | < 0.5 |
| Win Rate | > 45% | > 35% | < 30% |
| Profit Factor | > 1.5 | > 1.2 | < 1.0 |
| Max Drawdown | < 10% | < 15% | > 20% |
| Total Trades | > 100 | > 50 | < 20 |

---

## Next Steps

Once you have a profitable model (Sharpe > 1.0, Profit Factor > 1.2):

1. **Paper Trading** - Test with live data but no real money
2. **Risk Management** - Add position sizing, portfolio exposure limits
3. **Model Monitoring** - Track prediction distribution over time
4. **Auto-Retraining** - Retrain weekly/monthly on recent data
5. **Multi-Symbol** - Expand beyond SPY (QQQ, IWM, etc.)
6. **Ensemble Models** - Combine multiple models for robustness

**Remember:** ML models degrade over time. Monitor performance and retrain regularly.

---

## Resources

- **Triple Barrier Method**: "Advances in Financial Machine Learning" by Marcos López de Prado
- **XGBoost Docs**: https://xgboost.readthedocs.io/
- **pandas-ta**: https://github.com/twopirllc/pandas-ta
- **Imbalanced-learn**: https://imbalanced-learn.org/

---

**Last Updated:** 2025-11-08
