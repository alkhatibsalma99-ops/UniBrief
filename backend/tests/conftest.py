import os
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import text

from app.database import engine


# Protect the original database.
if (
    engine.url.database != "unibrief_test_db"
    or engine.url.host not in ("127.0.0.1", "localhost")
):
    raise RuntimeError(
        "Tests must use the local unibrief_test_db database."
    )

with engine.connect() as connection:
    actual_database = connection.execute(
        text("SELECT current_database()")
    ).scalar()

    if actual_database != "unibrief_test_db":
        raise RuntimeError("Unsafe database connection.")


# Protect the original translation cache.
cache_path = os.getenv("TRANSLATION_CACHE_PATH")

if (
    not cache_path
    or not Path(cache_path).name.startswith("unibrief_test_")
    or Path(cache_path).resolve().parent
    != Path(os.environ["TEMP"]).resolve()
):
    raise RuntimeError("Unsafe translation cache path.")


# Block real R2 connections during tests.
def block_r2_connection(*args, **kwargs):
    raise RuntimeError(
        "Real R2 connections are forbidden during tests."
    )


@pytest.fixture(autouse=True)
def protect_external_storage():
    with patch(
        "app.r2_storage.get_r2_client",
        side_effect=block_r2_connection,
    ):
        yield
# Block real AI requests during tests.

def block_ai_request(*args, **kwargs):

    raise RuntimeError(
        "Real AI requests are forbidden during tests."
    )


@pytest.fixture(autouse=True)
def protect_external_ai():

    with patch(
        "app.ai_service.client.responses.create",
        side_effect=block_ai_request,
    ):

        yield