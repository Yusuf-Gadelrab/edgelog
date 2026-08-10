# EdgeLog

![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)
![FastAPI](https://img.shields.io/badge/backend-FastAPI-009688)
![Status](https://img.shields.io/badge/status-personal%20project-lightgrey)

EdgeLog is a trade journal analyzer: import your closed trades as a CSV and it computes
expectancy in R, win rate, profit factor, max drawdown, an equity curve, and a per-setup edge
breakdown — with a plain-English verdict on whether the data says you actually have an edge.
It's built for discretionary and systematic traders who already log trades and want the math
done honestly, on their own numbers, instead of a vibe.

> ### ⚠️ Not financial advice
> EdgeLog is analysis software, not a signal service or an advisor. It only computes statistics
> on trade history **you** provide — it does not recommend trades, predict prices, or manage
> money. Past performance (yours or anyone else's) does not predict future results. Trading
> stocks, options, and other instruments involves substantial risk of loss, and you can lose
> more than you put in. Nothing in this repo or its output is investment advice.

## Quickstart

Requires Python 3.11+ and [`uv`](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/Yusuf-Gadelrab/edgelog.git
cd edgelog
./run.sh                       # installs deps via uv and starts the server
# → http://127.0.0.1:8920
```

`run.sh` just wraps `uv run uvicorn main:app --host 127.0.0.1 --port 8920`. Everything is
local — SQLite database on disk, no signup, no telemetry, no cloud sync by default. Your trade
history never leaves your machine unless you explicitly trigger a broker sync.

## CSV schema

Drop a `journal.csv` on the page (or `POST` it to `/api/import`). One row per **closed** trade:

```
date,symbol,setup,direction,entry,stop,target,exit,shares,fees,notes
```

| Column      | Required | Notes |
|-------------|----------|-------|
| `date`      | yes      | Trade date, `YYYY-MM-DD` recommended (used for sorting, weekly reports, and the calendar heatmap). |
| `symbol`    | yes      | Ticker; normalized to uppercase on import. |
| `setup`     | yes*     | Free-text tag for your strategy/setup. Blank rows are stored as `untagged`. |
| `direction` | yes      | `long` or `short` (case-insensitive). |
| `entry`     | yes      | Entry price, numeric. |
| `stop`      | yes      | Stop-loss price, numeric. Must sit on the correct side of entry (≤ entry for longs, ≥ entry for shorts) — this is what defines your risk unit (R). |
| `target`    | yes*     | Target price, numeric. Column must exist but the value may be blank (defaults to `0`). |
| `exit`      | yes      | Actual exit/fill price, numeric. |
| `shares`    | yes      | Position size, numeric. |
| `fees`      | yes*     | Commissions/fees, numeric. Column must exist but the value may be blank (defaults to `0`). |
| `notes`     | no       | Free text, truncated to 500 characters. The only column you can omit entirely. |

`*` — the header must be present, but the per-row value can be empty and will default sensibly.

Rows that fail to parse (bad direction, non-numeric price, or a stop on the wrong side of entry)
are skipped individually and reported back with the line number and reason — the rest of the
import still goes through.

## What it computes

Every metric is derived from the R-multiple of each trade — the trade's result measured in
units of its own initial risk (`entry` − `stop`) — so setups with different price levels and
position sizes are directly comparable.

- **Expectancy (R):** the mean R-multiple across all trades — the single number that answers
  "do I have an edge."
- **Win rate:** percentage of trades with R > 0, plus average winning and losing R.
- **Profit factor:** gross dollar profit on winning trades divided by gross dollar loss on
  losing trades.
- **Max drawdown (R):** the largest peak-to-trough decline on the cumulative-R equity curve.
- **Edge by setup:** trade count, expectancy, win rate, and total P&L per setup tag, sorted
  best to worst, so you can see which setup is carrying the others (and which is bleeding).
- **R distribution:** a histogram of trades bucketed by integer R outcome.
- **Discipline tracking (optional):** define rules (max risk per trade, max trades per day,
  a setup whitelist, or "stop required") and EdgeLog computes adherence %, the expectancy gap
  between clean and rule-broken trades, the R cost of breaking rules, and your current clean
  streak.
- **The verdict:** a generated plain-English read of the whole journal — including a warning
  if you have under ~20 trades (not enough data to judge), a call on whether expectancy is
  positive, marginal, or negative, and a flag if one setup is subsidizing another.
- **Weekly review:** a markdown-formatted recap (net R, expectancy, adherence, best/worst
  trade) for any ISO week, copyable straight into a trading journal or Notion doc.

## Broker sync

Two optional, opt-in sync scripts pull filled orders into the same journal so you don't have to
hand-transcribe them. Both are read-only against the broker (they never place, modify, or
cancel orders) and store credentials only in a local, gitignored `.env` file — nothing is
hardcoded in this repo.

- **Alpaca** (`alpaca_sync.py`) — calls Alpaca's official REST API (`/v2/account/activities/FILL`),
  FIFO-matches buy/sell fills into closed round-trip trades, and dedupes by fill ID. Needs
  `ALPACA_API_KEY` / `ALPACA_API_SECRET` in `.env`. Synced trades carry no stop/target (raw
  fills don't have them) and are tagged `alpaca-sync`.
- **Robinhood** (`robinhood_sync.py`) — pulls filled stock orders and dedupes by order ID.
  Needs `RH_USERNAME` / `RH_PASSWORD` in `.env`. **Caution:** this uses [`robin_stocks`](https://github.com/jmfernandes/robin_stocks),
  an unofficial, reverse-engineered client for Robinhood's private mobile-app API — Robinhood
  does not publish a public developer API. Robinhood's Terms of Service prohibit unauthorized
  automated access, and accounts using unofficial clients like this have been restricted or
  locked. Use at your own risk, on an account you're willing to put at risk.

## Also in here (experimental, API-only)

- **AI coach** (`/api/coach`, wired to the "AI Review" button in the UI) — streams a short,
  numbers-based critique of your recent trades and discipline stats from a **local** LLM via
  Ollama (`http://localhost:11434`). Nothing is sent anywhere if Ollama isn't running; it just
  fails gracefully. This is commentary generated from your own stats, not a signal or a
  recommendation.
- **Quick backtest runner** (`POST /api/backtest/run`, no UI yet) — runs a simple RSI or
  EMA-crossover signal against historical data (via `vectorbt` + `yfinance`) for a symbol you
  choose. It's a toy backtest for exploring an idea, not a validated strategy — a good backtest
  result here is not evidence of a future edge.

A few other modules in this repo (`engine/optimizer.py`, `execution/`) are early, unfinished
sketches around walk-forward optimization and semi-autonomous signal alerts. They aren't wired
into the running app and shouldn't be treated as working features.

## Stack

FastAPI + SQLite on the backend, a single-file vanilla JS dashboard on the front end (hand-drawn
SVG equity curve and histogram — no charting library). Fully local by default.

## Status

Personal project, actively used but early. Built to answer one question about my own trading —
expect rough edges, and expect the schema/API to change without notice.

## More from this author

- [DIRA](https://github.com/Yusuf-Gadelrab/dira) — zero-dependency security scanner for startup codebases.
- [EventReels](https://github.com/Yusuf-Gadelrab/eventreels) — local ffmpeg highlight-reel automation.
- [EcoImpact](https://github.com/Yusuf-Gadelrab/ecoimpact) — local-first litter map + cleanup impact meter.

Portfolio: <https://yusuf-gadelrab.github.io/> · All projects: <https://yusuf-gadelrab.github.io/everything.html>

## License

© 2026 Yusuf Gadelrab. All rights reserved. Source is public for portfolio and evaluation
purposes only: no license is granted to copy, modify, or redistribute this code.

---

## About the author

Built by **Yusuf Gadelrab** — computer science student at San José State University (BS Computer Science, expected May 2028), AI/ML builder, and co-author of two peer-reviewed SIGCSE Technical Symposium 2026 papers on computer science education ([DOI 10.1145/3770761.3777339](https://doi.org/10.1145/3770761.3777339)).

- Portfolio: <https://yusuf-gadelrab.github.io/>
- About / FAQ: <https://yusuf-gadelrab.github.io/about.html>
- Guides: <https://yusuf-gadelrab.github.io/guides.html>
- Contact: yusuf.gadelrab06@gmail.com
