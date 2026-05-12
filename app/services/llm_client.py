"""Unified LLM client supporting multiple AI providers."""
from __future__ import annotations

from enum import Enum

from openai import AsyncOpenAI


class Provider(str, Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"
    GROK = "grok"
    KIMI = "kimi"


PROVIDER_CONFIGS: dict[Provider, dict] = {
    Provider.OPENAI: {
        "base_url": None,
        "model": "gpt-4o",
        "label": "OpenAI",
    },
    Provider.ANTHROPIC: {
        "base_url": None,
        "model": "claude-sonnet-4-6",
        "label": "Anthropic",
    },
    Provider.GEMINI: {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "model": "gemini-2.0-flash",
        "label": "Google Gemini",
    },
    Provider.GROK: {
        "base_url": "https://api.x.ai/v1",
        "model": "grok-3-mini",
        "label": "Grok",
    },
    Provider.KIMI: {
        "base_url": "https://api.moonshot.ai/v1",
        "model": "kimi-k2.6",
        "label": "Kimi",
        # kimi-k2.6 is a reasoning model that emits a large `reasoning_content`
        # field counted against max_tokens. We don't use that content, so we
        # disable thinking — content fills the full token budget instead.
        "extra_body": {"thinking": {"type": "disabled"}},
    },
}


async def call_llm(
    provider: Provider,
    api_key: str,
    system: str,
    user: str,
    max_tokens: int = 8192,
) -> str:
    """Call an LLM provider and return the response text."""
    if not api_key:
        raise ValueError(f"API key is required for provider '{provider}'")

    config = PROVIDER_CONFIGS[provider]

    if provider == Provider.ANTHROPIC:
        import anthropic as anthropic_sdk  # optional dep — only imported when needed

        client = anthropic_sdk.AsyncAnthropic(api_key=api_key)
        message = await client.messages.create(
            model=config["model"],
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        content = message.content[0].text if message.content else None
        if content is None:
            raise ValueError("Anthropic returned an empty response")
        return content

    # All other providers use the OpenAI-compatible API
    client_kwargs: dict = {"api_key": api_key}
    if config["base_url"]:
        client_kwargs["base_url"] = config["base_url"]
    client = AsyncOpenAI(**client_kwargs)
    create_kwargs: dict = {
        "model": config["model"],
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "max_tokens": max_tokens,
    }
    if extra := config.get("extra_body"):
        create_kwargs["extra_body"] = extra
    response = await client.chat.completions.create(**create_kwargs)
    if not response.choices:
        raise ValueError(f"{provider} returned no choices")
    choice = response.choices[0]
    content = choice.message.content
    if not content:
        # Reasoning models (e.g. kimi-k2.6) can exhaust max_tokens on internal
        # reasoning_content and emit empty content. Surface a useful error.
        finish_reason = getattr(choice, "finish_reason", "unknown")
        raise ValueError(
            f"{provider} returned empty content (finish_reason={finish_reason}); "
            f"increase max_tokens — reasoning models need extra headroom."
        )
    return content
