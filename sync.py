import sqlite3
from pathlib import Path
import time

DB_PATH = Path(__file__).parent / "edgelog.db"

def mark_synced(trade_ids: list[int]):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(f"UPDATE trades SET synced_at = ? WHERE id IN ({','.join(['?']*len(trade_ids))})", 
                     [time.time()] + trade_ids)

def get_unsynced_trades():
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        return [dict(row) for row in conn.execute("SELECT * FROM trades WHERE synced_at IS NULL")]
