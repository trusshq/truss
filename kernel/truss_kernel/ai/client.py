"""OpenAI-compatible chat client.

One client, every provider: DeepSeek, OpenRouter, Groq, Together, Ollama,
vLLM, LM Studio, OpenAI — anything speaking /chat/completions.
"""
import httpx


class ProviderError(RuntimeError):
    def __init__(self, status: int, detail: str):
        super().__init__(f"provider returned {status}: {detail[:300]}")
        self.status = status
        self.detail = detail


async def chat_completion(
    base_url: str,
    api_key: str,
    model: str,
    messages: list[dict],
    tools: list[dict] | None = None,
    temperature: float = 0.2,
    timeout_s: float = 60.0,
    usage_sink: dict | None = None,
) -> dict:
    """POST /chat/completions and return the first choice's message dict.

    If `usage_sink` is a dict, it is filled with the provider's token usage
    ({"prompt_tokens", "completion_tokens", "total_tokens"}) when reported.
    """
    url = base_url.rstrip("/") + "/chat/completions"
    payload: dict = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    async with httpx.AsyncClient(timeout=timeout_s) as client:
        try:
            resp = await client.post(url, json=payload, headers=headers)
        except httpx.HTTPError as e:
            raise ProviderError(0, f"cannot reach provider at {base_url}: {e}") from e

    if resp.status_code != 200:
        raise ProviderError(resp.status_code, resp.text)

    body = resp.json()
    if usage_sink is not None:
        u = body.get("usage") or {}
        usage_sink["prompt_tokens"] = int(u.get("prompt_tokens") or 0)
        usage_sink["completion_tokens"] = int(u.get("completion_tokens") or 0)
        usage_sink["total_tokens"] = int(u.get("total_tokens") or 0)
    choices = body.get("choices") or []
    if not choices:
        raise ProviderError(200, f"provider returned no choices: {body}")
    return choices[0].get("message") or {}
