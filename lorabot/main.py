"""Command-line entry point."""

from __future__ import annotations

import argparse

from lorabot.assistant import AssistantEngine
from lorabot.config import load_settings
from lorabot.llm import OllamaClient
from lorabot.mesh import MeshBot
from lorabot.news import NewsService
from lorabot.web_search import WebSearchService


def main() -> None:
    parser = argparse.ArgumentParser(description="Private Meshtastic conversational assistant")
    parser.add_argument("--config", default="config.ini", help="Path to config.ini")
    parser.add_argument("--check", action="store_true", help="Validate config, sources, and Ollama")
    parser.add_argument("--ask", help="Ask locally without connecting a radio")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    import logging

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    settings = load_settings(args.config)
    llm = OllamaClient(settings.ollama)
    news = NewsService(settings.news)
    engine = AssistantEngine(settings, llm, news, WebSearchService(settings.web))

    if args.check:
        llm.health()
        print(
            f"OK: config valid, {len(news.feeds)} feeds loaded, "
            f"Ollama reachable with model {settings.ollama.model!r} configured."
        )
        return
    if args.ask:
        print(engine.respond("local-test", args.ask).text)
        return
    MeshBot(settings, engine).run()


if __name__ == "__main__":
    main()
