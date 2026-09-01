"""Low-overhead web search retrieval."""

from __future__ import annotations

from lorabot.config import WebSettings
from lorabot.models import SourceRef
from lorabot.text import clean_text


class WebSearchError(RuntimeError):
    pass


class WebSearchService:
    def __init__(self, settings: WebSettings):
        self.settings = settings

    def search(self, query: str) -> list[SourceRef]:
        if not self.settings.enabled:
            raise WebSearchError("Web search is disabled")
        if self.settings.provider != "ddgs":
            raise WebSearchError(f"Unsupported web provider: {self.settings.provider}")
        try:
            from ddgs import DDGS

            results = DDGS(timeout=int(self.settings.timeout_seconds)).text(
                query=query,
                region=self.settings.region,
                safesearch=self.settings.safesearch,
                max_results=self.settings.max_results,
            )
        except Exception as exc:  # provider exceptions vary between releases
            raise WebSearchError(f"Search failed: {exc}") from exc

        sources = [
            SourceRef(
                title=clean_text(str(result.get("title", "Untitled"))),
                url=str(result.get("href", "")),
                snippet=clean_text(str(result.get("body", "")))[:600],
            )
            for result in results
            if result.get("href")
        ]
        if not sources:
            raise WebSearchError("Search returned no results")
        return sources
