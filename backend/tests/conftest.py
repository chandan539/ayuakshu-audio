"""Pytest defaults for AYUAKSHU Audio backend tests."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# Never cold-load Chatterbox during unit tests.
os.environ.setdefault("OFFLINEVOICE_SKIP_WARMUP", "1")

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
sys.path.insert(0, str(BACKEND))

from app.main import create_app  # noqa: E402


@pytest.fixture()
def client(tmp_path: Path):
    os.environ["OFFLINEVOICE_MODELS_DIR"] = str(ROOT / "models")
    os.environ["OFFLINEVOICE_DATA_DIR"] = str(tmp_path / "data")
    os.environ["OFFLINEVOICE_EXPORT_ROOT"] = str(tmp_path)
    app = create_app(data_dir=tmp_path / "data", host="127.0.0.1", port=0)
    with TestClient(app) as c:
        yield c
