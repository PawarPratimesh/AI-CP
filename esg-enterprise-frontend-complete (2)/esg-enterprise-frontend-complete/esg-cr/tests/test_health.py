import sys
from pathlib import Path

from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from main import app  # noqa: E402

client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_root_redirects_to_docs():
    response = client.get("/", follow_redirects=False)
    assert response.status_code in {307, 302}
    assert response.headers["location"] == "/docs"
