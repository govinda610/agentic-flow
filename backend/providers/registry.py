from langchain_anthropic import ChatAnthropic
from config import settings
from functools import lru_cache

def get_llm(model: str | None = None, temperature: float = 0.0, max_tokens: int = 4096):
    """
    Returns a ChatAnthropic instance pointed at z.ai (GLM-5-turbo).
    Uses LangChain's ChatAnthropic with a custom base_url for full
    compatibility with create_agent(..., response_format=...) and astream_events().
    """
    if not settings.glm_api_key:
        raise RuntimeError("GLM_API_KEY is not set in environment or .env file.")
    resolved_model = model or settings.glm_model
    return _get_llm_cached(resolved_model, temperature, max_tokens)


@lru_cache(maxsize=32)
def _get_llm_cached(model: str, temperature: float, max_tokens: int):
    return ChatAnthropic(
        model=model,
        api_key=settings.glm_api_key,
        base_url=settings.glm_base_url,
        temperature=temperature,
        max_tokens=max_tokens,
    )
