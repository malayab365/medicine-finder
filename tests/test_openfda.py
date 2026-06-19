import httpx

from app.services.openfda import fetch_adverse_events, fetch_label
from tests.conftest import load_fixture


async def test_fetch_label_by_rxcui():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["search"] == 'openfda.rxcui:"5640"'
        return httpx.Response(200, json=load_fixture("openfda_ibuprofen.json"))

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        label = await fetch_label(rxcui="5640", client=client)

    assert label is not None
    assert "temporary relief" in label.indications
    assert "every 4 to 6 hours" in label.dosage
    assert "stomach bleeding" in label.warnings.lower()
    assert "nausea" in label.adverse_reactions.lower()


async def test_fetch_label_returns_none_on_404():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"error": {"code": "NOT_FOUND"}})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        label = await fetch_label(rxcui="0000", client=client)

    assert label is None


async def test_fetch_label_requires_rxcui_or_name():
    label = await fetch_label()
    assert label is None


async def test_fetch_adverse_events_by_rxcui():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["search"] == 'patient.drug.openfda.rxcui:"5640"'
        assert request.url.params["count"] == "patient.reaction.reactionmeddrapt.exact"
        return httpx.Response(200, json=load_fixture("openfda_event_ibuprofen.json"))

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        events = await fetch_adverse_events(rxcui="5640", limit=3, client=client)

    assert [e.term for e in events] == ["Nausea", "Drug Ineffective", "Headache"]
    assert events[0].count == 5321


async def test_fetch_adverse_events_returns_empty_on_404():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"error": {"code": "NOT_FOUND"}})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        events = await fetch_adverse_events(rxcui="0000", client=client)

    assert events == []


async def test_fetch_adverse_events_requires_rxcui_or_name():
    assert await fetch_adverse_events() == []
