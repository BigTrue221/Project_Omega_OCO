import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from core.llm import LLMClient


def test_llama_cpp_remains_the_default_local_protocol(monkeypatch):
    monkeypatch.setenv("USE_CLOUD_LLM", "false")
    monkeypatch.delenv("OCO_LOCAL_LLM_PROVIDER", raising=False)
    monkeypatch.setenv("OCO_LOCAL_LLM_URL", "http://127.0.0.1:8081/v1/chat/completions")
    monkeypatch.delenv("OCO_LOCAL_LLM_MODEL", raising=False)
    monkeypatch.setenv("OCO_OLLAMA_NUM_CTX", "9999")
    monkeypatch.setenv("OCO_OLLAMA_TIMEOUT", "1")

    client = LLMClient()
    captured = {}

    def fake_post(url, headers, data, timeout):
        captured.update(url=url, data=data, timeout=timeout)
        return '{"choices":[{"message":{"content":"ok"}}]}'

    monkeypatch.setattr(client, "_curl_post", fake_post)
    assert client.chat("system", "user") == "ok"
    assert captured["url"].endswith("/v1/chat/completions")
    assert captured["data"]["model"] == "qwen"
    assert captured["timeout"] == 120
    assert "options" not in captured["data"]
    assert "response_format" not in captured["data"]


def test_ollama_is_an_explicit_additive_option(monkeypatch):
    monkeypatch.setenv("USE_CLOUD_LLM", "false")
    monkeypatch.setenv("OCO_LOCAL_LLM_PROVIDER", "ollama")
    monkeypatch.setenv("OCO_LOCAL_LLM_URL", "http://127.0.0.1:11434/api/chat")
    monkeypatch.setenv("OCO_LOCAL_LLM_MODEL", "ollama/dolphin3-mistral-32k:latest")
    monkeypatch.setenv("OCO_OLLAMA_NUM_CTX", "2048")
    monkeypatch.setenv("OCO_OLLAMA_TIMEOUT", "300")

    client = LLMClient()
    captured = {}

    def fake_post(url, headers, data, timeout):
        captured.update(url=url, data=data, timeout=timeout)
        return '{"message":{"content":"{\\"ok\\":true}"},"done":true}'

    monkeypatch.setattr(client, "_curl_post", fake_post)
    assert client.chat("system", "user", response_format="json_object") == '{"ok":true}'
    assert captured["data"]["model"] == "dolphin3-mistral-32k:latest"
    assert captured["data"]["options"] == {"num_ctx": 2048}
    assert captured["data"]["stream"] is False
    assert captured["data"]["format"] == "json"
    assert "response_format" not in captured["data"]
