"""LLM factory: Claude (Anthropic SDK), Gemini or OpenAI, or None when no API key is configured.

Every provider is returned as a LangChain Runnable that takes the rendered chat prompt and returns
the answer, so the RAG chain in pipeline.py is the same for all of them.
"""

from __future__ import annotations

import logging
import re

import anthropic
from langchain_core.prompt_values import PromptValue
from langchain_core.runnables import Runnable, RunnableLambda

from app.config import Settings

log = logging.getLogger(__name__)

# Provider errors can echo the API key (Google: "Consumer 'api_key:AQ...' has been suspended"),
# so it is removed before the error text is sent to the UI.
SECRET = re.compile(r"api_key:[\w.-]+|\b(?:AIza|AQ\.|sk-|gsk_)[\w.-]{10,}")


class ClaudeRefusal(Exception):
    """Claude's safety classifiers declined the request (stop_reason == "refusal")."""


class ClaudeChat:
    """Calls Claude through the official Anthropic SDK (Messages API)."""

    def __init__(self, settings: Settings):
        self.model = settings.anthropic_model
        self.effort = settings.anthropic_effort
        # 60 s per attempt so a chat request never hangs for the SDK's 10-minute default
        self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key, timeout=60.0, max_retries=2)

    @staticmethod
    def to_anthropic(prompt: PromptValue) -> tuple[str, list[dict]]:
        """Split a LangChain chat prompt into Claude's top-level system prompt and user/assistant turns."""
        system, messages = [], []
        for m in prompt.to_messages():
            if m.type == "system":
                system.append(m.content)
            elif m.type in ("human", "ai"):
                messages.append({"role": "user" if m.type == "human" else "assistant", "content": m.content})
        while messages and messages[0]["role"] != "user":  # the conversation must start with a user turn
            messages.pop(0)
        return "\n\n".join(system), messages

    def __call__(self, prompt: PromptValue) -> str:
        system, messages = self.to_anthropic(prompt)
        response = self.client.beta.messages.create(
            model=self.model,
            max_tokens=16000,
            system=system,
            messages=messages,
            output_config={"effort": self.effort},
            # if a safety classifier declines, the API retries on Anthropic's recommended fallback model
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
        if response.stop_reason == "refusal":
            category = getattr(response.stop_details, "category", None)
            raise ClaudeRefusal(f"Claude declined the request (category: {category})")
        return "".join(block.text for block in response.content if block.type == "text")


def get_llm(settings: Settings) -> Runnable | None:
    provider = settings.resolved_provider
    if provider == "anthropic":
        if not settings.anthropic_api_key:
            raise ValueError("LLM_PROVIDER=anthropic but ANTHROPIC_API_KEY is not set")
        if not settings.anthropic_api_key.startswith("sk-ant-"):
            log.warning("ANTHROPIC_API_KEY does not look like a Claude API key (expected 'sk-ant-...'); "
                        "Claude will probably reject it")
        return RunnableLambda(ClaudeChat(settings), name="claude")
    if provider == "gemini":
        if not settings.google_api_key:
            raise ValueError("LLM_PROVIDER=gemini but GOOGLE_API_KEY / GEMINI_API_KEY is not set")
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(model=settings.gemini_model, google_api_key=settings.google_api_key,
                                      temperature=settings.llm_temperature, max_retries=2, timeout=60,
                                      vertexai=settings.google_vertexai or None)
    if provider == "openai":
        if not settings.openai_api_key:
            raise ValueError("LLM_PROVIDER=openai but OPENAI_API_KEY is not set")
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(model=settings.openai_model, api_key=settings.openai_api_key,
                          base_url=settings.openai_base_url, temperature=settings.llm_temperature,
                          max_retries=2, timeout=60)
    if provider == "none":
        return None
    raise ValueError(f"Unknown LLM_PROVIDER '{settings.llm_provider}' (use auto, anthropic, gemini, openai or none)")


def model_name(settings: Settings) -> str | None:
    return {
        "anthropic": settings.anthropic_model,
        "gemini": settings.gemini_model,
        "openai": settings.openai_model,
    }.get(settings.resolved_provider)


def describe_llm_error(provider: str, exc: Exception) -> str:
    """A short, actionable explanation of why the LLM call failed (shown in the UI)."""
    if isinstance(exc, ClaudeRefusal):
        return str(exc)
    if isinstance(exc, anthropic.AuthenticationError):
        return ("Claude rejected the API key (401). Claude API keys start with sk-ant- and are created at "
                "platform.claude.com > API Keys. Update ANTHROPIC_API_KEY in backend/.env and restart.")
    if isinstance(exc, anthropic.PermissionDeniedError):
        return "This Claude API key is not allowed to use the model (403)."
    if isinstance(exc, anthropic.NotFoundError):
        return "The Claude model was not found or is not available to this API key (404). Check ANTHROPIC_MODEL."
    if isinstance(exc, anthropic.RateLimitError):
        return "Claude rate limit reached (429). Try again in a minute."
    if isinstance(exc, anthropic.APIStatusError):
        if exc.status_code == 402:
            return "Claude API billing problem (402). Add credits to the Anthropic account."
        return f"Claude API error ({exc.status_code}): {exc.message}"
    if isinstance(exc, anthropic.APIConnectionError):  # includes timeouts
        return "Could not reach the Claude API (network error or timeout)."
    text = str(exc)
    if provider == "gemini":
        if "CONSUMER_SUSPENDED" in text or "has been suspended" in text or "denied access" in text:
            return ("Google has blocked the project that owns this Gemini API key (403: suspended or denied access), "
                    "so no Gemini model will work with it. Contact Google support, or put an ANTHROPIC_API_KEY or "
                    "OPENAI_API_KEY in backend/.env, remove GOOGLE_API_KEY and restart.")
        if "API_KEY_INVALID" in text or "API key not valid" in text:
            return "Google rejected the Gemini API key as invalid. Update GOOGLE_API_KEY in backend/.env and restart."
        if "RESOURCE_EXHAUSTED" in text:
            return "Gemini quota or rate limit reached (429). Try again later or check the project's quota."
    # e.g. "model not found" from Google/OpenAI; redact before truncating so a cut-off key is still removed
    detail = SECRET.sub("[redacted]", " ".join(text.split()))[:240]
    return f"The {provider} LLM call failed ({type(exc).__name__}: {detail})."
