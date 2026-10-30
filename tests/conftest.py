"""New tests use temporary profiles; legacy scripts run in separate processes."""

import pytest


@pytest.fixture(autouse=True)
def isolated_profile(tmp_path, monkeypatch):
    monkeypatch.setenv('CLIPFLOW_DATA_DIR', str(tmp_path / 'profile'))
