"""WEGEK AI factory — the LLM authors the whole site, then critiques and repairs
its own rendered output in a loop until it meets the quality bar.

This is the generative pipeline (Stage 0 plan -> codegen -> render -> critique ->
repair), as opposed to the older fixed-template engine. The LLM writes bespoke
Three.js / GLSL / particle / post-processing code per brief; a headless browser
renders and screenshots it; a multimodal critic scores the screenshots against an
Active-Theory-level rubric and emits concrete fixes; the loop repairs and repeats.
"""
