from __future__ import annotations

import json
import os
import urllib.request
from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class OpenAIConfig:
    api_key: str
    model: str = "gpt-4o-mini"
    base_url: str = "https://api.openai.com/v1"
    timeout_s: int = 60


class OpenAIClient:
    """
    Minimal OpenAI client (no extra deps).
    Uses env var OPENAI_API_KEY by default.
    """

    def __init__(self, config: Optional[OpenAIConfig] = None) -> None:
        if config is None:
            key = os.environ.get("OPENAI_API_KEY", "").strip()
            self.config = OpenAIConfig(api_key=key)
        else:
            self.config = config

    def enabled(self) -> bool:
        return bool(self.config.api_key)

    def chat(self, system: str, user: str, temperature: float = 0.2) -> str:
        if not self.enabled():
            raise RuntimeError("OPENAI_API_KEY not set")

        url = f"{self.config.base_url}/chat/completions"
        payload = {
            "model": self.config.model,
            "temperature": temperature,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.config.api_key}",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self.config.timeout_s) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data["choices"][0]["message"]["content"]

