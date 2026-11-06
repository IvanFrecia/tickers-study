# Historical error

Two different measurements are easy to mix up. They are kept apart here.

## Walk-forward training error

These numbers come from the last weekly training run that was still publishing
on 2026-11-05T23:22:47Z, for the market week 2026-11-05 through 2026-11-06.
Loss was weighted MSE, horizon 5 sessions, 8 epochs, 1 backtest split.
All 20 configured symbols finished that run. None failed to train.

`status` uses the study gate: active only when backtest MAE is under 10 and
R² is at least 0.60. Otherwise the symbol stays under review. That gate is
not a trading rule.

MAE is in the price units of the symbol. `000660.KS` is priced in KRW, so its
MAE is not comparable to a US dollar price. MAPE and R² are the comparable
columns.

| Symbol | Status | MAE | RMSE | MAPE % | R² |
|---|---|---:|---:|---:|---:|
| BA | active | 7.72 | 9.96 | 4.15 | 0.875 |
| MRNA | active | 8.04 | 15.80 | 8.62 | 0.928 |
| RKLB | active | 8.93 | 13.56 | 10.44 | 0.645 |
| AMZN | under_review | 11.00 | 14.90 | 4.82 | 0.668 |
| AAPL | under_review | 18.48 | 28.93 | 6.88 | 0.487 |
| VST | under_review | 21.94 | 27.58 | 13.30 | -0.818 |
| GOOG | under_review | 27.06 | 40.17 | 9.45 | 0.728 |
| CVX | under_review | 30.22 | 41.65 | 17.31 | -2.258 |
| VRT | under_review | 31.78 | 41.32 | 12.38 | 0.468 |
| DELL | under_review | 32.84 | 56.41 | 10.93 | 0.869 |
| NVDA | under_review | 36.64 | 53.34 | 21.72 | -1.086 |
| TSLA | under_review | 48.58 | 59.19 | 12.24 | -1.368 |
| MU | under_review | 59.96 | 122.32 | 13.27 | 0.870 |
| WDC | under_review | 62.83 | 139.05 | 19.81 | 0.417 |
| ALAB | under_review | 78.71 | 97.64 | 26.72 | -6.084 |
| AVGO | under_review | 85.93 | 109.21 | 28.80 | -0.624 |
| SMCI | under_review | 7.09 | 10.20 | 19.52 | -0.229 |
| STX | under_review | 122.48 | 259.01 | 22.41 | 0.234 |
| SNDK | under_review | 564.92 | 761.49 | 41.64 | -10.476 |
| 000660.KS | under_review | 102626.81 | 189080.68 | 12.18 | 0.923 |

Negative R² on this run: CVX, NVDA, TSLA, VST, SMCI, ALAB, AVGO, SNDK.
SMCI's MAE is under 10 and its R² is still negative, so it stays under review.
A large price and a negative R² is not a tight call.

## Resolved week-ahead results

`historical_error.json` holds the latest resolved previous-week comparison
for each symbol and target week. The record covers 138 weekly runs from the
week of 2026-02-26 through the run generated at 2026-11-05T23:22:47Z.
After one row per symbol and target week, that is **324 resolved calls**,
target weeks **2026-03-27 through 2026-10-30**.

The week ending 2026-11-06 was still unresolved in that last run, so it is
not in the file.

Across those 324 calls, the predicted direction matched the realized week
**144 times (44.4%)**. The median absolute `error_pct` was **7.82**.
`error_pct` is signed `(actual - predicted) / predicted`. It is not MAPE.
MAPE in the training table divides by the actual close inside the backtest.

A symbol with 3 resolved weeks is a short sample. Read the count before the rate.

| Symbol | Resolved weeks | Direction match | Median abs error % |
|---|---:|---:|---:|
| 000660.KS | 4 | 0.75 | 13.58 |
| AAPL | 22 | 0.55 | 2.90 |
| ALAB | 3 | 1.00 | 18.04 |
| AMZN | 26 | 0.38 | 3.83 |
| AVGO | 3 | 0.00 | 13.38 |
| BA | 26 | 0.35 | 1.26 |
| CVX | 22 | 0.59 | 5.12 |
| DELL | 3 | 1.00 | 4.09 |
| GOOG | 26 | 0.42 | 12.31 |
| MRNA | 3 | 1.00 | 9.65 |
| MU | 22 | 0.41 | 7.50 |
| NVDA | 26 | 0.42 | 9.15 |
| RKLB | 3 | 0.67 | 5.38 |
| SMCI | 22 | 0.27 | 9.41 |
| SNDK | 22 | 0.55 | 81.23 |
| STX | 22 | 0.45 | 9.47 |
| TSLA | 22 | 0.27 | 9.81 |
| VRT | 22 | 0.36 | 4.86 |
| VST | 3 | 1.00 | 8.12 |
| WDC | 22 | 0.45 | 12.50 |

The separate first-call ledger field was filled on 4 symbol-weeks only, all
for the target week 2026-03-27, with 1 direction match out of 4. The table
above is the previous-week comparison, which is the resolved series the
runs actually stored.

Closes, tone, and forward paths are not in the file.
