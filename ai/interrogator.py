import httpx
import json
import sqlite3
from pathlib import Path
from typing import Dict, Any

DB_PATH = Path(__file__).parent.parent / "edgelog.db"
EDGES_PATH = Path(__file__).parent / "learned-market-edges.md"

def get_recent_trades(limit: int = 5):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    try:
        # We need the table to exist.
        rows = c.execute("SELECT * FROM trades ORDER BY date DESC, id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]
    except Exception:
        return []
    finally:
        conn.close()

async def interrogate_trades() -> Dict[str, Any]:
    trades = get_recent_trades(5)
    if not trades:
        return {"verdict": "No trades logged yet. Go execute.", "rule_broken": False, "psychological_leak": "Inaction", "market_edge_identified": "None", "actionable_advice": "Start paper trading to build data."}

    # Format context for Ollama
    trade_context = "Recent Trades:\\n"
    for t in trades:
        pnl = t.get("exit_px", 0) - t.get("entry", 0)
        if t.get("direction") == "short":
            pnl = -pnl
        trade_context += f"- {t['date']} | {t['symbol']} | {t['direction'].upper()} | Entry: {t['entry']} | Exit: {t['exit_px']} | Setup: {t['setup']} | PnL: {round(pnl, 2)}\\n"

    prompt = f"""You are Hermes, a ruthless quantitative trading coach. 
Analyze the following recent trades. Identify the core psychological leak or market edge.
Return ONLY valid JSON matching this exact schema:
{{
    "verdict": "A 2-sentence harsh but true breakdown of the trading behavior.",
    "rule_broken": true/false,
    "psychological_leak": "e.g., FOMO, Revenge Trading, Impatience, None",
    "market_edge_identified": "e.g., EMA Cross works well on AAPL",
    "actionable_advice": "1 strict rule for tomorrow"
}}

{trade_context}
"""

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "http://localhost:11434/api/generate",
                json={
                    "model": "qwen3:8b",
                    "prompt": prompt,
                    "stream": False,
                    "format": "json"
                },
                timeout=30.0
            )
            data = resp.json()
            return json.loads(data.get("response", "{}"))
    except Exception as e:
        return {"error": str(e), "verdict": "Failed to reach Hermes (Ollama not running?)."}

def log_edge(edge: str):
    if not edge or edge.lower() == "none":
        return
    
    if not EDGES_PATH.exists():
        with open(EDGES_PATH, "w") as f:
            f.write("# Learned Market Edges\\n\\n")
            
    with open(EDGES_PATH, "a") as f:
        f.write(f"\\n### {edge}\\nwhen: observed by Hermes\\nuses: 1 · status: raw\\n")
