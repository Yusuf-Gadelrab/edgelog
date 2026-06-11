import os
import sqlite3
import getpass
from pathlib import Path
from collections import defaultdict, deque
import robin_stocks.robinhood as r
from dotenv import load_dotenv

DB_PATH = Path(__file__).parent / "edgelog.db"

instrument_cache = {}

def get_symbol(url):
    if url not in instrument_cache:
        try:
            instrument_cache[url] = r.stocks.get_symbol_by_url(url)
        except Exception:
            instrument_cache[url] = "UNKNOWN"
    return instrument_cache[url]

def sync_robinhood(interactive=True):
    if interactive:
        print("EdgeLog ⮂ Robinhood Sync")
        print("--------------------------")
    load_dotenv()
    rh_username = os.getenv("RH_USERNAME")
    rh_password = os.getenv("RH_PASSWORD")
    
    if interactive:
        if not rh_username:
            rh_username = input("Robinhood Username: ")
        if not rh_password:
            rh_password = getpass.getpass("Robinhood Password: ")

    if interactive:
        print("Logging in to Robinhood...")
    
    try:
        if rh_username and rh_password:
            r.login(rh_username, rh_password, store_session=True)
        else:
            if not interactive:
                raise Exception("Missing RH_USERNAME in .env. Please run robinhood_sync.py in terminal first or add credentials to .env")
            r.login(store_session=True)
    except Exception as e:
        if not interactive:
            raise Exception(str(e))
        else:
            print("Login failed:", e)
            return {"inserted": 0, "skipped": 0}

    if interactive:
        print("Fetching filled stock orders (this may take a moment)...")
    orders = r.orders.get_all_stock_orders()
    
    filled_orders = [o for o in orders if o["state"] == "filled"]
    filled_orders.sort(key=lambda x: x["last_transaction_at"])
    if interactive:
        print(f"Found {len(filled_orders)} filled executions.")
    
    open_positions = defaultdict(deque)
    completed_trades = []
    
    if interactive:
        print("Pairing buys and sells into round-trip trades...")
    for o in filled_orders:
        symbol = get_symbol(o["instrument"])
        side = o["side"]
        qty = float(o["cumulative_quantity"])
        price = float(o["average_price"])
        fees = float(o["fees"])
        date = o["last_transaction_at"].split("T")[0]
        
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
                    "setup": "rh-sync",
                    "direction": "long",
                    "entry": round(avg_entry, 2),
                    "stop": 0.0,
                    "target": 0.0,
                    "exit_px": round(price, 2),
                    "shares": round(matched_qty, 4),
                    "fees": round(fees, 2),
                    "notes": f"RH Order ID: {o['id']}"
                })
                
    if interactive:
        print(f"Identified {len(completed_trades)} completed trades.")
    
    if not DB_PATH.exists():
        if interactive:
            print(f"EdgeLog DB not found at {DB_PATH}. Run the app once to initialize.")
        return {"inserted": 0, "skipped": 0}

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    inserted = 0
    skipped = 0
    
    for t in completed_trades:
        o_id = t["notes"].split("RH Order ID: ")[1]
        exists = c.execute("SELECT 1 FROM trades WHERE notes LIKE ?", (f"%{o_id}%",)).fetchone()
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
        print("Refresh your EdgeLog dashboard to see them.")
        
    return {"inserted": inserted, "skipped": skipped}

if __name__ == "__main__":
    sync_robinhood(interactive=True)
