from pathlib import Path

import pytest

from lorabot.config import load_settings


def test_example_config_loads(tmp_path: Path):
    root = Path(__file__).parents[1]
    config = tmp_path / "config.ini"
    config.write_text((root / "config.example.ini").read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / "sources.json").write_text('{"feeds":[{"name":"x","url":"https://x"}]}')
    settings = load_settings(config)
    assert settings.meshtastic.channel_index == 1
    assert settings.meshtastic.serial_port is None
    assert settings.news.sources_file == (tmp_path / "sources.json").resolve()


def test_invalid_channel_is_rejected(tmp_path: Path):
    config = tmp_path / "config.ini"
    config.write_text("[meshtastic]\nchannel_index=9\n")
    with pytest.raises(ValueError, match="channel_index"):
        load_settings(config)
