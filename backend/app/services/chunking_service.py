import re

import tiktoken

from app.config import get_settings

settings = get_settings()

encoding = tiktoken.encoding_for_model("gpt-4")

HEADING_PATTERNS = [
    (r'^# ', 1),
    (r'^## ', 2),
    (r'^### ', 3),
    (r'^#### ', 4),
]


def count_tokens(text: str) -> int:
    return len(encoding.encode(text))


def recursive_heading_chunk(
    text: str,
    metadata: dict,
    chunk_size: int,
    chunk_overlap: int,
    heading_level: int = 0,
) -> list[dict]:
    token_count = count_tokens(text)
    if token_count <= chunk_size:
        return [{"content": text, "token_count": token_count, "metadata": metadata}]

    # Try splitting by next heading level
    if heading_level < len(HEADING_PATTERNS):
        pattern, level = HEADING_PATTERNS[heading_level]
        sections = re.split(f'(?m)(?={pattern})', text)
        sections = [s for s in sections if s.strip()]

        if len(sections) > 1:
            chunks = []
            for section in sections:
                heading_match = re.match(pattern, section, re.MULTILINE)
                section_heading = heading_match.group(0).strip().lstrip("#").strip() if heading_match else ""
                sub_meta = {**metadata, f"h{level}": section_heading}
                chunks.extend(recursive_heading_chunk(
                    section, sub_meta, chunk_size, chunk_overlap, heading_level + 1
                ))
            return chunks

        return recursive_heading_chunk(text, metadata, chunk_size, chunk_overlap, heading_level + 1)

    # Fallback: split by paragraphs
    paragraphs = text.split("\n\n")
    if len(paragraphs) > 1:
        chunks = []
        current = ""
        for para in paragraphs:
            candidate = current + "\n\n" + para if current else para
            if count_tokens(candidate) <= chunk_size:
                current = candidate
            else:
                if current:
                    chunks.append({"content": current, "token_count": count_tokens(current), "metadata": metadata})
                current = para
        if current:
            chunks.append({"content": current, "token_count": count_tokens(current), "metadata": metadata})

        final = []
        for c in chunks:
            if c["token_count"] > chunk_size:
                final.extend(sentence_boundary_split(c["content"], metadata, chunk_size, chunk_overlap))
            else:
                final.append(c)
        return final

    # Last resort: sentence-boundary-aware split
    return sentence_boundary_split(text, metadata, chunk_size, chunk_overlap)


def sentence_boundary_split(
    text: str,
    metadata: dict,
    chunk_size: int,
    chunk_overlap: int,
) -> list[dict]:
    sentences = re.split(r'(?<=[。！？.!?\n])', text)
    sentences = [s for s in sentences if s.strip()]

    chunks = []
    current = ""
    for sent in sentences:
        candidate = current + sent
        if count_tokens(candidate) <= chunk_size:
            current = candidate
        else:
            if current:
                chunks.append({"content": current, "token_count": count_tokens(current), "metadata": metadata})
            current = sent
    if current:
        chunks.append({"content": current, "token_count": count_tokens(current), "metadata": metadata})

    # Add overlap by prepending tail of previous chunk
    if chunk_overlap > 0 and len(chunks) > 1:
        for i in range(1, len(chunks)):
            prev_tokens = encoding.encode(chunks[i - 1]["content"])
            overlap_tokens = prev_tokens[-chunk_overlap:]
            overlap_text = encoding.decode(overlap_tokens)
            chunks[i]["content"] = overlap_text + chunks[i]["content"]
            chunks[i]["token_count"] = count_tokens(chunks[i]["content"])

    return chunks


def smart_chunk(sections: list[dict]) -> list[dict]:
    all_chunks = []
    chunk_size = settings.chunk_size
    chunk_overlap = settings.chunk_overlap

    for section in sections:
        content = section["content"]
        metadata = section.get("metadata", {})

        # Table detection — keep tables whole
        lines = content.split("\n")
        table_lines = [l for l in lines if "|" in l and l.strip().startswith("|")]
        if len(table_lines) > 2 and len(table_lines) / max(len(lines), 1) > 0.5:
            token_count = count_tokens(content)
            all_chunks.append({
                "content": content,
                "token_count": token_count,
                "metadata": {**metadata, "type": "table"},
            })
            continue

        all_chunks.extend(
            recursive_heading_chunk(content, metadata, chunk_size, chunk_overlap)
        )

    return all_chunks
