"""Train XGBoost classifier for trend-following strategy with focused features."""

import sys
from pathlib import Path
import pandas as pd
import numpy as np
import xgboost as xgb
from sklearn.metrics import classification_report, confusion_matrix, f1_score, accuracy_score
from sklearn.model_selection import train_test_split
import joblib
import json
from datetime import datetime

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.ml.trend_following_features import TrendFollowingFeatureEngineer
from app.ml.labeling import Labeler


def load_data():
    """Load historical OHLCV data from Parquet files."""
    print("="*70)
    print("LOADING DATA")
    print("="*70)

    data_dir = Path('data/processed')

    # Load 5-min data (primary timeframe)
    print("\n1. Loading 5-minute data (primary)...")
    df_5min = pd.read_parquet(data_dir / 'SPY_5min_ohlcv.parquet')
    for col in ['open', 'high', 'low', 'close', 'vwap']:
        if col in df_5min.columns:
            df_5min[col] = df_5min[col].astype(float)
    print(f"   Loaded {len(df_5min):,} rows")
    print(f"   Date range: {df_5min['time'].min()} to {df_5min['time'].max()}")

    # Load other timeframes for multi-timeframe slopes
    print("\n2. Loading 1-minute data...")
    df_1min = pd.read_parquet(data_dir / 'SPY_1min_ohlcv.parquet')
    for col in ['open', 'high', 'low', 'close', 'vwap']:
        if col in df_1min.columns:
            df_1min[col] = df_1min[col].astype(float)
    print(f"   Loaded {len(df_1min):,} rows")

    print("\n3. Loading 15-minute data...")
    df_15min = pd.read_parquet(data_dir / 'SPY_15min_ohlcv.parquet')
    for col in ['open', 'high', 'low', 'close', 'vwap']:
        if col in df_15min.columns:
            df_15min[col] = df_15min[col].astype(float)
    print(f"   Loaded {len(df_15min):,} rows")

    print("\n4. Loading 30-minute data...")
    df_30min = pd.read_parquet(data_dir / 'SPY_30min_ohlcv.parquet')
    for col in ['open', 'high', 'low', 'close', 'vwap']:
        if col in df_30min.columns:
            df_30min[col] = df_30min[col].astype(float)
    print(f"   Loaded {len(df_30min):,} rows")

    return df_5min, df_1min, df_15min, df_30min


def create_features(df_5min, df_1min, df_15min, df_30min):
    """Create trend-following features (~28 features)."""
    print("\n" + "="*70)
    print("FEATURE ENGINEERING (Trend-Following)")
    print("="*70)

    print("\nCreating focused trend-following features...")
    print("  - EMA slopes (16 features)")
    print("  - ADX trend strength (4 features)")
    print("  - EMA alignment (4 features)")
    print("  - Bar reclaim pattern (1 feature)")
    print("  - Price vs VWAP (1 feature)")
    print("  - Time features (2 features)")
    print("\nThis may take a few minutes...")

    # Create feature engineer
    engineer = TrendFollowingFeatureEngineer(
        df_5min=df_5min,
        df_1min=df_1min,
        df_15min=df_15min,
        df_30min=df_30min
    )

    # Generate all features
    df_features = engineer.create_all_features()

    # Get feature column names
    feature_cols = engineer.get_feature_names()

    print(f"\n✓ Created {len(df_features.columns)} total columns")
    print(f"  Original OHLCV: ~9 columns")
    print(f"  Usable features for ML: {len(feature_cols)} features")
    print(f"\nFeature breakdown:")
    print(f"  - EMA slopes: 16")
    print(f"  - ADX values: 4")
    print(f"  - Alignment strength: 4")
    print(f"  - Bar reclaim: 1")
    print(f"  - Price vs VWAP: 1")
    print(f"  - Time: 2")
    print(f"  Total: {len(feature_cols)}")

    return df_features, feature_cols


def create_labels(df):
    """Create labels using trend-following method."""
    print("\n" + "="*70)
    print("LABELING (Trend-Following)")
    print("="*70)

    print("\nApplying Trend-Following Labeling...")
    print("  Entry criteria:")
    print("    - LONG: Bullish EMA alignment + bar reclaims EMA20 + price > VWAP")
    print("    - SHORT: Bearish EMA alignment + bar breaks EMA20 + price < VWAP")
    print("  Exit criteria:")
    print("    - LONG exit: Close below EMA20")
    print("    - SHORT exit: Close above EMA20")
    print("  Minimum profit: 0.1%")

    labeler = Labeler()
    df['label'] = labeler.trend_following_labels(
        df,
        ema_period=20,
        min_profit_pct=0.1
    )

    # Analyze label distribution
    print("\n" + "-"*70)
    print("LABEL DISTRIBUTION")
    print("-"*70)

    stats = labeler.analyze_label_distribution(df['label'])

    print(f"\nTotal samples: {stats['total_samples']:,}")
    print(f"\nClass distribution:")
    for label, count in sorted(stats['counts'].items()):
        pct = stats['percentages'][label]
        label_int = int(label)
        label_name = {-1: 'SELL', 0: 'HOLD', 1: 'BUY'}[label_int]
        print(f"  {label_name:6s} ({label_int:2d}): {count:6,} ({pct:5.2f}%)")

    print(f"\nImbalance ratio: {stats['imbalance_ratio']:.2f}")
    print(f"Balanced: {'Yes ✓' if stats['is_balanced'] else 'No ✗ (will use class weights)'}")

    # Get class weights for training
    class_weights = labeler.get_recommended_class_weights(df['label'])
    print(f"\nRecommended class weights:")
    for label, weight in sorted(class_weights.items()):
        label_name = {-1: 'SELL', 0: 'HOLD', 1: 'BUY'}[label]
        print(f"  {label_name}: {weight:.3f}")

    return df, class_weights


def prepare_data(df, feature_cols):
    """Prepare data for training."""
    print("\n" + "="*70)
    print("DATA PREPARATION")
    print("="*70)

    # Remove rows with NaN labels
    print(f"\nRemoving rows with NaN labels...")
    print(f"  Before: {len(df):,} rows")
    df_clean = df.dropna(subset=['label']).copy()
    print(f"  After: {len(df_clean):,} rows")
    print(f"  Removed: {len(df) - len(df_clean):,} rows")

    # Remove rows with any NaN features
    print(f"\nRemoving rows with NaN features...")
    print(f"  Before: {len(df_clean):,} rows")
    df_clean = df_clean.dropna(subset=feature_cols)
    print(f"  After: {len(df_clean):,} rows")
    print(f"  Removed: {len(df.dropna(subset=['label'])) - len(df_clean):,} rows")

    # Temporal split (last 20% for testing)
    split_idx = int(len(df_clean) * 0.8)
    train_df = df_clean.iloc[:split_idx]
    test_df = df_clean.iloc[split_idx:]

    print(f"\nTemporal split (80/20):")
    print(f"  Train: {len(train_df):,} rows ({len(train_df)/len(df_clean)*100:.1f}%)")
    print(f"  Test:  {len(test_df):,} rows ({len(test_df)/len(df_clean)*100:.1f}%)")

    if 'time' in train_df.columns:
        print(f"\n  Train period: {train_df['time'].min()} to {train_df['time'].max()}")
        print(f"  Test period:  {test_df['time'].min()} to {test_df['time'].max()}")

    # Prepare X and y
    X_train = train_df[feature_cols].values
    y_train = train_df['label'].values
    X_test = test_df[feature_cols].values
    y_test = test_df['label'].values

    print(f"\n  X_train shape: {X_train.shape}")
    print(f"  X_test shape:  {X_test.shape}")

    return X_train, y_train, X_test, y_test, feature_cols


def train_model(X_train, y_train, X_test, y_test, class_weights):
    """Train XGBoost classifier."""
    print("\n" + "="*70)
    print("MODEL TRAINING")
    print("="*70)

    # Calculate sample weights
    sample_weights = np.array([class_weights[int(label)] for label in y_train])

    # XGBoost parameters
    params = {
        'objective': 'multi:softmax',
        'num_class': 3,
        'max_depth': 6,
        'learning_rate': 0.1,
        'n_estimators': 100,
        'subsample': 0.8,
        'colsample_bytree': 0.8,
        'random_state': 42,
        'tree_method': 'hist',
        'n_jobs': 8,
        'eval_metric': 'mlogloss'
    }

    print("\nXGBoost parameters:")
    for key, value in params.items():
        print(f"  {key}: {value}")

    print("\nTraining model...")
    model = xgb.XGBClassifier(**params)
    model.fit(
        X_train,
        y_train + 1,  # Convert -1,0,1 to 0,1,2 for XGBoost
        sample_weight=sample_weights,
        eval_set=[(X_test, y_test + 1)],
        verbose=False
    )

    print("✓ Training complete")

    return model


def evaluate_model(model, X_train, y_train, X_test, y_test):
    """Evaluate model performance."""
    print("\n" + "="*70)
    print("MODEL EVALUATION")
    print("="*70)

    # Predictions (convert back from 0,1,2 to -1,0,1)
    y_train_pred = model.predict(X_train) - 1
    y_test_pred = model.predict(X_test) - 1

    # Training metrics
    train_acc = accuracy_score(y_train, y_train_pred)
    train_f1 = f1_score(y_train, y_train_pred, average='weighted')

    # Test metrics
    test_acc = accuracy_score(y_test, y_test_pred)
    test_f1 = f1_score(y_test, y_test_pred, average='weighted')

    print(f"\nTraining Performance:")
    print(f"  Accuracy: {train_acc*100:.2f}%")
    print(f"  F1 Score: {train_f1:.4f}")

    print(f"\nTest Performance:")
    print(f"  Accuracy: {test_acc*100:.2f}%")
    print(f"  F1 Score: {test_f1:.4f}")

    # Confusion matrix
    print(f"\nTest Confusion Matrix:")
    cm = confusion_matrix(y_test, y_test_pred)
    print("          Predicted")
    print("           SELL  HOLD  BUY")
    print(f"Actual SELL  {cm[0,0]:4d}  {cm[0,1]:4d}  {cm[0,2]:4d}")
    print(f"       HOLD  {cm[1,0]:4d}  {cm[1,1]:4d}  {cm[1,2]:4d}")
    print(f"       BUY   {cm[2,0]:4d}  {cm[2,1]:4d}  {cm[2,2]:4d}")

    # Classification report
    print(f"\nClassification Report (Test Set):")
    print(classification_report(
        y_test,
        y_test_pred,
        target_names=['SELL', 'HOLD', 'BUY'],
        digits=4
    ))

    return {
        'train_accuracy': train_acc,
        'train_f1': train_f1,
        'test_accuracy': test_acc,
        'test_f1': test_f1
    }


def analyze_feature_importance(model, feature_cols):
    """Analyze and display feature importance."""
    print("\n" + "="*70)
    print("FEATURE IMPORTANCE")
    print("="*70)

    importance = model.feature_importances_
    feature_importance = pd.DataFrame({
        'feature': feature_cols,
        'importance': importance
    }).sort_values('importance', ascending=False)

    print(f"\nTop 20 Most Important Features:")
    print("-"*70)
    for idx, row in feature_importance.head(20).iterrows():
        print(f"  {row['feature']:35s}: {row['importance']*100:5.2f}%")

    print(f"\nFeature Importance Summary:")
    print(f"  Top feature importance: {feature_importance['importance'].max()*100:.2f}%")
    print(f"  Top 10 cumulative: {feature_importance['importance'].head(10).sum()*100:.2f}%")
    print(f"  Top 20 cumulative: {feature_importance['importance'].head(20).sum()*100:.2f}%")

    # Save to CSV
    output_path = Path('data/results/trend_following_feature_importance.csv')
    output_path.parent.mkdir(parents=True, exist_ok=True)
    feature_importance.to_csv(output_path, index=False)
    print(f"\n✓ Feature importance saved to {output_path}")

    return feature_importance


def save_model(model, feature_cols, metrics):
    """Save trained model and metadata."""
    print("\n" + "="*70)
    print("SAVING MODEL")
    print("="*70)

    models_dir = Path('models')
    models_dir.mkdir(exist_ok=True)

    # Save model
    model_path = models_dir / 'xgboost_spy_trend_following.pkl'
    joblib.dump(model, model_path)
    print(f"\n✓ Model saved to {model_path}")

    # Save feature columns
    feature_cols_path = models_dir / 'trend_following_feature_columns.json'
    with open(feature_cols_path, 'w') as f:
        json.dump({'features': feature_cols}, f, indent=2)
    print(f"✓ Feature columns saved to {feature_cols_path}")

    # Save metadata
    metadata = {
        'model_type': 'XGBoost',
        'strategy': 'trend_following',
        'num_features': len(feature_cols),
        'training_date': datetime.now().isoformat(),
        'metrics': metrics,
        'xgboost_params': {
            'objective': 'multi:softmax',
            'num_class': 3,
            'max_depth': 6,
            'learning_rate': 0.1,
            'n_estimators': 100
        }
    }

    metadata_path = models_dir / 'trend_following_metadata.json'
    with open(metadata_path, 'w') as f:
        json.dump(metadata, f, indent=2)
    print(f"✓ Metadata saved to {metadata_path}")

    print(f"\n" + "="*70)
    print("TRAINING COMPLETE")
    print("="*70)
    print(f"\nModel files:")
    print(f"  - {model_path}")
    print(f"  - {feature_cols_path}")
    print(f"  - {metadata_path}")
    print(f"\nNext steps:")
    print(f"  1. Review feature importance in data/results/trend_following_feature_importance.csv")
    print(f"  2. Run backtest with: POST /api/v1/backtest (see bruno/trader-bot/Backtest/)")
    print(f"  3. Deploy strategy if metrics are good")


def main():
    """Main training pipeline."""
    # 1. Load data
    df_5min, df_1min, df_15min, df_30min = load_data()

    # 2. Create features
    df_features, feature_cols = create_features(df_5min, df_1min, df_15min, df_30min)

    # 3. Create labels
    df_labeled, class_weights = create_labels(df_features)

    # 4. Prepare data
    X_train, y_train, X_test, y_test, feature_cols = prepare_data(df_labeled, feature_cols)

    # 5. Train model
    model = train_model(X_train, y_train, X_test, y_test, class_weights)

    # 6. Evaluate model
    metrics = evaluate_model(model, X_train, y_train, X_test, y_test)

    # 7. Analyze feature importance
    feature_importance = analyze_feature_importance(model, feature_cols)

    # 8. Save model
    save_model(model, feature_cols, metrics)


if __name__ == '__main__':
    main()
