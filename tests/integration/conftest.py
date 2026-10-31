"""Integration fixtures."""

import pytest

from clipflow.domain.events import (
    CancellationToken,
)
from clipflow.providers.base import ExecutionContext
from tests.support.media import NoAuth


@pytest.fixture
def context():
    from tests.instagram_fixtures import Gate

    events = []
    return ExecutionContext(CancellationToken(), events.append, NoAuth(), Gate()), events
