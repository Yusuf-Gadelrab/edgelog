import time
from pathlib import Path
from fastapi.testclient import TestClient
import main
import pytest

def test_stats_performance():
    main.DB_PATH = Path("/tmp/perf_test.db")
    if main.DB_PATH.exists(): main.DB_PATH.unlink()
    main.init_db()
    c = TestClient(main.app)
    
    # Import 1000 trades
    data = "date,symbol,setup,direction,entry,stop,target,exit,shares,fees,notes\n" + \
           "\n".join([f"2026-06-0{i%9+1},AAPL,test,long,100,90,110,105,10,0,test" for i in range(1000)])
    c.post("/api/import", files={"file": ("j.csv", data, "text/csv")})
    
    start = time.time()
    c.get("/api/stats")
    elapsed = time.time() - start
    assert elapsed < 0.5  # Stats should be fast

