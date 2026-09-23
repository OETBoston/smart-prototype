"""Regression coverage for description backfills and failed generation."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pandas as pd
import pytest
from api_updater import descriptions, transformer
from api_updater.utils import logic
from curb_utils.ai_client import GeminiOptions


def test_backfill_preserves_ids_content_and_existing_text(monkeypatch) -> None:
    policies = pd.DataFrame(
        {
            "curb_policy_id": ["new", "reused", "blank", "placeholder", "reviewed"],
            "description": [
                None,
                float("nan"),
                "  ",
                "NO DESCRIPTION AVAILABLE",
                "Keep exactly",
            ],
            "policy_json": ['{"rules": []}'] * 5,
            "priority": [1, 2, 3, 4, 5],
        }
    )
    original = policies.copy(deep=True)
    generate = AsyncMock(return_value=[" No Parking 9:00 AM–12:00 PM "] * 4)
    monkeypatch.setattr(transformer, "get_policy_descriptions", generate)
    result = transformer.fill_missing_policy_descriptions(policies, GeminiOptions(), 2)
    assert generate.await_args.args[0]["curb_policy_id"].tolist() == [
        "new",
        "reused",
        "blank",
        "placeholder",
    ]
    assert result.loc[4, "description"] == "Keep exactly"
    assert result.loc[0, "description"] == "No Parking 9:00 AM–12:00 PM"
    pd.testing.assert_frame_equal(
        result.drop(columns="description"), original.drop(columns="description")
    )
    pd.testing.assert_frame_equal(policies, original)
    transformer.fill_missing_policy_descriptions(result, GeminiOptions(), 2)
    assert generate.await_count == 1


@pytest.mark.parametrize(
    "result", [[], [""], ["  "], [None], ["NO DESCRIPTION AVAILABLE"]]
)
def test_incomplete_generation_fails_without_modifying_input(
    monkeypatch, result
) -> None:
    policies = pd.DataFrame(
        {"curb_policy_id": ["existing"], "description": [None], "policy_json": ["{}"]}
    )
    monkeypatch.setattr(
        transformer, "get_policy_descriptions", AsyncMock(return_value=result)
    )
    with pytest.raises(ValueError, match="incomplete"):
        transformer.fill_missing_policy_descriptions(policies, GeminiOptions(), 1)
    assert policies.loc[0, "description"] is None


def test_generation_exception_propagates(monkeypatch) -> None:
    policies = pd.DataFrame({"description": [None], "policy_json": ["{}"]})
    monkeypatch.setattr(
        transformer,
        "get_policy_descriptions",
        AsyncMock(side_effect=RuntimeError("API failed")),
    )
    with pytest.raises(RuntimeError, match="API failed"):
        transformer.fill_missing_policy_descriptions(policies, GeminiOptions(), 1)


@pytest.mark.parametrize("text", [None, "", "  ", "NO DESCRIPTION AVAILABLE"])
def test_empty_model_response_is_not_publishable(monkeypatch, text) -> None:
    monkeypatch.setattr(
        descriptions,
        "call_gemini_client_aio",
        AsyncMock(return_value=SimpleNamespace(text=text)),
    )
    with pytest.raises(ValueError, match="empty or placeholder"):
        asyncio.run(
            descriptions.generate_description(
                object(),
                asyncio.Semaphore(1),
                "prompt",
                "instructions",
                GeminiOptions(),
            )
        )


def test_empty_batch_never_initializes_gemini(monkeypatch) -> None:
    def unexpected_client() -> None:
        raise AssertionError("Empty batch must not initialize Gemini")

    monkeypatch.setattr(logic, "init_gemini_client", unexpected_client)
    assert (
        asyncio.run(logic.get_policy_descriptions(pd.DataFrame(), GeminiOptions(), 1))
        == []
    )
