"""Tests for the Flask web interface."""

import json
import threading
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from web_app import _jobs, app


@pytest.fixture
def client():
    """Flask test client with TESTING mode enabled."""
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


@pytest.fixture(autouse=True)
def clean_jobs():
    """Clear the global _jobs dict before and after each test."""
    _jobs.clear()
    yield
    _jobs.clear()


# ===========================================================================
# POST /generate
# ===========================================================================

class TestGenerateRoute:
    """Tests for the POST /generate endpoint."""

    def test_empty_url_returns_400(self, client) -> None:
        """Empty URL field returns HTTP 400."""
        resp = client.post(
            "/generate",
            data=json.dumps({"url": ""}),
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_missing_url_field_returns_400(self, client) -> None:
        """Missing URL key returns HTTP 400."""
        resp = client.post(
            "/generate",
            data=json.dumps({"strategy": "lowest_position"}),
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_valid_url_returns_job_id(self, client, monkeypatch) -> None:
        """Valid URL returns a JSON response containing a job_id key."""
        monkeypatch.setattr(threading, "Thread", MagicMock())
        resp = client.post(
            "/generate",
            data=json.dumps({"url": "https://youtu.be/test"}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert "job_id" in data
        assert len(data["job_id"]) == 8

    def test_job_created_in_jobs_dict(self, client, monkeypatch) -> None:
        """The new job_id is added to the _jobs dict with status 'running'."""
        monkeypatch.setattr(threading, "Thread", MagicMock())
        resp = client.post(
            "/generate",
            data=json.dumps({"url": "https://youtu.be/test"}),
            content_type="application/json",
        )
        job_id = resp.get_json()["job_id"]
        assert job_id in _jobs
        assert _jobs[job_id]["status"] == "running"


# ===========================================================================
# GET /stream/<job_id>
# ===========================================================================

class TestStreamRoute:
    """Tests for the GET /stream/<job_id> SSE endpoint."""

    def test_unknown_job_id_sends_error_event(self, client) -> None:
        """Streaming a non-existent job_id emits an error SSE event."""
        resp = client.get("/stream/nonexistent")
        # Consume all SSE data
        body = resp.data.decode("utf-8")
        assert '"type": "error"' in body or '"type":"error"' in body


# ===========================================================================
# GET /download/<job_id>
# ===========================================================================

class TestDownloadRoute:
    """Tests for the GET /download/<job_id> endpoint."""

    def test_unknown_job_returns_404(self, client) -> None:
        """Non-existent job_id returns 404."""
        resp = client.get("/download/nonexistent")
        assert resp.status_code == 404

    def test_job_without_xml_path_returns_404(self, client) -> None:
        """Job with xml_path=None returns 404."""
        _jobs["abc123"] = {
            "status": "done",
            "xml_path": None,
            "tab": None,
            "log": [],
            "error": None,
            "step": "done",
        }
        resp = client.get("/download/abc123")
        assert resp.status_code == 404

    def test_known_job_with_xml_returns_200(self, client, tmp_path: Path) -> None:
        """Job with a valid xml_path returns the file with HTTP 200."""
        xml_file = tmp_path / "bass_tab.xml"
        xml_file.write_text("<score/>", encoding="utf-8")
        _jobs["def456"] = {
            "status": "done",
            "xml_path": str(xml_file),
            "tab": None,
            "log": [],
            "error": None,
            "step": "done",
        }
        resp = client.get("/download/def456")
        assert resp.status_code == 200
