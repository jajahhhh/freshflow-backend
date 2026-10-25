from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.models import (
    InventorySnapshot,
    Notification,
    Prediction,
    Product,
    Recommendation,
    RecommendationRun,
    Store,
    WeatherInput,
)
from app.rules import ASSUMPTIONS, NEAR_EXPIRY_DAYS, evaluate_snapshot, weather_factor
from app.schemas import PredictionIn, RunIn, WeatherIn, utc_naive


class ServiceError(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail


def as_dict(record):
    result = {}
    for column in record.__table__.columns:
        name = column.name
        if name in {"request_payload", "raw_payload"}:
            continue
        value = getattr(record, name)
        if isinstance(value, Decimal):
            value = float(value)
        elif isinstance(value, datetime):
            value = value.replace(tzinfo=timezone.utc).isoformat()
        elif isinstance(value, date):
            value = value.isoformat()
        result[name] = value
    return result


def require_store(session, store_id):
    store = session.get(Store, store_id)
    if store is None:
        raise ServiceError(404, "Store not found")
    return store


def require_product(session, product_id):
    product = session.get(Product, product_id)
    if product is None:
        raise ServiceError(404, "Product not found")
    return product


def _existing_request(session, model, payload):
    existing = session.scalar(select(model).where(model.request_id == payload.request_id))
    if existing is not None:
        stored = existing.raw_payload if model is WeatherInput else existing.request_payload
        if stored != payload.model_dump(mode="json"):
            raise ServiceError(409, "request_id already exists with different input")
    return existing


def save_prediction(session: Session, payload: PredictionIn):
    existing = _existing_request(session, Prediction, payload)
    if existing is not None:
        return existing
    store = require_store(session, payload.store_id)
    require_product(session, payload.product_id)
    if payload.input_cutoff_at is not None:
        start_of_day = datetime.combine(
            payload.target_date, datetime.min.time(), tzinfo=ZoneInfo(store.timezone)
        )
        if payload.input_cutoff_at >= start_of_day:
            raise ServiceError(422, "input_cutoff_at must precede the target business day")
    values = payload.model_dump()
    values["input_cutoff_at"] = utc_naive(payload.input_cutoff_at)
    record = Prediction(**values, request_payload=payload.model_dump(mode="json"))
    session.add(record)
    session.flush()
    return record


def save_weather(session: Session, payload: WeatherIn):
    existing = _existing_request(session, WeatherInput, payload)
    if existing is not None:
        return existing
    require_store(session, payload.store_id)
    duplicate = session.scalar(
        select(WeatherInput).where(
            WeatherInput.scenario_id == payload.scenario_id,
            WeatherInput.store_id == payload.store_id,
            WeatherInput.target_date == payload.target_date,
        )
    )
    if duplicate is not None:
        raise ServiceError(409, "Scenario/store/date already exists; use a new scenario_id")
    record = WeatherInput(
        **payload.model_dump(),
        source="MOCK",
        is_mock=True,
        raw_payload=payload.model_dump(mode="json"),
    )
    session.add(record)
    session.flush()
    return record


def inventory_summary(session, day, store_id=None):
    conditions = [InventorySnapshot.snapshot_date == day]
    if store_id is not None:
        conditions.append(InventorySnapshot.store_id == store_id)
    near = InventorySnapshot.days_to_expiry.between(0, NEAR_EXPIRY_DAYS) & (
        InventorySnapshot.opening_inventory_units > 0
    )
    row = (
        session.execute(
            select(
                func.count().label("snapshot_count"),
                func.count(func.distinct(InventorySnapshot.store_id)).label("store_count"),
                func.count(func.distinct(InventorySnapshot.product_id)).label("product_count"),
                func.coalesce(func.sum(InventorySnapshot.opening_inventory_units), 0).label(
                    "total_opening_units"
                ),
                func.coalesce(
                    func.sum(case((InventorySnapshot.opening_inventory_units == 0, 1), else_=0)), 0
                ).label("zero_stock_count"),
                func.coalesce(func.sum(case((near, 1), else_=0)), 0).label(
                    "near_expiry_in_stock_count"
                ),
            ).where(*conditions)
        )
        .mappings()
        .one()
    )
    return {
        "date": day.isoformat(),
        "store_id": store_id,
        "stock_basis": "OPENING_INVENTORY",
        **{key: int(value) for key, value in row.items()},
    }


def generate_run(session: Session, payload: RunIn):
    existing = _existing_request(session, RecommendationRun, payload)
    if existing is not None:
        return existing
    require_store(session, payload.store_id)
    store = session.get(Store, payload.store_id)
    run_opening_utc = (
        datetime.combine(
            payload.snapshot_date, datetime.min.time(), tzinfo=ZoneInfo(store.timezone)
        )
        .astimezone(timezone.utc)
        .replace(tzinfo=None)
    )
    snapshots = session.scalars(
        select(InventorySnapshot)
        .where(
            InventorySnapshot.snapshot_date == payload.snapshot_date,
            InventorySnapshot.store_id == payload.store_id,
        )
        .order_by(InventorySnapshot.product_id)
    ).all()
    if not snapshots:
        raise ServiceError(404, "No inventory snapshots for this store and date")
    run = RecommendationRun(**payload.model_dump(), request_payload=payload.model_dump(mode="json"))
    session.add(run)
    session.flush()
    for snapshot in snapshots:
        snapshot_input = as_dict(snapshot)
        input_payload = {
            "snapshot": snapshot_input,
            "assumptions": ASSUMPTIONS,
            "rule_version": payload.rule_version,
            "is_mock": payload.prediction_source == "MOCK"
            or "MOCK" in snapshot.snapshot_source.upper(),
            "prediction_ids": [],
            "weather_ids": [],
            "forecast_dates": [],
            "baseline_forecast": [],
            "weather_factors": [],
            "adjusted_forecast": [],
            "weather_evidence": [],
            "run_opening_utc": run_opening_utc.isoformat() + "+00:00",
        }
        if snapshot.days_to_expiry <= 0:
            outcome = evaluate_snapshot(snapshot_input, [])
        else:
            horizon = snapshot.delivery_lead_time_days + 1
            if snapshot.days_to_expiry <= NEAR_EXPIRY_DAYS:
                horizon = max(horizon, snapshot.days_to_expiry)
            missing, model_versions = [], set()
            for offset in range(horizon):
                target = payload.snapshot_date + timedelta(days=offset)
                prediction_statement = select(Prediction).where(
                    Prediction.store_id == payload.store_id,
                    Prediction.product_id == snapshot.product_id,
                    Prediction.target_date == target,
                    Prediction.source == payload.prediction_source,
                    Prediction.contains_weather_effect.is_(False),
                )
                if payload.prediction_source == "ML_MODEL":
                    prediction_statement = prediction_statement.where(
                        Prediction.input_cutoff_at.is_not(None),
                        Prediction.input_cutoff_at < run_opening_utc,
                    )
                prediction = session.scalar(
                    prediction_statement.order_by(
                        Prediction.generated_at.desc(), Prediction.prediction_id.desc()
                    )
                )
                weather = session.scalar(
                    select(WeatherInput).where(
                        WeatherInput.store_id == payload.store_id,
                        WeatherInput.target_date == target,
                        WeatherInput.scenario_id == payload.scenario_id,
                    )
                )
                if weather is not None:
                    input_payload["is_mock"] = input_payload["is_mock"] or weather.is_mock
                    input_payload["weather_evidence"].append(
                        {
                            "weather_id": weather.weather_id,
                            "date": target.isoformat(),
                            "source": weather.source,
                        }
                    )
                if prediction is None or weather is None:
                    missing.append(
                        {
                            "date": target.isoformat(),
                            "prediction_missing": prediction is None,
                            "weather_missing": weather is None,
                        }
                    )
                    continue
                model_versions.add(prediction.model_version)
                factor = weather_factor(weather.condition)
                adjusted = prediction.predicted_units * Decimal(str(factor))
                input_payload["prediction_ids"].append(prediction.prediction_id)
                input_payload["weather_ids"].append(weather.weather_id)
                input_payload["forecast_dates"].append(target.isoformat())
                input_payload["baseline_forecast"].append(float(prediction.predicted_units))
                input_payload["weather_factors"].append(factor)
                input_payload["adjusted_forecast"].append(float(adjusted))
                input_payload["is_mock"] = input_payload["is_mock"] or weather.is_mock
            input_payload["model_versions"] = sorted(model_versions)
            if missing or len(model_versions) > 1:
                input_payload["missing_inputs"] = missing
                outcome = {
                    "status": "DATA_NOT_READY",
                    "actions": [],
                    "reason_code": "MISSING_INPUTS" if missing else "INCONSISTENT_MODEL_VERSION",
                }
            else:
                outcome = evaluate_snapshot(snapshot_input, input_payload["adjusted_forecast"])
        recommendation = Recommendation(
            run_id=run.run_id,
            snapshot_id=snapshot.snapshot_id,
            status=outcome["status"],
            reason_code=outcome.get("reason_code"),
            actions=outcome["actions"],
            input_payload=input_payload,
            result_payload=outcome,
            decision_date=payload.snapshot_date,
        )
        session.add(recommendation)
        session.flush()
        if outcome["status"] == "READY":
            run.ready_count += 1
        elif outcome["status"] == "REVIEW_REQUIRED":
            run.review_count += 1
        else:
            run.not_ready_count += 1
        if outcome["status"] != "READY" or any(
            a["action"] != "NO_ACTION" for a in outcome["actions"]
        ):
            session.add(
                Notification(
                    recommendation_id=recommendation.recommendation_id,
                    store_id=snapshot.store_id,
                    message=f"{snapshot.product_id}: {outcome.get('reason_code') or ', '.join(a['action'] for a in outcome['actions'])}",
                )
            )
        run.total_items += 1
    session.flush()
    return run
