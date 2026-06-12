"""EdgeLog — trade journal analytics. Your edge as a number, not a vibe.

Imports the journal.csv schema (one row per closed trade):
date,symbol,setup,direction,entry,stop,target,exit,shares,fees,notes
No advice, no signals, no broker credentials — analytics on the user's own history only.
"""

import csv
import io
import os
import sqlite3
import statistics
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, List, Any, Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse

DB_PATH = Path(__file__).parent / "edgelog.db"
STATIC = Path(__file__).parent / "static"

app = FastAPI(title="EdgeLog")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Allow Next.js local dev
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
        c.execute("""CREATE TABLE IF NOT EXISTS rules(
            id INTEGER PRIMARY KEY, name TEXT, kind TEXT, param REAL,
            setups TEXT, active INTEGER DEFAULT 1)""")


init_db()


def r_multiple(direction: str, entry: float, stop: float, exit_px: float) -> float:
    """Reward measured in units of initial risk. The journal's core number."""
    if direction == "long" and stop > entry:
        raise ValueError("Long stop must be <= entry")
    if direction == "short" and stop < entry:
        raise ValueError("Short stop must be >= entry")
        
    risk = abs(entry - stop)
    if risk == 0: return 0.0 # Avoid division by zero
    move = (exit_px - entry) if direction == "long" else (entry - exit_px)
    return round(move / risk, 3)


def dollars(direction: str, entry: float, exit_px: float, shares: float, fees: float) -> float:
    move = (exit_px - entry) if direction == "long" else (entry - exit_px)
    return round(move * shares - (fees or 0.0), 2)


def evaluate_rules(trades: List[Dict[str, Any]], rules: List[Dict[str, Any]]) -> Dict[int, List[int]]:
    """Evaluates trades against active rules. Returns {trade_id: [rule_id, ...]}"""
    breaks = {}
    active_rules = [r for r in rules if r["active"]]
    
    # Precompute per-day counts for max_per_day
    day_counts = {}
    # Sort trades by date to ensure day order is correct
    sorted_trades = sorted(trades, key=lambda t: (t["date"], t["id"]))
    # Create mapping of trade_id -> day_order
    trade_day_order = {}
    current_day = None
    order = 0
    for t in sorted_trades:
        if t["date"] != current_day:
            current_day = t["date"]
            order = 1
        else:
            order += 1
        trade_day_order[t["id"]] = order
    
    for t in trades:
        t["_day_order"] = trade_day_order[t["id"]]

    for t in trades:
        t_breaks = []
        for r in active_rules:
            broken = False
            if r["kind"] == "max_risk":
                risk = abs(t["entry"] - t["stop"]) * t["shares"]
                if risk > r["param"]:
                    broken = True
            elif r["kind"] == "max_per_day":
                if t["_day_order"] > r["param"]:
                    broken = True
            elif r["kind"] == "setup_whitelist":
                allowed = [s.strip() for s in (r["setups"] or "").split(",")]
                if t["setup"] not in allowed:
                    broken = True
            elif r["kind"] == "stop_required":
                # Check for stop=0 or no stop
                if not t["stop"] or t["stop"] == 0 or t["stop"] == t["entry"]:
                    broken = True
            
            if broken:
                t_breaks.append(r["id"])
        if t_breaks:
            breaks[t["id"]] = t_breaks
    return breaks

@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")

@app.get("/api/rules")
def list_rules():
    with db() as c:
        return [dict(r) for r in c.execute("SELECT * FROM rules")]

@app.post("/api/rules")
def create_rule(rule: dict):
    with db() as c:
        c.execute("INSERT INTO rules(name, kind, param, setups) VALUES(?,?,?,?)",
                  (rule["name"], rule["kind"], rule.get("param"), rule.get("setups")))
    return {"ok": True}

@app.patch("/api/rules/{rule_id}")
def update_rule(rule_id: int, rule: dict):
    with db() as c:
        if "active" in rule:
            c.execute("UPDATE rules SET active = ? WHERE id = ?", (rule["active"], rule_id))
        if "param" in rule:
            c.execute("UPDATE rules SET param = ? WHERE id = ?", (rule["param"], rule_id))
    return {"ok": True}

@app.delete("/api/rules/{rule_id}")
def delete_rule(rule_id: int):
    with db() as c:
        c.execute("DELETE FROM rules WHERE id = ?", (rule_id,))
    return {"ok": True}


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
                r_multiple(direction, vals[0], vals[1], vals[2])
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

@app.get("/api/sync/state")
def get_sync_state():
    with db() as c:
        last_sync = c.execute("SELECT MAX(synced_at) FROM trades").fetchone()[0]
    return {"last_sync": last_sync}

@app.get("/api/export.csv")
def export_csv():
    trades = list_trades()
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=FIELDS)
    writer.writeheader()
    for t in trades:
        row = {f: t.get(f) for f in FIELDS}
        row["exit"] = t.get("exit_px")
        writer.writerow(row)
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=edgelog_export.csv"}
    )

@app.post("/api/sync/robinhood")
def trigger_robinhood_sync():
    try:
        from robinhood_sync import sync_robinhood
        return sync_robinhood(interactive=False)
    except Exception as e:
        raise HTTPException(500, f"Robinhood sync failed: {str(e)}. "
                                 "If this is an auth error, please run 'uv run python robinhood_sync.py' "
                                 "in your terminal to authenticate first.")

@app.post("/api/sync/alpaca")
def trigger_alpaca_sync():
    try:
        from alpaca_sync import sync_alpaca
        res = sync_alpaca(interactive=False)
        return res
    except Exception as e:
        raise HTTPException(500, f"Alpaca sync failed: {str(e)}")

@app.post("/api/sync/summeros")
def sync_summeros():
    journal_path = Path.home() / "SummerOS" / "trading" / "journal.csv"
    if not journal_path.exists():
        raise HTTPException(404, f"Journal file not found at {journal_path}")
        
    with open(journal_path, "r", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        missing = [f for f in FIELDS[:-1] if f not in (reader.fieldnames or [])]
        if missing:
            raise HTTPException(422, f"CSV missing columns: {missing} — expected {FIELDS}")
            
        inserted, skipped = 0, []
        with db() as c:
            # Full sync replaces the DB contents
            c.execute("DELETE FROM trades")
            for i, row in enumerate(reader, start=2):
                try:
                    direction = row["direction"].strip().lower()
                    if direction not in ("long", "short"):
                        raise ValueError(f"direction must be long/short, got {direction!r}")
                    vals = [float(row[k]) for k in ("entry", "stop", "exit", "shares")]
                    r_multiple(direction, vals[0], vals[1], vals[2])
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
                    
    return {"inserted": inserted, "skipped": len(skipped), "errors": skipped[:5]}

@app.post("/api/backtest/run")
def api_backtest_run(payload: dict):
    try:
        from engine.vbt_runner import run_backtest
        symbol = payload.get("symbol", "SPY")
        strategy = payload.get("strategy", "RSI_DIVERGENCE")
        params = payload.get("params", {})
        res = run_backtest(symbol, strategy, params)
        return res
    except Exception as e:
        raise HTTPException(500, f"Backtest failed: {str(e)}")


@app.get("/api/hermes/interrogate")
async def api_hermes_interrogate():
    try:
        from ai.interrogator import interrogate_trades, log_edge
        res = await interrogate_trades()
        
        # Log market edge if identified
        edge = res.get("market_edge_identified")
        if edge and str(edge).lower() != "none":
            log_edge(str(edge))
            
        return res
    except Exception as e:
        raise HTTPException(500, f"Hermes failed: {str(e)}")

@app.post("/api/coach")
async def ai_coach():
    s = stats()
    if not s.get("trades"):
        raise HTTPException(400, "No trades to review.")
    
    trades = list_trades()
    recent = trades[-30:]
    
    expectancy = s.get("expectancy_r")
    win_rate = s.get("win_rate")
    profit_factor = s.get("profit_factor")
    
    discipline = s.get("discipline", {})
    adherence = discipline.get("adherence_pct", "N/A")
    cost = discipline.get("cost_of_breaking_r", "N/A")
    broken_trades = discipline.get("broken_trades", 0)
    
    data_summary = f"Overall Stats:\nExpectancy: {expectancy}R\nWin Rate: {win_rate}%\nProfit Factor: {profit_factor}\n\n"
    data_summary += f"Discipline Metrics:\nAdherence: {adherence}%\nBroken Trades: {broken_trades}\nCost of breaking rules: {cost}R\n\n"
    data_summary += "Recent Trades (last 30):\n"
    for t in reversed(recent):
        data_summary += f"- Date: {t['date']}, Symbol: {t['symbol']}, Setup: {t['setup']}, R: {t['r']}R, Notes: {t['notes']}\n"
        
    prompt = (
        "You are a ruthless, quantitative trading coach. Review this recent trade data and discipline record. "
        "Give me 1 paragraph on what I am doing right, 1 paragraph on my fatal flaws/rule-breaking, "
        "and 3 bullet points of actionable advice for tomorrow. Be direct, use numbers, no fluff.\n\n"
        f"{data_summary}"
    )
    
    async def stream_response():
        import httpx
        import json
        try:
            async with httpx.AsyncClient() as client:
                async with client.stream("POST", "http://localhost:11434/api/generate", json={"model": "qwen3:8b", "prompt": prompt}) as r:
                    async for line in r.aiter_lines():
                        if line:
                            try:
                                data = json.loads(line)
                                if "response" in data:
                                    yield data["response"]
                            except Exception:
                                pass
        except Exception as e:
            yield f"\n\n[Error communicating with local LLM: {str(e)}]"

    return StreamingResponse(stream_response(), media_type="text/plain")


@app.get("/api/stats")
def stats():
    trades = list_trades()
    if not trades:
        return {"trades": 0}
    
    rules = list_rules()
    breaks = evaluate_rules(trades, rules)
    
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
        s = by_setup.setdefault(t["setup"], {"trades": 0, "rs": [], "pnl": 0.0, "breaks": 0})
        s["trades"] += 1
        s["rs"].append(t["r"])
        s["pnl"] = round(s["pnl"] + t["pnl"], 2)
        if rules and t["id"] in breaks:
            s["breaks"] += 1
    setups = [{"setup": k, "trades": v["trades"],
               "expectancy": round(statistics.mean(v["rs"]), 3),
               "win_rate": round(100 * sum(1 for r in v["rs"] if r > 0) / v["trades"], 1),
               "pnl": v["pnl"],
               "breaks": v["breaks"]}
              for k, v in by_setup.items()]
    setups.sort(key=lambda s: s["expectancy"], reverse=True)

    lo, hi = int(min(rs) // 1), int(max(rs) // 1) + 1
    hist = [{"bucket": f"{b}R", "count": sum(1 for r in rs if b <= r < b + 1)}
            for b in range(lo, hi + 1)]

    daily_stats = {}
    for t in trades:
        d = daily_stats.setdefault(t["date"], {"date": t["date"], "r": 0.0, "trades": 0})
        d["trades"] += 1
        d["r"] = round(d["r"] + t["r"], 3)
    daily = list(daily_stats.values())
    daily.sort(key=lambda x: x["date"])

    expectancy = round(statistics.mean(rs), 3)
    response = {
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
        "daily": daily,
        "verdict": verdict(expectancy, len(trades), setups),
    }

    if rules:
        clean_ids = [t["id"] for t in trades if t["id"] not in breaks]
        broken_ids = [t["id"] for t in trades if t["id"] in breaks]
        
        clean_rs = [t["r"] for t in trades if t["id"] in clean_ids]
        broken_rs = [t["r"] for t in trades if t["id"] in broken_ids]
        
        clean_trades = len(clean_ids)
        broken_trades = len(broken_ids)
        
        # Streak
        streak = 0
        for t in reversed(trades):
            if t["id"] not in breaks:
                streak += 1
            else:
                break
        
        active_rules = [r for r in rules if r["active"]]
        by_rule = []
        for r in active_rules:
            r_broken_ids = [tid for tid, rids in breaks.items() if r["id"] in rids]
            r_broken_rs = [t["r"] for t in trades if t["id"] in r_broken_ids]
            if r_broken_ids:
                by_rule.append({
                    "rule": r["name"],
                    "breaks": len(r_broken_ids),
                    "broken_expectancy_r": round(statistics.mean(r_broken_rs), 2)
                })

        response["discipline"] = {
            "adherence_pct": round(100 * clean_trades / len(trades), 1),
            "clean_trades": clean_trades,
            "broken_trades": broken_trades,
            "clean_expectancy_r": round(statistics.mean(clean_rs), 2) if clean_rs else 0,
            "broken_expectancy_r": round(statistics.mean(broken_rs), 2) if broken_rs else 0,
            "cost_of_breaking_r": round(((statistics.mean(clean_rs) if clean_rs else 0) - (statistics.mean(broken_rs) if broken_rs else 0)) * broken_trades, 2),
            "current_clean_streak": streak,
            "by_rule": by_rule
        }
        
        if response["discipline"]["broken_expectancy_r"] < response["discipline"]["clean_expectancy_r"] - 0.3 and broken_trades >= 5:
            cost = response["discipline"]["cost_of_breaking_r"]
            response["verdict"] += f" Rule-breaking trades run {response['discipline']['broken_expectancy_r']}R vs {response['discipline']['clean_expectancy_r']}R clean: discipline is worth {cost}R total."

    return response


@app.get("/api/report/weekly")
def weekly_report(week: str = None):
    # Default to current ISO week start (Monday)
    if not week:
        today = datetime.now()
        start = today - timedelta(days=today.weekday())
    else:
        start = datetime.strptime(week, "%Y-%m-%d")
    end = start + timedelta(days=6)
    
    trades = list_trades()
    week_trades = [t for t in trades if start <= datetime.strptime(t["date"], "%Y-%m-%d") <= end]
    
    net_r = sum(t["r"] for t in week_trades)
    expectancy = round(statistics.mean([t["r"] for t in week_trades]), 3) if week_trades else 0
    adherence = round(100 * len([t for t in week_trades if t["id"] not in evaluate_rules(week_trades, list_rules())]) / len(week_trades), 1) if week_trades else 0
    
    best = sorted(week_trades, key=lambda t: t["r"], reverse=True)[0] if week_trades else None
    worst = sorted(week_trades, key=lambda t: t["r"])[0] if week_trades else None
    
    markdown = f"## Weekly Review ({start.date()} to {end.date()})\n"
    markdown += f"- Total Trades: {len(week_trades)}\n"
    markdown += f"- Net R: {round(net_r, 2)}R\n"
    markdown += f"- Expectancy: {expectancy}R\n"
    markdown += f"- Adherence: {adherence}%\n"
    if best: markdown += f"- Best: {best['symbol']} ({best['r']}R)\n"
    if worst: markdown += f"- Worst: {worst['symbol']} ({worst['r']}R)\n"
    markdown += "\n---\n*Which rule would have saved the most R this week?*"
    
    return {
        "week_start": start.strftime("%Y-%m-%d"),
        "week_end": end.strftime("%Y-%m-%d"),
        "trades": len(week_trades),
        "net_r": round(net_r, 2),
        "expectancy_r": expectancy,
        "adherence_pct": adherence,
        "best_setup": {"name": best["setup"], "r": best["r"]} if best else None,
        "worst_setup": {"name": worst["setup"], "r": worst["r"]} if worst else None,
        "biggest_win_r": best["r"] if best else 0,
        "biggest_loss_r": worst["r"] if worst else 0,
        "clean_streak": 0, # Placeholder
        "markdown": markdown
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
