"""HTTP integration tests for imports and the dated recommendation workflow."""

import pytest


DATE = "2026-10-12"


def inventory(client, headers, **params):
    response = client.get(
        "/api/v1/inventory",
        headers=headers,
        params={"date": DATE, "limit": 200, **params},
    )
    assert response.status_code == 200, response.text
    return response.json()


def summary(client, headers, **params):
    response = client.get(
        "/api/v1/inventory/summary",
        headers=headers,
        params={"date": DATE, **params},
    )
    assert response.status_code == 200, response.text
    return response.json()


def post_json(client, path, headers, payload):
    response = client.post(f"/api/v1/{path}", headers=headers, json=payload)
    assert response.is_success, response.text
    return response.json()


def recommendations(client, headers, run_id):
    response = client.get("/api/v1/recommendations", headers=headers, params={"run_id": run_id})
    assert response.status_code == 200, response.text
    return response.json()["items"]


def test_health_is_public(client):
    assert client.get("/health").status_code == 200


@pytest.mark.parametrize("headers", [{}, {"X-API-Key": "incorrect-key"}])
def test_inventory_requires_valid_api_key(client, headers):
    response = client.get("/api/v1/inventory", headers=headers, params={"date": DATE})
    assert response.status_code == 401


def test_staff_cannot_import(client, staff_headers, csv_bytes):
    response = client.post(
        "/api/v1/inventory/imports",
        headers=staff_headers,
        files={"file": ("inventory.csv", csv_bytes([{}]), "text/csv")},
    )
    assert response.status_code == 403


def test_actual_csv_import_preserves_expected_statistics(client, staff_headers, imported_inventory):
    data = summary(client, staff_headers)
    assert data["snapshot_count"] == 128
    assert data["store_count"] == 4
    assert data["product_count"] == 32
    assert data["total_opening_units"] == 3103
    assert data["zero_stock_count"] == 2
    assert data["near_expiry_in_stock_count"] == 70
    page = inventory(client, staff_headers)
    assert page["date"] == DATE
    assert page["total"] == page["count"] == len(page["items"]) == 128
    first = next(
        item
        for item in page["items"]
        if item["store_id"] == "STORE_01" and item["product_id"] == "PROD_001"
    )
    assert first["opening_inventory_units"] == 10
    assert first["days_to_expiry"] == 2
    assert first["snapshot_source"] == "MOCK_FOR_WEATHER_INTEGRATION_TEST"
    for missing_field in ("product_name", "category", "regular_price", "barcode"):
        assert first[missing_field] is None


def test_import_accepts_bom_and_whole_number_decimals(client, staff_headers, import_csv, csv_bytes):
    response = import_csv(csv_bytes([{}]))
    assert response.is_success, response.text
    item = inventory(client, staff_headers)["items"][0]
    assert item["days_to_expiry"] == 2
    assert item["standard_shelf_life_days"] == 6
    assert isinstance(item["days_to_expiry"], int)


@pytest.mark.parametrize(
    "invalid_row",
    [
        {"Days_To_Expiry": "2.5"},
        {"Opening_Inventory_Units": "-1"},
        {"Opening_Inventory_Units": "1.5"},
        {"Delivery_Lead_Time_Days": "-1"},
        {"Standard_Shelf_Life_Days": "0"},
        {"Date": "not-a-date"},
    ],
)
def test_invalid_csv_rejects_entire_import(
    client, staff_headers, import_csv, csv_bytes, invalid_row
):
    response = import_csv(
        csv_bytes(
            [
                {"Product_ID": "PROD_VALID"},
                {"Product_ID": "PROD_INVALID", **invalid_row},
            ]
        )
    )
    assert response.status_code in {400, 422}, response.text
    assert summary(client, staff_headers)["snapshot_count"] == 0


def test_import_dry_run_does_not_persist(client, staff_headers, import_csv, csv_bytes):
    response = import_csv(csv_bytes([{}]), dry_run=True)
    assert response.is_success, response.text
    assert summary(client, staff_headers)["snapshot_count"] == 0
    response = import_csv(csv_bytes([{}]))
    assert response.is_success, response.text
    assert summary(client, staff_headers)["snapshot_count"] == 1


def test_same_file_import_is_idempotent(client, staff_headers, import_csv, inventory_csv_path):
    content = inventory_csv_path.read_bytes()
    first = import_csv(content)
    second = import_csv(content)
    assert first.is_success, first.text
    assert second.is_success, second.text
    assert first.json()["import_id"] == second.json()["import_id"]
    assert summary(client, staff_headers)["snapshot_count"] == 128


def test_equivalent_rows_in_different_file_bytes_are_not_duplicated(
    client, staff_headers, import_csv, csv_bytes
):
    first = import_csv(csv_bytes([{}], bom=True))
    second = import_csv(csv_bytes([{}], bom=False))
    assert first.is_success, first.text
    assert second.is_success, second.text
    assert second.json()["inserted_rows"] == 0
    assert second.json()["unchanged_rows"] == 1
    assert summary(client, staff_headers)["snapshot_count"] == 1


def test_changed_snapshot_conflicts_and_rolls_back_other_rows(
    client, admin_headers, staff_headers, import_csv, csv_bytes
):
    assert import_csv(csv_bytes([{}])).is_success
    response = import_csv(
        csv_bytes(
            [
                {"Product_ID": "PROD_NEW", "Store_ID": "STORE_NEW"},
                {"Opening_Inventory_Units": "999"},
            ]
        )
    )
    assert response.status_code == 409, response.text
    data = inventory(client, staff_headers)
    assert data["total"] == 1
    assert data["items"][0]["opening_inventory_units"] == 10
    # The failed transaction must leave an audit record, without a successful job.
    jobs = client.get("/api/v1/inventory/imports", headers=admin_headers).json()
    assert jobs["total"] == 1
    attempts = client.get("/api/v1/inventory/import-attempts", headers=admin_headers).json()
    assert attempts["total"] == 2
    failed = [attempt for attempt in attempts["items"] if attempt["status"] == "FAILED"]
    assert len(failed) == 1
    assert failed[0]["error"]


def test_store_date_and_expiry_filters_do_not_mix_snapshots(
    client, staff_headers, imported_inventory
):
    by_store = inventory(client, staff_headers, store_id="STORE_02")
    assert by_store["total"] == 32
    assert {row["store_id"] for row in by_store["items"]} == {"STORE_02"}
    other_date = inventory(client, staff_headers, date="2026-10-13")
    assert other_date["total"] == 0
    expiring = inventory(client, staff_headers, max_days=2, in_stock_only=True)
    assert expiring["total"] == 70
    assert all(
        row["days_to_expiry"] <= 2 and row["opening_inventory_units"] > 0
        for row in expiring["items"]
    )


def test_pagination_returns_disjoint_pages(client, staff_headers, imported_inventory):
    first = inventory(client, staff_headers, limit=10, offset=0)
    second = inventory(client, staff_headers, limit=10, offset=10)
    assert first["total"] == second["total"] == 128
    assert first["count"] == second["count"] == 10

    def keys(page):
        return {(row["store_id"], row["product_id"]) for row in page["items"]}

    assert keys(first).isdisjoint(keys(second))


def test_negative_prediction_is_rejected(
    client, import_csv, csv_bytes, service_headers, prediction_payload
):
    assert import_csv(csv_bytes([{}])).is_success
    response = client.post(
        "/api/v1/predictions",
        headers=service_headers,
        json=prediction_payload(predicted_units=-1),
    )
    assert response.status_code == 422, response.text


def test_staff_cannot_write_predictions(client, staff_headers, prediction_payload):
    response = client.post("/api/v1/predictions", headers=staff_headers, json=prediction_payload())
    assert response.status_code == 403


def test_prediction_request_is_idempotent_and_changed_payload_conflicts(
    client, import_csv, csv_bytes, service_headers, prediction_payload
):
    assert import_csv(csv_bytes([{}])).is_success
    payload = prediction_payload()
    first = post_json(client, "predictions", service_headers, payload)
    second = post_json(client, "predictions", service_headers, payload)
    assert first == second
    response = client.post(
        "/api/v1/predictions",
        headers=service_headers,
        json={**payload, "predicted_units": 99},
    )
    assert response.status_code == 409, response.text


def test_missing_forecasts_remain_not_ready(
    client,
    import_csv,
    csv_bytes,
    admin_headers,
    staff_headers,
    weather_payload,
    run_payload,
):
    assert import_csv(csv_bytes([{}])).is_success
    post_json(client, "weather/mock", admin_headers, weather_payload())
    run = post_json(client, "recommendation-runs", admin_headers, run_payload())
    assert run["not_ready_count"] == 1
    assert run["ready_count"] == 0
    item = recommendations(client, staff_headers, run["run_id"])[0]
    assert item["status"] == "DATA_NOT_READY"
    assert item["actions"] == []


def test_weather_request_is_idempotent_and_cannot_be_changed_in_place(
    client, import_csv, csv_bytes, admin_headers, weather_payload
):
    assert import_csv(csv_bytes([{}])).is_success
    payload = weather_payload()
    first = post_json(client, "weather/mock", admin_headers, payload)
    second = post_json(client, "weather/mock", admin_headers, payload)
    assert first == second
    response = client.post(
        "/api/v1/weather/mock",
        headers=admin_headers,
        json={**payload, "condition": "Clear"},
    )
    assert response.status_code == 409, response.text


def test_expiry_today_requires_policy_review(
    client, import_csv, csv_bytes, admin_headers, staff_headers, run_payload
):
    assert import_csv(csv_bytes([{"Days_To_Expiry": "0.0"}])).is_success
    run = post_json(client, "recommendation-runs", admin_headers, run_payload())
    assert run["review_count"] == 1
    item = recommendations(client, staff_headers, run["run_id"])[0]
    assert item["status"] == "REVIEW_REQUIRED"
    assert item["reason_code"] == "CHECK_EXPIRY_POLICY"
    assert item["actions"] == []


def test_recommendation_run_request_is_idempotent(
    client, import_csv, csv_bytes, admin_headers, staff_headers, run_payload
):
    assert import_csv(csv_bytes([{}])).is_success
    payload = run_payload()
    first = post_json(client, "recommendation-runs", admin_headers, payload)
    second = post_json(client, "recommendation-runs", admin_headers, payload)
    assert first == second
    assert len(recommendations(client, staff_headers, first["run_id"])) == 1


def test_weather_from_another_day_cannot_fill_missing_weather(
    client,
    import_csv,
    csv_bytes,
    admin_headers,
    staff_headers,
    service_headers,
    prediction_payload,
    weather_payload,
    run_payload,
):
    assert import_csv(csv_bytes([{}])).is_success
    for target_date in (DATE, "2026-10-13"):
        post_json(
            client,
            "predictions",
            service_headers,
            prediction_payload(target_date=target_date),
        )
    post_json(
        client,
        "weather/mock",
        admin_headers,
        weather_payload(target_date="2026-10-13"),
    )
    run = post_json(client, "recommendation-runs", admin_headers, run_payload())
    assert run["not_ready_count"] == 1
    item = recommendations(client, staff_headers, run["run_id"])[0]
    assert item["status"] == "DATA_NOT_READY"
    assert item["actions"] == []


def test_dated_forecasts_and_rain_scenario_produce_explainable_discount(
    client,
    import_csv,
    csv_bytes,
    admin_headers,
    staff_headers,
    service_headers,
    prediction_payload,
    weather_payload,
    run_payload,
):
    assert import_csv(csv_bytes([{}])).is_success
    for target_date in (DATE, "2026-10-13"):
        post_json(
            client,
            "predictions",
            service_headers,
            prediction_payload(target_date=target_date, predicted_units=3),
        )
        post_json(
            client,
            "weather/mock",
            admin_headers,
            weather_payload(target_date=target_date),
        )
    run = post_json(client, "recommendation-runs", admin_headers, run_payload())
    assert run["ready_count"] == 1
    assert run["not_ready_count"] == run["review_count"] == 0
    item = recommendations(client, staff_headers, run["run_id"])[0]
    assert item["status"] == "READY"
    assert item["approval_status"] == "PROPOSED"
    discount = next(action for action in item["actions"] if action["action"] == "DISCOUNT")
    # Two dated baseline forecasts of 3, each adjusted once by Rain's mock 0.8.
    assert discount["potential_excess_units"] == pytest.approx(10 - 3 * 0.8 * 2)
    assert discount["discount_percent"] == 20
    # A recommendation cannot change the original opening snapshot.
    assert inventory(client, staff_headers)["items"][0]["opening_inventory_units"] == 10


def test_public_deals_start_empty(client):
    response = client.get("/api/v1/deals")
    assert response.status_code == 200
    assert response.json()["items"] == []


def test_staff_cannot_approve_recommendation(client, staff_headers, ready_discount):
    recommendation_id = ready_discount["recommendation"]["recommendation_id"]
    response = client.patch(
        f"/api/v1/recommendations/{recommendation_id}/status",
        headers=staff_headers,
        json={"status": "APPROVED"},
    )
    assert response.status_code == 403


def test_approval_requires_metadata_before_a_public_deal_is_visible(
    client, admin_headers, ready_discount
):
    recommendation_id = ready_discount["recommendation"]["recommendation_id"]
    assert client.get("/api/v1/deals", params={"date": DATE}).json()["items"] == []
    approval = client.patch(
        f"/api/v1/recommendations/{recommendation_id}/status",
        headers=admin_headers,
        json={"status": "APPROVED"},
    )
    assert approval.status_code == 200, approval.text
    assert approval.json()["approval_status"] == "APPROVED"
    # CSV product IDs alone cannot supply a usable customer offer.
    assert client.get("/api/v1/deals", params={"date": DATE}).json()["items"] == []
    metadata = client.patch(
        "/api/v1/products/PROD_001",
        headers=admin_headers,
        json={"product_name": "Demo product", "regular_price": 100, "barcode": "0012345"},
    )
    assert metadata.status_code == 200, metadata.text
    assert metadata.json()["barcode"] == "0012345"
    response = client.get("/api/v1/deals", params={"date": DATE})
    assert response.status_code == 200, response.text
    assert response.json()["count"] == 1
    deal = response.json()["items"][0]
    assert deal["recommendation_id"] == recommendation_id
    assert deal["product_name"] == "Demo product"
    assert deal["regular_price"] == 100
    assert deal["recommended_price"] == 80
    assert deal["inventory_date"] == DATE
    assert deal["is_mock"] is True
    assert deal["stock_basis"] == "OPENING_INVENTORY"
    # The default current-day feed must not silently publish this historical demo.
    assert client.get("/api/v1/deals", params={"date": "2026-10-13"}).json()["items"] == []
    rejected = client.patch(
        f"/api/v1/recommendations/{recommendation_id}/status",
        headers=admin_headers,
        json={"status": "REJECTED"},
    )
    assert rejected.status_code == 200, rejected.text
    assert client.get("/api/v1/deals", params={"date": DATE}).json()["items"] == []


def test_new_run_hides_a_previously_approved_offer(
    client, admin_headers, ready_discount, run_payload
):
    recommendation_id = ready_discount["recommendation"]["recommendation_id"]
    response = client.patch(
        "/api/v1/products/PROD_001",
        headers=admin_headers,
        json={"product_name": "Demo product", "regular_price": 100},
    )
    assert response.status_code == 200, response.text
    response = client.patch(
        f"/api/v1/recommendations/{recommendation_id}/status",
        headers=admin_headers,
        json={"status": "APPROVED"},
    )
    assert response.status_code == 200, response.text
    assert client.get("/api/v1/deals", params={"date": DATE}).json()["count"] == 1
    post_json(client, "recommendation-runs", admin_headers, run_payload())
    # A new proposal requires its own approval; the old approved run is superseded.
    assert client.get("/api/v1/deals", params={"date": DATE}).json()["items"] == []
