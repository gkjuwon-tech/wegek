# WEGEK Backend

FastAPI orchestrator for the WEGEK 7-stage AI 3D website pipeline.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:app --reload   # http://localhost:8000/docs

ruff check . && mypy app && pytest -q
```

All external integrations are optional — see [`../.env.example`](../.env.example).
With no keys the pipeline runs fully on procedural generation. Layout:

- `app/config.py` — settings (env-driven, all keys optional)
- `app/schemas.py` — pipeline data models (`SitePlan`, `Job`, `Stage`, …)
- `app/store.py` — SQLite persistence + asyncio pub/sub for WebSocket fanout
- `app/clients/` — real HTTP clients (LLM, BFL/FLUX, Tripo)
- `app/presets/` — shader / lighting / camera libraries + category mapping
- `app/pipeline/` — `stage0..7` + `orchestrator` + codegen `templates/`
- `app/routers/` — REST (`jobs`) + WebSocket (`ws`)
- `app/main.py` — app factory, CORS, static `/sites`, optional built studio
