# Evaluation & Monitoring Toolkit

This folder contains small helper scripts to keep performance checks consistent across tickers.

## Quick usage

### 1. Generate forecasts + evaluate the latest available close
```bash
python evaluation/run_daily.py --tickers AAPL AMZN BA CVX
```
- Reads `configs/tickers.toml` and the corresponding promoted artefacts (`artifacts/<TICKER>/…/best_model.keras`).
- Produces same-day forecasts in `predictions/<TICKER>/<DATE>.json`.
- Evaluates against realised closes (if available) into `reports/daily/<TICKER>/<DATE>.json`.
- Keeps a consolidated log in `reports/risk_package/latest_week_summary.json`.

### 2. Summarise a time window (e.g., last two weeks)
```bash
python evaluation/weekly_summary.py --start 2025-09-12 --end 2025-09-30 --tickers AAPL AMZN BA CVX
```
- Reads per-day evaluation JSON files.
- Reports mean/standard deviation for MAE/MAPE/RMSE per ticker.
- Appends the result to `reports/risk_package/paper_trading_metrics.json`.

## Success & failure cues

| Signal | What it means | Next action |
|--------|----------------|-------------|
| MAE ≤ backtest MAE × 1.5 and MAPE stable | Forecasts behaving as during validation | Keep daily loop running, update weekly metrics |
| MAE spikes > threshold for 2 consecutive days | Potential regime shift / data glitch | Inspect prediction JSON and price history, consider retrain |
| `evaluate_predictions` raises “Actual data not yet available” | Market hasn’t closed or data missing | Re-run after close or ensure price history includes the date |
| Warnings about tf retracing | Using new shapes each call | Future optimisation; safe to ignore for daily runs |

## Extending
- Update `--model-path` / `--scaler-path` arguments if you promote fresh artefacts.
- Add tickers to the `--tickers` flag or default list in `run_daily.py`.
- For longer retrospectives, stage evaluation JSONs in `reports/daily/<TICKER>/` and point `weekly_summary.py` to the date range of interest.
