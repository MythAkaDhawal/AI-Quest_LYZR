import json
import time
from typing import Type, TypeVar
from pydantic import BaseModel, ValidationError
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from backend.core.config import settings
from backend.utils.logging_config import logger

T = TypeVar("T", bound=BaseModel)


class AgentUnavailableError(Exception):
    pass


@retry(
    reraise=True,
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.5, min=0.5, max=4.0),
    retry=retry_if_exception_type((ValidationError, json.JSONDecodeError, ConnectionError, ValueError)),
)
def call_llm_agent(
    prompt: str,
    agent_name: str,
    role: str,
    goal: str,
    instructions: str,
    model_cls: Type[T],
) -> tuple[T, dict, float]:
    t0 = time.perf_counter()
    raw_response_text = None
    prompt_tokens = 0
    completion_tokens = 0

    # Transport Selection: Try Lyzr ADK Studio first, fallback to Groq SDK
    if settings.LYZR_API_KEY and settings.LYZR_API_KEY != "your_lyzr_api_key_here":
        try:
            from lyzr import Studio

            studio = Studio(api_key=settings.LYZR_API_KEY)
            agent = studio.create_agent(
                name=agent_name,
                provider=f"groq/{settings.GROQ_MODEL_ID}",
                role=role,
                goal=goal,
                instructions=instructions,
                temperature=0,
                response_format={"type": "json_object"},
            )
            res = agent.run(prompt)
            raw_response_text = res.response
            usage = getattr(res, "usage", None)
            if usage:
                prompt_tokens = getattr(usage, "prompt_tokens", 0)
                completion_tokens = getattr(usage, "completion_tokens", 0)
        except Exception as exc:
            logger.warning(f"Lyzr Studio call failed for {agent_name}, attempting direct Groq SDK: {exc}")

    if not raw_response_text and settings.GROQ_API_KEY and settings.GROQ_API_KEY != "your_groq_api_key_here":
        from groq import Groq

        client = Groq(api_key=settings.GROQ_API_KEY)
        chat_completion = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model=settings.GROQ_MODEL_ID,
            response_format={"type": "json_object"},
            temperature=0.0,
        )
        raw_response_text = chat_completion.choices[0].message.content
        if getattr(chat_completion, "usage", None):
            prompt_tokens = chat_completion.usage.prompt_tokens
            completion_tokens = chat_completion.usage.completion_tokens

    if not raw_response_text:
        raise ValueError("Neither LYZR_API_KEY nor GROQ_API_KEY is configured with valid credentials.")

    elapsed_ms = (time.perf_counter() - t0) * 1000

    # Clean potential markdown code blocks
    cleaned_text = raw_response_text.strip()
    if cleaned_text.startswith("```json"):
        cleaned_text = cleaned_text[7:]
    if cleaned_text.startswith("```"):
        cleaned_text = cleaned_text[3:]
    if cleaned_text.endswith("```"):
        cleaned_text = cleaned_text[:-3]
    cleaned_text = cleaned_text.strip()

    parsed = json.loads(cleaned_text)
    validated = model_cls.model_validate(parsed)

    if prompt_tokens == 0:
        prompt_tokens = len(prompt) // 4
    if completion_tokens == 0:
        completion_tokens = len(cleaned_text) // 4

    token_usage = {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
    }

    return validated, token_usage, elapsed_ms
