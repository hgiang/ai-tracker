from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import kimi
from app.services.kimi import call_kimi, close_kimi_client


@pytest.fixture(autouse=True)
async def reset_client():
    kimi._client = None
    yield
    await close_kimi_client()


@pytest.mark.unit
@patch("app.services.kimi.settings")
async def test_call_kimi_returns_content(mock_settings):
    mock_settings.kimi_api_key = "test-key"
    mock_settings.kimi_base_url = "https://api.moonshot.ai/v1"
    mock_settings.kimi_model = "kimi-k2.5"

    mock_message = MagicMock()
    mock_message.content = "Hello, world!"
    mock_choice = MagicMock()
    mock_choice.message = mock_message
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]

    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
    mock_client.close = AsyncMock()

    with patch("app.services.kimi.AsyncOpenAI", return_value=mock_client) as mock_ctor:
        result = await call_kimi(system="You are helpful.", user="Say hi.")
        # Second call must reuse the same client.
        await call_kimi(system="sys", user="again")

    assert result == "Hello, world!"
    assert mock_ctor.call_count == 1


@pytest.mark.unit
@patch("app.services.kimi.settings")
async def test_call_kimi_raises_on_empty_key(mock_settings):
    mock_settings.kimi_api_key = ""

    with pytest.raises(ValueError, match="KIMI_API_KEY"):
        await call_kimi(system="sys", user="msg")
