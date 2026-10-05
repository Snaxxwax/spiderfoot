"""Config endpoints must never return the PostgreSQL password (GET /config, /config/export
and /config/diff did, via __database and summary.db_path)."""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from spiderfoot.api.routers.config import _RedactingRoute
from fastapi import APIRouter

SECRET = "S3cretPw-not-real"


def test_every_config_route_masks_credentialed_urls():
    router = APIRouter(route_class=_RedactingRoute)

    @router.get("/export")
    def export():
        return {"__database": f"postgresql://spiderfoot:{SECRET}@postgres:5432/spiderfoot",
                "summary": {"db_path": f"password={SECRET} host=postgres"}, "n": 1}

    app = FastAPI()
    app.include_router(router)
    response = TestClient(app).get("/export")
    assert response.status_code == 200
    assert SECRET not in response.text
    body = response.json()  # still valid JSON with the right length
    assert body["__database"] == "postgresql://spiderfoot:***@postgres:5432/spiderfoot"
    assert body["summary"]["db_path"] == "password=*** host=postgres"
    assert body["n"] == 1
