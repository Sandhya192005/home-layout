"""Shared pytest fixtures: every test gets its own isolated in-memory SQLite
database (never the configured Postgres) wired into the FastAPI app via
dependency override, mirroring scripts/smoke_test_api.py."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401 register all models on Base.metadata
from app.api.v1.public import public_share_limiter
from app.core.database import Base, get_db
from app.main import app


@pytest.fixture()
def client():
    # Starlette's TestClient always reports the same fake client host, so the
    # rate limiter's per-IP counters would otherwise carry over between tests.
    public_share_limiter.reset()

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def register_and_login(client: TestClient, email: str = "test@example.com", password: str = "supersecret123") -> dict:
    client.post("/api/v1/auth/register", json={"email": email, "full_name": "Test User", "password": password})
    r = client.post("/api/v1/auth/login", data={"username": email, "password": password})
    token = r.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def auth_headers(client):
    return register_and_login(client)


@pytest.fixture()
def project(client, auth_headers):
    r = client.post(
        "/api/v1/projects", json={"name": "My New Home", "description": "3BHK duplex"}, headers=auth_headers
    )
    return r.json()


def requirement_payload(**overrides) -> dict:
    payload = {
        "plot_length": 55, "plot_width": 40, "facing": "north",
        "family_members": 5, "bedrooms": 3, "bathrooms": 3,
        "has_living_room": True, "has_dining_room": True, "has_pooja_room": True,
        "has_study_room": False, "has_utility_room": True, "balconies": 2,
        "cars": 1, "two_wheelers": 2, "floors": 2, "budget": 5_000_000,
        "vastu_compliant": True, "additional_rooms": [], "other_requirements": "Open kitchen preferred",
    }
    payload.update(overrides)
    return payload


@pytest.fixture()
def requirement(client, auth_headers, project):
    r = client.post(
        f"/api/v1/projects/{project['id']}/requirements", json=requirement_payload(), headers=auth_headers
    )
    return r.json()


@pytest.fixture()
def floor_plan(client, auth_headers, project, requirement):
    r = client.post(
        f"/api/v1/projects/{project['id']}/requirements/{requirement['id']}/generate", headers=auth_headers
    )
    return r.json()["floor_plan"]
