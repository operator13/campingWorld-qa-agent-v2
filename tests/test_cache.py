"""Tests for the determinism cache."""

from qa_agent.cache import _hash_inputs, get_cached, invalidate, set_cached


class TestHashInputs:
    def test_same_inputs_same_hash(self):
        h1 = _hash_inputs({"goal": "test", "ac": ["a", "b"]})
        h2 = _hash_inputs({"goal": "test", "ac": ["a", "b"]})
        assert h1 == h2

    def test_different_inputs_different_hash(self):
        h1 = _hash_inputs({"goal": "test1"})
        h2 = _hash_inputs({"goal": "test2"})
        assert h1 != h2

    def test_key_order_independent(self):
        h1 = _hash_inputs({"b": 2, "a": 1})
        h2 = _hash_inputs({"a": 1, "b": 2})
        assert h1 == h2


class TestCacheRoundTrip:
    def test_set_and_get(self, tmp_path, monkeypatch):
        import qa_agent.cache as cache_mod
        monkeypatch.setattr(cache_mod, "_CACHE_DIR", tmp_path / ".cache")

        inputs = {"goal": "test", "version": 1}
        outputs = {"plan": [{"id": "tc-1"}]}

        set_cached("planner", inputs, outputs)
        result = get_cached("planner", inputs)
        assert result is not None
        assert result["plan"][0]["id"] == "tc-1"

    def test_miss_on_different_inputs(self, tmp_path, monkeypatch):
        import qa_agent.cache as cache_mod
        monkeypatch.setattr(cache_mod, "_CACHE_DIR", tmp_path / ".cache")

        set_cached("planner", {"goal": "test1"}, {"plan": []})
        result = get_cached("planner", {"goal": "test2"})
        assert result is None

    def test_miss_on_empty_cache(self, tmp_path, monkeypatch):
        import qa_agent.cache as cache_mod
        monkeypatch.setattr(cache_mod, "_CACHE_DIR", tmp_path / ".cache")

        result = get_cached("planner", {"goal": "test"})
        assert result is None

    def test_invalidate_stage(self, tmp_path, monkeypatch):
        import qa_agent.cache as cache_mod
        monkeypatch.setattr(cache_mod, "_CACHE_DIR", tmp_path / ".cache")

        set_cached("planner", {"v": 1}, {"out": 1})
        set_cached("generator", {"v": 1}, {"out": 2})

        count = invalidate("planner")
        assert count == 1
        assert get_cached("planner", {"v": 1}) is None
        assert get_cached("generator", {"v": 1}) is not None

    def test_invalidate_all(self, tmp_path, monkeypatch):
        import qa_agent.cache as cache_mod
        monkeypatch.setattr(cache_mod, "_CACHE_DIR", tmp_path / ".cache")

        set_cached("a", {"v": 1}, {"out": 1})
        set_cached("b", {"v": 1}, {"out": 2})

        count = invalidate()
        assert count == 2
