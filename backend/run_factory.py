"""Driver for the WEGEK AI factory loop."""
from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

from app.factory import loop  # noqa: E402

BRIEF = (
    "CYPHER SHADOW X — a limited-edition hypebeast sneaker drop. Futuristic chrome-and-"
    "translucent high-top. Street-luxury, neon-noir energy. Build an immersive, "
    "Active-Theory-calibre WebGL scrollytelling site that makes this single sneaker feel "
    "like a religious artifact: particle storms, glass/iridescent materials, cinematic camera, "
    "kinetic typography. 4-5 scroll beats. Deep, moody, deliberate palette."
)

if __name__ == "__main__":
    job = sys.argv[1] if len(sys.argv) > 1 else "factory-cypher"
    iters = int(sys.argv[2]) if len(sys.argv) > 2 else 4
    site = Path("_data/sites") / job
    res = loop.run(
        BRIEF, site,
        glb=Path("_data/assets/sneaker.glb"),
        max_iters=iters, pass_score=0.85,
    )
    print("RESULT:", res["site_dir"], "best", res["best"]["score"])
