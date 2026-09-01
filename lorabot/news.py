"""Curated RSS/Atom retrieval."""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path

import requests

from lorabot.config import NewsSettings
from lorabot.models import Article
from lorabot.text import clean_text


class NewsError(RuntimeError):
    pass


def _element_text(element: ET.Element, names: tuple[str, ...]) -> str:
    for child in element.iter():
        local_name = child.tag.rsplit("}", 1)[-1].lower()
        if local_name in names and child.text:
            return child.text.strip()
    return ""


def _entry_link(element: ET.Element) -> str:
    for child in element.iter():
        if child.tag.rsplit("}", 1)[-1].lower() != "link":
            continue
        href = child.attrib.get("href", "").strip()
        if href:
            return href
        if child.text:
            return child.text.strip()
    return ""


def _published(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    except (TypeError, ValueError):
        try:
            parsed = datetime.fromisoformat(value)
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
        except ValueError:
            return None


class NewsService:
    def __init__(self, settings: NewsSettings, session: requests.Session | None = None):
        self.settings = settings
        self.session = session or requests.Session()
        self.interests, self.feeds = self._load_sources(settings.sources_file)

    @staticmethod
    def _load_sources(path: Path) -> tuple[tuple[str, ...], tuple[dict[str, object], ...]]:
        if not path.is_file():
            raise FileNotFoundError(
                f"News sources not found: {path}. Copy sources.example.json to sources.json."
            )
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise NewsError(f"Could not read news sources: {exc}") from exc
        feeds = data.get("feeds", [])
        if not isinstance(feeds, list) or not feeds:
            raise NewsError("sources.json must contain at least one feed")
        normalized: list[dict[str, object]] = []
        for feed in feeds:
            if not isinstance(feed, dict) or not feed.get("name") or not feed.get("url"):
                raise NewsError("Each feed requires name and url")
            normalized.append(feed)
        interests = tuple(str(value) for value in data.get("interests", []) if str(value).strip())
        return interests, tuple(normalized)

    def _fetch_feed(self, feed: dict[str, object]) -> list[Article]:
        name = str(feed["name"])
        url = str(feed["url"])
        topics = tuple(str(topic) for topic in feed.get("topics", []))
        try:
            response = self.session.get(
                url,
                timeout=self.settings.request_timeout_seconds,
                headers={"User-Agent": "LoRaBot/0.1 (+RSS reader)"},
            )
            response.raise_for_status()
            root = ET.fromstring(response.content)
        except (requests.RequestException, ET.ParseError) as exc:
            raise NewsError(f"{name}: {exc}") from exc

        entries = [
            item for item in root.iter() if item.tag.rsplit("}", 1)[-1].lower() in {"item", "entry"}
        ]
        articles: list[Article] = []
        for entry in entries[: self.settings.items_per_feed]:
            title = clean_text(_element_text(entry, ("title",)))
            if not title:
                continue
            summary = _element_text(entry, ("description", "summary", "content"))
            summary = clean_text(re.sub(r"<[^>]+>", " ", summary))[:500]
            date_text = _element_text(entry, ("pubdate", "published", "updated"))
            articles.append(
                Article(
                    title=title,
                    url=_entry_link(entry),
                    summary=summary,
                    source=name,
                    topics=topics,
                    published=_published(date_text),
                )
            )
        return articles

    def fetch(self, topic: str = "") -> list[Article]:
        articles: list[Article] = []
        errors: list[str] = []
        for feed in self.feeds:
            try:
                articles.extend(self._fetch_feed(feed))
            except NewsError as exc:
                errors.append(str(exc))

        if not articles:
            detail = "; ".join(errors) if errors else "no feed entries"
            raise NewsError(f"No news could be retrieved ({detail})")

        query_terms = {
            word.lower()
            for word in re.findall(r"[a-zA-Z0-9]+", topic or " ".join(self.interests))
            if len(word) > 2
        }

        def score(article: Article) -> tuple[int, float]:
            haystack = " ".join((article.title, article.summary, " ".join(article.topics))).lower()
            relevance = sum(1 for term in query_terms if term in haystack)
            timestamp = article.published.timestamp() if article.published else 0.0
            return relevance, timestamp

        unique: dict[str, Article] = {}
        for article in articles:
            key = article.url or article.title.lower()
            unique.setdefault(key, article)
        return sorted(unique.values(), key=score, reverse=True)[: self.settings.max_articles]
