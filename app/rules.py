"""Transparent prototype rules for daily inventory recommendations.

An expiry value of 2 permits sales on the snapshot date and the following day.
The caller supplies a continuous, date-matched forecast starting on that date.
These rules express declared demo assumptions; they are not a learned model.
"""

from decimal import Decimal, InvalidOperation, ROUND_CEILING, ROUND_HALF_EVEN
from math import isfinite


RULE_VERSION = "rules_v1"
NEAR_EXPIRY_DAYS = 2
ASSUMPTIONS = {
    "incoming_units": 0,
    "safety_stock_units": 0,
    "review_days": 1,
}

# Treat sub-billionth-unit differences as numerical noise, especially before
# rounding an order upward to a whole unit.
_EPSILON = Decimal("0.000000001")
_ZERO = Decimal(0)


def _number(value: object, name: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        raise ValueError(f"{name} must be a finite number")
    try:
        number = Decimal(str(value))
        representable = isfinite(float(number))
    except (InvalidOperation, ValueError, OverflowError) as exc:
        raise ValueError(f"{name} must be a finite number") from exc
    if not number.is_finite() or not representable:
        raise ValueError(f"{name} must be a finite number")
    return number


def _integer(value: object, name: str) -> int:
    number = _number(value, name)
    if number != number.to_integral_value():
        raise ValueError(f"{name} must be a whole number")
    return int(number)


def _positive_difference(value: Decimal) -> Decimal:
    return value if value > _EPSILON else _ZERO


def _ceil_units(value: Decimal) -> int:
    nearest = value.to_integral_value(rounding=ROUND_HALF_EVEN)
    if abs(value - nearest) <= _EPSILON:
        value = nearest
    return int(value.to_integral_value(rounding=ROUND_CEILING))


def weather_factor(condition: str) -> float:
    """Return the declared mock multiplier, rejecting unknown conditions."""
    factors = {"Clear": 1.0, "Clouds": 1.0, "Rain": 0.8}
    if not isinstance(condition, str) or condition not in factors:
        raise ValueError("Supported weather conditions are Clear, Clouds, and Rain")
    return factors[condition]


def evaluate_snapshot(snapshot: dict, adjusted_forecast: list[float]) -> dict:
    """Evaluate a snapshot using nonnegative, finite daily demand estimates.

    Missing forecast days produce DATA_NOT_READY. Expired inventory and stock
    expiring today require a policy review. Malformed inputs raise ValueError.
    A forecast may yield both a discount for old stock and an order for new stock.
    """
    required_fields = (
        "opening_inventory_units",
        "days_to_expiry",
        "delivery_lead_time_days",
    )
    if not isinstance(snapshot, dict) or any(field not in snapshot for field in required_fields):
        raise ValueError("Snapshot is missing required inventory fields")

    stock_units = _integer(snapshot["opening_inventory_units"], "opening_inventory_units")
    days = _integer(snapshot["days_to_expiry"], "days_to_expiry")
    lead = _integer(snapshot["delivery_lead_time_days"], "delivery_lead_time_days")
    if stock_units < 0:
        raise ValueError("opening_inventory_units must be nonnegative")
    if lead < 0:
        raise ValueError("delivery_lead_time_days must be nonnegative")
    if not isinstance(adjusted_forecast, (list, tuple)):
        raise ValueError("adjusted_forecast must contain daily demand values")

    forecast = []
    for index, value in enumerate(adjusted_forecast):
        number = _number(value, f"adjusted_forecast[{index}]")
        if number < 0:
            raise ValueError("Forecast values must be nonnegative")
        forecast.append(number)

    if days <= 0:
        return {
            "status": "REVIEW_REQUIRED",
            "reason_code": "EXPIRED_STOCK" if days < 0 else "CHECK_EXPIRY_POLICY",
            "actions": [],
        }

    required_days = lead + ASSUMPTIONS["review_days"]
    if days <= NEAR_EXPIRY_DAYS:
        required_days = max(required_days, days)
    if len(forecast) < required_days:
        return {
            "status": "DATA_NOT_READY",
            "reason_code": "INSUFFICIENT_FORECAST_HORIZON",
            "actions": [],
        }

    stock = Decimal(stock_units)
    actions = []
    shortage_today = _positive_difference(forecast[0] - stock)

    if days <= NEAR_EXPIRY_DAYS:
        expected_sales = sum(forecast[:days], _ZERO)
        potential_excess = _positive_difference(stock - expected_sales)
        if potential_excess:
            actions.append(
                {
                    "action": "DISCOUNT",
                    "discount_percent": 20,
                    "potential_excess_units": float(potential_excess),
                    "reason_code": "NEAR_EXPIRY_EXCESS",
                }
            )

    demand_before_arrival = sum(forecast[:lead], _ZERO)
    stock_on_arrival = max(stock - demand_before_arrival, _ZERO)
    if days <= lead:
        stock_on_arrival = _ZERO

    # Earlier unmet sales are lost, not backordered into the arrival day's order.
    deficit = _positive_difference(forecast[lead] - stock_on_arrival)
    order_units = _ceil_units(deficit)
    if order_units:
        actions.append(
            {
                "action": "RESTOCK",
                "recommended_order_units": order_units,
                "arrival_in_days": lead,
                "reason_code": "PROJECTED_SHORTAGE_AFTER_ARRIVAL",
            }
        )

    if not actions:
        actions.append({"action": "NO_ACTION", "reason_code": "NO_RULE_TRIGGERED"})

    return {
        "status": "READY",
        "shortage_today_estimate": float(shortage_today),
        "actions": actions,
    }
