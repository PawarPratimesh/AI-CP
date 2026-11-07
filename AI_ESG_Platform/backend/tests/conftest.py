"""Shared test fixtures for Green Software Intelligence tests.

Sets up an isolated SQLite database and a minimal FastAPI app containing
only the green router (avoids loading the heavy sentence-transformers model).
"""

import os
import tempfile

# Set test database path BEFORE any green module imports.
_fd, _test_db_path = tempfile.mkstemp(suffix=".db")
os.close(_fd)
os.environ["GREEN_DB_PATH"] = _test_db_path


import pytest  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.green.router import router as green_router  # noqa: E402


@pytest.fixture
def client():
    """Return a TestClient for a minimal app with only green routes."""
    app = FastAPI()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(green_router)
    return TestClient(app)
