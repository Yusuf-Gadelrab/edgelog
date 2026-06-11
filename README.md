# EdgeLog 📈

**Your edge as a number, not a vibe.** A trade journal analyzer: import your trades as CSV,
get your expectancy in R, win rate, profit factor, max drawdown, equity curve, R distribution,
and a per-setup edge breakdown with a plain-English verdict.

Built because most trade journals tell you what you did. This one tells you whether you
actually have an edge, and which setup is paying for the others.

## Run
```bash
./run.sh        # → http://127.0.0.1:8920
```
Drop a `journal.csv` on the page. Schema:
```
date,symbol,setup,direction,entry,stop,target,exit,shares,fees,notes
```

## What it computes
- **Expectancy (R):** average R-multiple per trade, the one number that defines an edge
- **Profit factor:** gross wins / gross losses
- **Max drawdown in R:** peak-to-trough on the cumulative R curve
- **Edge by setup:** expectancy, win rate, and P&L per setup so you can cut what's bleeding
- **The verdict:** a generated plain-English read of the whole journal

## Stack
FastAPI + SQLite + a single-file vanilla JS dashboard (SVG equity curve, no chart library).
Fully local: your trade history never leaves your machine.

## Tests
```bash
uv run pytest tests/
```

Not financial advice. Analytics on your own executed trades only.
