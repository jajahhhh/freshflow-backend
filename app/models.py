from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def utc_now() -> datetime:
    from datetime import timezone

    return datetime.now(timezone.utc).replace(tzinfo=None)


class Store(Base):
    __tablename__ = "stores"
    store_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    store_name: Mapped[str | None] = mapped_column(String(150))
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    timezone: Mapped[str] = mapped_column(String(60), default="Asia/Bangkok")


class Product(Base):
    __tablename__ = "products"
    product_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    product_name: Mapped[str | None] = mapped_column(String(200))
    category: Mapped[str | None] = mapped_column(String(100))
    regular_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    barcode: Mapped[str | None] = mapped_column(String(64), unique=True)
    __table_args__ = (CheckConstraint("regular_price >= 0", name="ck_product_price"),)


class ImportJob(Base):
    __tablename__ = "import_jobs"
    import_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    file_name: Mapped[str] = mapped_column(String(255))
    checksum: Mapped[str] = mapped_column(String(64), unique=True)
    total_rows: Mapped[int]
    inserted_rows: Mapped[int] = mapped_column(default=0)
    unchanged_rows: Mapped[int] = mapped_column(default=0)
    status: Mapped[str] = mapped_column(String(30), default="COMPLETED")
    imported_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class ImportAttempt(Base):
    __tablename__ = "import_attempts"
    attempt_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    file_name: Mapped[str] = mapped_column(String(255))
    checksum: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(30))
    error: Mapped[str | None] = mapped_column(String(2000))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class InventorySnapshot(Base):
    __tablename__ = "inventory_snapshots"
    snapshot_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    snapshot_date: Mapped[date]
    store_id: Mapped[str] = mapped_column(ForeignKey("stores.store_id"))
    product_id: Mapped[str] = mapped_column(ForeignKey("products.product_id"))
    opening_inventory_units: Mapped[int]
    days_to_expiry: Mapped[int]
    standard_shelf_life_days: Mapped[int]
    delivery_lead_time_days: Mapped[int]
    snapshot_source: Mapped[str] = mapped_column(String(100))
    import_id: Mapped[int] = mapped_column(ForeignKey("import_jobs.import_id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    __table_args__ = (
        UniqueConstraint("snapshot_date", "store_id", "product_id", name="uq_snapshot"),
        CheckConstraint("opening_inventory_units >= 0", name="ck_stock"),
        CheckConstraint("standard_shelf_life_days > 0", name="ck_shelf"),
        CheckConstraint("delivery_lead_time_days >= 0", name="ck_lead"),
        Index("ix_expiring", "snapshot_date", "store_id", "days_to_expiry"),
    )


class Prediction(Base):
    __tablename__ = "demand_predictions"
    prediction_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    request_id: Mapped[str] = mapped_column(String(100), unique=True)
    store_id: Mapped[str] = mapped_column(ForeignKey("stores.store_id"))
    product_id: Mapped[str] = mapped_column(ForeignKey("products.product_id"))
    target_date: Mapped[date]
    predicted_units: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    prediction_kind: Mapped[str] = mapped_column(String(50))
    model_version: Mapped[str] = mapped_column(String(100))
    source: Mapped[str] = mapped_column(String(30))
    contains_weather_effect: Mapped[bool] = mapped_column(Boolean, default=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    input_cutoff_at: Mapped[datetime | None] = mapped_column(DateTime)
    request_payload: Mapped[dict] = mapped_column(JSON)
    __table_args__ = (
        CheckConstraint("predicted_units >= 0", name="ck_prediction"),
        Index("ix_forecast", "store_id", "product_id", "target_date", "source"),
    )


class WeatherInput(Base):
    __tablename__ = "weather_inputs"
    weather_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    request_id: Mapped[str] = mapped_column(String(100), unique=True)
    scenario_id: Mapped[str] = mapped_column(String(100))
    store_id: Mapped[str] = mapped_column(ForeignKey("stores.store_id"))
    target_date: Mapped[date]
    condition: Mapped[str] = mapped_column(String(30))
    temperature_c: Mapped[Decimal | None] = mapped_column(Numeric(7, 3))
    rain_mm_1h: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    source: Mapped[str] = mapped_column(String(30), default="MOCK")
    is_mock: Mapped[bool] = mapped_column(Boolean, default=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    raw_payload: Mapped[dict] = mapped_column(JSON)
    __table_args__ = (
        UniqueConstraint("scenario_id", "store_id", "target_date", name="uq_weather_scenario"),
    )


class RecommendationRun(Base):
    __tablename__ = "recommendation_runs"
    run_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    request_id: Mapped[str] = mapped_column(String(100), unique=True)
    snapshot_date: Mapped[date]
    store_id: Mapped[str] = mapped_column(ForeignKey("stores.store_id"))
    scenario_id: Mapped[str] = mapped_column(String(100))
    rule_version: Mapped[str] = mapped_column(String(100))
    prediction_source: Mapped[str] = mapped_column(String(30))
    total_items: Mapped[int] = mapped_column(default=0)
    ready_count: Mapped[int] = mapped_column(default=0)
    not_ready_count: Mapped[int] = mapped_column(default=0)
    review_count: Mapped[int] = mapped_column(default=0)
    status: Mapped[str] = mapped_column(String(30), default="COMPLETED")
    request_payload: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class Recommendation(Base):
    __tablename__ = "recommendations"
    recommendation_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("recommendation_runs.run_id"))
    snapshot_id: Mapped[int] = mapped_column(ForeignKey("inventory_snapshots.snapshot_id"))
    status: Mapped[str] = mapped_column(String(30))
    approval_status: Mapped[str] = mapped_column(String(30), default="PROPOSED")
    reason_code: Mapped[str | None] = mapped_column(String(100))
    actions: Mapped[list] = mapped_column(JSON)
    input_payload: Mapped[dict] = mapped_column(JSON)
    result_payload: Mapped[dict] = mapped_column(JSON)
    decision_date: Mapped[date]
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime)
    decided_by_role: Mapped[str | None] = mapped_column(String(30))
    __table_args__ = (UniqueConstraint("run_id", "snapshot_id", name="uq_run_snapshot"),)


class Notification(Base):
    __tablename__ = "notifications"
    notification_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    recommendation_id: Mapped[int] = mapped_column(
        ForeignKey("recommendations.recommendation_id"), unique=True
    )
    store_id: Mapped[str] = mapped_column(ForeignKey("stores.store_id"))
    message: Mapped[str] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    read_at: Mapped[datetime | None] = mapped_column(DateTime)
