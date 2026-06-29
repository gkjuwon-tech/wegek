from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient

from app.main import app


def test_health_and_presets():
    with TestClient(app) as client:
        r = client.get("/api/health")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "ok"
        assert "planner_llm" in body["integrations"]

        r = client.get("/api/presets")
        assert r.status_code == 200
        presets = r.json()
        assert "gradient_noise_dark" in presets["shaders"]
        assert "studio_dramatic" in presets["lighting"]


def test_create_job_runs_offline_pipeline_to_completion():
    with TestClient(app) as client:
        r = client.post("/api/jobs", json={"prompt": "luxury watch landing page, mechanism reveal"})
        assert r.status_code == 201
        job_id = r.json()["id"]

        # poll until the background pipeline finishes
        final = None
        for _ in range(60):
            jr = client.get(f"/api/jobs/{job_id}")
            assert jr.status_code == 200
            final = jr.json()
            if final["status"] in ("succeeded", "failed"):
                break
            asyncio.run(asyncio.sleep(0.25))

        assert final is not None
        assert final["status"] == "succeeded", final.get("error")
        assert final["site_url"] == f"/sites/{job_id}/index.html"
        assert final["plan"]["project_name"]
        assert final["review_score"] is not None

        # generated site is served and is real HTML
        site = client.get(final["site_url"])
        assert site.status_code == 200
        assert "gl_FragColor" in site.text


def test_get_unknown_job_404():
    with TestClient(app) as client:
        assert client.get("/api/jobs/doesnotexist").status_code == 404
