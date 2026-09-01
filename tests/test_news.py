from pathlib import Path

from lorabot.config import NewsSettings
from lorabot.news import NewsService


class Response:
    content = b"""<?xml version='1.0'?><feed xmlns='http://www.w3.org/2005/Atom'>
      <entry><title>Space telescope update</title><summary>New images arrived.</summary>
      <link href='https://example.com/space'/><updated>2026-08-31T10:00:00Z</updated></entry>
    </feed>"""

    def raise_for_status(self):
        return None


class Session:
    def get(self, *args, **kwargs):
        return Response()


def test_atom_feed_is_supported(tmp_path: Path):
    sources = tmp_path / "sources.json"
    sources.write_text(
        '{"interests":["space"],"feeds":[{"name":"Test","url":"https://feed","topics":["space"]}]}'
    )
    service = NewsService(NewsSettings(sources, 4, 4, 1), Session())
    articles = service.fetch("space")
    assert articles[0].title == "Space telescope update"
    assert articles[0].url == "https://example.com/space"
