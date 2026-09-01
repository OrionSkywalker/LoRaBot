from pathlib import Path

from lorabot.assistant import AssistantEngine
from lorabot.config import (
    AssistantSettings,
    MeshtasticSettings,
    NewsSettings,
    OllamaSettings,
    RadioSettings,
    Settings,
    WebSettings,
)
from lorabot.models import Article, SourceRef


class FakeLLM:
    def __init__(self):
        self.calls = []

    def chat(self, messages, system_prompt):
        self.calls.append((messages, system_prompt))
        return "A compact answer [1]."


class FakeNews:
    interests = ("space",)

    def fetch(self, topic=""):
        return [Article("Moon update", "https://example.com/moon", "New mission.", "Test")]


class FakeWeb:
    def search(self, query):
        return [SourceRef("Current result", "https://example.com/current", "Fresh fact")]


def settings():
    return Settings(
        meshtastic=MeshtasticSettings(None, 1, False, (), ""),
        assistant=AssistantSettings("LoRaBot", "Be concise.", 2, 620, 180, 4, "thinking"),
        ollama=OllamaSettings("http://localhost", "test", 1, 128, 20, 0.2, "1m"),
        news=NewsSettings(Path("sources.json"), 3, 3, 1),
        web=WebSettings(True, "ddgs", "us-en", "moderate", 3, 1),
        radio=RadioSettings(0, 0, True, 3, 10),
    )


def test_general_conversation_uses_history():
    llm = FakeLLM()
    engine = AssistantEngine(settings(), llm, FakeNews(), FakeWeb())
    engine.respond("!abc", "What is LoRa?")
    engine.respond("!abc", "Why is it useful?")
    second_messages = llm.calls[1][0]
    assert second_messages[0] == {"role": "user", "content": "What is LoRa?"}
    assert second_messages[-1]["content"] == "Why is it useful?"


def test_news_language_routes_to_curated_feeds():
    llm = FakeLLM()
    engine = AssistantEngine(settings(), llm, FakeNews(), FakeWeb())
    reply = engine.respond("!abc", "Could I get news updates about space?")
    assert "Reply 'sources'" in reply.text
    assert reply.sources[0].url == "https://example.com/moon"


def test_current_question_routes_to_web():
    llm = FakeLLM()
    engine = AssistantEngine(settings(), llm, FakeNews(), FakeWeb())
    reply = engine.respond("!abc", "What is the current status of the mission?")
    assert reply.sources[0].title == "Current result"


def test_forget_clears_sources():
    engine = AssistantEngine(settings(), FakeLLM(), FakeNews(), FakeWeb())
    engine.respond("!abc", "search moon")
    engine.respond("!abc", "forget")
    assert engine.respond("!abc", "sources").text.startswith("No stored")
