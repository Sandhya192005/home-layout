"""End-to-end smoke test of the API using an isolated in-memory SQLite DB
(not the configured Postgres) — purely to validate routing/ORM/auth wiring.

Run: python scripts/smoke_test_api.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
import app.models  # noqa: F401 register all models on Base.metadata

engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base.metadata.create_all(bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


from app.main import app
from fastapi.testclient import TestClient

app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)

# 1. Register + login
r = client.post("/api/v1/auth/register", json={
    "email": "test@example.com", "full_name": "Test User", "password": "supersecret123"
})
assert r.status_code == 201, r.text
print("register OK", r.json())

r = client.post("/api/v1/auth/login", data={"username": "test@example.com", "password": "supersecret123"})
assert r.status_code == 200, r.text
token = r.json()["access_token"]
headers = {"Authorization": f"Bearer {token}"}
print("login OK")

r = client.get("/api/v1/auth/me", headers=headers)
assert r.status_code == 200, r.text
print("me OK", r.json())

# 2. Create project
r = client.post("/api/v1/projects", json={"name": "My New Home", "description": "3BHK duplex"}, headers=headers)
assert r.status_code == 201, r.text
project = r.json()
print("project OK", project)

# 3. Submit requirement
req_payload = {
    "plot_length": 55, "plot_width": 40, "facing": "north",
    "family_members": 5, "bedrooms": 3, "bathrooms": 3,
    "has_living_room": True, "has_dining_room": True, "has_pooja_room": True,
    "has_study_room": False, "has_utility_room": True, "balconies": 2,
    "cars": 1, "two_wheelers": 2, "floors": 2, "budget": 5_000_000,
    "vastu_compliant": True, "additional_rooms": [], "other_requirements": "Open kitchen preferred",
}
r = client.post(f"/api/v1/projects/{project['id']}/requirements", json=req_payload, headers=headers)
assert r.status_code == 201, r.text
requirement = r.json()
print("requirement OK", requirement["id"])

# 4. Generate floor plan
r = client.post(
    f"/api/v1/projects/{project['id']}/requirements/{requirement['id']}/generate", headers=headers
)
assert r.status_code == 200, r.text
gen = r.json()
print("generate OK — warnings:", gen["warnings"])
print("floor_plan id:", gen["floor_plan"]["id"], "version:", gen["floor_plan"]["version"],
      "area:", gen["floor_plan"]["total_built_up_area"], "cost:", gen["floor_plan"]["estimated_cost"])
assert len(gen["floor_plan"]["plan_data"]["floors"]) == 2

# 5. Fetch latest floor plan + suggestions
r = client.get(f"/api/v1/projects/{project['id']}/floorplans/latest", headers=headers)
assert r.status_code == 200, r.text
print("latest floorplan fetch OK")

r = client.get(f"/api/v1/projects/{project['id']}/suggestions/latest", headers=headers)
assert r.status_code == 200, r.text
print("suggestions OK:", len(r.json()["suggestions"]), "suggestions")

# 6. Regenerate with changed requirement -> should get a NEW version and different plan
req_payload2 = dict(req_payload)
req_payload2["plot_width"] = 30
req_payload2["cars"] = 0
r = client.post(f"/api/v1/projects/{project['id']}/requirements", json=req_payload2, headers=headers)
assert r.status_code == 201, r.text
requirement2 = r.json()
r = client.post(
    f"/api/v1/projects/{project['id']}/requirements/{requirement2['id']}/generate", headers=headers
)
assert r.status_code == 200, r.text
gen2 = r.json()
print("regenerate OK — version:", gen2["floor_plan"]["version"], "area:", gen2["floor_plan"]["total_built_up_area"])
assert gen2["floor_plan"]["version"] == 2
assert gen2["floor_plan"]["total_built_up_area"] != gen["floor_plan"]["total_built_up_area"]
print("\nDynamic behavior confirmed: changing plot width + cars changed the generated plan and area.")

# 7. Auth boundary check — another user cannot see this project
r = client.post("/api/v1/auth/register", json={
    "email": "other@example.com", "full_name": "Other User", "password": "supersecret123"
})
r2 = client.post("/api/v1/auth/login", data={"username": "other@example.com", "password": "supersecret123"})
other_headers = {"Authorization": f"Bearer {r2.json()['access_token']}"}
r3 = client.get(f"/api/v1/projects/{project['id']}", headers=other_headers)
assert r3.status_code == 403, r3.text
print("cross-user auth isolation OK (403 as expected)")

print("\nALL SMOKE TESTS PASSED")
