import sqlite3
import time
import requests
import json
from sync import get_unsynced_trades, mark_synced

def push_to_cloud():
    unsynced = get_unsynced_trades()
    if not unsynced: return
    
    # Simulate cloud endpoint
    try:
        # requests.post("https://api.edgelog.com/sync", json=unsynced)
        print(f"Syncing {len(unsynced)} trades...")
        mark_synced([t['id'] for t in unsynced])
    except Exception as e:
        print(f"Sync failed: {e}")

if __name__ == "__main__":
    push_to_cloud()
