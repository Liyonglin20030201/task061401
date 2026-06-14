import tiktoken

from app.config import get_settings

settings = get_settings()

encoding = tiktoken.encoding_for_model("gpt-4")


def count_tokens(text: str) -> int:
    return len(encoding.encode(text))


def chunk_text(
    sections: list[dict],
    chunk_size: int = None,
    chunk_overlap: int = None,
) -> list[dict]:
    if chunk_size is None:
        chunk_size = settings.chunk_size
    if chunk_overlap is None:
        chunk_overlap = settings.chunk_overlap

    chunks = []

    for section in sections:
        content = section["content"]
        metadata = section.get("metadata", {})
        tokens = encoding.encode(content)

        if len(tokens) <= chunk_size:
            chunks.append({
                "content": content,
                "token_count": len(tokens),
                "metadata": metadata,
            })
        else:
            # Sliding window chunking with overlap
            start = 0
            while start < len(tokens):
                end = min(start + chunk_size, len(tokens))
                chunk_tokens = tokens[start:end]
                chunk_text_decoded = encoding.decode(chunk_tokens)

                chunks.append({
                    "content": chunk_text_decoded,
                    "token_count": len(chunk_tokens),
                    "metadata": {**metadata, "chunk_part": f"{start//chunk_size + 1}"},
                })

                if end >= len(tokens):
                    break
                start += chunk_size - chunk_overlap

    return chunks


def smart_chunk(sections: list[dict]) -> list[dict]:
    """
    Hybrid chunking strategy:
    1. Respect structural boundaries (sections from parsing)
    2. Split oversized sections with sliding window + overlap
    3. Preserve table integrity (don't split tables)
    """
    processed_sections = []

    for section in sections:
        content = section["content"]
        metadata = section.get("metadata", {})

        # Detect tables (simple heuristic: lines with | separators)
        lines = content.split("\n")
        table_lines = [l for l in lines if "|" in l and l.strip().startswith("|")]

        if len(table_lines) > 2 and len(table_lines) / max(len(lines), 1) > 0.5:
            # This section is primarily a table — keep it whole
            processed_sections.append({
                "content": content,
                "metadata": {**metadata, "type": "table"},
            })
        else:
            # Split by paragraph boundaries first
            paragraphs = content.split("\n\n")
            current_group = ""

            for para in paragraphs:
                test_group = current_group + "\n\n" + para if current_group else para
                if count_tokens(test_group) <= settings.chunk_size:
                    current_group = test_group
                else:
                    if current_group:
                        processed_sections.append({
                            "content": current_group,
                            "metadata": metadata,
                        })
                    current_group = para

            if current_group:
                processed_sections.append({
                    "content": current_group,
                    "metadata": metadata,
                })

    return chunk_text(processed_sections)
