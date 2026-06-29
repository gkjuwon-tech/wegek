"""Driver: critique loop over the engine (spec) pipeline."""
from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")
from app.factory import engine_loop  # noqa: E402

BRIEF = ("CYPHER SHADOW X — limited hypebeast chrome sneaker drop. Immersive Active-Theory-style "
         "3D world the camera travels through on scroll: reverent neon-noir shrine, the sneaker "
         "enshrined among architecture, particle storms, scenes that change as you scroll.")
if __name__ == "__main__":
    job = sys.argv[1] if len(sys.argv) > 1 else "loop-cypher"
    iters = int(sys.argv[2]) if len(sys.argv) > 2 else 2
    engine_loop.run(BRIEF, job, max_iters=iters, pass_score=0.85)
