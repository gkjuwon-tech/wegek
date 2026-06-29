from __future__ import annotations

import asyncio

from app.clients.bfl import BFLClient
from app.clients.gemini_image import GeminiImageClient
from app.clients.llm import LLMClient
from app.clients.tripo import TripoClient, _is_url
from app.config import Settings
from app.pipeline.stage1_images import select_image_client
from app.pipeline.stage6_codegen import _build_bundle
from app.schemas import GlobalStyle, Object3D, Section, SitePlan


def _settings(**overrides) -> Settings:
    return Settings(_env_file=None, **overrides)  # type: ignore[call-arg]


# --- planner provider resolution ------------------------------------------- #
def test_llm_resolves_gemini_when_selected():
    llm = LLMClient(_settings(planner_provider="gemini", gemini_api_key="g"))
    assert llm.provider == "gemini"
    assert llm.available
    assert llm.label == "gemini:gemini-2.5-flash"


def test_llm_auto_prefers_anthropic_then_openai_then_gemini():
    assert LLMClient(_settings(anthropic_api_key="a", openai_api_key="o", gemini_api_key="g")).provider == "anthropic"
    assert LLMClient(_settings(openai_api_key="o", gemini_api_key="g")).provider == "openai"
    assert LLMClient(_settings(gemini_api_key="g")).provider == "gemini"
    assert LLMClient(_settings()).provider == "none"


def test_llm_gemini_selected_but_no_key_is_unavailable():
    assert not LLMClient(_settings(planner_provider="gemini")).available


# --- image provider selection ---------------------------------------------- #
def test_select_image_client_auto_prefers_bfl_then_gemini():
    assert isinstance(select_image_client(_settings(bfl_api_key="b", gemini_api_key="g")), BFLClient)
    assert isinstance(select_image_client(_settings(gemini_api_key="g")), GeminiImageClient)
    assert select_image_client(_settings()) is None


def test_select_image_client_explicit_choice():
    # explicit gemini ignores a present bfl key
    assert isinstance(
        select_image_client(_settings(image_provider="gemini", bfl_api_key="b", gemini_api_key="g")),
        GeminiImageClient,
    )
    # explicit bfl with no bfl key -> None (no silent gemini fallback)
    assert select_image_client(_settings(image_provider="bfl", gemini_api_key="g")) is None


# --- tripo reference handling ----------------------------------------------- #
def test_tripo_url_detection_and_descriptor():
    assert _is_url("https://x/y.png")
    assert not _is_url("/tmp/local.png")

    client = TripoClient(_settings(tripo_api_key="t"))
    desc = asyncio.run(client._file_descriptor(None, "https://cdn/x.png"))  # type: ignore[arg-type]
    assert desc == {"type": "png", "url": "https://cdn/x.png"}


# --- bundle no longer leaks intermediate reference images -------------------- #
def test_bundle_strips_reference_images():
    plan = SitePlan(
        project_name="WATCH",
        sections=[Section(id="hero", objects=["o1"])],
        objects=[Object3D(id="o1", description="d", reference_images=["/tmp/secret_path.png"])],
        global_style=GlobalStyle(),
    )
    bundle = _build_bundle(plan)
    obj = bundle["plan"]["objects"][0]
    assert "reference_images" not in obj
    assert "/tmp/secret_path.png" not in str(bundle)
