import unittest

from app.rules import ASSUMPTIONS, RULE_VERSION, evaluate_snapshot, weather_factor


def snapshot(stock=10, expiry=5, lead=1):
    return {
        "opening_inventory_units": stock,
        "days_to_expiry": expiry,
        "delivery_lead_time_days": lead,
    }


class RecommendationRulesTests(unittest.TestCase):
    def test_declared_assumptions_and_version(self):
        self.assertEqual(RULE_VERSION, "rules_v1")
        self.assertEqual(
            ASSUMPTIONS,
            {"incoming_units": 0, "safety_stock_units": 0, "review_days": 1},
        )

    def test_missing_forecast_never_becomes_zero_demand(self):
        for values in ([], [3.0]):
            with self.subTest(values=values):
                result = evaluate_snapshot(snapshot(), values)
                self.assertEqual(result["status"], "DATA_NOT_READY")
                self.assertEqual(result["reason_code"], "INSUFFICIENT_FORECAST_HORIZON")
                self.assertEqual(result["actions"], [])

    def test_zero_lead_still_needs_today_forecast(self):
        result = evaluate_snapshot(snapshot(lead=0), [])
        self.assertEqual(result["status"], "DATA_NOT_READY")

    def test_near_expiry_needs_entire_selling_window(self):
        result = evaluate_snapshot(snapshot(expiry=2, lead=0), [3.0])
        self.assertEqual(result["status"], "DATA_NOT_READY")

    def test_expired_and_expiring_today_require_distinct_review(self):
        for expiry, reason in ((-1, "EXPIRED_STOCK"), (0, "CHECK_EXPIRY_POLICY")):
            with self.subTest(expiry=expiry):
                result = evaluate_snapshot(snapshot(expiry=expiry), [])
                self.assertEqual(result["status"], "REVIEW_REQUIRED")
                self.assertEqual(result["reason_code"], reason)
                self.assertEqual(result["actions"], [])

    def test_declared_discount_scenario(self):
        result = evaluate_snapshot(snapshot(expiry=2), [2.4, 2.4])
        self.assertEqual(result["status"], "READY")
        self.assertEqual(len(result["actions"]), 1)
        discount = result["actions"][0]
        self.assertEqual(discount["action"], "DISCOUNT")
        self.assertEqual(discount["discount_percent"], 20)
        self.assertEqual(discount["potential_excess_units"], 5.2)

    def test_today_lost_sales_are_not_added_to_arrival_day_order(self):
        result = evaluate_snapshot(snapshot(stock=2), [5.0, 6.0])
        self.assertEqual(result["shortage_today_estimate"], 3.0)
        self.assertEqual(
            result["actions"],
            [{
                "action": "RESTOCK",
                "recommended_order_units": 6,
                "arrival_in_days": 1,
                "reason_code": "PROJECTED_SHORTAGE_AFTER_ARRIVAL",
            }],
        )

    def test_expiry_before_arrival_removes_projected_old_stock(self):
        result = evaluate_snapshot(snapshot(stock=10, expiry=1), [1.0, 2.0])
        actions = {action["action"]: action for action in result["actions"]}
        self.assertEqual(set(actions), {"DISCOUNT", "RESTOCK"})
        self.assertEqual(actions["DISCOUNT"]["potential_excess_units"], 9.0)
        self.assertEqual(actions["RESTOCK"]["recommended_order_units"], 2)

    def test_zero_lead_orders_only_today_deficit(self):
        result = evaluate_snapshot(snapshot(stock=2, lead=0), [5.0])
        restock = result["actions"][0]
        self.assertEqual(restock["recommended_order_units"], 3)
        self.assertEqual(restock["arrival_in_days"], 0)

    def test_zero_stock_and_zero_forecast_need_no_action(self):
        result = evaluate_snapshot(snapshot(stock=0), [0.0, 0.0])
        self.assertEqual(result["shortage_today_estimate"], 0.0)
        self.assertEqual(result["actions"][0]["action"], "NO_ACTION")

    def test_far_expiry_does_not_require_full_shelf_life_forecast(self):
        result = evaluate_snapshot(snapshot(expiry=28), [2.0, 2.0])
        self.assertEqual(result["status"], "READY")
        self.assertEqual(result["actions"][0]["action"], "NO_ACTION")

    def test_longer_lead_consumes_only_pre_arrival_stock(self):
        result = evaluate_snapshot(snapshot(stock=10, lead=2), [2.0, 3.0, 8.0])
        self.assertEqual(result["actions"][0]["recommended_order_units"], 3)

    def test_fractional_demand_does_not_create_false_order(self):
        result = evaluate_snapshot(snapshot(stock=1), [0.1, 0.9])
        self.assertEqual(result["actions"][0]["action"], "NO_ACTION")

    def test_integer_boundary_ignores_float_noise(self):
        result = evaluate_snapshot(snapshot(stock=0), [0.0, 1.0000000000000002])
        self.assertEqual(result["actions"][0]["recommended_order_units"], 1)

    def test_real_fractional_deficit_rounds_up(self):
        result = evaluate_snapshot(snapshot(stock=0), [0.0, 1.01])
        self.assertEqual(result["actions"][0]["recommended_order_units"], 2)

    def test_invalid_forecasts_are_rejected(self):
        for invalid in (-1, float("nan"), float("inf"), float("-inf"), True, "3", None):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    evaluate_snapshot(snapshot(), [0.0, invalid])

    def test_nonsequence_forecast_is_rejected(self):
        for invalid in (None, "3,4", {0: 3, 1: 4}):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    evaluate_snapshot(snapshot(), invalid)

    def test_invalid_snapshot_values_are_rejected(self):
        invalid_snapshots = [
            {},
            None,
            snapshot(stock=-1),
            snapshot(stock=1.5),
            snapshot(stock=True),
            snapshot(lead=-1),
            snapshot(lead=0.5),
            snapshot(expiry=float("nan")),
            snapshot(expiry=1.5),
        ]
        for invalid in invalid_snapshots:
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    evaluate_snapshot(invalid, [1.0, 1.0])

    def test_invalid_values_are_rejected_even_after_required_horizon(self):
        with self.assertRaises(ValueError):
            evaluate_snapshot(snapshot(), [1.0, 1.0, float("nan")])


class WeatherFactorTests(unittest.TestCase):
    def test_supported_mock_weather(self):
        self.assertEqual(weather_factor("Rain"), 0.8)
        self.assertEqual(weather_factor("Clear"), 1.0)
        self.assertEqual(weather_factor("Clouds"), 1.0)

    def test_unknown_weather_is_not_silently_treated_as_clear(self):
        for condition in ("Snow", "", "rain", None):
            with self.subTest(condition=condition):
                with self.assertRaises(ValueError):
                    weather_factor(condition)


if __name__ == "__main__":
    unittest.main()
