import pytest

from motion_caption.registry import Registry


def test_register_and_get():
    registry: Registry[int] = Registry("thing")
    registry.add("a", 1)
    assert registry.get("a") == 1


def test_decorator_form():
    registry = Registry("thing")
    values = []

    @registry.register("b")
    def build():
        return "made"

    values.append(build)
    assert registry.get("b")() == "made"


def test_aliases():
    registry = Registry("thing")
    registry.add("full", 10, aliases=["short"])
    assert registry.get("short") == 10


def test_duplicate_rejected():
    registry = Registry("thing")
    registry.add("a", 1)
    with pytest.raises(KeyError):
        registry.add("a", 2)


def test_overwrite_allowed():
    registry = Registry("thing")
    registry.add("a", 1)
    registry.add("a", 2, overwrite=True)
    assert registry.get("a") == 2


def test_constructor_overwrite_policy():
    registry = Registry("thing", allow_overwrite=True)
    registry.add("a", 1)
    registry.add("a", 2)
    assert registry.get("a") == 2


def test_missing_raises_helpful_error():
    registry = Registry("theme")
    registry.add("music", object())
    with pytest.raises(KeyError, match="theme"):
        registry.get("nope")


def test_get_or_none():
    registry = Registry("thing")
    registry.add("a", 1)
    assert registry.get_or_none("a") == 1
    assert registry.get_or_none("missing") is None


def test_keys_items_len_contains():
    registry = Registry("thing")
    registry.add("a", 1)
    registry.add("b", 2)
    assert registry.keys == ["a", "b"]
    assert registry.items == {"a": 1, "b": 2}
    assert len(registry) == 2
    assert "a" in registry
    assert "zzz" not in registry


def test_empty_key_rejected():
    registry = Registry("thing")
    with pytest.raises(ValueError):
        registry.add(" ", 1)


def test_thread_safety():
    registry = Registry("thing")
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda i: registry.add(f"k{i}", i), range(100)))
    assert len(registry) == 100
    assert registry.get("k99") == 99
