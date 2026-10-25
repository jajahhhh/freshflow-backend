import csv
import hashlib
import io
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models import ImportAttempt, ImportJob, InventorySnapshot, Product, Store

MAX_FILE_BYTES = 2_000_000
CSV_COLUMNS = [
    "Date",
    "Store_ID",
    "Product_ID",
    "Opening_Inventory_Units",
    "Days_To_Expiry",
    "Standard_Shelf_Life_Days",
    "Delivery_Lead_Time_Days",
    "Snapshot_Source",
]
NUMERIC_COLUMNS = {
    "Opening_Inventory_Units": ("opening_inventory_units", 0),
    "Days_To_Expiry": ("days_to_expiry", -2147483648),
    "Standard_Shelf_Life_Days": ("standard_shelf_life_days", 1),
    "Delivery_Lead_Time_Days": ("delivery_lead_time_days", 0),
}


class ImportConflict(ValueError):
    pass


def parse_csv(content: bytes) -> tuple[list[dict], list[dict]]:
    if len(content) > MAX_FILE_BYTES:
        raise ValueError("File exceeds 2 MB")
    try:
        reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig"), newline=""), strict=True)
    except UnicodeDecodeError as exc:
        raise ValueError("CSV must use UTF-8 encoding") from exc
    try:
        if (
            not reader.fieldnames
            or len(reader.fieldnames) != 8
            or set(reader.fieldnames) != set(CSV_COLUMNS)
        ):
            raise ValueError("CSV columns must match: " + ", ".join(CSV_COLUMNS))
    except csv.Error as exc:
        raise ValueError("Malformed CSV header") from exc
    records, warnings, seen = [], [], set()
    try:
        for raw in reader:
            line = reader.line_num
            if None in raw or any(raw[name] is None for name in CSV_COLUMNS):
                raise ValueError(f"Row {line}: incorrect number of columns")
            raw = {key: value.strip() for key, value in raw.items()}
            if any(not raw[name] for name in CSV_COLUMNS):
                raise ValueError(f"Row {line}: missing required value")
            try:
                day = date.fromisoformat(raw["Date"])
                if day.isoformat() != raw["Date"]:
                    raise ValueError()
            except ValueError as exc:
                raise ValueError(f"Row {line}: Date must be YYYY-MM-DD") from exc
            row = {
                "snapshot_date": day,
                "store_id": raw["Store_ID"],
                "product_id": raw["Product_ID"],
                "snapshot_source": raw["Snapshot_Source"],
            }
            for column, limit in [("Store_ID", 40), ("Product_ID", 40), ("Snapshot_Source", 100)]:
                if len(raw[column]) > limit:
                    raise ValueError(f"Row {line}: {column} exceeds {limit} characters")
            for column, (field, minimum) in NUMERIC_COLUMNS.items():
                try:
                    value = Decimal(raw[column])
                except InvalidOperation as exc:
                    raise ValueError(f"Row {line}: {column} must be numeric") from exc
                if not value.is_finite() or value != value.to_integral_value():
                    raise ValueError(f"Row {line}: {column} must be a finite whole number")
                if not minimum <= value <= 2147483647:
                    raise ValueError(f"Row {line}: {column} is out of range")
                row[field] = int(value)
            if row["delivery_lead_time_days"] > 365:
                raise ValueError(f"Row {line}: lead time exceeds the supported 365-day horizon")
            key = (day, row["store_id"], row["product_id"])
            if key in seen:
                raise ValueError(f"Row {line}: duplicate Date + Store_ID + Product_ID")
            seen.add(key)
            if row["days_to_expiry"] > row["standard_shelf_life_days"]:
                warnings.append({"row": line, "code": "EXPIRY_EXCEEDS_STANDARD_SHELF_LIFE"})
            records.append(row)
    except csv.Error as exc:
        raise ValueError(f"Malformed CSV near line {reader.line_num}") from exc
    if not records:
        raise ValueError("CSV has no data rows")
    return records, warnings


def _attempt(factory, filename, checksum, status, error=None):
    with factory.begin() as session:
        session.add(
            ImportAttempt(file_name=filename, checksum=checksum, status=status, error=error)
        )


def import_records(factory, records, filename, checksum, warnings=None, dry_run=False):
    report = {
        "total_rows": len(records),
        "stores": len({r["store_id"] for r in records}),
        "products": len({r["product_id"] for r in records}),
        "warnings": warnings or [],
    }
    if dry_run:
        return {"status": "validated", **report}
    with factory.begin() as session:
        previous = session.scalar(select(ImportJob).where(ImportJob.checksum == checksum))
        if previous:
            return {
                "status": "already_imported",
                "import_id": previous.import_id,
                "inserted_rows": 0,
                "unchanged_rows": previous.total_rows,
                **report,
            }
        job = ImportJob(file_name=filename, checksum=checksum, total_rows=len(records))
        session.add(job)
        session.flush()
        for row in records:
            existing = session.scalar(
                select(InventorySnapshot).where(
                    InventorySnapshot.snapshot_date == row["snapshot_date"],
                    InventorySnapshot.store_id == row["store_id"],
                    InventorySnapshot.product_id == row["product_id"],
                )
            )
            if existing:
                if any(getattr(existing, key) != value for key, value in row.items()):
                    raise ImportConflict(
                        f"Snapshot conflict: {row['snapshot_date']} / {row['store_id']} / {row['product_id']}"
                    )
                job.unchanged_rows += 1
                continue
            if session.get(Store, row["store_id"]) is None:
                session.add(Store(store_id=row["store_id"]))
            if session.get(Product, row["product_id"]) is None:
                session.add(Product(product_id=row["product_id"]))
            session.flush()
            session.add(InventorySnapshot(**row, import_id=job.import_id))
            job.inserted_rows += 1
        session.flush()
        result = {
            "status": "imported",
            "import_id": job.import_id,
            "inserted_rows": job.inserted_rows,
            "unchanged_rows": job.unchanged_rows,
            **report,
        }
    return result


def import_inventory(factory, content: bytes, filename: str, dry_run: bool = False) -> dict:
    filename = Path(filename).name[:255] or "inventory.csv"
    checksum = hashlib.sha256(content).hexdigest()
    try:
        records, warnings = parse_csv(content)
        result = import_records(factory, records, filename, checksum, warnings, dry_run)
    except (ValueError, IntegrityError) as exc:
        _attempt(
            factory,
            filename,
            checksum,
            "FAILED",
            str(exc)[:2000] if isinstance(exc, ValueError) else "Concurrent import conflict",
        )
        if isinstance(exc, IntegrityError):
            raise ImportConflict(
                "Concurrent import conflict; retry after inspecting prior imports"
            ) from exc
        raise
    _attempt(factory, filename, checksum, "DRY_RUN" if dry_run else "SUCCESS")
    return result
