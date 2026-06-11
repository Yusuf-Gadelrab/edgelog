import sys
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import main

TEST_CSV = """date,symbol,setup,direction,entry,stop,target,exit,shares,fees,notes
2026-06-01,SOXL,ORB,long,28.00,27.00,30.00,29.00,100,0,1
2026-06-01,SOXL,ORB,long,28.00,27.00,30.00,29.00,100,0,2
2026-06-01,SOXL,ORB,long,28.00,27.00,30.00,29.00,100,0,3 (3rd trade)
2026-06-02,NVDA,VCP,long,120.00,110.00,130.00,125.00,10,0,4
2026-06-02,NVDA,VCP,long,120.00,120.00,130.00,125.00,10,0,5 (no stop)
2026-06-03,TSLA,fade,short,250.00,260.00,240.00,245.00,500,0,6 (huge risk)
2026-06-04,AMD,bad,long,100.00,90.00,110.00,105.00,100,0,7 (bad setup)
2026-06-05,QQQ,fade,short,450.00,460.00,440.00,445.00,20,0,8
"""

def fresh_client(tmp_path) -> TestClient:
    main.DB_PATH = Path(tmp_path) / "test_rules.db"
    if main.DB_PATH.exists():
        main.DB_PATH.unlink()
    main.init_db()
    return TestClient(main.app)

def test_rules_engine_and_discipline(tmp_path):
    c = fresh_client(tmp_path)
    res = c.post("/api/import", files={"file": ("j.csv", TEST_CSV, "text/csv")})
    print(f"Import result: {res.json()}")
    
    trades = c.get("/api/trades").json()
    print(f"Total trades imported: {len(trades)}")
    
    # 1. Setup Rules
    c.post("/api/rules", json={"name": "Max Risk", "kind": "max_risk", "param": 1000}) # huge risk trade is $5000 * 500 = too big
    c.post("/api/rules", json={"name": "Max Daily", "kind": "max_per_day", "param": 2})
    c.post("/api/rules", json={"name": "Whitelist", "kind": "setup_whitelist", "setups": "ORB,VCP,fade"})
    c.post("/api/rules", json={"name": "Stop Req", "kind": "stop_required"})

    # 2. Assert stats have discipline
    s = c.get("/api/stats").json()
    assert "discipline" in s
    
    # 3. Verify counts
    # ORB trade 3 is 3rd on June 1st (max_per_day break)
    # NVDA trade 5 has no stop (stop_required break)
    # TSLA trade 6 has risk $10 * 500 = $5000 > $1000 (max_risk break)
    # AMD trade 7 has 'bad' setup (setup_whitelist break)
    
    print(f"Breaks: {s.get('discipline', {}).get('broken_trades')}")
    d = s["discipline"]
    # Total trades: 8. Broken: trade 3, 5, 6, 7. Clean: trade 1, 2, 4, 8.
    assert d["clean_trades"] == 4
    assert d["broken_trades"] == 4
    assert d["adherence_pct"] == 50.0
    
    # 4. Toggle rule off
    # Disable "Stop Req"
    rules = c.get("/api/rules").json()
    stop_rule = [r for r in rules if r["name"] == "Stop Req"][0]
    c.patch(f"/api/rules/{stop_rule['id']}", json={"active": 0})
    
    s = c.get("/api/stats").json()
    assert s["discipline"]["broken_trades"] == 3 # trade 5 no longer broken
    
    # 5. CRUD roundtrip
    assert len(c.get("/api/rules").json()) == 4
    c.delete(f"/api/rules/{stop_rule['id']}")
    assert len(c.get("/api/rules").json()) == 3
