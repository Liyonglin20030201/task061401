import random
import time
from collections import OrderedDict
from threading import Lock


class TTLCache:
    def __init__(self, maxsize: int = 256, ttl: int = 60, jitter: float = 0.2):
        self._cache: OrderedDict = OrderedDict()
        self._maxsize = maxsize
        self._ttl = ttl
        self._jitter = jitter  # ±20% random spread on expiry
        self._lock = Lock()

    def _effective_ttl(self) -> float:
        spread = self._ttl * self._jitter
        return self._ttl + random.uniform(-spread, spread)

    def get(self, key: str):
        with self._lock:
            if key in self._cache:
                value, expires_at = self._cache[key]
                if time.time() < expires_at:
                    self._cache.move_to_end(key)
                    return value
                del self._cache[key]
        return None

    def set(self, key: str, value):
        with self._lock:
            expires_at = time.time() + self._effective_ttl()
            self._cache[key] = (value, expires_at)
            if len(self._cache) > self._maxsize:
                self._cache.popitem(last=False)

    def invalidate(self, key: str):
        with self._lock:
            self._cache.pop(key, None)

    def clear(self):
        with self._lock:
            self._cache.clear()


user_cache = TTLCache(maxsize=128, ttl=60, jitter=0.2)
kb_access_cache = TTLCache(maxsize=256, ttl=120, jitter=0.2)
query_cache = TTLCache(maxsize=512, ttl=30, jitter=0.3)
