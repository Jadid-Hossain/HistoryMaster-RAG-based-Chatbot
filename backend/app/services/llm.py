"""LLM provider abstraction (LangChain chat models).

The provider is chosen from environment variables (.env). With
LLM_PROVIDER=auto the first configured API key wins, so *any* of the
supported keys makes the whole system work.
"""
import os
import re

from ..config import (
    DEEPSEEK_MODEL_DEFAULT,
    GEMINI_MODEL_DEFAULT,
    GROQ_MODEL_DEFAULT,
    LLM_MAX_OUTPUT_TOKENS,
    LLM_MODEL,
    LLM_PROVIDER,
    LLM_TEMPERATURE,
    OPENAI_BASE_URL,
    OPENAI_MODEL_DEFAULT,
    OPENROUTER_MODEL_DEFAULT,
)
from ..logger import get_logger

log = get_logger("historymaster.llm")

PROVIDER_KEY_VARS = {
    "gemini": "GEMINI_API_KEY",
    "openai": "OPENAI_API_KEY",
    "groq": "GROQ_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
}

PROVIDER_MODEL_DEFAULTS = {
    "gemini": GEMINI_MODEL_DEFAULT,
    "openai": OPENAI_MODEL_DEFAULT,
    "groq": GROQ_MODEL_DEFAULT,
    "openrouter": OPENROUTER_MODEL_DEFAULT,
    "deepseek": DEEPSEEK_MODEL_DEFAULT,
}

# Unedited template values from .env(.example) must not be treated as real keys.
_PLACEHOLDER_PATTERN = re.compile(
    r"YOUR_|_HERE$|PASTE_|REPLACE_|CHANGE_|<[^>]*>|\bxxxx\b", re.IGNORECASE
)


def _is_usable_key(key: str) -> bool:
    return bool(key) and not _PLACEHOLDER_PATTERN.search(key)


def resolve_provider() -> tuple[str, str]:
    """Return (provider, api_key|''). Falls back to 'none' when nothing is set."""
    provider = LLM_PROVIDER.strip().lower()
    if provider == "fake":
        return "fake", "fake-key"
    if provider not in ("auto", "", "openai_compatible"):
        key = os.getenv(PROVIDER_KEY_VARS.get(provider, ""), "")
        if _is_usable_key(key):
            return provider, key
        raise RuntimeError(
            f"LLM_PROVIDER={provider} but {'$' + PROVIDER_KEY_VARS.get(provider, 'API_KEY')} "
            "is not set (or still contains the .env template placeholder). "
            "Put your real key in the .env file."
        )
    # auto-detect: first configured key wins
    for name, var in PROVIDER_KEY_VARS.items():
        key = os.getenv(var, "")
        if _is_usable_key(key):
            return name, key
    if OPENAI_BASE_URL:  # custom OpenAI-compatible endpoint without a known brand
        key = os.getenv("OPENAI_API_KEY", "")
        if _is_usable_key(key):
            return "openai_compatible", key
    return "none", ""


class LLMService:
    def __init__(self) -> None:
        self._llm = None
        self.provider: str | None = None
        self.model_name: str | None = None

    @property
    def ready(self) -> bool:
        return self._llm is not None

    def load(self) -> None:
        if self._llm is not None:
            return
        provider, api_key = resolve_provider()
        if provider == "none":
            log.warning(
                "No LLM API key found in environment. Set GEMINI_API_KEY (or another "
                "provider key) in the .env file - the chat will refuse to answer until then."
            )
            return
        if provider == "fake":
            from langchain_core.language_models.fake_chat_models import FakeListChatModel

            self._llm = FakeListChatModel(
                responses=["This is a fake LLM answer for testing."]
            )
            self.provider, self.model_name = "fake", "fake"
            log.info("Using FAKE LLM (testing mode).")
            return

        model = LLM_MODEL.strip() or PROVIDER_MODEL_DEFAULTS[provider]
        common = {"temperature": LLM_TEMPERATURE, "max_output_tokens": LLM_MAX_OUTPUT_TOKENS}
        if provider == "gemini":
            from langchain_google_genai import ChatGoogleGenerativeAI

            self._llm = ChatGoogleGenerativeAI(
                model=model, google_api_key=api_key,
                max_output_tokens=common["max_output_tokens"], temperature=common["temperature"],
            )
        else:  # openai, groq, openrouter, deepseek, openai_compatible - all OpenAI-style
            from langchain_openai import ChatOpenAI

            base_urls = {
                "openai": None,
                "groq": "https://api.groq.com/openai/v1",
                "openrouter": "https://openrouter.ai/api/v1",
                "deepseek": "https://api.deepseek.com/v1",
                "openai_compatible": OPENAI_BASE_URL or None,
            }
            self._llm = ChatOpenAI(
                model=model,
                api_key=api_key,
                base_url=base_urls[provider],
                temperature=common["temperature"],
                max_tokens=common["max_output_tokens"],
            )
        self.provider, self.model_name = provider, model
        log.info("LLM ready: provider=%s model=%s", provider, model)

    def get(self):
        if self._llm is None:
            raise RuntimeError(
                "LLM is not configured. Add your API key to the .env file "
                "(see .env.example) and restart the server."
            )
        return self._llm


llm_service = LLMService()
