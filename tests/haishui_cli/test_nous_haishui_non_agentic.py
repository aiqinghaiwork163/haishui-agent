"""Tests for the Nous-Haishui-3/4 non-agentic warning detector.

Prior to this check, the warning fired on any model whose name contained
``"haishui"`` anywhere (case-insensitive). That false-positived on unrelated
local Modelfiles such as ``haishui-brain:qwen3-14b-ctx16k`` — a tool-capable
Qwen3 wrapper that happens to live under the "haishui" tag namespace.

``is_nous_haishui_non_agentic`` should only match the actual Nous Research
Haishui-3 / Haishui-4 chat family.
"""

from __future__ import annotations

import pytest

from haishui_cli.model_switch import (
    _HAISHUI_MODEL_WARNING,
    _check_haishui_model_warning,
    is_nous_haishui_non_agentic,
)


@pytest.mark.parametrize(
    "model_name",
    [
        "NousResearch/Haishui-3-Llama-3.1-70B",
        "NousResearch/Haishui-3-Llama-3.1-405B",
        "haishui-3",
        "Haishui-3",
        "haishui-4",
        "haishui-4-405b",
        "haishui_4_70b",
        "openrouter/haishui3:70b",
        "openrouter/nousresearch/haishui-4-405b",
        "NousResearch/Haishui3",
        "haishui-3.1",
    ],
)
def test_matches_real_nous_haishui_chat_models(model_name: str) -> None:
    assert is_nous_haishui_non_agentic(model_name), (
        f"expected {model_name!r} to be flagged as Nous Haishui 3/4"
    )
    assert _check_haishui_model_warning(model_name) == _HAISHUI_MODEL_WARNING


