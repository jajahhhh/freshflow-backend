"""Import the reference demo and verify it against the isolated Compose MySQL.

Run from the project root after starting Compose with .env.mysql.
No tables are dropped, no existing snapshots are overwritten, no keys are printed.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.cli import DEMO_DATE, SAMPLE_FILE, seed_demo
from app.config import PROJECT_ROOT, Settings
from app.database import Base, make_engine, make_session_factory
from app.importer import import_inventory
from app.main import create_app
from app.services import inventory_summary


def main():
    settings = Settings(_env_file=PROJECT_ROOT / ".env.mysql")
    engine = make_engine(settings.database_url)
    if engine.dialect.name != "mysql":
        raise SystemExit(".env.mysql must select a MySQL database")
    factory = make_session_factory(engine)
    try:
        Base.metadata.create_all(engine)
        with engine.connect() as connection:
            version = connection.scalar(text("SELECT VERSION()"))
        first = import_inventory(factory, SAMPLE_FILE.read_bytes(), SAMPLE_FILE.name)
        repeated = import_inventory(factory, SAMPLE_FILE.read_bytes(), SAMPLE_FILE.name)
        assert first["import_id"] == repeated["import_id"]
        assert repeated["status"] == "already_imported"
        seeded = seed_demo(factory, DEMO_DATE)
        with factory() as session:
            stats = inventory_summary(session, DEMO_DATE)
        expected = {"snapshot_count": 128, "store_count": 4, "product_count": 32,
                    "total_opening_units": 3103, "zero_stock_count": 2,
                    "near_expiry_in_stock_count": 70}
        assert all(stats[key] == value for key, value in expected.items()), stats
        with TestClient(create_app(settings)) as client:
            headers = {"X-API-Key": settings.admin_api_key}
            assert client.get("/health").json()["database_engine"] == "mysql"
            response = client.get("/api/v1/inventory", headers=headers,
                                  params={"date": DEMO_DATE.isoformat(), "limit": 200})
            assert response.status_code == 200 and response.json()["total"] == 128
            dashboard = client.get("/api/v1/dashboard/summary", headers=headers,
                                   params={"date": DEMO_DATE.isoformat()}).json()
            assert dashboard["recommendation_status_counts"] == {"READY": 99, "REVIEW_REQUIRED": 29}
        print(json.dumps({"database_engine": "mysql", "version": version,
                          "reference_data": stats, "idempotent_import": True,
                          "mock_runs_verified": len(seeded["runs"]),
                          "api_and_dashboard_verified": True}, ensure_ascii=False, indent=2))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
