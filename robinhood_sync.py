import os
import sqlite3
import getpass
from pathlib import Path
import robin_stocks.robinhood as r
from dotenv import load_dotenv

DB_PATH = Path(__file__).parent / "edgelog.db"

def sync_robinhood(interactive=True):
    load_dotenv()
    user = os.getenv("RH_USERNAME")
    pw = os.getenv("RH_PASSWORD")
    
    if interactive and not (user and pw):
        user = input("Robinhood Username: ")
        pw = getpass.getpass("Robinhood Password: ")
    elif not (user and pw):
        raise Exception("Missing RH_USERNAME in .env. Please run robinhood_sync.py in terminal first.")

    r.login(user, pw, store_session=True)
    orders = r.orders.get_all_stock_orders()
    
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        inserted = 0
        for order in orders:
            if order["state"] != "filled": continue
            
            # Check for existing sync
            rh_id = order["id"]
            if c.execute("SELECT 1 FROM trades WHERE notes LIKE ?", (f"%RH Order ID: {rh_id}%",)).fetchone():
                continue
            
            symbol = r.stocks.get_symbol_by_url(order["instrument"])
            # Prompt for setup/stop if missing (simulated as Robinhood data is stopless)
            setup = input(f"Enter setup for {symbol} ({order['side']}): ") or "robinhood"
            stop = input(f"Enter stop price for {symbol}: ") or 0
            
            c.execute("""INSERT INTO trades(date, symbol, setup, direction, entry, stop, shares, exit_px, notes) 
                         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                      (order["last_transaction_at"].split('T')[0], symbol, setup, 
                       order["side"], order["average_price"], stop, order["cumulative_quantity"], 
                       order["average_price"], f"RH Order ID: {rh_id}"))
            inserted += 1
        conn.commit()
    print(f"Sync complete: {inserted} trades imported.")
