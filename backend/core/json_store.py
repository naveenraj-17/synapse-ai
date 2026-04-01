"""
Thread-safe JSON file persistence with optional TTL caching.
Replaces duplicate load/save patterns across route files.
"""
import json
import os
import threading
import time


class JsonStore:
    def __init__(self, path: str, default_factory=list, cache_ttl: float = 0):
        """
        Args:
            path: Path to the JSON file.
            default_factory: Callable returning the default value (list or dict).
            cache_ttl: Seconds to cache loaded data (0 = no cache).
        """
        self.path = path
        self.default_factory = default_factory
        self._lock = threading.Lock()
        self._cache = None
        self._cache_time: float = 0
        self._cache_ttl = cache_ttl

    def load(self):
        with self._lock:
            now = time.time()
            if self._cache_ttl > 0 and self._cache is not None and (now - self._cache_time) < self._cache_ttl:
                return self._cache

            if not os.path.exists(self.path):
                return self.default_factory()
            try:
                with open(self.path, "r") as f:
                    data = json.load(f)
                if self._cache_ttl > 0:
                    self._cache = data
                    self._cache_time = now
                return data
            except Exception:
                return self.default_factory()

    def save(self, data):
        with self._lock:
            with open(self.path, "w") as f:
                json.dump(data, f, indent=4)
            if self._cache_ttl > 0:
                self._cache = data
                self._cache_time = time.time()
