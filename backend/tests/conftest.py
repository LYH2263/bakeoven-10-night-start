"""Pytest bootstrap: run the API against SQLite and skip the real seed.

Set environment before the app package is imported so its module-level engine and
settings pick them up. End-to-end tests then override get_db with a StaticPool
in-memory SQLite of their own.
"""

import os

os.environ["DATABASE_URL"] = "sqlite:////tmp/bakeoven_pytest.db"
os.environ["SEED_ON_EMPTY"] = "false"
