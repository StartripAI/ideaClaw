"""Authentication manager — BYOK + OAuth device flow.

Supports:
  1. BYOK (Bring Your Own Key) — via env var or config
  2. OAuth Device Code Flow — for providers that support it
  3. Stored tokens — saved to ~/.ideaclaw/credentials.json

Token resolution order:
  1. --api-key CLI flag
  2. Config file (llm.api_key)
  3. Stored credentials (~/.ideaclaw/credentials.json)
  4. Environment variable (OPENAI_API_KEY, ANTHROPIC_API_KEY, etc.)
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from rich.console import Console

console = Console()

CREDENTIALS_DIR = Path.home() / ".ideaclaw"
CREDENTIALS_FILE = CREDENTIALS_DIR / "credentials.json"

# Known provider configurations
PROVIDERS = {
    "openai": {
        "name": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "env_var": "OPENAI_API_KEY",
        "primary_model": "gpt-4o",
        "fallback_models": ["gpt-4o-mini"],
        "key_prefix": "sk-",
        "dashboard_url": "https://platform.openai.com/api-keys",
    },
    "anthropic": {
        "name": "Anthropic",
        "base_url": "https://api.anthropic.com/v1",
        "env_var": "ANTHROPIC_API_KEY",
        "primary_model": "claude-sonnet-4-20250514",
        "fallback_models": ["claude-haiku-4-20250514"],
        "key_prefix": "sk-ant-",
        "dashboard_url": "https://console.anthropic.com/settings/keys",
    },
    "deepseek": {
        "name": "DeepSeek",
        "base_url": "https://api.deepseek.com/v1",
        "env_var": "DEEPSEEK_API_KEY",
        "primary_model": "deepseek-chat",
        "fallback_models": ["deepseek-reasoner"],
        "key_prefix": "sk-",
        "dashboard_url": "https://platform.deepseek.com/api_keys",
    },
    "openrouter": {
        "name": "OpenRouter",
        "base_url": "https://openrouter.ai/api/v1",
        "env_var": "OPENROUTER_API_KEY",
        "primary_model": "anthropic/claude-sonnet-4-20250514",
        "fallback_models": ["openai/gpt-4o-mini"],
        "key_prefix": "sk-or-",
        "dashboard_url": "https://openrouter.ai/settings/keys",
    },
    "groq": {
        "name": "Groq",
        "base_url": "https://api.groq.com/openai/v1",
        "env_var": "GROQ_API_KEY",
        "primary_model": "llama-3.3-70b-versatile",
        "fallback_models": ["llama-3.1-8b-instant"],
        "key_prefix": "gsk_",
        "dashboard_url": "https://console.groq.com/keys",
    },
    "together": {
        "name": "Together AI",
        "base_url": "https://api.together.xyz/v1",
        "env_var": "TOGETHER_API_KEY",
        "primary_model": "meta-llama/Llama-3.3-70B-Instruct-Turbo",
        "fallback_models": [],
        "key_prefix": "",
        "dashboard_url": "https://api.together.ai/settings/api-keys",
    },
    "custom": {
        "name": "Custom (OpenAI-compatible)",
        "base_url": "",
        "env_var": "",
        "primary_model": "",
        "fallback_models": [],
        "key_prefix": "",
        "dashboard_url": "",
    },
}


@dataclass
class Credentials:
    """Resolved credentials for API access."""
    provider: str
    api_key: str
    base_url: str
    primary_model: str
    fallback_models: list
    source: str  # "cli", "config", "stored", "env"


def _load_stored() -> Dict[str, Any]:
    """Load stored credentials from disk."""
    if CREDENTIALS_FILE.exists():
        try:
            return json.loads(CREDENTIALS_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save_stored(data: Dict[str, Any]) -> None:
    """Save credentials to disk."""
    CREDENTIALS_DIR.mkdir(parents=True, exist_ok=True)
    CREDENTIALS_FILE.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    # Restrict permissions
    try:
        CREDENTIALS_FILE.chmod(0o600)
    except OSError:
        pass


def store_api_key(provider: str, api_key: str, base_url: str = "",
                  model: str = "") -> None:
    """Store an API key for a provider."""
    data = _load_stored()
    prov_info = PROVIDERS.get(provider, PROVIDERS["custom"])

    data[provider] = {
        "api_key": api_key,
        "base_url": base_url or prov_info["base_url"],
        "primary_model": model or prov_info["primary_model"],
        "fallback_models": prov_info["fallback_models"],
        "stored_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    _save_stored(data)


def remove_stored_key(provider: str) -> bool:
    """Remove a stored API key."""
    data = _load_stored()
    if provider in data:
        del data[provider]
        _save_stored(data)
        return True
    return False


def list_stored_providers() -> list:
    """List all providers with stored credentials."""
    data = _load_stored()
    result = []
    for provider, info in data.items():
        result.append({
            "provider": provider,
            "base_url": info.get("base_url", ""),
            "model": info.get("primary_model", ""),
            "stored_at": info.get("stored_at", ""),
            "key_preview": info.get("api_key", "")[:8] + "..." if info.get("api_key") else "",
        })
    return result


def resolve_credentials(
    config: Dict[str, Any],
    cli_provider: Optional[str] = None,
    cli_api_key: Optional[str] = None,
) -> Credentials:
    """Resolve API credentials from all available sources.

    Priority: CLI flag > config file > stored credentials > env var.
    """
    llm_config = config.get("llm", {})

    # 1. CLI flag
    if cli_api_key:
        provider = cli_provider or _detect_provider(cli_api_key)
        prov_info = PROVIDERS.get(provider, PROVIDERS["custom"])
        return Credentials(
            provider=provider,
            api_key=cli_api_key,
            base_url=llm_config.get("base_url") or prov_info["base_url"],
            primary_model=llm_config.get("primary_model") or prov_info["primary_model"],
            fallback_models=llm_config.get("fallback_models") or prov_info["fallback_models"],
            source="cli",
        )

    # 2. Config file
    config_key = llm_config.get("api_key", "")
    if config_key:
        provider = cli_provider or _detect_provider(config_key)
        prov_info = PROVIDERS.get(provider, PROVIDERS["custom"])
        return Credentials(
            provider=provider,
            api_key=config_key,
            base_url=llm_config.get("base_url") or prov_info["base_url"],
            primary_model=llm_config.get("primary_model") or prov_info["primary_model"],
            fallback_models=llm_config.get("fallback_models") or prov_info["fallback_models"],
            source="config",
        )

    # 3. Stored credentials
    stored = _load_stored()
    target_provider = cli_provider or llm_config.get("provider_name")
    if target_provider and target_provider in stored:
        info = stored[target_provider]
        return Credentials(
            provider=target_provider,
            api_key=info["api_key"],
            base_url=info.get("base_url", ""),
            primary_model=info.get("primary_model", ""),
            fallback_models=info.get("fallback_models", []),
            source="stored",
        )
    # Try first stored provider
    if stored:
        provider = next(iter(stored))
        info = stored[provider]
        return Credentials(
            provider=provider,
            api_key=info["api_key"],
            base_url=info.get("base_url", ""),
            primary_model=info.get("primary_model", ""),
            fallback_models=info.get("fallback_models", []),
            source="stored",
        )

    # 4. Environment variable
    for prov_id, prov_info in PROVIDERS.items():
        if prov_id == "custom":
            continue
        env_var = prov_info["env_var"]
        env_key = os.environ.get(env_var, "")
        if env_key:
            return Credentials(
                provider=prov_id,
                api_key=env_key,
                base_url=prov_info["base_url"],
                primary_model=prov_info["primary_model"],
                fallback_models=prov_info["fallback_models"],
                source="env",
            )

    # No credentials found
    return Credentials(
        provider="none",
        api_key="",
        base_url="",
        primary_model="",
        fallback_models=[],
        source="none",
    )


def _detect_provider(api_key: str) -> str:
    """Detect provider from API key prefix."""
    for prov_id, prov_info in PROVIDERS.items():
        prefix = prov_info.get("key_prefix", "")
        if prefix and api_key.startswith(prefix):
            # Special case: sk- matches both OpenAI and DeepSeek
            if prefix == "sk-" and prov_id == "openai":
                if api_key.startswith("sk-ant-"):
                    return "anthropic"
                return "openai"
            return prov_id
    return "custom"


def interactive_login() -> Optional[str]:
    """Interactive login flow for CLI.

    Walks the user through selecting a provider and entering their API key.
    Returns the provider name if successful, None if cancelled.
    """
    console.print("\n[bold blue]🦞 IdeaClaw Login[/bold blue]\n")
    console.print("Select a provider:\n")

    provider_list = [p for p in PROVIDERS if p != "custom"]
    for i, prov_id in enumerate(provider_list, 1):
        info = PROVIDERS[prov_id]
        console.print(f"  [bold]{i}[/bold]. {info['name']}")
    console.print(f"  [bold]{len(provider_list) + 1}[/bold]. Custom (OpenAI-compatible)")
    console.print()

    try:
        choice = input("Choose provider (1-7): ").strip()
    except (KeyboardInterrupt, EOFError):
        console.print("\n[yellow]Login cancelled.[/yellow]")
        return None

    try:
        idx = int(choice) - 1
        if 0 <= idx < len(provider_list):
            provider = provider_list[idx]
        elif idx == len(provider_list):
            provider = "custom"
        else:
            console.print("[red]Invalid choice.[/red]")
            return None
    except ValueError:
        console.print("[red]Invalid choice.[/red]")
        return None

    prov_info = PROVIDERS[provider]

    if provider == "custom":
        try:
            base_url = input("Base URL (e.g. http://localhost:11434/v1): ").strip()
            model = input("Model name: ").strip()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[yellow]Login cancelled.[/yellow]")
            return None
    else:
        base_url = prov_info["base_url"]
        model = prov_info["primary_model"]
        dashboard = prov_info["dashboard_url"]
        console.print(f"\n[dim]Get your API key at: {dashboard}[/dim]")

    try:
        api_key = input(f"\n{prov_info['name']} API key: ").strip()
    except (KeyboardInterrupt, EOFError):
        console.print("\n[yellow]Login cancelled.[/yellow]")
        return None

    if not api_key:
        console.print("[red]No API key provided.[/red]")
        return None

    store_api_key(provider, api_key, base_url=base_url, model=model)
    console.print(f"\n[bold green]✅ Saved {prov_info['name']} credentials to {CREDENTIALS_FILE}[/bold green]")
    console.print(f"[dim]Model: {model}[/dim]")
    return provider
