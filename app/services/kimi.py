from openai import AsyncOpenAI

from app.config import settings

_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(
            api_key=settings.kimi_api_key,
            base_url=settings.kimi_base_url,
        )
    return _client


async def close_kimi_client() -> None:
    global _client
    if _client is not None:
        await _client.close()
        _client = None


async def call_kimi(system: str, user: str, max_tokens: int = 8192) -> str:
    """Call Kimi K2.5 via the OpenAI-compatible API and return the response text."""
    if not settings.kimi_api_key:
        raise ValueError("KIMI_API_KEY is not configured")

    client = _get_client()
    response = await client.chat.completions.create(
        model=settings.kimi_model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        max_tokens=max_tokens,
    )
    if not response.choices:
        raise ValueError("Kimi returned a response with no choices")
    content = response.choices[0].message.content
    if content is None:
        raise ValueError("Kimi returned an empty response (no content in choices[0].message)")
    return content
