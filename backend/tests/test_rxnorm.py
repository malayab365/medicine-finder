import httpx

from app.services.rxnorm import normalize_name
from tests.conftest import load_fixture


async def test_normalize_name_exact_match():
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/rxcui.json"):
            return httpx.Response(200, json=load_fixture("rxnorm_rxcui_ibuprofen.json"))
        if path.endswith("/property.json"):
            return httpx.Response(200, json=load_fixture("rxnorm_property_5640.json"))
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        match = await normalize_name("ibuprofen", client=client)

    assert match is not None
    assert match.rxcui == "5640"
    assert match.name == "Ibuprofen"


async def test_normalize_name_falls_back_to_approximate():
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/rxcui.json"):
            return httpx.Response(200, json={"idGroup": {"name": "ibuprofin"}})
        if path.endswith("/approximateTerm.json"):
            return httpx.Response(
                200, json={"approximateGroup": {"candidate": [{"rxcui": "5640"}]}}
            )
        if path.endswith("/property.json"):
            return httpx.Response(200, json=load_fixture("rxnorm_property_5640.json"))
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        match = await normalize_name("ibuprofin", client=client)

    assert match is not None
    assert match.rxcui == "5640"


async def test_normalize_name_no_match():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/rxcui.json"):
            return httpx.Response(200, json={"idGroup": {"name": "zzzz"}})
        return httpx.Response(200, json={"approximateGroup": {"candidate": []}})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        match = await normalize_name("zzzz", client=client)

    assert match is None
