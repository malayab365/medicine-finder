from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.triage import is_emergency, triage


def _fake_client(content: str) -> AsyncMock:
    client = AsyncMock()
    client.chat.completions.create = AsyncMock(
        return_value=SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
        )
    )
    return client


@pytest.mark.parametrize(
    "text",
    [
        "I have crushing chest pain",
        "thinking about suicide",
        "I want to kill myself",
        "severe bleeding from my arm",
        "my face is drooping and speech is slurred",
        "I can't breathe",
    ],
)
def test_is_emergency_detects_keywords(text):
    assert is_emergency(text) is True


def test_is_emergency_allows_normal_symptoms():
    assert is_emergency("runny nose and a sore throat") is False


async def test_triage_parses_candidates():
    client = _fake_client('{"emergency": false, "candidates": ["acetaminophen", "ibuprofen"]}')
    result = await triage("headache", client=client)
    assert result.emergency is False
    assert result.candidates == ["acetaminophen", "ibuprofen"]


async def test_triage_caps_candidates_at_five():
    client = _fake_client('{"candidates": ["a", "b", "c", "d", "e", "f", "g"]}')
    result = await triage("symptoms", client=client)
    assert len(result.candidates) == 5


async def test_triage_handles_llm_emergency_flag():
    client = _fake_client('{"emergency": true, "candidates": []}')
    result = await triage("something", client=client)
    assert result.emergency is True
    assert result.candidates == []


async def test_triage_handles_unparseable_response():
    client = _fake_client("not json at all")
    result = await triage("symptoms", client=client)
    assert result.emergency is False
    assert result.candidates == []
