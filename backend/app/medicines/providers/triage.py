"""Symptom text → candidate OTC drug names via an LLM (OpenRouter, OpenAI-compatible).

The LLM proposes candidate *names* only; the factual label details shown to the user
are re-fetched from OpenFDA, keeping the model out of the factual-claims path. A
hard-coded emergency keyword check (`is_emergency`) is meant to run BEFORE this is
ever called. Raw symptom text is never logged.
"""

import json
import logging
from dataclasses import dataclass, field

from openai import AsyncOpenAI

from app.core.config import settings

logger = logging.getLogger(__name__)

# Hard-coded safety net. The caller runs this before any LLM call and short-circuits.
EMERGENCY_KEYWORDS = (
    "chest pain",
    "suicid",  # suicide, suicidal
    "kill myself",
    "severe bleeding",
    "won't stop bleeding",
    "wont stop bleeding",
    "stroke",
    "drooping",  # facial drooping — stroke sign, robust to phrasing
    "slurred",  # slurred speech — stroke sign
    "numbness on one side",
    "can't breathe",
    "cant breathe",
    "cannot breathe",
    "difficulty breathing",
)

SYSTEM_PROMPT = (
    "You are a cautious assistant for an informational medicine-lookup tool. "
    "Given a user's described symptoms, suggest up to 5 common over-the-counter "
    "medicines commonly used for such symptoms. Prefer generic names. "
    'Respond ONLY with a JSON object of the form {"emergency": false, '
    '"candidates": ["name1", "name2"]}. If the symptoms suggest a medical emergency '
    "(e.g. chest pain, severe bleeding, stroke signs, suicidal thoughts), respond with "
    '{"emergency": true, "candidates": []} and suggest nothing. '
    "Do not include dosages, explanations, or any text outside the JSON."
)


@dataclass
class TriageResult:
    emergency: bool = False
    candidates: list[str] = field(default_factory=list)


def is_emergency(symptoms: str) -> bool:
    text = symptoms.lower()
    return any(keyword in text for keyword in EMERGENCY_KEYWORDS)


def _parse(content: str) -> TriageResult:
    data = json.loads(content)
    if data.get("emergency"):
        return TriageResult(emergency=True)
    candidates = [str(c).strip() for c in (data.get("candidates") or []) if str(c).strip()]
    return TriageResult(candidates=candidates[:5])


async def triage(symptoms: str, *, client: AsyncOpenAI | None = None) -> TriageResult:
    """Ask the LLM for candidate medicine names. Run `is_emergency` before calling."""
    own_client = client is None
    client = client or AsyncOpenAI(
        api_key=settings.openrouter_api_key, base_url=settings.openrouter_base_url
    )
    try:
        response = await client.chat.completions.create(
            model=settings.openrouter_model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": symptoms},
            ],
            temperature=0,
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content or "{}"
        try:
            result = _parse(content)
        except (json.JSONDecodeError, ValueError):
            logger.warning("triage: could not parse LLM response")
            result = TriageResult()
        # Log non-PII counts only — never the raw symptom text.
        logger.info(
            "triage complete: emergency=%s candidates=%d",
            result.emergency,
            len(result.candidates),
        )
        return result
    finally:
        if own_client:
            await client.close()
