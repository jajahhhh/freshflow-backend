"""Regression cases discovered during an independent correctness review."""


def test_malformed_csv_header_is_validation_error_and_audited(client, admin_headers):
    response = client.post(
        "/api/v1/inventory/imports",
        headers=admin_headers,
        files={"file": ("broken.csv", b'"Date,Store_ID\n', "text/csv")},
    )
    assert response.status_code == 422, response.text
    attempts = client.get(
        "/api/v1/inventory/import-attempts", headers=admin_headers
    ).json()["items"]
    assert len(attempts) == 1
    assert attempts[0]["status"] == "FAILED"


def test_horizon_forecast_cannot_use_data_after_snapshot_opening(
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
    for target, cutoff in (
        ("2026-10-12", "2026-10-11T23:00:00+07:00"),
        # Valid before its own target date, but unavailable at opening on Oct 12.
        ("2026-10-13", "2026-10-12T12:00:00+07:00"),
    ):
        prediction = client.post(
            "/api/v1/predictions",
            headers=service_headers,
            json=prediction_payload(
                target_date=target,
                source="ML_MODEL",
                model_version="model_v1",
                input_cutoff_at=cutoff,
            ),
        )
        assert prediction.is_success, prediction.text
        weather = client.post(
            "/api/v1/weather/mock",
            headers=service_headers,
            json=weather_payload(target_date=target),
        )
        assert weather.is_success, weather.text

    response = client.post(
        "/api/v1/recommendation-runs",
        headers=admin_headers,
        json=run_payload(prediction_source="ML_MODEL"),
    )
    assert response.is_success, response.text
    run = response.json()
    assert run["ready_count"] == 0
    assert run["not_ready_count"] == 1
    recommendations = client.get(
        "/api/v1/recommendations",
        headers=staff_headers,
        params={"run_id": run["run_id"]},
    ).json()["items"]
    assert recommendations[0]["status"] == "DATA_NOT_READY"


def test_review_retains_inventory_mock_provenance(
    client, import_csv, csv_bytes, admin_headers, staff_headers, run_payload
):
    assert import_csv(csv_bytes([{"Days_To_Expiry": "0"}])).is_success
    response = client.post(
        "/api/v1/recommendation-runs",
        headers=admin_headers,
        json=run_payload(prediction_source="ML_MODEL"),
    )
    assert response.is_success, response.text
    run = response.json()
    recommendations = client.get(
        "/api/v1/recommendations",
        headers=staff_headers,
        params={"run_id": run["run_id"]},
    ).json()["items"]
    assert recommendations[0]["status"] == "REVIEW_REQUIRED"
    assert recommendations[0]["input_payload"]["is_mock"] is True
