from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class InputModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, str_strip_whitespace=True)


class PredictionIn(InputModel):
    request_id: str = Field(min_length=1, max_length=100)
    store_id: str = Field(min_length=1, max_length=40)
    product_id: str = Field(min_length=1, max_length=40)
    target_date: date
    predicted_units: Decimal = Field(ge=0, max_digits=18, decimal_places=6)
    prediction_kind: Literal["BASELINE_SALES_PROXY"] = "BASELINE_SALES_PROXY"
    model_version: str = Field(min_length=1, max_length=100)
    source: Literal["MOCK", "ML_MODEL"]
    contains_weather_effect: Literal[False] = False
    input_cutoff_at: AwareDatetime | None = None


class WeatherIn(InputModel):
    request_id: str = Field(min_length=1, max_length=100)
    scenario_id: str = Field(min_length=1, max_length=100)
    store_id: str = Field(min_length=1, max_length=40)
    target_date: date
    condition: Literal["Clear", "Rain", "Clouds"]
    temperature_c: Decimal | None = Field(default=None, ge=-100, le=100, decimal_places=3)
    rain_mm_1h: Decimal | None = Field(default=None, ge=0, le=999999999, decimal_places=3)


class RunIn(InputModel):
    request_id: str = Field(min_length=1, max_length=100)
    snapshot_date: date
    store_id: str = Field(min_length=1, max_length=40)
    scenario_id: str = Field(min_length=1, max_length=100)
    rule_version: Literal["rules_v1"] = "rules_v1"
    prediction_source: Literal["MOCK", "ML_MODEL"] = "MOCK"


class ProductPatch(InputModel):
    product_name: str | None = Field(default=None, min_length=1, max_length=200)
    category: str | None = Field(default=None, min_length=1, max_length=100)
    regular_price: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    barcode: str | None = Field(default=None, min_length=1, max_length=64)


class ApprovalIn(InputModel):
    status: Literal["APPROVED", "REJECTED"]


class SnapshotIn(InputModel):
    snapshot_date: date
    store_id: str = Field(min_length=1, max_length=40)
    product_id: str = Field(min_length=1, max_length=40)
    opening_inventory_units: int = Field(ge=0, le=2147483647, strict=True)
    days_to_expiry: int = Field(ge=-2147483648, le=2147483647, strict=True)
    standard_shelf_life_days: int = Field(ge=1, le=2147483647, strict=True)
    delivery_lead_time_days: int = Field(ge=0, le=365, strict=True)


def utc_naive(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    from datetime import timezone

    return value.astimezone(timezone.utc).replace(tzinfo=None)
