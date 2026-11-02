from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect
from sqlmodel import Session, SQLModel, create_engine

from app import database
from app.main import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'test.db'}",
        connect_args={"check_same_thread": False},
    )
    monkeypatch.setattr(database, "engine", engine)

    def override_session():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[database.get_session] = override_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    SQLModel.metadata.drop_all(engine)
    engine.dispose()


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_concurrent_profile_initialization_is_race_safe(client):
    with ThreadPoolExecutor(max_workers=8) as pool:
        responses = list(
            pool.map(
                lambda _: client.get("/api/v1/profile?user_id=first-visit"),
                range(8),
            )
        )
    assert all(response.status_code == 200 for response in responses)
    assert len({response.json()["user_id"] for response in responses}) == 1


def test_profile_get_and_update(client):
    profile = client.get("/api/v1/profile").json()
    assert profile["daily_goal_ml"] == 2500

    response = client.put(
        "/api/v1/profile",
        json={
            "display_name": "Aqua Tester",
            "daily_goal_ml": 2200,
            "wake_time": "06:30",
            "sleep_time": "22:15",
        },
    )
    assert response.status_code == 200
    assert response.json()["display_name"] == "Aqua Tester"
    assert response.json()["daily_goal_ml"] == 2200
    assert client.put(
        "/api/v1/profile",
        json={"display_name": "Test", "daily_goal_ml": 9000},
    ).status_code == 422


def test_entry_create_list_update_delete_and_user_scope(client):
    created = client.post(
        "/api/v1/entries",
        json={
            "amount_ml": 300,
            "drink_type": "water",
            "consumed_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    assert created.status_code == 201
    entry = created.json()
    assert entry["consumed_at"].endswith("+00:00")
    assert client.get("/api/v1/entries").json()[0]["id"] == entry["id"]

    updated = client.patch(
        f"/api/v1/entries/{entry['id']}",
        json={"amount_ml": 450, "drink_type": "tea"},
    )
    assert updated.status_code == 200
    assert updated.json()["amount_ml"] == 450
    assert client.patch(
        f"/api/v1/entries/{entry['id']}?user_id=another-user",
        json={"amount_ml": 200},
    ).status_code == 404
    assert client.delete(f"/api/v1/entries/{entry['id']}").json()["deleted"]
    assert client.get("/api/v1/entries").json() == []
    assert client.post("/api/v1/entries", json={"amount_ml": 0}).status_code == 422


def test_offline_entry_retries_are_idempotent(client):
    payload = {
        "amount_ml": 300,
        "client_entry_id": "mobile-retry-1",
        "consumed_at": datetime.now(timezone.utc).isoformat(),
    }
    first = client.post("/api/v1/entries", json=payload)
    retry = client.post("/api/v1/entries", json=payload)
    assert first.status_code == retry.status_code == 201
    assert first.json()["id"] == retry.json()["id"]
    assert len(client.get("/api/v1/entries").json()) == 1


def test_existing_database_adds_client_sync_column(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'existing.db'}")
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE waterentry ("
            "id INTEGER PRIMARY KEY, user_id VARCHAR, amount_ml INTEGER, "
            "drink_type VARCHAR, consumed_at DATETIME, created_at DATETIME)"
        )
    monkeypatch.setattr(database, "engine", engine)

    database.create_db_and_tables()

    column_names = {
        column["name"] for column in inspect(engine).get_columns("waterentry")
    }
    assert "client_entry_id" in column_names
    indexes = inspect(engine).get_indexes("waterentry")
    assert any(index["name"] == "ix_waterentry_client_entry_id" for index in indexes)
    engine.dispose()


def test_dashboard_and_weekly_analytics_are_database_backed(client):
    client.post(
        "/api/v1/entries",
        json={"amount_ml": 375, "consumed_at": datetime.now(timezone.utc).isoformat()},
    )
    dashboard = client.get("/api/v1/dashboard").json()
    assert dashboard["total_ml"] == 375
    assert dashboard["entries_count"] == 1

    weekly = client.get("/api/v1/analytics/weekly").json()
    assert len(weekly["days"]) == 7
    assert sum(day["amount_ml"] for day in weekly["days"]) == 375


def test_reminders_create_update_delete_and_validation(client):
    created = client.post(
        "/api/v1/reminders",
        json={"label": "Mid-morning", "reminder_time": "10:30"},
    )
    assert created.status_code == 201
    reminder_id = created.json()["id"]
    assert client.get("/api/v1/reminders").json()[0]["reminder_time"] == "10:30"

    updated = client.put(
        f"/api/v1/reminders/{reminder_id}",
        json={"label": "Lunch", "reminder_time": "12:00", "enabled": False},
    )
    assert updated.status_code == 200
    assert updated.json()["enabled"] is False
    assert client.delete(f"/api/v1/reminders/{reminder_id}").json()["deleted"]
    assert client.get("/api/v1/reminders").json() == []
    assert client.post(
        "/api/v1/reminders",
        json={"reminder_time": "25:61"},
    ).status_code == 422


def test_coach_discloses_guided_fallback_and_uses_real_context(client, monkeypatch):
    monkeypatch.setattr("app.main.settings.openai_api_key", "")
    client.put(
        "/api/v1/profile",
        json={"display_name": "Mina", "daily_goal_ml": 2000},
    )
    client.post("/api/v1/entries", json={"amount_ml": 600})
    result = client.post(
        "/api/v1/coach",
        json={"question": "How can I build a habit?"},
    )
    assert result.status_code == 200
    assert result.json()["generated_by_ai"] is False
    assert result.json()["source"] == "guided_fallback"
    assert result.json()["context"]["display_name"] == "Mina"
    assert result.json()["context"]["logged_today_ml"] == 600
