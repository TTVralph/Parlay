from __future__ import annotations

from collections import OrderedDict
from typing import Generic, TypeVar


K = TypeVar('K')
V = TypeVar('V')


class RequestCache(Generic[K, V]):
    """Minimal in-memory cache for provider HTTP payloads."""

    def __init__(self, *, max_entries: int = 128) -> None:
        self._max_entries = max_entries
        self._entries: OrderedDict[K, V] = OrderedDict()

    def get(self, key: K) -> V | None:
        if key not in self._entries:
            return None
        value = self._entries.pop(key)
        self._entries[key] = value
        return value

    def set(self, key: K, value: V) -> None:
        if key in self._entries:
            self._entries.pop(key)
        self._entries[key] = value
        while len(self._entries) > self._max_entries:
            self._entries.popitem(last=False)

    def __contains__(self, key: K) -> bool:
        return key in self._entries

    def __getitem__(self, key: K) -> V:
        return self._entries[key]

    def __setitem__(self, key: K, value: V) -> None:
        self.set(key, value)

