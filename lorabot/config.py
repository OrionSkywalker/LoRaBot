"""Configuration loading with validation and useful defaults."""

from __future__ import annotations

import configparser
from dataclasses import dataclass
from pathlib import Path


def _csv(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.split(",") if item.strip())


@dataclass(frozen=True)
class MeshtasticSettings:
    serial_port: str | None
    channel_index: int
    require_direct_message: bool
    allowed_node_ids: tuple[str, ...]
    wake_word: str


@dataclass(frozen=True)
class AssistantSettings:
    name: str
    system_prompt: str
    history_turns: int
    max_response_chars: int
    chunk_bytes: int
    max_chunks: int
    thinking_message: str


@dataclass(frozen=True)
class OllamaSettings:
    url: str
    model: str
    timeout_seconds: float
    context_tokens: int
    max_output_tokens: int
    temperature: float
    keep_alive: str


@dataclass(frozen=True)
class NewsSettings:
    sources_file: Path
    max_articles: int
    items_per_feed: int
    request_timeout_seconds: float


@dataclass(frozen=True)
class WebSettings:
    enabled: bool
    provider: str
    region: str
    safesearch: str
    max_results: int
    timeout_seconds: float


@dataclass(frozen=True)
class RadioSettings:
    message_delay_seconds: float
    channel_quiet_seconds: float
    want_ack: bool
    queue_size: int
    requests_per_hour: int


@dataclass(frozen=True)
class Settings:
    meshtastic: MeshtasticSettings
    assistant: AssistantSettings
    ollama: OllamaSettings
    news: NewsSettings
    web: WebSettings
    radio: RadioSettings


def load_settings(path: str | Path) -> Settings:
    config_path = Path(path).expanduser().resolve()
    if not config_path.is_file():
        raise FileNotFoundError(
            f"Configuration not found: {config_path}. Copy config.example.ini to config.ini."
        )

    parser = configparser.ConfigParser(interpolation=None)
    parser.read(config_path, encoding="utf-8")

    raw_port = parser.get("meshtastic", "serial_port", fallback="auto").strip()
    channel_index = parser.getint("meshtastic", "channel_index", fallback=1)
    if not 0 <= channel_index <= 7:
        raise ValueError("meshtastic.channel_index must be between 0 and 7")

    chunk_bytes = parser.getint("assistant", "chunk_bytes", fallback=180)
    if not 64 <= chunk_bytes <= 220:
        raise ValueError("assistant.chunk_bytes must be between 64 and 220")

    max_chunks = parser.getint("assistant", "max_chunks", fallback=4)
    if not 1 <= max_chunks <= 8:
        raise ValueError("assistant.max_chunks must be between 1 and 8")

    sources_path = Path(parser.get("news", "sources_file", fallback="sources.json"))
    if not sources_path.is_absolute():
        sources_path = config_path.parent / sources_path

    settings = Settings(
        meshtastic=MeshtasticSettings(
            serial_port=None if raw_port.lower() == "auto" else raw_port,
            channel_index=channel_index,
            require_direct_message=parser.getboolean(
                "meshtastic", "require_direct_message", fallback=False
            ),
            allowed_node_ids=tuple(
                node.lower()
                for node in _csv(parser.get("meshtastic", "allowed_node_ids", fallback=""))
            ),
            wake_word=parser.get("meshtastic", "wake_word", fallback="").strip(),
        ),
        assistant=AssistantSettings(
            name=parser.get("assistant", "name", fallback="LoRaBot").strip(),
            system_prompt=parser.get(
                "assistant",
                "system_prompt",
                fallback=(
                    "You are a concise assistant reached over a low-bandwidth radio. "
                    "Answer directly, and say when you are uncertain."
                ),
            ).strip(),
            history_turns=parser.getint("assistant", "history_turns", fallback=4),
            max_response_chars=parser.getint("assistant", "max_response_chars", fallback=620),
            chunk_bytes=chunk_bytes,
            max_chunks=max_chunks,
            thinking_message=parser.get(
                "assistant", "thinking_message", fallback="LoRaBot: thinking..."
            ).strip(),
        ),
        ollama=OllamaSettings(
            url=parser.get("ollama", "url", fallback="http://127.0.0.1:11434").rstrip("/"),
            model=parser.get("ollama", "model", fallback="llama3.2:3b").strip(),
            timeout_seconds=parser.getfloat("ollama", "timeout_seconds", fallback=120),
            context_tokens=parser.getint("ollama", "context_tokens", fallback=2048),
            max_output_tokens=parser.getint("ollama", "max_output_tokens", fallback=180),
            temperature=parser.getfloat("ollama", "temperature", fallback=0.3),
            keep_alive=parser.get("ollama", "keep_alive", fallback="10m").strip(),
        ),
        news=NewsSettings(
            sources_file=sources_path.resolve(),
            max_articles=parser.getint("news", "max_articles", fallback=6),
            items_per_feed=parser.getint("news", "items_per_feed", fallback=8),
            request_timeout_seconds=parser.getfloat("news", "request_timeout_seconds", fallback=12),
        ),
        web=WebSettings(
            enabled=parser.getboolean("web", "enabled", fallback=True),
            provider=parser.get("web", "provider", fallback="ddgs").lower().strip(),
            region=parser.get("web", "region", fallback="us-en").strip(),
            safesearch=parser.get("web", "safesearch", fallback="moderate").strip(),
            max_results=parser.getint("web", "max_results", fallback=4),
            timeout_seconds=parser.getfloat("web", "timeout_seconds", fallback=10),
        ),
        radio=RadioSettings(
            message_delay_seconds=parser.getfloat("radio", "message_delay_seconds", fallback=2.5),
            channel_quiet_seconds=parser.getfloat("radio", "channel_quiet_seconds", fallback=3.0),
            want_ack=parser.getboolean("radio", "want_ack", fallback=True),
            queue_size=parser.getint("radio", "queue_size", fallback=12),
            requests_per_hour=parser.getint("radio", "requests_per_hour", fallback=12),
        ),
    )

    if settings.assistant.history_turns < 0:
        raise ValueError("assistant.history_turns cannot be negative")
    if settings.radio.requests_per_hour < 1:
        raise ValueError("radio.requests_per_hour must be positive")
    return settings
