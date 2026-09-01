"""Shared value objects used by the assistant services."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class SourceRef:
    title: str
    url: str
    snippet: str = ""


@dataclass(frozen=True)
class Article:
    title: str
    url: str
    summary: str
    source: str
    topics: tuple[str, ...] = ()
    published: datetime | None = None


@dataclass(frozen=True)
class BotReply:
    text: str
    sources: tuple[SourceRef, ...] = ()
