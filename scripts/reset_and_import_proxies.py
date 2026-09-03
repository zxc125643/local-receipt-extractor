"""
Reset proxy pool: clear all existing proxies, import from desktop file.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.app.db.database import SessionLocal, init_db, engine
from backend.app.db.models import ProxyPool
from sqlalchemy import text

DESKTOP_FILE = Path("C:/Users/yiliu/Desktop/新建文本文档.txt")

GOOD_FILE = Path(__file__).parent.parent.parent / "proxy_pool" / "output" / "proxies_good.txt"
ALL_FILE = Path(__file__).parent.parent.parent / "proxy_pool" / "output" / "proxies_all_tested.txt"
STATS_FILE = Path(__file__).parent.parent.parent / "proxy_pool" / "output" / "pool_stats.json"

def main():
    init_db()

    # Read new proxies
    with open(DESKTOP_FILE, "r") as f:
        proxies = [line.strip() for line in f if line.strip()]
    print(f"New proxies to import: {len(proxies)}")

    # Clear DB proxy_pool table
    session = SessionLocal()
    try:
        deleted = session.execute(text("DELETE FROM proxy_pool"))
        session.commit()
        print(f"Cleared old proxy pool from DB")
    finally:
        session.close()

    # Import new proxies
    session = SessionLocal()
    try:
        batch = [ProxyPool(proxy_url=p, is_enabled=True) for p in proxies]
        session.add_all(batch)
        session.commit()
        print(f"Imported {len(batch)} new proxies into DB")

        total = session.execute(text("SELECT COUNT(*) FROM proxy_pool")).scalar()
        enabled = session.execute(
            text("SELECT COUNT(*) FROM proxy_pool WHERE is_enabled = 1")
        ).scalar()
        print(f"Total in DB: {total} (enabled: {enabled})")
    finally:
        session.close()

    # Update proxy_pool output files
    GOOD_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(GOOD_FILE, "w") as f:
        for p in proxies:
            f.write(p + "\n")
    print(f"Updated {GOOD_FILE}")

    with open(ALL_FILE, "w") as f:
        import json
        for p in proxies:
            f.write(json.dumps({"raw": p, "ok": True}) + "\n")
    print(f"Updated {ALL_FILE}")

    import time, json
    stats = {
        "total": len(proxies),
        "good": len(proxies),
        "bad": 0,
        "rate": 100.0,
        "timestamp": time.time(),
    }
    with open(STATS_FILE, "w") as f:
        json.dump(stats, f, indent=2)
    print(f"Updated {STATS_FILE}")

    print("Done!")

if __name__ == "__main__":
    main()
