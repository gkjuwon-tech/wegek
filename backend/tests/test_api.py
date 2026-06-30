from __future__ import annotations

from fastapi.testclient import TestClient

import app.main as main

client = TestClient(main.app)


def test_healthz():
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_create_job_returns_id(monkeypatch):
    # don't run the heavy pipeline (network + Blender) during the API test
    async def _noop(job_id: str) -> None:
        return None

    monkeypatch.setattr(main, "_run", _noop)
    r = client.post("/jobs", json={"prompt": "luxury chrome sneaker drop"})
    assert r.status_code == 200
    assert "id" in r.json()


def test_spec_404_for_unknown_job():
    assert client.get("/jobs/deadbeef/spec").status_code == 404
