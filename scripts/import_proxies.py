"""
Bulk import good proxies from proxy_pool into the outlook-batch-manager database.
Usage: python scripts/import_proxies.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.app.db.database import SessionLocal, init_db, engine
from backend.app.db.models import ProxyPool
from sqlalchemy import select, text

GOOD_PROXIES = Path(__file__).parent.parent.parent / "proxy_pool" / "output" / "proxies_good.txt"

def main():
    init_db()

    print(f"Reading good proxies from: {GOOD_PROXIES}")
    with open(GOOD_PROXIES, "r") as f:
        proxies = [line.strip() for line in f if line.strip()]
    print(f"Total proxies to import: {len(proxies)}")

    session = SessionLocal()
    try:
        existing = set()
        for row in session.execute(select(ProxyPool.proxy_url)).scalars():
            existing.add(row)
        print(f"Existing proxies in DB: {len(existing)}")

        new_count = 0
        batch = []
        for p in proxies:
            if p not in existing:
                batch.append(ProxyPool(proxy_url=p, is_enabled=True))
                new_count += 1

        if batch:
            session.add_all(batch)
            session.commit()
            print(f"Imported: {new_count} new proxies")
        else:
            print("No new proxies to import (all already exist)")

        total = session.execute(select(text("COUNT(*) FROM proxy_pool"))).scalar()
        enabled = session.execute(
            select(text("COUNT(*) FROM proxy_pool WHERE is_enabled = 1"))
        ).scalar()
        print(f"Total in DB: {total} (enabled: {enabled})")
    finally:
        session.close()


if __name__ == "__main__":
    main()
