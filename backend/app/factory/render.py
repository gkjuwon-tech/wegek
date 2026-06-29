"""Headless render + scroll screenshots + console error capture (Playwright sync).

Serves the site dir over a local HTTP server (so ES modules + vendored libs load)
and drives a headless Chromium to render the WebGL site and shoot it at several
scroll positions — the eyes of the critique loop.
"""
from __future__ import annotations

import functools
import http.server
import socketserver
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright

CHROME = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"


def _serve(directory: Path) -> tuple[socketserver.TCPServer, int]:
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(directory))
    httpd = socketserver.TCPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, httpd.server_address[1]


def render(site_dir: str | Path, out_prefix: str, shots: int = 4) -> dict:
    """Render the site and capture `shots`+1 scroll screenshots.

    Returns {ready, errors:[...], images:[paths], scroll_height}.
    """
    site_dir = Path(site_dir)
    httpd, port = _serve(site_dir)
    errors: list[str] = []
    images: list[str] = []
    ready = False
    sh = 0
    try:
        with sync_playwright() as p:
            b = p.chromium.launch(
                executable_path=CHROME,
                args=["--no-sandbox", "--use-gl=angle", "--use-angle=swiftshader",
                      "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"],
            )
            pg = b.new_page(viewport={"width": 1440, "height": 900})

            def _benign(t: str) -> bool:
                # offline font CDNs / favicon are harmless in the headless sandbox.
                return any(s in t for s in ("fonts.googleapis", "fonts.gstatic", "favicon"))

            # Console "Failed to load resource" lines carry no URL, so we can't tell a
            # benign font 404 from a real one — track real resource failures via
            # requestfailed (which has the URL) and ignore generic resource console noise.
            pg.on("console", lambda m: (errors.append(f"[{m.type}] {m.text[:240]}")
                                        if m.type == "error" and "Failed to load resource" not in m.text else None))
            pg.on("requestfailed", lambda req: (errors.append(f"[requestfailed] {req.url[:160]}")
                                                if not _benign(req.url) else None))
            pg.on("pageerror", lambda e: errors.append(f"[pageerror] {str(e)[:240]}"))
            pg.goto(f"http://127.0.0.1:{port}/index.html", wait_until="load", timeout=45000)
            try:
                pg.wait_for_function("window.__WEGEK_READY__===true", timeout=30000)
                ready = True
            except Exception:
                errors.append("[harness] __WEGEK_READY__ never set (likely a JS/GLSL error or hang)")
            pg.wait_for_timeout(2500)
            sh = pg.evaluate("document.body.scrollHeight") or 900
            vh = 900
            steps = max(1, min(shots, round((sh - vh) / vh) or 1))
            for i in range(steps + 1):
                y = int(i * max(0, sh - vh) / max(1, steps))
                pg.evaluate(f"window.scrollTo(0,{y})")
                pg.wait_for_timeout(1500)
                out = f"{out_prefix}_{i}.png"
                pg.screenshot(path=out)
                images.append(out)
            b.close()
    finally:
        httpd.shutdown()
    return {"ready": ready, "errors": errors, "images": images, "scroll_height": sh}
