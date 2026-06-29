"""TEMPORARY test scaffold: source free 3D assets when Tripo is unavailable.

While Tripo (image->3D) is offline, the planner still asks for real meshes ("an
18-piece scene of ..."). This resolver turns each requested mesh into a real GLB
by searching Objaverse's LVIS-annotated subset (key-free, fetched via HTTPS) and
downloading a match. The factory's critique loop can reject a mismatch, and we
re-resolve excluding the previous pick.

This whole module is a stopgap — gate it with FACTORY_ASSET_SOURCE and remove /
swap back to Tripo once 3D generation is restored.
"""
from __future__ import annotations

import gzip
import json
import re
import subprocess
from pathlib import Path

HF = "https://huggingface.co/datasets/allenai/objaverse/resolve/main"
LVIS_URL = f"{HF}/lvis-annotations.json.gz"
PATHS_URL = f"{HF}/object-paths.json.gz"

_CACHE = Path(__file__).resolve().parent.parent.parent / "_data" / "assets_cache"
_INDEX: tuple[dict, dict] | None = None


def _curl(url: str, timeout: int = 180) -> bytes:
    r = subprocess.run(["curl", "-sL", "-m", str(timeout), url], capture_output=True)
    if r.returncode != 0 or not r.stdout:
        raise RuntimeError(f"download failed: {url}: {r.stderr.decode()[:160]}")
    return r.stdout


def _load_index() -> tuple[dict, dict]:
    """(lvis: category->[uid], paths: uid->relpath), cached on disk."""
    global _INDEX
    if _INDEX is not None:
        return _INDEX
    _CACHE.mkdir(parents=True, exist_ok=True)
    lvis_f, paths_f = _CACHE / "lvis.json", _CACHE / "object_paths.json"
    if not lvis_f.exists():
        lvis_f.write_bytes(gzip.decompress(_curl(LVIS_URL)))
    if not paths_f.exists():
        paths_f.write_bytes(gzip.decompress(_curl(PATHS_URL)))
    lvis = json.loads(lvis_f.read_text())
    paths = json.loads(paths_f.read_text())
    _INDEX = (lvis, paths)
    return _INDEX


_STOP = {"the", "and", "for", "with", "type", "kind", "old", "new"}


def _stem(t: str) -> str:
    # crude singularisation so sneaker/sneakers, shoe/shoes match
    if t.endswith("es") and len(t) > 4:
        return t[:-2]
    if t.endswith("s") and len(t) > 3:
        return t[:-1]
    return t


def _tokens(s: str) -> set[str]:
    return {_stem(t) for t in re.split(r"[^a-z0-9]+", s.lower()) if len(t) > 2 and t not in _STOP}


# expand common queries toward words that actually appear in LVIS category names
_SYN = {"sneaker": "shoe", "trainer": "shoe", "footwear": "shoe", "column": "pillar",
        "lamppost": "lamp", "streetlamp": "lamp"}


def _best_category(query: str, lvis: dict) -> str | None:
    qt = _tokens(query)
    qt |= {_SYN[t] for t in list(qt) if t in _SYN}
    if not qt:
        return None
    # an exact LVIS category named in the query wins outright
    for t in qt:
        if t in lvis:
            return t
    best, best_score = None, 0.0
    for cat in lvis:
        ct = _tokens(cat.replace("_", " "))
        if not ct:
            continue
        # exact whole-token overlap only (no substring, so "rock" != "rocking");
        # tie-break toward the more specific/shorter category name.
        overlap = len(qt & ct)
        if overlap == 0:
            continue
        score = overlap - 0.02 * len(ct)
        if score > best_score:
            best, best_score = cat, score
    return best


def resolve(query: str, dest_dir: Path, asset_id: str, exclude: set[str] | None = None) -> dict | None:
    """Download a free GLB matching `query` into dest_dir/models/<asset_id>.glb.

    Returns {id, path, uid, category, query} or None if nothing usable was found.
    """
    exclude = exclude or set()
    lvis, paths = _load_index()
    cat = _best_category(query, lvis)
    if not cat:
        return None
    candidates = [u for u in lvis[cat] if u not in exclude and u in paths]
    for uid in candidates[:6]:
        try:
            data = _curl(f"{HF}/{paths[uid]}")
        except Exception:
            continue
        if data[:4] != b"glTF":
            continue
        models = dest_dir / "models"
        models.mkdir(parents=True, exist_ok=True)
        (models / f"{asset_id}.glb").write_bytes(data)
        return {"id": asset_id, "path": f"models/{asset_id}.glb", "uid": uid,
                "category": cat, "query": query}
    return None
