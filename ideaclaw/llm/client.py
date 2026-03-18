"""OpenAI-compatible LLM client with fallback chain.

Adapted from AutoResearchClaw's llm/ module pattern.
Supports any OpenAI-compatible API: OpenAI, Anthropic (via proxy),
DeepSeek, local models, etc.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

from rich.console import Console

console = Console()


class LLMClient:
    """OpenAI-compatible LLM client.

    Uses stdlib urllib to avoid hard dependency on httpx.
    """

    def __init__(self, config: Dict[str, Any]):
        self.base_url = config.get("base_url", "https://api.openai.com/v1").rstrip("/")
        self.api_key = config.get("api_key") or os.environ.get(
            config.get("api_key_env", "OPENAI_API_KEY"), ""
        )
        self.primary_model = config.get("primary_model", "gpt-4o")
        self.fallback_models = config.get("fallback_models", ["gpt-4o-mini"])

        if not self.api_key:
            console.print(
                f"[yellow]⚠ No API key found. Set {config.get('api_key_env', 'OPENAI_API_KEY')} "
                f"or provide llm.api_key in config.[/yellow]"
            )

    def chat(
        self,
        system_prompt: str,
        user_prompt: str,
        model: Optional[str] = None,
        json_mode: bool = False,
        max_tokens: Optional[int] = None,
        temperature: float = 0.3,
    ) -> str:
        """Send a chat completion request to OpenAI-compatible API.

        Args:
            system_prompt: System message.
            user_prompt: User message.
            model: Model name (defaults to primary_model).
            json_mode: If True, request JSON output format.
            max_tokens: Maximum tokens in response.
            temperature: Sampling temperature.

        Returns:
            Response text from the LLM.
        """
        model = model or self.primary_model
        url = f"{self.base_url}/chat/completions"

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        body: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
        }
        if max_tokens:
            body["max_tokens"] = max_tokens
        if json_mode:
            body["response_format"] = {"type": "json_object"}

        payload = json.dumps(body).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        req = urllib.request.Request(url, data=payload, headers=headers, method="POST")

        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                resp_data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8", errors="ignore") if e.fp else ""
            raise RuntimeError(
                f"LLM API error {e.code}: {error_body[:500]}"
            ) from e
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise RuntimeError(f"LLM API connection error: {e}") from e

        choices = resp_data.get("choices", [])
        if not choices:
            raise RuntimeError(f"LLM returned no choices: {resp_data}")

        content = choices[0].get("message", {}).get("content", "")
        if not content:
            raise RuntimeError(f"LLM returned empty content: {resp_data}")

        return content

    def chat_with_fallback(
        self,
        system_prompt: str,
        user_prompt: str,
        json_mode: bool = False,
        max_tokens: Optional[int] = None,
        temperature: float = 0.3,
    ) -> str:
        """Try primary model, then fall back to secondary models on failure."""
        models = [self.primary_model] + self.fallback_models
        last_error: Optional[Exception] = None

        for model in models:
            try:
                return self.chat(
                    system_prompt,
                    user_prompt,
                    model=model,
                    json_mode=json_mode,
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
            except Exception as e:
                last_error = e
                console.print(f"  [yellow]⚠ Model {model} failed: {e}[/yellow]")
                if model != models[-1]:
                    console.print(f"  [dim]Trying next fallback...[/dim]")

        raise RuntimeError(f"All models failed. Last error: {last_error}")
