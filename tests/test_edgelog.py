import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import main  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

CSV = """date,symbol,setup,direction,entry,stop,target,exit,shares,fees,notes
2026-06-01,SOXL,ORB,long,28.50,27.90,30.00,29.70,100,0,clean breakout
2026-06-02,SOXL,ORB,long,30.00,29.50,31.50,29.50,100,2,stopped flat
2026-06-03,NVDA,VCP,long,120.00,118.00,126.00,125.00,10,0,worked
2026-06-04,TSLA,fade,short,250.00,255.00,240.00,253.00,10,1,squeezed out
2026-06-05,QQQ,fade,short,450.00,452.00,444.00,446.00,20,0,faded the gap
"""


def fresh_client(tmp_path) -> TestClient:
    main.DB_PATH = Path(tmp_path) / "t.db"
    main.init_db()
    return TestClient(main.app)


def test_r_math():
    assert main.r_multiple("long", 28.50, 27.90, 29.70) == 2.0
    assert main.r_multiple("long", 30.00, 29.50, 29.50) == -1.0
    assert main.r_multiple("short", 250.0, 255.0, 240.0) == 2.0
    assert main.r_multiple("short", 250.0, 255.0, 253.0) == -0.6
    with pytest.raises(ValueError):
        main.r_multiple("long", 10.0, 11.0, 12.0)  # stop above entry on a long
    assert main.dollars("long", 28.50, 29.70, 100, 0) == 120.0
    assert main.dollars("short", 250.0, 253.0, 10, 1) == -31.0


def test_import_and_stats(tmp_path):
    c = fresh_client(tmp_path)
    r = c.post("/api/import", files={"file": ("journal.csv", CSV, "text/csv")})
    assert r.status_code == 201
    assert r.json() == {"imported": 5, "skipped": []}

    s = c.get("/api/stats").json()
    assert s["trades"] == 5
    # rs: +2, -1, +2.5, -0.6, +2 → expectancy 0.98
    assert s["expectancy_r"] == pytest.approx(0.98)
    assert s["win_rate"] == 60.0
    assert s["max_drawdown_r"] == 1.0
    assert s["equity_curve"][-1]["cum_r"] == pytest.approx(4.9)
    assert s["net_pnl"] == pytest.approx(120 - 52 + 50 - 31 + 80)

    setups = {x["setup"]: x for x in s["setups"]}
    assert setups["VCP"]["expectancy"] == 2.5
    assert setups["fade"]["trades"] == 2
    assert s["setups"][0]["setup"] == "VCP"  # sorted by expectancy

    assert "20 trades" in s["verdict"]  # small-sample warning at n=5


def test_import_validates(tmp_path):
    c = fresh_client(tmp_path)
    bad = CSV.replace("date,symbol", "when,symbol")
    assert c.post("/api/import", files={"file": ("x.csv", bad, "text/csv")}).status_code == 422

    mixed = CSV + "2026-06-06,AMD,ORB,long,100,101,110,105,10,0,stop on wrong side\n"
    r = c.post("/api/import", files={"file": ("x.csv", mixed, "text/csv")})
    j = r.json()
    assert j["imported"] == 5 and len(j["skipped"]) == 1 and j["skipped"][0]["line"] == 7


def test_reset_and_dashboard(tmp_path):
    c = fresh_client(tmp_path)
    c.post("/api/import", files={"file": ("j.csv", CSV, "text/csv")})
    assert c.delete("/api/trades").json() == {"ok": True}
    assert c.get("/api/stats").json() == {"trades": 0}
    assert c.get("/").status_code == 200

def test_daily_aggregation(tmp_path):
    c = fresh_client(tmp_path)
    csv2 = "date,symbol,setup,direction,entry,stop,target,exit,shares,fees,notes\n" \
           "2026-06-01,SOXL,ORB,long,28.50,27.90,30.00,29.70,100,0,trade1\n" \
           "2026-06-01,SOXS,fade,short,10.00,10.50,9.00,9.50,100,0,trade2\n"
    c.post("/api/import", files={"file": ("j.csv", csv2, "text/csv")})
    s = c.get("/api/stats").json()
    assert len(s["daily"]) == 1
    assert s["daily"][0]["date"] == "2026-06-01"
    assert s["daily"][0]["trades"] == 2
    assert s["daily"][0]["r"] == 3.0

def test_export_round_trip(tmp_path):
    c = fresh_client(tmp_path)
    c.post("/api/import", files={"file": ("journal.csv", CSV, "text/csv")})
    s1 = c.get("/api/stats").json()
    
    export_resp = c.get("/api/export.csv")
    assert export_resp.status_code == 200
    
    # new client & db
    main.DB_PATH = Path(tmp_path) / "t2.db"
    main.init_db()
    c2 = TestClient(main.app)
    c2.post("/api/import", files={"file": ("exported.csv", export_resp.text, "text/csv")})
    s2 = c2.get("/api/stats").json()
    assert s1 == s2
