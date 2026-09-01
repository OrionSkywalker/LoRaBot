from lorabot.text import split_mesh_text, truncate_text


def test_utf8_chunks_respect_byte_limit():
    chunks = split_mesh_text("Weather ☀ update " * 30, max_bytes=80, max_chunks=4)
    assert 1 < len(chunks) <= 4
    assert all(len(chunk.encode("utf-8")) <= 80 for chunk in chunks)
    assert chunks[-1].endswith("…")


def test_short_text_is_not_numbered():
    assert split_mesh_text("hello", 80, 4) == ["hello"]


def test_truncate_normalizes_whitespace():
    assert truncate_text("a\n  b", 10) == "a b"
