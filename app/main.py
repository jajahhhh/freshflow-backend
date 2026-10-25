import hashlib
import hmac
import json
from contextlib import asynccontextmanager
from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyHeader
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import Settings
from app.database import Base, make_engine, make_session_factory
from app.importer import ImportConflict, import_inventory, import_records
from app.models import (
    ImportAttempt,
    ImportJob,
    InventorySnapshot,
    Notification,
    Prediction,
    Product,
    Recommendation,
    RecommendationRun,
    Store,
    WeatherInput,
    utc_now,
)
from app.rules import ASSUMPTIONS, RULE_VERSION
from app.schemas import ApprovalIn, PredictionIn, ProductPatch, RunIn, SnapshotIn, WeatherIn
from app.services import (
    ServiceError,
    as_dict,
    generate_run,
    inventory_summary,
    require_product,
    save_prediction,
    save_weather,
)

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    engine = make_engine(settings.database_url)
    factory = make_session_factory(engine)

    @asynccontextmanager
    async def lifespan(_app):
        Base.metadata.create_all(engine)
        yield
        engine.dispose()

    application = FastAPI(
        title="FreshFlow Backend",
        version="0.1.0",
        lifespan=lifespan,
        description=(
            "Student 2 prototype. CSV stores OPENING inventory, not live stock. "
            "Use Authorize with a local X-API-Key from .env. "
            "Mock weather/predictions are explicitly labelled. Demo date: 2026-10-12."
        ),
    )
    application.state.engine = engine
    application.state.session_factory = factory
    application.state.settings = settings
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH"],
        allow_headers=["Content-Type", "Authorization", "X-API-Key"],
    )

    @application.exception_handler(ServiceError)
    async def service_error(_request, exc):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    @application.exception_handler(IntegrityError)
    async def integrity_error(_request, _exc):
        return JSONResponse(status_code=409, content={"detail": "Database constraint conflict"})

    def get_db():
        with factory.begin() as session:
            yield session

    def role(key: str | None = Depends(api_key_header)):
        if key:
            for name, expected in [
                ("admin", settings.admin_api_key),
                ("staff", settings.staff_api_key),
                ("service", settings.service_api_key),
            ]:
                if hmac.compare_digest(key.encode(), expected.encode()):
                    return name
        raise HTTPException(401, "Missing or invalid X-API-Key")

    def roles(*allowed):
        def check(current_role: str = Depends(role)):
            if current_role not in allowed:
                raise HTTPException(403, "Role is not permitted for this operation")
            return current_role

        return check

    internal = roles("admin", "staff")
    admin = roles("admin")
    service = roles("admin", "service")

    def page(session, statement, limit, offset):
        total = session.scalar(
            select(func.count()).select_from(statement.order_by(None).subquery())
        )
        rows = session.scalars(statement.limit(limit).offset(offset)).all()
        return {
            "total": total,
            "count": len(rows),
            "limit": limit,
            "offset": offset,
            "items": [as_dict(row) for row in rows],
        }

    @application.get("/", include_in_schema=False)
    def root():
        return {"name": "FreshFlow Backend", "docs": "/docs", "demo_date": "2026-10-12"}

    @application.get("/health", tags=["Health"])
    def health():
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
        except SQLAlchemyError as exc:
            raise HTTPException(503, "Database unavailable") from exc
        return {"status": "ok", "database": "ok", "database_engine": engine.dialect.name}

    @application.post("/api/v1/inventory/imports", tags=["Inventory"])
    def upload_inventory(
        file: UploadFile = File(...), dry_run: bool = False, _role: str = Depends(admin)
    ):
        try:
            return import_inventory(
                factory, file.file.read(2_000_001), file.filename or "inventory.csv", dry_run
            )
        except ImportConflict as exc:
            raise HTTPException(409, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @application.get("/api/v1/inventory/imports", tags=["Inventory"])
    def list_imports(
        limit: int = Query(50, ge=1, le=200),
        offset: int = Query(0, ge=0),
        db: Session = Depends(get_db),
        _role: str = Depends(admin),
    ):
        return page(db, select(ImportJob).order_by(ImportJob.import_id.desc()), limit, offset)

    @application.get("/api/v1/inventory/import-attempts", tags=["Inventory"])
    def list_import_attempts(
        limit: int = Query(50, ge=1, le=200),
        offset: int = Query(0, ge=0),
        db: Session = Depends(get_db),
        _role: str = Depends(admin),
    ):
        return page(
            db, select(ImportAttempt).order_by(ImportAttempt.attempt_id.desc()), limit, offset
        )

    @application.get("/api/v1/inventory/imports/{import_id}", tags=["Inventory"])
    def get_import(import_id: int, db: Session = Depends(get_db), _role: str = Depends(admin)):
        job = db.get(ImportJob, import_id)
        if job is None:
            raise HTTPException(404, "Import not found")
        return as_dict(job)

    @application.post("/api/v1/inventory/snapshots", tags=["Inventory"])
    def manual_snapshot(payload: SnapshotIn, _role: str = Depends(admin)):
        row = {**payload.model_dump(), "snapshot_source": "MANUAL_ENTRY"}
        digest = hashlib.sha256(json.dumps(row, default=str, sort_keys=True).encode()).hexdigest()
        try:
            return import_records(factory, [row], "manual-entry", digest)
        except ImportConflict as exc:
            raise HTTPException(409, str(exc)) from exc

    @application.get("/api/v1/inventory", tags=["Inventory"])
    def get_inventory(
        snapshot_date: date = Query(alias="date"),
        store_id: str | None = None,
        product_id: str | None = None,
        max_days: int | None = Query(None, ge=0),
        in_stock_only: bool = False,
        limit: int = Query(50, ge=1, le=200),
        offset: int = Query(0, ge=0),
        db: Session = Depends(get_db),
        _role: str = Depends(internal),
    ):
        statement = select(InventorySnapshot).where(
            InventorySnapshot.snapshot_date == snapshot_date
        )
        if store_id is not None:
            statement = statement.where(InventorySnapshot.store_id == store_id)
        if product_id is not None:
            statement = statement.where(InventorySnapshot.product_id == product_id)
        if max_days is not None:
            statement = statement.where(InventorySnapshot.days_to_expiry.between(0, max_days))
        if in_stock_only:
            statement = statement.where(InventorySnapshot.opening_inventory_units > 0)
        result = page(
            db,
            statement.order_by(InventorySnapshot.store_id, InventorySnapshot.product_id),
            limit,
            offset,
        )
        ids = {row["product_id"] for row in result["items"]}
        products = (
            {
                p.product_id: p
                for p in db.scalars(select(Product).where(Product.product_id.in_(ids)))
            }
            if ids
            else {}
        )
        for row in result["items"]:
            product = products[row["product_id"]]
            row.update(
                {
                    key: as_dict(product)[key]
                    for key in ["product_name", "category", "regular_price", "barcode"]
                }
            )
        return {"date": snapshot_date.isoformat(), "stock_basis": "OPENING_INVENTORY", **result}

    @application.get("/api/v1/inventory/summary", tags=["Inventory"])
    def get_summary(
        snapshot_date: date = Query(alias="date"),
        store_id: str | None = None,
        db: Session = Depends(get_db),
        _role: str = Depends(internal),
    ):
        return inventory_summary(db, snapshot_date, store_id)

    @application.get("/api/v1/stores", tags=["Master data"])
    def get_stores(db: Session = Depends(get_db), _role: str = Depends(internal)):
        return {"items": [as_dict(s) for s in db.scalars(select(Store).order_by(Store.store_id))]}

    @application.get("/api/v1/products", tags=["Master data"])
    def get_products(
        limit: int = Query(50, ge=1, le=200),
        offset: int = Query(0, ge=0),
        db: Session = Depends(get_db),
        _role: str = Depends(internal),
    ):
        return page(db, select(Product).order_by(Product.product_id), limit, offset)

    @application.get("/api/v1/products/{product_id}", tags=["Master data"])
    def get_product(product_id: str, db: Session = Depends(get_db), _role: str = Depends(internal)):
        return as_dict(require_product(db, product_id))

    @application.patch("/api/v1/products/{product_id}", tags=["Master data"])
    def patch_product(
        product_id: str,
        payload: ProductPatch,
        db: Session = Depends(get_db),
        _role: str = Depends(admin),
    ):
        product = require_product(db, product_id)
        changes = payload.model_dump(exclude_unset=True)
        if not changes:
            raise HTTPException(422, "Provide at least one product field")
        for field, value in changes.items():
            setattr(product, field, value)
        db.flush()
        return as_dict(product)

    @application.post("/api/v1/predictions", tags=["Predictions"])
    def post_prediction(
        payload: PredictionIn, db: Session = Depends(get_db), _role: str = Depends(service)
    ):
        return as_dict(save_prediction(db, payload))

    @application.get("/api/v1/predictions", tags=["Predictions"])
    def get_predictions(
        store_id: str | None = None,
        product_id: str | None = None,
        target_date: date | None = None,
        source: str | None = None,
        limit: int = Query(50, ge=1, le=200),
        offset: int = Query(0, ge=0),
        db: Session = Depends(get_db),
        _role: str = Depends(internal),
    ):
        statement = select(Prediction)
        for field, value in [
            ("store_id", store_id),
            ("product_id", product_id),
            ("target_date", target_date),
            ("source", source),
        ]:
            if value is not None:
                statement = statement.where(getattr(Prediction, field) == value)
        return page(db, statement.order_by(Prediction.prediction_id.desc()), limit, offset)

    @application.post("/api/v1/weather/mock", tags=["Weather"])
    def post_weather(
        payload: WeatherIn, db: Session = Depends(get_db), _role: str = Depends(service)
    ):
        return as_dict(save_weather(db, payload))

    @application.get("/api/v1/weather", tags=["Weather"])
    def get_weather(
        store_id: str | None = None,
        target_date: date | None = None,
        scenario_id: str | None = None,
        limit: int = Query(50, ge=1, le=200),
        offset: int = Query(0, ge=0),
        db: Session = Depends(get_db),
        _role: str = Depends(internal),
    ):
        statement = select(WeatherInput)
        for field, value in [
            ("store_id", store_id),
            ("target_date", target_date),
            ("scenario_id", scenario_id),
        ]:
            if value is not None:
                statement = statement.where(getattr(WeatherInput, field) == value)
        return page(db, statement.order_by(WeatherInput.weather_id), limit, offset)

    @application.post("/api/v1/recommendation-runs", tags=["Recommendations"])
    def post_run(payload: RunIn, db: Session = Depends(get_db), _role: str = Depends(internal)):
        return as_dict(generate_run(db, payload))

    @application.get("/api/v1/recommendation-runs/{run_id}", tags=["Recommendations"])
    def get_run(run_id: int, db: Session = Depends(get_db), _role: str = Depends(internal)):
        run = db.get(RecommendationRun, run_id)
        if run is None:
            raise HTTPException(404, "Run not found")
        return as_dict(run)

    @application.get("/api/v1/recommendations", tags=["Recommendations"])
    def get_recommendations(
        run_id: int | None = None,
        store_id: str | None = None,
        snapshot_date: date | None = Query(None, alias="date"),
        limit: int = Query(50, ge=1, le=200),
        offset: int = Query(0, ge=0),
        db: Session = Depends(get_db),
        _role: str = Depends(internal),
    ):
        statement = select(Recommendation).join(InventorySnapshot)
        if run_id is not None:
            statement = statement.where(Recommendation.run_id == run_id)
        if store_id is not None:
            statement = statement.where(InventorySnapshot.store_id == store_id)
        if snapshot_date is not None:
            statement = statement.where(Recommendation.decision_date == snapshot_date)
        return page(db, statement.order_by(Recommendation.recommendation_id), limit, offset)

    @application.patch(
        "/api/v1/recommendations/{recommendation_id}/status", tags=["Recommendations"]
    )
    def approve(
        recommendation_id: int,
        payload: ApprovalIn,
        db: Session = Depends(get_db),
        current_role: str = Depends(admin),
    ):
        recommendation = db.get(Recommendation, recommendation_id)
        if recommendation is None:
            raise HTTPException(404, "Recommendation not found")
        if recommendation.status != "READY":
            raise HTTPException(409, "Only READY recommendations may be approved or rejected")
        if recommendation.approval_status != payload.status:
            recommendation.approval_status = payload.status
            recommendation.decided_at = utc_now()
            recommendation.decided_by_role = current_role
        return as_dict(recommendation)

    @application.get("/api/v1/dashboard/summary", tags=["Dashboard"])
    def dashboard(
        snapshot_date: date = Query(alias="date"),
        store_id: str | None = None,
        run_id: int | None = None,
        db: Session = Depends(get_db),
        _role: str = Depends(internal),
    ):
        statement = (
            select(Recommendation)
            .join(InventorySnapshot)
            .where(Recommendation.decision_date == snapshot_date)
        )
        if store_id is not None:
            statement = statement.where(InventorySnapshot.store_id == store_id)
        # Default to one latest run per store, so reruns/scenarios are not double counted.
        if run_id is not None:
            statement = statement.where(Recommendation.run_id == run_id)
        else:
            latest = (
                select(func.max(RecommendationRun.run_id))
                .where(RecommendationRun.snapshot_date == snapshot_date)
                .group_by(RecommendationRun.store_id)
            )
            statement = statement.where(Recommendation.run_id.in_(latest))
        counts, actions = {}, {}
        for rec in db.scalars(statement):
            counts[rec.status] = counts.get(rec.status, 0) + 1
            for action in rec.actions:
                name = action["action"]
                actions[name] = actions.get(name, 0) + 1
        return {
            **inventory_summary(db, snapshot_date, store_id),
            "recommendation_status_counts": counts,
            "action_counts": actions,
            "rules_version": RULE_VERSION,
            "assumptions": ASSUMPTIONS,
            "actual_waste_units": None,
        }

    @application.get("/api/v1/notifications", tags=["Notifications"])
    def notifications(
        store_id: str | None = None,
        unread_only: bool = False,
        limit: int = Query(50, ge=1, le=200),
        offset: int = Query(0, ge=0),
        db: Session = Depends(get_db),
        _role: str = Depends(internal),
    ):
        statement = select(Notification)
        if store_id is not None:
            statement = statement.where(Notification.store_id == store_id)
        if unread_only:
            statement = statement.where(Notification.read_at.is_(None))
        return {
            "inbox_scope": "SHARED_STAFF_DEMO",
            **page(db, statement.order_by(Notification.notification_id.desc()), limit, offset),
        }

    @application.patch("/api/v1/notifications/{notification_id}/read", tags=["Notifications"])
    def read_notification(
        notification_id: int, db: Session = Depends(get_db), _role: str = Depends(internal)
    ):
        notification = db.get(Notification, notification_id)
        if notification is None:
            raise HTTPException(404, "Notification not found")
        if notification.read_at is None:
            notification.read_at = utc_now()
        return as_dict(notification)

    @application.get("/api/v1/deals", tags=["Customer demo"])
    def deals(
        as_of_date: date | None = Query(None, alias="date"),
        store_id: str | None = None,
        db: Session = Depends(get_db),
    ):
        today = datetime.now(ZoneInfo("Asia/Bangkok")).date()
        day = as_of_date or today
        statement = (
            select(Recommendation, InventorySnapshot, Product)
            .join(InventorySnapshot, Recommendation.snapshot_id == InventorySnapshot.snapshot_id)
            .join(Product, InventorySnapshot.product_id == Product.product_id)
            .where(
                Recommendation.approval_status == "APPROVED",
                Recommendation.status == "READY",
                Recommendation.decision_date == day,
                InventorySnapshot.opening_inventory_units > 0,
                InventorySnapshot.days_to_expiry > 0,
                Product.product_name.is_not(None),
                Product.regular_price > 0,
            )
        )
        if store_id is not None:
            statement = statement.where(InventorySnapshot.store_id == store_id)
        latest = (
            select(func.max(RecommendationRun.run_id))
            .where(RecommendationRun.snapshot_date == day)
            .group_by(RecommendationRun.store_id)
        )
        statement = statement.where(Recommendation.run_id.in_(latest))
        items = []
        for rec, snapshot, product in db.execute(statement):
            for action in rec.actions:
                if action["action"] != "DISCOUNT":
                    continue
                percent = Decimal(str(action["discount_percent"]))
                discounted = (product.regular_price * (1 - percent / 100)).quantize(Decimal("0.01"))
                items.append(
                    {
                        "recommendation_id": rec.recommendation_id,
                        "store_id": snapshot.store_id,
                        "product_id": product.product_id,
                        "product_name": product.product_name,
                        "regular_price": float(product.regular_price),
                        "discount_percent": float(percent),
                        "recommended_price": float(discounted),
                        "inventory_date": day.isoformat(),
                        "stock_basis": "OPENING_INVENTORY",
                        "is_mock": rec.input_payload["is_mock"],
                    }
                )
        return {
            "date": day.isoformat(),
            "historical_preview": day != today,
            "prototype_only": True,
            "count": len(items),
            "items": items,
        }

    return application


app = create_app()
