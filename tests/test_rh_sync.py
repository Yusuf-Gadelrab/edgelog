import sys
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import main
from unittest.mock import patch, MagicMock

# Mock robin_stocks to prevent real login
@patch("robinhood_sync.r")
@patch("robinhood_sync.os.getenv")
def test_robinhood_sync_dedupe(mock_env, mock_r, tmp_path):
    # Mock env vars
    def side_effect(key):
        if key == "RH_USERNAME": return "dummy"
        if key == "RH_PASSWORD": return "dummy"
        return None
    mock_env.side_effect = side_effect
    
    # Setup mock orders
    mock_r.orders.get_all_stock_orders.return_value = [
        {"id": "1", "state": "filled", "last_transaction_at": "2026-06-10T10:00:00Z", 
         "side": "buy", "cumulative_quantity": "10", "average_price": "100.00", "fees": "0.01", "instrument": "https://api.robinhood.com/instruments/1/"},
        {"id": "2", "state": "filled", "last_transaction_at": "2026-06-10T11:00:00Z", 
         "side": "sell", "cumulative_quantity": "10", "average_price": "110.00", "fees": "0.01", "instrument": "https://api.robinhood.com/instruments/1/"}
    ]
    mock_r.stocks.get_symbol_by_url.return_value = "AAPL"
    
    # Init client
    main.DB_PATH = Path(tmp_path) / "test_rh.db"
    main.init_db()
    
    # Inject DB_PATH into robinhood_sync
    import robinhood_sync
    robinhood_sync.DB_PATH = main.DB_PATH
    
    c = TestClient(main.app)
    
    # 1. Sync
    robinhood_sync.sync_robinhood(interactive=False)
    
    # 2. Assert sync
    trades = c.get("/api/trades").json()
    assert len(trades) == 1
    assert trades[0]["symbol"] == "AAPL"
    assert "RH Order ID: 2" in trades[0]["notes"]
    
    # 3. Sync again (should dedupe)
    robinhood_sync.sync_robinhood(interactive=False)
    trades = c.get("/api/trades").json()
    assert len(trades) == 1

def test_stats_tolerance_stopless(tmp_path):
    main.DB_PATH = Path(tmp_path) / "test_tolerance.db"
    main.init_db()
    c = TestClient(main.app)
    
    # Import trade with 0 stop
    c.post("/api/import", files={"file": ("j.csv", "date,symbol,setup,direction,entry,stop,target,exit,shares,fees,notes\n2026-06-01,AAPL,rh-sync,long,100,0,0,110,10,0,none", "text/csv")})
    
    # Should not crash
    s = c.get("/api/stats").json()
    assert s["trades"] == 1
