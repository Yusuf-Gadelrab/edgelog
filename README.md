# EdgeLog 📈

EdgeLog is a trade journal analyzer that imports your trades as CSV and reports whether you
actually have an edge: expectancy in R, win rate, profit factor, max drawdown, equity curve,
R distribution, and a per-setup edge breakdown with a plain-English verdict.

**Your edge as a number, not a vibe.**

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
- **Discipline tracking:** adherence metrics, rule-breaking costs (in R), and clean-trade streaks.
- **The verdict:** a generated plain-English read of the whole journal, including discipline impact.

## Stack
FastAPI + SQLite + a single-file vanilla JS dashboard (SVG equity curve, no chart library).
Fully local: your trade history never leaves your machine.

## Robinhood sync (experimental)
Sync your filled stock orders from Robinhood:
```bash
uv run python robinhood_sync.py  # authenticate in terminal first
```
Sync is read-only and idempotent (dedupes via order ID). Setup requires `RH_USERNAME` and `RH_PASSWORD` in `EdgeLog/app/.env` (gitignored).
"""
Robinhood fills do not have setup/stop data; they appear as 'rh-sync' setup trades. Stats analytics tolerate these stopless rows.
"""

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
