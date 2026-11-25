"""Claude integration tests. A fake client stands in for the Anthropic API: no key or network needed."""

from types import SimpleNamespace

import anthropic
import httpx2
import pytest
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from app.config import Settings
from app.rag.llm import ClaudeChat, ClaudeRefusal, describe_llm_error, get_llm, model_name
from app.rag.pipeline import SYSTEM_PROMPT, USER_PROMPT


def settings(**overrides) -> Settings:
    values = {"llm_provider": "auto", "anthropic_api_key": "test-key", "google_api_key": None,
              "openai_api_key": None, **overrides}
    return Settings(_env_file=None, **values)


class FakeMessages:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


def fake_chat(response) -> tuple[ClaudeChat, FakeMessages]:
    chat = ClaudeChat(settings())
    fake = FakeMessages(response)
    chat.client = SimpleNamespace(beta=SimpleNamespace(messages=fake))
    return chat, fake


def prompt_value(history):
    prompt = ChatPromptTemplate.from_messages([("system", SYSTEM_PROMPT), MessagesPlaceholder("history"), ("human", USER_PROMPT)])
    return prompt.invoke({"context": "[S1] Route 5 CIDCO to SGGS Institute", "question": "CIDCO to SGGS?",
                          "history": history, "now": "Friday 16 October 2026, 09:10", "day_type": "Weekday"})


def test_provider_selection():
    assert settings().resolved_provider == "anthropic"  # Claude preferred when its key is set
    assert settings(anthropic_api_key=None, openai_api_key="x").resolved_provider == "openai"
    gemini = settings(anthropic_api_key=None, google_api_key="x")
    assert gemini.resolved_provider == "gemini" and model_name(gemini) == "gemini-flash-latest"
    assert get_llm(gemini).model.endswith("gemini-flash-latest")
    assert settings(llm_provider="claude").resolved_provider == "anthropic"
    groq = get_llm(settings(llm_provider="openai", openai_api_key="x", openai_base_url="https://api.groq.com/openai/v1"))
    assert groq.openai_api_base == "https://api.groq.com/openai/v1"
    assert model_name(settings()) == "claude-opus-5-5"
    assert get_llm(settings()) is not None
    with pytest.raises(ValueError):
        get_llm(settings(llm_provider="anthropic", anthropic_api_key=None))


def test_prompt_conversion_and_request():
    response = SimpleNamespace(stop_reason="end_turn", stop_details=None, content=[
        SimpleNamespace(type="thinking", thinking=""),
        SimpleNamespace(type="text", text="Take **Route 5** [S1]."),
    ])
    chat, fake = fake_chat(response)
    history = [("ai", "stray assistant turn"), ("user", "hi"), ("ai", "Hello!")]
    assert chat(prompt_value(history)) == "Take **Route 5** [S1]."

    request = fake.calls[0]
    assert request["model"] == "claude-opus-5-5"
    assert "You are RoutePilot" in request["system"] and "Friday 16 October 2026" in request["system"]
    assert [m["role"] for m in request["messages"]] == ["user", "assistant", "user"]  # leading assistant turn dropped
    assert "[S1] Route 5" in request["messages"][-1]["content"]
    assert request["fallbacks"] == "default" and request["betas"] == ["server-side-fallback-2026-07-01"]
    assert request["output_config"] == {"effort": "medium"}
    assert "temperature" not in request and "thinking" not in request


def test_refusal_raises():
    response = SimpleNamespace(stop_reason="refusal", stop_details=SimpleNamespace(category="cyber"), content=[])
    chat, _ = fake_chat(response)
    with pytest.raises(ClaudeRefusal, match="cyber"):
        chat(prompt_value([]))


def test_error_descriptions():
    request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")

    def status_error(cls, code):
        return cls("error", response=httpx2.Response(code, request=request), body=None)

    assert "API key" in describe_llm_error("anthropic", status_error(anthropic.AuthenticationError, 401))
    assert "rate limit" in describe_llm_error("anthropic", status_error(anthropic.RateLimitError, 429))
    assert "billing" in describe_llm_error("anthropic", status_error(anthropic.APIStatusError, 402))
    assert "network" in describe_llm_error("anthropic", anthropic.APIConnectionError(request=request))


def test_gemini_errors_are_explained_without_the_key():
    key = "AQ.FakeKeyForTests0123456789abcdef"
    suspended = Exception(f"403 PERMISSION_DENIED. Consumer 'api_key:{key}' has been suspended. CONSUMER_SUSPENDED")
    assert "suspended" in describe_llm_error("gemini", suspended)
    denied = Exception("403 PERMISSION_DENIED. Your project has been denied access. Please contact support.")
    assert "blocked" in describe_llm_error("gemini", denied)
    assert "invalid" in describe_llm_error("gemini", Exception("400 INVALID_ARGUMENT. API key not valid."))
    assert "quota" in describe_llm_error("gemini", Exception("429 RESOURCE_EXHAUSTED."))
    message = describe_llm_error("gemini", Exception(f"500 INTERNAL for 'api_key:{key}' and AIzaSyFake0123456789"))
    assert key not in message and "AIzaSy" not in message and "[redacted]" in message
