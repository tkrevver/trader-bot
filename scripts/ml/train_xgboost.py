"""Train XGBoost classifier for SPY trading with multi-timeframe features."""

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

from app.ml.feature_engineering import FeatureEngineer
from app.ml.labeling import Labeler


def load_data():
    """Load historical OHLCV data from Parquet files."""
    print("="*70)
    print("LOADING DATA")
    print("="*70)

    data_dir = Path('data/processed')

    # Load all timeframes
    print("\n1. Loading 1-minute data...")
    df_1min = pd.read_parquet(data_dir / 'SPY_1min_ohlcv.parquet')
    # Convert decimal columns to float
    for col in ['open', 'high', 'low', 'close', 'vwap']:
        if col in df_1min.columns:
            df_1min[col] = df_1min[col].astype(float)
    print(f"   Loaded {len(df_1min):,} rows")
    print(f"   Date range: {df_1min['time'].min()} to {df_1min['time'].max()}")

    print("\n2. Loading 5-minute data...")
    df_5min = pd.read_parquet(data_dir / 'SPY_5min_ohlcv.parquet')
    for col in ['open', 'high', 'low', 'close', 'vwap']:
        if col in df_5min.columns:
            df_5min[col] = df_5min[col].astype(float)
    print(f"   Loaded {len(df_5min):,} rows")

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

    return df_1min, df_5min, df_15min, df_30min


def create_features(df_1min, df_5min, df_15min, df_30min):
    """Create multi-timeframe features."""
    print("\n" + "="*70)
    print("FEATURE ENGINEERING")
    print("="*70)

    print("\nCreating features across all timeframes...")
    print("This may take a few minutes...")

    # Create feature engineer
    engineer = FeatureEngineer(
        df_1min=df_1min,
        df_5min=df_5min,
        df_15min=df_15min,
        df_30min=df_30min
    )

    # Generate all features
    df_features = engineer.create_all_features()

    print(f"\n✓ Created {len(df_features.columns)} total columns")
    print(f"  Original OHLCV: 9 columns (time, symbol, open, high, low, close, volume, vwap, trades)")
    print(f"  Features added: {len(df_features.columns) - 9} features")

    # Get feature column names (excluding OHLCV and metadata)
    feature_cols = engineer.get_feature_columns(exclude_ohlcv=True)
    print(f"\n✓ Usable features for ML: {len(feature_cols)}")

    return df_features, feature_cols


def create_labels(df):
    """Create labels using Triple Barrier Method."""
    print("\n" + "="*70)
    print("LABELING")
    print("="*70)

    print("\nApplying Triple Barrier Method...")
    print("  Profit target: 0.5%")
    print("  Stop loss: 0.3%")
    print("  Time limit: 30 bars (30 minutes)")

    labeler = Labeler()
    df['label'] = labeler.triple_barrier(
        df,
        profit_target_pct=0.5,
        stop_loss_pct=0.3,
        time_limit_bars=30
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

    # Remove rows with NaN labels (last 30 bars can't be labeled)
    print(f"\nRemoving rows with NaN labels...")
    print(f"  Before: {len(df):,} rows")
    df_clean = df.dropna(subset=['label']).copy()
    print(f"  After: {len(df_clean):,} rows")
    print(f"  Removed: {len(df) - len(df_clean):,} rows")

    # Fill NaN in features (from indicator calculations at start)
    print(f"\nHandling missing values in features...")
    X = df_clean[feature_cols].copy()

    # Count NaN before
    nan_count_before = X.isna().sum().sum()
    print(f"  NaN values before: {nan_count_before:,}")

    # Forward fill then backfill, then fill remaining with 0
    X = X.fillna(method='ffill').fillna(method='bfill').fillna(0)

    # Count NaN after
    nan_count_after = X.isna().sum().sum()
    print(f"  NaN values after: {nan_count_after:,}")

    # Get labels
    y = df_clean['label'].copy()

    # Convert labels to 0, 1, 2 for XGBoost (it expects 0-indexed classes)
    # -1 (SELL) → 0
    #  0 (HOLD) → 1
    #  1 (BUY)  → 2
    y_encoded = y.replace({-1: 0, 0: 1, 1: 2})

    print(f"\nFinal dataset:")
    print(f"  Samples: {len(X):,}")
    print(f"  Features: {len(feature_cols)}")
    print(f"  Labels: {len(y):,}")

    return X, y_encoded, df_clean['time']


def split_data(X, y, times):
    """Split data chronologically (no shuffling for time series)."""
    print("\n" + "="*70)
    print("TRAIN/VAL/TEST SPLIT")
    print("="*70)

    # Split chronologically
    n = len(X)
    train_end = int(n * 0.70)
    val_end = int(n * 0.85)

    X_train = X.iloc[:train_end]
    X_val = X.iloc[train_end:val_end]
    X_test = X.iloc[val_end:]

    y_train = y.iloc[:train_end]
    y_val = y.iloc[train_end:val_end]
    y_test = y.iloc[val_end:]

    times_train = times.iloc[:train_end]
    times_val = times.iloc[train_end:val_end]
    times_test = times.iloc[val_end:]

    print(f"\nSplit (chronological, no shuffle):")
    print(f"  Train: {len(X_train):6,} samples ({len(X_train)/n*100:.1f}%) - {times_train.min()} to {times_train.max()}")
    print(f"  Val:   {len(X_val):6,} samples ({len(X_val)/n*100:.1f}%) - {times_val.min()} to {times_val.max()}")
    print(f"  Test:  {len(X_test):6,} samples ({len(X_test)/n*100:.1f}%) - {times_test.min()} to {times_test.max()}")

    return X_train, X_val, X_test, y_train, y_val, y_test


def train_model(X_train, y_train, X_val, y_val, class_weights):
    """Train XGBoost classifier."""
    print("\n" + "="*70)
    print("MODEL TRAINING")
    print("="*70)

    # Calculate sample weights from class weights
    # Map encoded labels (0, 1, 2) to class weights
    weight_map = {
        0: class_weights[-1],  # SELL
        1: class_weights[0],   # HOLD
        2: class_weights[1]    # BUY
    }
    sample_weights = y_train.map(weight_map).values

    print("\nXGBoost Configuration:")
    params = {
        'objective': 'multi:softmax',
        'num_class': 3,
        'max_depth': 6,
        'learning_rate': 0.1,
        'n_estimators': 100,
        'subsample': 0.8,
        'colsample_bytree': 0.8,
        'min_child_weight': 5,
        'gamma': 0.1,
        'random_state': 42,
        'n_jobs': -1,
        'tree_method': 'hist'  # Faster for large datasets
    }

    for key, value in params.items():
        print(f"  {key}: {value}")

    print("\nTraining model...")
    print("This may take a few minutes...")

    model = xgb.XGBClassifier(**params)

    # Train with sample weights to handle class imbalance
    model.fit(
        X_train,
        y_train,
        sample_weight=sample_weights,
        eval_set=[(X_val, y_val)],
        verbose=False
    )

    print("\n✓ Training complete!")

    return model, params


def evaluate_model(model, X_train, y_train, X_val, y_val, X_test, y_test):
    """Evaluate model performance."""
    print("\n" + "="*70)
    print("MODEL EVALUATION")
    print("="*70)

    # Predictions
    y_train_pred = model.predict(X_train)
    y_val_pred = model.predict(X_val)
    y_test_pred = model.predict(X_test)

    # Calculate metrics
    train_acc = accuracy_score(y_train, y_train_pred)
    val_acc = accuracy_score(y_val, y_val_pred)
    test_acc = accuracy_score(y_test, y_test_pred)

    train_f1 = f1_score(y_train, y_train_pred, average='weighted')
    val_f1 = f1_score(y_val, y_val_pred, average='weighted')
    test_f1 = f1_score(y_test, y_test_pred, average='weighted')

    print("\n" + "-"*70)
    print("ACCURACY")
    print("-"*70)
    print(f"  Train: {train_acc:.4f} ({train_acc*100:.2f}%)")
    print(f"  Val:   {val_acc:.4f} ({val_acc*100:.2f}%)")
    print(f"  Test:  {test_acc:.4f} ({test_acc*100:.2f}%)")

    print("\n" + "-"*70)
    print("F1 SCORE (Weighted)")
    print("-"*70)
    print(f"  Train: {train_f1:.4f}")
    print(f"  Val:   {val_f1:.4f}")
    print(f"  Test:  {test_f1:.4f}")

    # Check for overfitting
    overfit_acc = train_acc - val_acc
    overfit_f1 = train_f1 - val_f1

    print("\n" + "-"*70)
    print("OVERFITTING CHECK")
    print("-"*70)
    print(f"  Accuracy gap (train - val): {overfit_acc:.4f} ({overfit_acc*100:.2f}%)")
    print(f"  F1 gap (train - val): {overfit_f1:.4f}")

    if overfit_acc < 0.05 and overfit_f1 < 0.05:
        print("  Status: Good ✓ (minimal overfitting)")
    elif overfit_acc < 0.10 and overfit_f1 < 0.10:
        print("  Status: Acceptable ⚠ (some overfitting)")
    else:
        print("  Status: Overfitting ✗ (consider regularization)")

    # Validation set detailed report
    print("\n" + "-"*70)
    print("VALIDATION SET - CLASSIFICATION REPORT")
    print("-"*70)

    # Convert back to original labels for report
    y_val_original = y_val.replace({0: -1, 1: 0, 2: 1})
    y_val_pred_original = pd.Series(y_val_pred).replace({0: -1, 1: 0, 2: 1})

    print(classification_report(
        y_val_original,
        y_val_pred_original,
        target_names=['SELL', 'HOLD', 'BUY'],
        digits=4
    ))

    # Confusion matrix
    print("\n" + "-"*70)
    print("VALIDATION SET - CONFUSION MATRIX")
    print("-"*70)
    cm = confusion_matrix(y_val_original, y_val_pred_original, labels=[-1, 0, 1])
    print("\n        Predicted")
    print("          SELL    HOLD     BUY")
    print(f"Actual")
    print(f"SELL    {cm[0,0]:6d}  {cm[0,1]:6d}  {cm[0,2]:6d}")
    print(f"HOLD    {cm[1,0]:6d}  {cm[1,1]:6d}  {cm[1,2]:6d}")
    print(f"BUY     {cm[2,0]:6d}  {cm[2,1]:6d}  {cm[2,2]:6d}")

    metrics = {
        'train_accuracy': float(train_acc),
        'val_accuracy': float(val_acc),
        'test_accuracy': float(test_acc),
        'train_f1': float(train_f1),
        'val_f1': float(val_f1),
        'test_f1': float(test_f1),
        'overfit_accuracy_gap': float(overfit_acc),
        'overfit_f1_gap': float(overfit_f1)
    }

    return metrics, y_val_pred


def analyze_feature_importance(model, feature_cols):
    """Analyze and display feature importance."""
    print("\n" + "="*70)
    print("FEATURE IMPORTANCE")
    print("="*70)

    # Get feature importance
    importance_df = pd.DataFrame({
        'feature': feature_cols,
        'importance': model.feature_importances_
    }).sort_values('importance', ascending=False)

    print("\nTop 20 Most Important Features:")
    print("-"*70)
    for i, row in importance_df.head(20).iterrows():
        bar_length = int(row['importance'] * 100)
        bar = '█' * bar_length
        print(f"{row['feature']:35s} {row['importance']:.4f} {bar}")

    # Save full importance to CSV
    importance_file = 'data/results/feature_importance.csv'
    Path('data/results').mkdir(parents=True, exist_ok=True)
    importance_df.to_csv(importance_file, index=False)
    print(f"\n✓ Full feature importance saved to {importance_file}")

    return importance_df


def save_model(model, params, metrics, feature_cols):
    """Save trained model and metadata."""
    print("\n" + "="*70)
    print("SAVING MODEL")
    print("="*70)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    model_dir = Path('models')
    model_dir.mkdir(parents=True, exist_ok=True)

    # Save model
    model_file = model_dir / f'xgboost_spy_{timestamp}.pkl'
    joblib.dump(model, model_file)
    print(f"\n✓ Model saved to {model_file}")

    # Save latest version (symlink/copy)
    latest_file = model_dir / 'xgboost_spy_latest.pkl'
    joblib.dump(model, latest_file)
    print(f"✓ Latest model saved to {latest_file}")

    # Save metadata
    metadata = {
        'timestamp': timestamp,
        'model_file': str(model_file),
        'model_type': 'XGBClassifier',
        'num_features': len(feature_cols),
        'feature_columns': feature_cols,
        'hyperparameters': params,
        'metrics': metrics,
        'labeling_config': {
            'method': 'triple_barrier',
            'profit_target_pct': 0.5,
            'stop_loss_pct': 0.3,
            'time_limit_bars': 30
        }
    }

    metadata_file = model_dir / f'xgboost_spy_{timestamp}_metadata.json'
    with open(metadata_file, 'w') as f:
        json.dump(metadata, f, indent=2)
    print(f"✓ Metadata saved to {metadata_file}")

    # Save feature columns for production use
    feature_file = model_dir / 'feature_columns.json'
    with open(feature_file, 'w') as f:
        json.dump({'features': feature_cols}, f, indent=2)
    print(f"✓ Feature columns saved to {feature_file}")

    return model_file, metadata_file


def main():
    """Main training pipeline."""
    print("\n" + "="*70)
    print("XGBOOST TRAINING PIPELINE - SPY TRADING")
    print("="*70)
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # 1. Load data
    df_1min, df_5min, df_15min, df_30min = load_data()

    # 2. Create features
    df_features, feature_cols = create_features(df_1min, df_5min, df_15min, df_30min)

    # 3. Create labels
    df_labeled, class_weights = create_labels(df_features)

    # 4. Prepare data
    X, y, times = prepare_data(df_labeled, feature_cols)

    # 5. Split data
    X_train, X_val, X_test, y_train, y_val, y_test = split_data(X, y, times)

    # 6. Train model
    model, params = train_model(X_train, y_train, X_val, y_val, class_weights)

    # 7. Evaluate model
    metrics, y_val_pred = evaluate_model(model, X_train, y_train, X_val, y_val, X_test, y_test)

    # 8. Analyze feature importance
    importance_df = analyze_feature_importance(model, feature_cols)

    # 9. Save model
    model_file, metadata_file = save_model(model, params, metrics, feature_cols)

    # Final summary
    print("\n" + "="*70)
    print("TRAINING COMPLETE")
    print("="*70)
    print(f"\nCompleted: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"\nModel Performance:")
    print(f"  Validation Accuracy: {metrics['val_accuracy']:.2%}")
    print(f"  Validation F1 Score: {metrics['val_f1']:.4f}")
    print(f"  Test Accuracy: {metrics['test_accuracy']:.2%}")
    print(f"  Test F1 Score: {metrics['test_f1']:.4f}")

    print(f"\nNext Steps:")
    print(f"  1. Review feature importance in data/results/feature_importance.csv")
    print(f"  2. Create MLStrategy class using model: {model_file.name}")
    print(f"  3. Run backtest to evaluate trading performance")
    print(f"  4. If Sharpe > 1.0 and Win Rate > 55%, proceed to paper trading")

    print("\n" + "="*70)


if __name__ == '__main__':
    main()
