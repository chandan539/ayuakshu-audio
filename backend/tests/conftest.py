"""Pytest defaults for AYUAKSHU Audio backend tests."""

from __future__ import annotations

import os

# Never cold-load Chatterbox during unit tests.
os.environ.setdefault("OFFLINEVOICE_SKIP_WARMUP", "1")
