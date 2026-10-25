"""Isolated API fixtures: no network, API credentials, or persistent database."""

import csv
import io
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


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


@pytest.fixture
def client():
    settings = Settings(
        database_url="sqlite://",
        admin_api_key="test-admin",
        staff_api_key="test-staff",
        service_api_key="test-service",
        _env_file=None,
    )
    with TestClient(create_app(settings)) as test_client:
        yield test_client


@pytest.fixture
def admin_headers():
    return {"X-API-Key": "test-admin"}


@pytest.fixture
def staff_headers():
    return {"X-API-Key": "test-staff"}


@pytest.fixture
def service_headers():
    return {"X-API-Key": "test-service"}


@pytest.fixture
def inventory_csv_path():
    return Path(__file__).resolve().parents[1] / "data" / "inventory_mock_2026-10-12.csv"


@pytest.fixture
def csv_bytes():
    """Create small CSVs with source column names, including real-file decimals."""

    def build(rows, *, bom=True):
        stream = io.StringIO(newline="")
        writer = csv.DictWriter(stream, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for overrides in rows:
            row = {
                "Date": "2026-10-12",
                "Store_ID": "STORE_01",
                "Product_ID": "PROD_001",
                "Opening_Inventory_Units": "10",
                "Days_To_Expiry": "2.0",
                "Standard_Shelf_Life_Days": "6.0",
                "Delivery_Lead_Time_Days": "1",
                "Snapshot_Source": "MOCK_FOR_WEATHER_INTEGRATION_TEST",
            }
            row.update(overrides)
            writer.writerow(row)
        return stream.getvalue().encode("utf-8-sig" if bom else "utf-8")

    return build


@pytest.fixture
def import_csv(client, admin_headers):
    def upload(content, *, dry_run=False):
        return client.post(
            "/api/v1/inventory/imports",
            params={"dry_run": str(dry_run).lower()},
            headers=admin_headers,
            files={"file": ("inventory.csv", content, "text/csv")},
        )

    return upload


@pytest.fixture
def imported_inventory(import_csv, inventory_csv_path):
    response = import_csv(inventory_csv_path.read_bytes())
    assert response.is_success, response.text
    return response.json()


@pytest.fixture
def prediction_payload():
    def build(**overrides):
        payload = {
            "request_id": str(uuid4()),
            "store_id": "STORE_01",
            "product_id": "PROD_001",
            "target_date": "2026-10-12",
            "predicted_units": 3.0,
            "prediction_kind": "BASELINE_SALES_PROXY",
            "model_version": "mock_v1",
            "source": "MOCK",
            "contains_weather_effect": False,
        }
        payload.update(overrides)
        return payload

    return build


@pytest.fixture
def weather_payload():
    def build(**overrides):
        payload = {
            "request_id": str(uuid4()),
            "scenario_id": "rain_demo",
            "store_id": "STORE_01",
            "target_date": "2026-10-12",
            "condition": "Rain",
            "temperature_c": 28.0,
            "rain_mm_1h": 1.0,
        }
        payload.update(overrides)
        return payload

    return build


@pytest.fixture
def run_payload():
    def build(**overrides):
        payload = {
            "request_id": str(uuid4()),
            "snapshot_date": "2026-10-12",
            "store_id": "STORE_01",
            "scenario_id": "rain_demo",
            "rule_version": "rules_v1",
            "prediction_source": "MOCK",
        }
        payload.update(overrides)
        return payload

    return build


@pytest.fixture
def ready_discount(
    client,
    import_csv,
    csv_bytes,
    admin_headers,
    service_headers,
    staff_headers,
    prediction_payload,
    weather_payload,
    run_payload,
):
    """Create a reviewable, dated discount through the public HTTP contracts."""
    response = import_csv(csv_bytes([{}]))
    assert response.is_success, response.text
    for target_date in ("2026-10-12", "2026-10-13"):
        response = client.post(
            "/api/v1/predictions",
            headers=service_headers,
            json=prediction_payload(target_date=target_date),
        )
        assert response.is_success, response.text
        response = client.post(
            "/api/v1/weather/mock",
            headers=admin_headers,
            json=weather_payload(target_date=target_date),
        )
        assert response.is_success, response.text
    response = client.post(
        "/api/v1/recommendation-runs",
        headers=admin_headers,
        json=run_payload(),
    )
    assert response.is_success, response.text
    run = response.json()
    response = client.get(
        "/api/v1/recommendations",
        headers=staff_headers,
        params={"run_id": run["run_id"]},
    )
    assert response.status_code == 200, response.text
    recommendation = response.json()["items"][0]
    assert recommendation["status"] == "READY"
    return {"run": run, "recommendation": recommendation}
