import pytest

from sciencelogo_mcp.helper import RacketHelper


@pytest.fixture(scope="session")
def helper():
    racket = RacketHelper()
    yield racket
    racket.close()
