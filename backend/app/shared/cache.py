"""A tiny async-aware LRU cache.

`functools.lru_cache` caches the returned coroutine, which can only be awaited
once, so it can't wrap async functions. This decorator awaits the call and caches
the *result*. Keys are built from the call's args and kwargs, excluding `client`
(the injected HTTP client is irrelevant to the result and not part of the key).
"""

from collections import OrderedDict
from functools import wraps


def async_lru_cache(maxsize: int = 256):
    def decorator(func):
        cache: OrderedDict = OrderedDict()

        @wraps(func)
        async def wrapper(*args, **kwargs):
            key = (args, tuple(sorted((k, v) for k, v in kwargs.items() if k != "client")))
            if key in cache:
                cache.move_to_end(key)
                return cache[key]
            result = await func(*args, **kwargs)
            cache[key] = result
            cache.move_to_end(key)
            if len(cache) > maxsize:
                cache.popitem(last=False)
            return result

        wrapper.cache_clear = cache.clear
        wrapper.cache_info = lambda: {"size": len(cache), "maxsize": maxsize}
        return wrapper

    return decorator
