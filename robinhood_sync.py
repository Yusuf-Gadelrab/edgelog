import os
import sqlite3
import getpass
from pathlib import Path
import robin_stocks.robinhood as r
from dotenv import load_dotenv

DB_PATH = Path(__file__).parent / "edgelog.db"

def sync_robinhood(interactive=True, default_setup="robinhood", default_stop=0):
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
            
            symbol = r.stocks.get_symbol_by_url(order["instrument"])
            
            # Stable dedupe key: date+symbol+side+shares+entry
            rh_id = order["id"]
            date = order["last_transaction_at"].split('T')[0]
            side = order["side"]
            shares = float(order["cumulative_quantity"])
            entry = float(order["average_price"])
            
            # Check for existing sync using the stable key or the RH order ID
            if c.execute("""SELECT 1 FROM trades 
                            WHERE date=? AND symbol=? AND direction=? AND shares=? AND entry=? 
                            OR notes LIKE ?""", 
                         (date, symbol, side, shares, entry, f"%RH Order ID: {rh_id}%")).fetchone():
                continue
            
            # Use defaults if not interactive
            setup = default_setup
            stop = default_stop
            if interactive:
                setup = input(f"Enter setup for {symbol} ({order['side']}): ") or default_setup
                stop = input(f"Enter stop price for {symbol}: ") or default_stop
            
            c.execute("""INSERT INTO trades(date, symbol, setup, direction, entry, stop, shares, exit_px, notes) 
                         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                      (order["last_transaction_at"].split('T')[0], symbol, setup, 
                       order["side"], order["average_price"], stop, order["cumulative_quantity"], 
                       order["average_price"], f"RH Order ID: {rh_id}"))
            inserted += 1
        conn.commit()
    print(f"Sync complete: {inserted} trades imported.")
