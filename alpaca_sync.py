import os
import sqlite3
import requests
from pathlib import Path
from collections import defaultdict, deque
from dotenv import load_dotenv

DB_PATH = Path(__file__).parent / "edgelog.db"

def sync_alpaca(interactive=True):
    if interactive:
        print("EdgeLog ⮂ Alpaca Sync")
        print("-----------------------")
    load_dotenv()
    alpaca_api_key = os.getenv("ALPACA_API_KEY")
    alpaca_api_secret = os.getenv("ALPACA_API_SECRET")
    alpaca_base_url = os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")
    
    if interactive and not alpaca_api_key:
        alpaca_api_key = input("Alpaca API Key: ")
    if interactive and not alpaca_api_secret:
        alpaca_api_secret = input("Alpaca API Secret: ")
        
    if not alpaca_api_key or not alpaca_api_secret:
        if interactive:
            print("Missing Alpaca credentials. Check .env or inputs.")
        return {"inserted": 0, "skipped": 0}
        
    headers = {
        "APCA-API-KEY-ID": alpaca_api_key,
        "APCA-API-SECRET-KEY": alpaca_api_secret
    }
    
    url = f"{alpaca_base_url}/v2/account/activities/FILL"
    
    if interactive:
        print("Fetching fills from Alpaca...")
    r = requests.get(url, headers=headers)
    if not r.ok:
        if interactive:
            print(f"Failed to fetch: {r.status_code} {r.text}")
        return {"inserted": 0, "skipped": 0}
        
    fills = r.json()
    fills.sort(key=lambda x: x["transaction_time"])
    
    if interactive:
        print(f"Found {len(fills)} filled executions.")
        
    open_positions = defaultdict(deque)
    completed_trades = []
    
    for f in fills:
        symbol = f["symbol"]
        side = f["side"] # buy or sell
        qty = float(f["qty"])
        price = float(f["price"])
        date = f["transaction_time"][:10]
        
        # Simple FIFO matching for Longs
        if side == "buy":
            open_positions[symbol].append({"qty": qty, "price": price})
        elif side == "sell":
            qty_to_match = qty
            entry_cost = 0.0
            matched_qty = 0.0
            
            while qty_to_match > 0 and open_positions[symbol]:
                oldest = open_positions[symbol][0]
                match_amount = min(qty_to_match, oldest["qty"])
                
                entry_cost += match_amount * oldest["price"]
                matched_qty += match_amount
                qty_to_match -= match_amount
                
                oldest["qty"] -= match_amount
                if oldest["qty"] <= 0:
                    open_positions[symbol].popleft()
                    
            if matched_qty > 0:
                avg_entry = entry_cost / matched_qty
                completed_trades.append({
                    "date": date,
                    "symbol": symbol,
                    "setup": "alpaca-sync",
                    "direction": "long",
                    "entry": round(avg_entry, 2),
                    "stop": 0.0,
                    "target": 0.0,
                    "exit_px": round(price, 2),
                    "shares": round(matched_qty, 4),
                    "fees": 0.0,
                    "notes": f"Alpaca Sync: {f['id']}"
                })
                
    if not DB_PATH.exists():
        if interactive:
            print("EdgeLog DB not found. Ensure backend is initialized.")
        return {"inserted": 0, "skipped": 0}
        
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    inserted = 0
    skipped = 0
    
    for t in completed_trades:
        f_id = t["notes"].split("Alpaca Sync: ")[1]
        exists = c.execute("SELECT 1 FROM trades WHERE notes LIKE ?", (f"%{f_id}%",)).fetchone()
        if exists:
            skipped += 1
            continue
            
        c.execute("""
            INSERT INTO trades (date, symbol, setup, direction, entry, stop, target, exit_px, shares, fees, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (t["date"], t["symbol"], t["setup"], t["direction"], t["entry"], t["stop"], t["target"], t["exit_px"], t["shares"], t["fees"], t["notes"]))
        inserted += 1
        
    conn.commit()
    conn.close()
    
    if interactive:
        print(f"Sync complete. New trades logged: {inserted} | Already synced: {skipped}")
        
    return {"inserted": inserted, "skipped": skipped}

if __name__ == "__main__":
    sync_alpaca(interactive=True)
