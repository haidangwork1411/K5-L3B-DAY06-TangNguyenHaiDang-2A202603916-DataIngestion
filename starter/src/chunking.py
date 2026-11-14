"""Implement fixed-size and structure-aware chunking."""
from .models import Chunk, DocumentPage


def fixed_size(page: DocumentPage, size: int, overlap: int) -> list[Chunk]:
    """Split text into overlapping windows and retain page metadata."""
    if size <= 0:
        raise ValueError(f"size must be positive, got {size}")
    if overlap < 0 or overlap >= size:
        raise ValueError(f"overlap must satisfy 0 <= overlap < size, got {overlap} for size {size}")

    text = page.text
    if not text or not text.strip():
        return []

    chunks: list[Chunk] = []
    step = size - overlap
    start = 0
    chunk_idx = 1

    while start < len(text):
        end = start + size
        chunk_text = text[start:end].strip()
        if chunk_text:
            chunk_id = f"{page.document_id}_p{page.page}_f{chunk_idx:03d}"
            chunk_meta = dict(page.metadata)
            chunk_meta["chunk_strategy"] = "fixed_size"
            chunk_meta["chunk_index"] = chunk_idx
            chunk_meta["char_count"] = len(chunk_text)
            chunks.append(
                Chunk(
                    chunk_id=chunk_id,
                    document_id=page.document_id,
                    source=page.source,
                    page=page.page,
                    text=chunk_text,
                    metadata=chunk_meta,
                )
            )
            chunk_idx += 1

        if end >= len(text):
            break
        start += step

    return chunks


def by_paragraph(page: DocumentPage, max_size: int) -> list[Chunk]:
    """Group paragraphs, split oversized paragraphs and retain metadata."""
    if max_size <= 0:
        raise ValueError(f"max_size must be positive, got {max_size}")

    text = page.text
    if not text or not text.strip():
        return []

    # Split text into paragraphs based on line breaks and terminal punctuation
    lines = text.splitlines(keepends=True)
    paras: list[str] = []
    current_lines: list[str] = []

    for line in lines:
        current_lines.append(line)
        stripped = line.strip()
        if stripped.endswith((".", ":", "!", "?", ".”", ".\"", ".\"")):
            paras.append("".join(current_lines))
            current_lines = []
    if current_lines:
        paras.append("".join(current_lines))

    paragraphs = [p.strip() for p in paras if p.strip()]
    if not paragraphs:
        paragraphs = [text.strip()]

    # Group paragraphs up to max_size, and split any paragraph exceeding max_size
    raw_chunks: list[str] = []
    current_group: list[str] = []
    current_len = 0

    for para in paragraphs:
        para_len = len(para)
        if para_len > max_size:
            # Emit current group first if non-empty
            if current_group:
                raw_chunks.append("\n\n".join(current_group))
                current_group = []
                current_len = 0

            # Split oversized paragraph into windows of at most max_size
            sub_step = max_size - 50 if max_size > 100 else max_size
            sub_start = 0
            while sub_start < len(para):
                sub_end = min(sub_start + max_size, len(para))
                sub_slice = para[sub_start:sub_end].strip()
                if sub_slice:
                    raw_chunks.append(sub_slice)
                if sub_end >= len(para):
                    break
                sub_start += sub_step
        else:
            added_len = para_len if not current_group else para_len + 2
            if current_len + added_len <= max_size:
                current_group.append(para)
                current_len += added_len
            else:
                if current_group:
                    raw_chunks.append("\n\n".join(current_group))
                current_group = [para]
                current_len = para_len

    if current_group:
        raw_chunks.append("\n\n".join(current_group))

    # Convert to Chunk objects with deterministic IDs
    chunks: list[Chunk] = []
    for chunk_idx, chunk_text in enumerate(raw_chunks, start=1):
        if not chunk_text.strip():
            continue
        chunk_id = f"{page.document_id}_p{page.page}_b{chunk_idx:03d}"
        chunk_meta = dict(page.metadata)
        chunk_meta["chunk_strategy"] = "by_paragraph"
        chunk_meta["chunk_index"] = chunk_idx
        chunk_meta["char_count"] = len(chunk_text)
        chunks.append(
            Chunk(
                chunk_id=chunk_id,
                document_id=page.document_id,
                source=page.source,
                page=page.page,
                text=chunk_text,
                metadata=chunk_meta,
            )
        )

    return chunks
