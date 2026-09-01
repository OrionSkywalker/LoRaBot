"""Utilities for producing LoRa-friendly text."""

from __future__ import annotations

import re


def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def truncate_text(text: str, max_chars: int) -> str:
    text = clean_text(text)
    if len(text) <= max_chars:
        return text
    return text[: max(1, max_chars - 1)].rstrip() + "…"


def _split_to_byte_limit(text: str, max_bytes: int) -> list[str]:
    chunks: list[str] = []
    remaining = text.strip()
    while remaining:
        encoded = remaining.encode("utf-8")
        if len(encoded) <= max_bytes:
            chunks.append(remaining)
            break

        used = 0
        end = 0
        last_space = -1
        for index, char in enumerate(remaining):
            width = len(char.encode("utf-8"))
            if used + width > max_bytes:
                break
            used += width
            end = index + 1
            if char.isspace():
                last_space = end

        if last_space > 0:
            end = last_space
        if end == 0:
            end = 1
        chunks.append(remaining[:end].strip())
        remaining = remaining[end:].strip()
    return [chunk for chunk in chunks if chunk]


def split_mesh_text(text: str, max_bytes: int = 180, max_chunks: int = 4) -> list[str]:
    """Split text without breaking UTF-8 and reserve room for part labels."""
    text = clean_text(text)
    if not text:
        return []
    if len(text.encode("utf-8")) <= max_bytes:
        return [text]

    body_limit = max_bytes - 8
    chunks = _split_to_byte_limit(text, body_limit)
    clipped = len(chunks) > max_chunks
    chunks = chunks[:max_chunks]
    if clipped:
        last = chunks[-1]
        while len((last + "…").encode("utf-8")) > body_limit:
            last = last[:-1]
        chunks[-1] = last.rstrip() + "…"

    total = len(chunks)
    return [f"({index}/{total}) {chunk}" for index, chunk in enumerate(chunks, 1)]
