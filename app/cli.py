"""Local database setup and explicitly labelled mock integration fixtures."""

import argparse
import json
from datetime import date, timedelta
from pathlib import Path

from sqlalchemy import select

from app.config import PROJECT_ROOT, Settings
from app.database import Base, make_engine, make_session_factory
from app.importer import import_inventory
from app.models import InventorySnapshot
from app.schemas import PredictionIn, RunIn, WeatherIn
from app.services import as_dict, generate_run, inventory_summary, save_prediction, save_weather

SAMPLE_FILE = PROJECT_ROOT / "data" / "inventory_mock_2026-10-12.csv"
DEMO_DATE = date(2026, 10, 12)


def seed_demo(factory, day):
    with factory() as session:
        snapshots = session.scalars(
            select(InventorySnapshot)
            .where(InventorySnapshot.snapshot_date == day)
            .order_by(InventorySnapshot.store_id, InventorySnapshot.product_id)
        ).all()
    if not snapshots:
        if day != DEMO_DATE:
            raise ValueError("Import inventory for the chosen date before seeding mock data")
        import_inventory(factory, SAMPLE_FILE.read_bytes(), SAMPLE_FILE.name)
        with factory() as session:
            snapshots = session.scalars(
                select(InventorySnapshot)
                .where(InventorySnapshot.snapshot_date == day)
                .order_by(InventorySnapshot.store_id, InventorySnapshot.product_id)
            ).all()
    with factory.begin() as session:
        stores = sorted({s.store_id for s in snapshots})
        horizon = max(
            max(s.delivery_lead_time_days + 1, s.days_to_expiry if 0 < s.days_to_expiry <= 2 else 0)
            for s in snapshots
        )
        for snapshot in snapshots:
            # Deliberately artificial test inputs, unrelated to stock or actual sales.
            for offset in range(horizon):
                target = day + timedelta(days=offset)
                save_prediction(
                    session,
                    PredictionIn(
                        request_id=f"demo-{snapshot.store_id}-{snapshot.product_id}-{target}-v1",
                        store_id=snapshot.store_id,
                        product_id=snapshot.product_id,
                        target_date=target,
                        predicted_units=3,
                        model_version="mock_v1",
                        source="MOCK",
                    ),
                )
        for store_id in stores:
            for scenario_id, condition in [("clear-demo", "Clear"), ("rain-demo", "Rain")]:
                for offset in range(horizon):
                    target = day + timedelta(days=offset)
                    save_weather(
                        session,
                        WeatherIn(
                            request_id=f"demo-{scenario_id}-{store_id}-{target}-v1",
                            scenario_id=scenario_id,
                            store_id=store_id,
                            target_date=target,
                            condition=condition,
                            temperature_c=29,
                            rain_mm_1h=2 if condition == "Rain" else 0,
                        ),
                    )
        runs = []
        for store_id in stores:
            for scenario_id in ["clear-demo", "rain-demo"]:
                run = generate_run(
                    session,
                    RunIn(
                        request_id=f"demo-{store_id}-{day}-{scenario_id}-rules-v1",
                        snapshot_date=day,
                        store_id=store_id,
                        scenario_id=scenario_id,
                    ),
                )
                runs.append(as_dict(run))
    return {
        "source": "MOCK",
        "date": day.isoformat(),
        "forecast_horizon_days": horizon,
        "mock_units_per_day": 3,
        "runs": runs,
        "note": "Synthetic test inputs only; no ML training, no external weather, no price changes.",
    }


def main():
    parser = argparse.ArgumentParser(description="FreshFlow local development commands")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init-db")
    importer = commands.add_parser("import-csv")
    importer.add_argument("file", type=Path)
    importer.add_argument("--dry-run", action="store_true")
    seed = commands.add_parser("seed-demo")
    seed.add_argument("--date", type=date.fromisoformat, default=DEMO_DATE)
    verify = commands.add_parser("verify-data")
    verify.add_argument("--date", type=date.fromisoformat, default=DEMO_DATE)
    args = parser.parse_args()
    settings = Settings()
    engine = make_engine(settings.database_url)
    factory = make_session_factory(engine)
    try:
        Base.metadata.create_all(engine)
        if args.command == "init-db":
            result = {
                "status": "ready",
                "database_engine": engine.dialect.name,
                "tables": sorted(Base.metadata.tables),
            }
        elif args.command == "import-csv":
            result = import_inventory(factory, args.file.read_bytes(), args.file.name, args.dry_run)
        elif args.command == "seed-demo":
            result = seed_demo(factory, args.date)
        else:
            with factory() as session:
                result = inventory_summary(session, args.date)
            expected = {
                "snapshot_count": 128,
                "store_count": 4,
                "product_count": 32,
                "total_opening_units": 3103,
                "zero_stock_count": 2,
                "near_expiry_in_stock_count": 70,
            }
            result["matches_reference_csv"] = all(result[k] == v for k, v in expected.items())
            if not result["matches_reference_csv"]:
                print(json.dumps(result, ensure_ascii=False, indent=2))
                raise SystemExit(1)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
