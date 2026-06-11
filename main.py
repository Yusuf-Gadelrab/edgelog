"""EdgeLog — trade journal analytics. Your edge as a number, not a vibe.

Imports the journal.csv schema (one row per closed trade):
date,symbol,setup,direction,entry,stop,target,exit,shares,fees,notes
No advice, no signals, no broker credentials — analytics on the user's own history only.
"""

import csv
import io
import sqlite3
import statistics
from contextlib import contextmanager
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

DB_PATH = Path(__file__).parent / "edgelog.db"
STATIC = Path(__file__).parent / "static"

app = FastAPI(title="EdgeLog")

FIELDS = ["date", "symbol", "setup", "direction", "entry", "stop",
          "target", "exit", "shares", "fees", "notes"]


@contextmanager
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with db() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS trades(
            id INTEGER PRIMARY KEY, date TEXT, symbol TEXT, setup TEXT,
            direction TEXT, entry REAL, stop REAL, target REAL, exit_px REAL,
            shares REAL, fees REAL, notes TEXT)""")


init_db()


def r_multiple(direction: str, entry: float, stop: float, exit_px: float) -> float:
    """Reward measured in units of initial risk. The journal's core number."""
    risk = (entry - stop) if direction == "long" else (stop - entry)
    if risk <= 0:
        raise ValueError("stop must be on the loss side of entry")
    move = (exit_px - entry) if direction == "long" else (entry - exit_px)
    return round(move / risk, 3)


def dollars(direction: str, entry: float, exit_px: float, shares: float, fees: float) -> float:
    move = (exit_px - entry) if direction == "long" else (entry - exit_px)
    return round(move * shares - fees, 2)


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.post("/api/import", status_code=201)
async def import_csv(file: UploadFile = File(...)):
    raw = (await file.read()).decode("utf-8", errors="replace")
    reader = csv.DictReader(io.StringIO(raw))
    missing = [f for f in FIELDS[:-1] if f not in (reader.fieldnames or [])]
    if missing:
        raise HTTPException(422, f"CSV missing columns: {missing} — expected {FIELDS}")
    inserted, skipped = 0, []
    with db() as c:
        for i, row in enumerate(reader, start=2):
            try:
                direction = row["direction"].strip().lower()
                if direction not in ("long", "short"):
                    raise ValueError(f"direction must be long/short, got {direction!r}")
                vals = [float(row[k]) for k in ("entry", "stop", "exit", "shares")]
                r_multiple(direction, vals[0], vals[1], vals[2])  # validates stop side
                c.execute(
                    "INSERT INTO trades(date,symbol,setup,direction,entry,stop,target,exit_px,"
                    "shares,fees,notes) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    (row["date"].strip(), row["symbol"].strip().upper(),
                     row["setup"].strip() or "untagged", direction,
                     vals[0], vals[1], float(row.get("target") or 0), vals[2], vals[3],
                     float(row.get("fees") or 0), (row.get("notes") or "").strip()[:500]))
                inserted += 1
            except (ValueError, KeyError) as e:
                skipped.append({"line": i, "error": str(e)})
    return {"imported": inserted, "skipped": skipped}


@app.get("/api/trades")
def list_trades():
    with db() as c:
        rows = [dict(r) for r in c.execute("SELECT * FROM trades ORDER BY date, id")]
    for t in rows:
        t["r"] = r_multiple(t["direction"], t["entry"], t["stop"], t["exit_px"])
        t["pnl"] = dollars(t["direction"], t["entry"], t["exit_px"], t["shares"], t["fees"])
    return rows


@app.delete("/api/trades")
def reset():
    with db() as c:
        c.execute("DELETE FROM trades")
    return {"ok": True}


@app.get("/api/stats")
def stats():
    trades = list_trades()
    if not trades:
        return {"trades": 0}
    rs = [t["r"] for t in trades]
    wins = [r for r in rs if r > 0]
    losses = [r for r in rs if r <= 0]
    gross_win = sum(t["pnl"] for t in trades if t["pnl"] > 0)
    gross_loss = -sum(t["pnl"] for t in trades if t["pnl"] < 0)

    curve, peak, max_dd, cum = [], 0.0, 0.0, 0.0
    for t in trades:
        cum = round(cum + t["r"], 3)
        curve.append({"date": t["date"], "cum_r": cum})
        peak = max(peak, cum)
        max_dd = max(max_dd, peak - cum)

    by_setup = {}
    for t in trades:
        s = by_setup.setdefault(t["setup"], {"trades": 0, "rs": [], "pnl": 0.0})
        s["trades"] += 1
        s["rs"].append(t["r"])
        s["pnl"] = round(s["pnl"] + t["pnl"], 2)
    setups = [{"setup": k, "trades": v["trades"],
               "expectancy": round(statistics.mean(v["rs"]), 3),
               "win_rate": round(100 * sum(1 for r in v["rs"] if r > 0) / v["trades"], 1),
               "pnl": v["pnl"]}
              for k, v in by_setup.items()]
    setups.sort(key=lambda s: s["expectancy"], reverse=True)

    lo, hi = int(min(rs) // 1), int(max(rs) // 1) + 1
    hist = [{"bucket": f"{b}R", "count": sum(1 for r in rs if b <= r < b + 1)}
            for b in range(lo, hi + 1)]

    expectancy = round(statistics.mean(rs), 3)
    return {
        "trades": len(trades),
        "expectancy_r": expectancy,
        "win_rate": round(100 * len(wins) / len(rs), 1),
        "avg_win_r": round(statistics.mean(wins), 2) if wins else 0,
        "avg_loss_r": round(statistics.mean(losses), 2) if losses else 0,
        "profit_factor": round(gross_win / gross_loss, 2) if gross_loss else None,
        "net_pnl": round(sum(t["pnl"] for t in trades), 2),
        "max_drawdown_r": round(max_dd, 2),
        "equity_curve": curve,
        "r_histogram": hist,
        "setups": setups,
        "verdict": verdict(expectancy, len(trades), setups),
    }


def verdict(expectancy: float, n: int, setups: list[dict]) -> str:
    if n < 20:
        return (f"Only {n} trades logged — your numbers aren't statistically meaningful yet. "
                f"Keep logging; judge nothing before ~20 trades.")
    best = setups[0]
    worst = setups[-1]
    if expectancy > 0.2:
        msg = f"Positive edge: +{expectancy}R per trade over {n} trades."
    elif expectancy > 0:
        msg = f"Marginally positive ({expectancy}R/trade) — real, but thin. Size carefully."
    else:
        msg = f"Negative expectancy ({expectancy}R/trade) — the data says stop and review."
    if len(setups) > 1 and worst["expectancy"] < 0 < best["expectancy"]:
        msg += (f" Your {best['setup']} trades (+{best['expectancy']}R) are subsidizing "
                f"{worst['setup']} ({worst['expectancy']}R) — cut or rework the latter.")
    return msg
