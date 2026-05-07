from __future__ import annotations

import ollama

from config.settings import LLM_MODEL, LLM_NUM_PREDICT, LLM_TIMEOUT_SECONDS


client = ollama.Client(timeout=LLM_TIMEOUT_SECONDS)


def call_llm(messages: list[dict[str, str]]) -> str:
    prompt_chars = sum(len(message.get("content", "")) for message in messages)
    print(
        f"DEBUG llm: calling {LLM_MODEL} messages={len(messages)} "
        f"chars={prompt_chars} timeout={LLM_TIMEOUT_SECONDS}s"
    )
    try:
        response = client.chat(
            model=LLM_MODEL,
            messages=messages,
            options={
                "temperature": 0,
                "num_predict": LLM_NUM_PREDICT,
            },
        )
    except Exception as exc:
        raise RuntimeError(
            f"Ollama call failed or timed out for model {LLM_MODEL}: {exc}"
        ) from exc

    return response["message"]["content"]
