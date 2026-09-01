from pathlib import Path

from lorabot.config import (
    AssistantSettings,
    MeshtasticSettings,
    NewsSettings,
    OllamaSettings,
    RadioSettings,
    Settings,
    WebSettings,
)
from lorabot.mesh import MeshBot, RateLimiter


class FakeAssistant:
    pass


class FakeInterface:
    def __init__(self):
        self.sent = []

    def sendText(self, text, **kwargs):
        self.sent.append((text, kwargs))


class LocalNode:
    nodeNum = 123


class SelfAwareInterface(FakeInterface):
    localNode = LocalNode()


def settings(require_direct=False):
    return Settings(
        meshtastic=MeshtasticSettings(None, 1, require_direct, (), ""),
        assistant=AssistantSettings("LoRaBot", "Be concise.", 2, 620, 180, 4, "thinking"),
        ollama=OllamaSettings("http://localhost", "test", 1, 128, 20, 0.2, "1m"),
        news=NewsSettings(Path("sources.json"), 3, 3, 1),
        web=WebSettings(True, "ddgs", "us-en", "moderate", 3, 1),
        radio=RadioSettings(0, 0, True, 3, 10),
    )


def test_wrong_channel_is_ignored():
    bot = MeshBot(settings(), FakeAssistant())
    interface = FakeInterface()
    bot.interface = interface
    bot.on_receive({"channel": 0, "fromId": "!abc", "decoded": {"text": "hello"}}, interface)
    assert bot.requests.empty()
    assert interface.sent == []


def test_private_channel_request_is_queued_and_acknowledged_directly():
    bot = MeshBot(settings(), FakeAssistant())
    interface = FakeInterface()
    bot.interface = interface
    bot.on_receive({"channel": 1, "fromId": "!abc", "decoded": {"text": "hello"}}, interface)
    request = bot.requests.get_nowait()
    assert request.node_id == "!abc"
    assert request.channel_index == 1
    assert interface.sent[0][1]["destinationId"] == "!abc"
    assert interface.sent[0][1]["channelIndex"] == 1


def test_direct_only_mode_rejects_channel_broadcast():
    bot = MeshBot(settings(require_direct=True), FakeAssistant())
    interface = FakeInterface()
    bot.interface = interface
    bot.on_receive(
        {
            "channel": 1,
            "fromId": "!abc",
            "to": 0xFFFFFFFF,
            "decoded": {"text": "hello"},
        },
        interface,
    )
    assert bot.requests.empty()


def test_message_from_connected_radio_is_ignored():
    bot = MeshBot(settings(), FakeAssistant())
    interface = SelfAwareInterface()
    bot.interface = interface
    bot.on_receive(
        {
            "channel": 1,
            "from": 123,
            "fromId": "!0000007b",
            "decoded": {"text": "echo"},
        },
        interface,
    )
    assert bot.requests.empty()


def test_rate_limiter_expires_old_events():
    limiter = RateLimiter(2)
    assert limiter.allow("!abc", now=0)
    assert limiter.allow("!abc", now=1)
    assert not limiter.allow("!abc", now=2)
    assert limiter.allow("!abc", now=3600)
