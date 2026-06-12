import sqlite3
import time
import requests
import json
import os
from sync import get_unsynced_trades, mark_synced

SYNC_URL = os.getenv("EDGELOG_SYNC_URL", "https://api.edgelog.com/sync")

def push_to_cloud():
    unsynced = get_unsynced_trades()
    if not unsynced: 
        print("No trades to sync.")
        return
    
    payload = {
        "trades": unsynced,
        "sync_time": time.time(),
        "client_version": "2.0.0"
    }
    
    try:
        # Structured push
        response = requests.post(SYNC_URL, json=payload, timeout=10)
        response.raise_for_status()
        
        # Mark as synced on success
        mark_synced([t['id'] for t in unsynced])
        print(f"Successfully synced {len(unsynced)} trades.")
    except Exception as e:
        print(f"Sync failed: {e}")

if __name__ == "__main__":
    push_to_cloud()
