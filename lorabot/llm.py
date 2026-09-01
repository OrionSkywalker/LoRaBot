"""Small Ollama HTTP client tuned for constrained hardware."""

from __future__ import annotations

from typing import Any

import requests

from lorabot.config import OllamaSettings


class OllamaError(RuntimeError):
    pass


class OllamaClient:
    def __init__(self, settings: OllamaSettings, session: requests.Session | None = None):
        self.settings = settings
        self.session = session or requests.Session()

    def health(self) -> bool:
        response = self.session.get(
            f"{self.settings.url}/api/tags", timeout=min(self.settings.timeout_seconds, 10)
        )
        response.raise_for_status()
        return True

    def chat(self, messages: list[dict[str, str]], system_prompt: str) -> str:
        payload: dict[str, Any] = {
            "model": self.settings.model,
            "messages": [{"role": "system", "content": system_prompt}, *messages],
            "stream": False,
            "keep_alive": self.settings.keep_alive,
            "options": {
                "num_ctx": self.settings.context_tokens,
                "num_predict": self.settings.max_output_tokens,
                "temperature": self.settings.temperature,
            },
        }
        try:
            response = self.session.post(
                f"{self.settings.url}/api/chat",
                json=payload,
                timeout=self.settings.timeout_seconds,
            )
            response.raise_for_status()
            content = response.json().get("message", {}).get("content", "").strip()
        except (requests.RequestException, ValueError) as exc:
            raise OllamaError(f"Ollama request failed: {exc}") from exc
        if not content:
            raise OllamaError("Ollama returned an empty response")
        return content
