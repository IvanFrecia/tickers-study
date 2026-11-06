# Tickers

Local research code for weekly equity-close studies. Apache-2.0.
Read [DISCLAIMER.md](DISCLAIMER.md) before using any number in this repository.
The error tables are in [docs/accuracy/HISTORICAL_ERROR.md](docs/accuracy/HISTORICAL_ERROR.md).

This tree runs on your machine. It does not include hosted deployment files.

## Run a forecast study

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m src.cli --config configs/smoke.toml
```

`configs/tickers.toml` is the full study roster. A full run trains a neural
model per symbol and downloads public prices. Start with `configs/smoke.toml`
if you only want to see the command work.

Weekly retrain writes local files under `reports/` and `predictions/`:

```bash
.venv/bin/python evaluation/retrain_publish_weekly.py --config configs/tickers.toml --prefer-local-prior-summary
```

## Dashboard

```bash
.venv/bin/python -m uvicorn app.server:app --host 127.0.0.1 --port 8080
```

Open `http://127.0.0.1:8080`. The page is open on localhost. To require a
password you chose yourself, set `TICKERS_AUTH_ENFORCED=true`,
`TICKERS_SESSION_SECRET` to a long random value, and
`TICKERS_ALLOWED_USERS_JSON` to a JSON object of email, role, and password.
The program refuses to start in that mode if the secret is missing. There is
no built-in password.

## Tests

```bash
.venv/bin/python -m unittest discover -s qa -p 'test_*.py'
```

## Accuracy

Training metrics and resolved week-ahead errors are separate.
See `docs/accuracy/HISTORICAL_ERROR.md`. Do not read a backtest R² as the
live week-ahead result.
