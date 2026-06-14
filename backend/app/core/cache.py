import time
from collections import OrderedDict
from threading import Lock


class TTLCache:
    def __init__(self, maxsize: int = 256, ttl: int = 60):
        self._cache: OrderedDict = OrderedDict()
        self._maxsize = maxsize
        self._ttl = ttl
        self._lock = Lock()

    def get(self, key: str):
        with self._lock:
            if key in self._cache:
                value, ts = self._cache[key]
                if time.time() - ts < self._ttl:
                    self._cache.move_to_end(key)
                    return value
                del self._cache[key]
        return None

    def set(self, key: str, value):
        with self._lock:
            self._cache[key] = (value, time.time())
            if len(self._cache) > self._maxsize:
                self._cache.popitem(last=False)

    def invalidate(self, key: str):
        with self._lock:
            self._cache.pop(key, None)

    def clear(self):
        with self._lock:
            self._cache.clear()


user_cache = TTLCache(maxsize=128, ttl=60)
kb_access_cache = TTLCache(maxsize=256, ttl=120)
query_cache = TTLCache(maxsize=512, ttl=30)
