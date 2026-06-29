"""Thin sync Gemini client for the factory (codegen + multimodal critique).

Uses Gemini's OpenAI-compatible endpoint, which accepts both long text completions
and multimodal messages (image_url data URIs) — so the same surface generates code
and critiques screenshots.
"""
from __future__ import annotations

import base64
import json
import os
import re

import httpx

BASE = os.environ.get("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta")
KEY = os.environ.get("GEMINI_API_KEY", "")
MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash")
TIMEOUT = float(os.environ.get("FACTORY_LLM_TIMEOUT", "300"))


def _post(messages: list[dict], max_tokens: int) -> str:
    resp = httpx.post(
        f"{BASE}/openai/chat/completions",
        headers={"Authorization": f"Bearer {KEY}"},
        json={"model": MODEL, "max_tokens": max_tokens, "messages": messages},
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"] or ""


def complete(system: str, user: str, max_tokens: int = 32000) -> str:
    return _post(
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        max_tokens,
    )


def complete_with_images(system: str, user: str, image_paths: list[str], max_tokens: int = 4000) -> str:
    content: list[dict] = [{"type": "text", "text": user}]
    for p in image_paths:
        with open(p, "rb") as fh:
            b64 = base64.b64encode(fh.read()).decode()
        content.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}})
    return _post(
        [{"role": "system", "content": system}, {"role": "user", "content": content}],
        max_tokens,
    )


def strip_html(text: str) -> str:
    text = text.strip()
    m = re.search(r"```(?:html)?\s*(.*?)```", text, re.DOTALL)
    if m:
        text = m.group(1).strip()
    i = text.lower().find("<!doctype")
    if i == -1:
        i = text.lower().find("<html")
    return text[i:] if i != -1 else text


def parse_json(text: str) -> dict:
    text = text.strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if m:
        text = m.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        a, b = text.find("{"), text.rfind("}")
        if a != -1 and b != -1:
            return json.loads(text[a:b + 1])
        raise
