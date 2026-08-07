"""Thread-safe generic plugin registry.

The registry is the seam for every pluggable subsystem: themes, animations,
easings, exporters, placement strategies and AI providers. Third-party code
registers through the same mechanism core code uses, either directly or via
importlib entry points.
"""

from __future__ import annotations

from importlib import metadata
from threading import RLock
from typing import Callable, Generic, Iterable, TypeVar

T = TypeVar("T")


class Registry(Generic[T]):
    """A key-addressed registry of plugin values, with alias support."""

    def __init__(self, name: str, *, allow_overwrite: bool = False) -> None:
        self._name = name
        self._allow_overwrite = allow_overwrite
        self._entries: dict[str, T] = {}
        self._aliases: dict[str, str] = {}
        self._lock = RLock()

    @property
    def name(self) -> str:
        return self._name

    def register(
        self,
        key: str,
        *,
        aliases: Iterable[str] = (),
        overwrite: bool | None = None,
    ) -> Callable[[T], T]:
        """Decorator form: ``@registry.register("key")``."""

        def decorate(value: T) -> T:
            self.add(key, value, aliases=aliases, overwrite=overwrite)
            return value

        return decorate

    def add(
        self,
        key: str,
        value: T,
        *,
        aliases: Iterable[str] = (),
        overwrite: bool | None = None,
    ) -> None:
        key = key.strip()
        if not key:
            raise ValueError(f"{self._name}: cannot register an empty key")
        with self._lock:
            if key in self._entries and not (overwrite if overwrite is not None else self._allow_overwrite):
                raise KeyError(f"{self._name} {key!r} is already registered")
            self._entries[key] = value
            for alias in aliases:
                self._aliases[alias.strip()] = key

    def get(self, key: str) -> T:
        with self._lock:
            resolved = self._aliases.get(key.strip(), key.strip())
            try:
                return self._entries[resolved]
            except KeyError as exc:
                available = ", ".join(sorted(self._entries))
                raise KeyError(
                    f"no {self._name} registered as {key!r}; available: {available}"
                ) from exc

    def get_or_none(self, key: str) -> T | None:
        try:
            return self.get(key)
        except KeyError:
            return None

    @property
    def keys(self) -> list[str]:
        with self._lock:
            return list(self._entries)

    @property
    def items(self) -> dict[str, T]:
        with self._lock:
            return dict(self._entries)

    def load_entry_points(self, group: str) -> int:
        """Register plugins advertised via ``importlib.metadata`` entry points."""
        count = 0
        for ep in metadata.entry_points(group=group):
            value = ep.load()
            self.add(ep.name, value, overwrite=True)
            count += 1
        return count

    def __contains__(self, key: str) -> bool:
        return self.get_or_none(key) is not None

    def __iter__(self):
        return iter(self._entries)

    def __len__(self) -> int:
        return len(self._entries)
