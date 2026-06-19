from app.cache import async_lru_cache


async def test_caches_result_and_skips_second_call():
    calls = []

    @async_lru_cache(maxsize=8)
    async def fn(x, *, client=None):
        calls.append(x)
        return x * 2

    assert await fn(3) == 6
    assert await fn(3) == 6  # served from cache
    assert calls == [3]


async def test_client_kwarg_excluded_from_key():
    calls = []

    @async_lru_cache(maxsize=8)
    async def fn(x, *, client=None):
        calls.append(client)
        return x

    await fn(1, client="a")
    await fn(1, client="b")  # different client, same key -> cached
    assert calls == ["a"]


async def test_evicts_least_recently_used():
    @async_lru_cache(maxsize=2)
    async def fn(x):
        return x

    await fn(1)
    await fn(2)
    await fn(1)  # refresh 1 as most-recently used
    await fn(3)  # evicts 2 (least recently used)
    assert fn.cache_info()["size"] == 2


async def test_cache_clear():
    calls = []

    @async_lru_cache(maxsize=8)
    async def fn(x):
        calls.append(x)
        return x

    await fn(5)
    fn.cache_clear()
    await fn(5)
    assert calls == [5, 5]
