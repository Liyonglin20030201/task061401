import pytest
from app.services.chunking_service import smart_chunk, count_tokens, recursive_heading_chunk, sentence_boundary_split


class TestChunking:
    def test_short_text_no_split(self):
        sections = [{"content": "This is a short text.", "metadata": {"page": 1}}]
        result = smart_chunk(sections)
        assert len(result) == 1
        assert result[0]["content"] == "This is a short text."

    def test_heading_based_split(self):
        text = "# Introduction\nSome intro text.\n\n# Details\nSome detail text.\n\n# Conclusion\nFinal thoughts."
        sections = [{"content": text, "metadata": {"source": "md"}}]
        result = smart_chunk(sections)
        assert len(result) == 3
        assert "Introduction" in result[0]["content"]
        assert "Details" in result[1]["content"]
        assert "Conclusion" in result[2]["content"]

    def test_heading_metadata_preserved(self):
        text = "# Title\nContent under title."
        chunks = recursive_heading_chunk(text, {"source": "md"}, chunk_size=500, chunk_overlap=64)
        assert len(chunks) == 1
        assert "h1" in chunks[0]["metadata"]
        assert chunks[0]["metadata"]["h1"] == "Title"

    def test_recursive_nested_headings(self):
        text = "# H1\n## H2a\nContent A.\n## H2b\nContent B."
        chunks = recursive_heading_chunk(text, {}, chunk_size=20, chunk_overlap=5)
        assert len(chunks) >= 2

    def test_sentence_boundary_split_no_mid_sentence_cut(self):
        text = "This is sentence one. This is sentence two. This is sentence three."
        chunks = sentence_boundary_split(text, {}, chunk_size=15, chunk_overlap=5)
        for chunk in chunks:
            content = chunk["content"].strip()
            assert content.endswith(".") or chunk == chunks[-1]

    def test_smart_chunk_table_preservation(self):
        table_content = "| Col1 | Col2 |\n|------|------|\n| A | B |\n| C | D |"
        sections = [{"content": table_content, "metadata": {}}]
        result = smart_chunk(sections)
        assert any(table_content in c["content"] for c in result)

    def test_count_tokens(self):
        text = "Hello, world!"
        tokens = count_tokens(text)
        assert tokens > 0
        assert isinstance(tokens, int)


class TestSensitiveFilter:
    def test_basic_detection(self):
        from app.services.sensitive_filter import SensitiveFilter
        f = SensitiveFilter()
        f._words = ["badword", "secret"]
        import re
        f._pattern = re.compile("|".join(re.escape(w) for w in f._words), re.IGNORECASE)

        found, matches = f.contains_sensitive("This contains badword here")
        assert found is True
        assert "badword" in matches

    def test_no_match(self):
        from app.services.sensitive_filter import SensitiveFilter
        f = SensitiveFilter()
        f._words = ["badword"]
        import re
        f._pattern = re.compile("|".join(re.escape(w) for w in f._words), re.IGNORECASE)

        found, matches = f.contains_sensitive("This is perfectly fine")
        assert found is False
        assert matches == []

    def test_masking(self):
        from app.services.sensitive_filter import SensitiveFilter
        f = SensitiveFilter()
        f._words = ["secret"]
        import re
        f._pattern = re.compile("|".join(re.escape(w) for w in f._words), re.IGNORECASE)

        masked = f.mask_sensitive("This is a secret message")
        assert "secret" not in masked
        assert "******" in masked


class TestAuth:
    def test_password_hash_and_verify(self):
        from app.core.security import hash_password, verify_password
        password = "testpassword123"
        hashed = hash_password(password)
        assert verify_password(password, hashed) is True
        assert verify_password("wrong", hashed) is False

    def test_token_creation_and_decode(self):
        import uuid
        from app.core.security import create_access_token, decode_token
        user_id = uuid.uuid4()
        token = create_access_token(user_id, "admin")
        payload = decode_token(token)
        assert payload is not None
        assert payload["sub"] == str(user_id)
        assert payload["role"] == "admin"
        assert payload["type"] == "access"

    def test_invalid_token_returns_none(self):
        from app.core.security import decode_token
        result = decode_token("invalid.token.here")
        assert result is None


class TestTTLCache:
    def test_set_and_get(self):
        from app.core.cache import TTLCache
        cache = TTLCache(maxsize=10, ttl=60)
        cache.set("key1", "value1")
        assert cache.get("key1") == "value1"

    def test_miss_returns_none(self):
        from app.core.cache import TTLCache
        cache = TTLCache(maxsize=10, ttl=60)
        assert cache.get("nonexistent") is None

    def test_invalidate(self):
        from app.core.cache import TTLCache
        cache = TTLCache(maxsize=10, ttl=60)
        cache.set("key1", "value1")
        cache.invalidate("key1")
        assert cache.get("key1") is None

    def test_maxsize_eviction(self):
        from app.core.cache import TTLCache
        cache = TTLCache(maxsize=2, ttl=60)
        cache.set("a", 1)
        cache.set("b", 2)
        cache.set("c", 3)
        # "a" should be evicted (oldest)
        assert cache.get("a") is None
        assert cache.get("b") == 2
        assert cache.get("c") == 3

    def test_clear(self):
        from app.core.cache import TTLCache
        cache = TTLCache(maxsize=10, ttl=60)
        cache.set("x", 1)
        cache.set("y", 2)
        cache.clear()
        assert cache.get("x") is None
        assert cache.get("y") is None
