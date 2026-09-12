from __future__ import annotations

from apps.api.senti_next.providers.config import _provider_has_key
from apps.api.senti_next.providers.openai_compat import OpenAICompatProvider


def test_deepseek_provider_uses_compatible_endpoint_and_key(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    provider = OpenAICompatProvider(provider_type="deepseek", model_name="deepseek-chat")

    assert _provider_has_key("deepseek") is True
    assert provider.name == "deepseek"
    assert provider.model == "deepseek-chat"
    assert provider._base_url == "https://api.deepseek.com/v1"
    assert provider._get_api_key() == "test-key"


def test_deepseek_structured_requests_use_json_object(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    provider = OpenAICompatProvider(provider_type="deepseek", model_name="deepseek-chat")
    captured = {}

    def fake_call(kwargs):
        captured.update(kwargs)
        return "{}"

    monkeypatch.setattr(provider, "_call_with_retry", fake_call)
    provider.generate("return json", response_schema={"type": "object"})

    assert captured["response_format"] == {"type": "json_object"}
