"""Minimal client for TypeSafe's System One API (Jev), with a content-addressed cache.

Endpoint and schema from https://docs.typesafe.ai/api (checked 2026-09-29):
``POST https://api.typesafe.ai/v1/systemone`` with ``Authorization: Bearer <key>`` and a
body ``{"state", "model", "questions"}``.  Only input tokens are billed ($0.042 / Mtok for
jev-1.13).  The model is pinned to ``jev-1.13.0`` so an alias move cannot change results
mid-experiment (docs/models: "pin that version's ID instead of the alias").

The API key is read from the environment (``JEV_API_KEY``) or from a ``KEY=value`` file
named by ``JEV_ENV_FILE``; it is never written to the cache, logs or results.
"""

from __future__ import annotations

import hashlib
import json
import os
import random
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ENDPOINT = "https://api.typesafe.ai/v1/systemone"
MODEL = "jev-1.13.0"
USD_PER_INPUT_TOKEN = 0.042 / 1_000_000
MAX_CHOICE_OPTIONS = 255


def load_api_key() -> str:
    key = os.environ.get("JEV_API_KEY")
    if not key and os.environ.get("JEV_ENV_FILE"):
        for line in Path(os.environ["JEV_ENV_FILE"]).read_text().splitlines():
            if line.startswith("JEV_API_KEY="):
                key = line.split("=", 1)[1].strip()
    if not key:
        raise RuntimeError("set JEV_API_KEY (or JEV_ENV_FILE pointing at a KEY=value file)")
    return key


@dataclass
class Usage:
    requests: int = 0
    cache_hits: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    seconds: float = 0.0
    retries: int = 0

    @property
    def usd(self) -> float:
        return self.input_tokens * USD_PER_INPUT_TOKEN

    def as_dict(self) -> dict[str, float | int]:
        return {**self.__dict__, "usd": self.usd}


@dataclass
class JevClient:
    cache_dir: Path
    model: str = MODEL
    timeout: float = 90.0
    max_attempts: int = 6
    usage: Usage = field(default_factory=Usage)
    _key: str | None = None
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def _cache_path(self, body: dict[str, Any]) -> Path:
        digest = hashlib.sha256(
            json.dumps(body, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()
        return self.cache_dir / digest[:2] / f"{digest}.json"

    def ask(self, state: Any, questions: dict[str, Any]) -> dict[str, Any]:
        """One request; returns the parsed response (from cache when available)."""
        for q in questions.values():
            if q.get("type") == "choice" and len(q["criteria"]) > MAX_CHOICE_OPTIONS:
                raise ValueError("too many choice options")
        body = {"state": state, "model": self.model, "questions": questions}
        path = self._cache_path(body)
        if path.exists():
            with self._lock:
                self.usage.cache_hits += 1
            cached: dict[str, Any] = json.loads(path.read_text())["response"]
            return cached
        if self._key is None:
            self._key = load_api_key()
        data = json.dumps(body, ensure_ascii=False).encode()
        t0 = time.perf_counter()
        for attempt in range(self.max_attempts):
            req = urllib.request.Request(
                ENDPOINT,
                data=data,
                method="POST",
                headers={
                    "Authorization": f"Bearer {self._key}",
                    "Content-Type": "application/json",
                },
            )
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    out: dict[str, Any] = json.loads(resp.read())
                break
            except urllib.error.HTTPError as exc:
                if exc.code in (429, 500, 502, 503, 504, 529) and attempt + 1 < self.max_attempts:
                    with self._lock:
                        self.usage.retries += 1
                    retry_after = exc.headers.get("retry-after")
                    time.sleep(float(retry_after) if retry_after else 2**attempt + random.random())
                    continue
                detail = exc.read().decode(errors="replace")[:500]
                raise RuntimeError(f"Jev API error {exc.code}: {detail}") from None
            except (urllib.error.URLError, TimeoutError):
                if attempt + 1 < self.max_attempts:
                    with self._lock:
                        self.usage.retries += 1
                    time.sleep(2**attempt + random.random())
                    continue
                raise
        u = out.get("usage", {})
        with self._lock:
            self.usage.requests += 1
            self.usage.seconds += time.perf_counter() - t0
            self.usage.input_tokens += int(u.get("input_tokens", 0))
            self.usage.output_tokens += int(u.get("output_tokens", 0))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"request": body, "response": out}, ensure_ascii=False))
        return out
