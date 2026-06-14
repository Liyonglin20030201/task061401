import pytest
from app.services.chunking_service import chunk_text, smart_chunk, count_tokens


class TestChunking:
    def test_short_text_no_split(self):
        sections = [{"content": "This is a short text.", "metadata": {"page": 1}}]
        result = chunk_text(sections, chunk_size=100, chunk_overlap=10)
        assert len(result) == 1
        assert result[0]["content"] == "This is a short text."

    def test_long_text_splits_with_overlap(self):
        long_text = "word " * 200  # ~200 tokens
        sections = [{"content": long_text.strip(), "metadata": {"page": 1}}]
        result = chunk_text(sections, chunk_size=50, chunk_overlap=10)
        assert len(result) > 1
        for chunk in result:
            assert chunk["token_count"] <= 50

    def test_metadata_preserved(self):
        sections = [{"content": "Hello world", "metadata": {"page": 3, "heading": "Intro"}}]
        result = chunk_text(sections, chunk_size=100, chunk_overlap=10)
        assert result[0]["metadata"]["page"] == 3
        assert result[0]["metadata"]["heading"] == "Intro"

    def test_smart_chunk_table_preservation(self):
        table_content = "| Col1 | Col2 |\n|------|------|\n| A | B |\n| C | D |"
        sections = [{"content": table_content, "metadata": {}}]
        result = smart_chunk(sections)
        # Table should be kept as one chunk
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
