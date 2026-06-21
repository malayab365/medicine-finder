from pydantic import BaseModel, Field

DISCLAIMER = "Informational only. Not medical advice. Consult a healthcare provider."


class NameSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=200)


class SuggestResponse(BaseModel):
    suggestions: list[str] = []


class Label(BaseModel):
    indications: str | None = None
    dosage: str | None = None
    warnings: str | None = None
    adverse_reactions: str | None = None


class AdverseEvent(BaseModel):
    term: str
    count: int


class NameSearchResponse(BaseModel):
    query: str
    matched_name: str | None = None
    rxcui: str | None = None
    label: Label | None = None
    adverse_events: list[AdverseEvent] = []
    disclaimer: str = DISCLAIMER


EMERGENCY_MESSAGE = (
    "Your symptoms may indicate a medical emergency. Call your local emergency "
    "number (such as 911) or go to the nearest emergency room now."
)


class SymptomSearchRequest(BaseModel):
    symptoms: str = Field(min_length=1, max_length=1000)


class Candidate(BaseModel):
    name: str
    matched_name: str | None = None
    rxcui: str | None = None
    label: Label | None = None


class SymptomSearchResponse(BaseModel):
    emergency: bool = False
    message: str | None = None
    candidates: list[Candidate] = []
    disclaimer: str = DISCLAIMER
