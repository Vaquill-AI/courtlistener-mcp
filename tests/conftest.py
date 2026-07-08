"""pytest configuration for CourtListener MCP tests."""

import os
from pathlib import Path
from typing import Any

# Provide a dummy server-side key so get_auth_headers() succeeds in the
# in-memory test client (which cannot send BYOK request headers). Set before
# importing the app so config picks it up too. Real HTTP is mocked by respx.
os.environ.setdefault("COURT_LISTENER_API_KEY", "test-token")
# Disable per-client rate limiting in tests (concurrency tests would trip it).
os.environ.setdefault("RATE_LIMIT_ENABLED", "false")

from _pytest.config import Config  # noqa: E402
from fastmcp import Client  # noqa: E402
from loguru import logger  # noqa: E402
import pytest  # noqa: E402

from app.server import ensure_setup, mcp  # noqa: E402

# Configure test logging
test_log_path = Path(__file__).parent / "test_logs" / "test.log"
test_log_path.parent.mkdir(exist_ok=True)
logger.add(test_log_path, rotation="10 MB", retention="1 week")

# Ensure server tools are set up before any tests run
ensure_setup()


@pytest.fixture
def client() -> Client[Any]:
    """Create a test client connected to the MCP server.

    Returns:
        A FastMCP test client connected to the server instance.

    """
    return Client(mcp)


def pytest_configure(config: Config) -> None:
    """Configure pytest with custom markers."""
    config.addinivalue_line(
        "markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')"
    )
    config.addinivalue_line("markers", "integration: marks tests as integration tests")


def pytest_collection_modifyitems(config: Config, items: list[pytest.Item]) -> None:
    """Skip integration tests (which hit the live CourtListener API) by default.

    Run them with a real key via: RUN_INTEGRATION=1 COURT_LISTENER_API_KEY=... pytest
    """
    if os.getenv("RUN_INTEGRATION") == "1":
        return
    skip_integration = pytest.mark.skip(
        reason="integration test; set RUN_INTEGRATION=1 and a real COURT_LISTENER_API_KEY to run"
    )
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip_integration)
