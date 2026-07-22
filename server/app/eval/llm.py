import json
import time
from typing import Any, Protocol

import httpx


class LLMProvider(Protocol):
    """Protocol for an LLM completion provider."""

    def complete(
        self,
        messages: list[dict[str, Any]],
        *,
        json_schema: dict | None = None,
        max_tokens: int = 4096,
    ) -> str:
        ...


class OpenAICompatProvider:
    """OpenAI-compatible chat completions provider with retries."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        timeout: float = 120,
        max_retries: int = 3,
        transport: httpx.BaseTransport | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.max_retries = max_retries
        self.client = httpx.Client(timeout=timeout, transport=transport)

    def _url(self) -> str:
        return f"{self.base_url}/chat/completions"

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _uses_kimi_parameters(self) -> bool:
        """Kimi K2.x accepts a narrower set of OpenAI-compatible parameters."""
        base_url = self.base_url.lower()
        return (
            self.model.lower().startswith("kimi-")
            or "moonshot.cn" in base_url
            or "moonshot.ai" in base_url
        )

    def complete(
        self,
        messages: list[dict[str, Any]],
        *,
        json_schema: dict | None = None,
        max_tokens: int = 4096,
    ) -> str:
        body: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
        }
        if self._uses_kimi_parameters():
            # Kimi K2.6 uses different fixed temperatures by thinking mode.
            # With thinking disabled (as used for structured evaluation), its
            # API requires 0.6. It also uses ``max_completion_tokens`` as the
            # current output limit.
            # Evaluation only needs the final JSON, so disable its optional
            # thinking trace to keep long project reviews within the HTTP
            # read timeout.
            body["temperature"] = 0.6
            body["max_completion_tokens"] = max_tokens
            body["thinking"] = {"type": "disabled"}
        else:
            body["temperature"] = 0.1
            body["max_tokens"] = max_tokens
        if json_schema is not None:
            body["response_format"] = {"type": "json_object"}

        last_exception: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                response = self.client.post(
                    self._url(), headers=self._headers(), json=body
                )
            except httpx.TimeoutException as exc:
                last_exception = exc
                if attempt == self.max_retries - 1:
                    raise
                time.sleep(2 ** attempt)
                continue

            if response.status_code == 429 or response.status_code >= 500:
                last_exception = httpx.HTTPStatusError(
                    f"HTTP {response.status_code}",
                    request=response.request,
                    response=response,
                )
                if attempt == self.max_retries - 1:
                    response.raise_for_status()
                time.sleep(2 ** attempt)
                continue

            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                # Preserve an API's concise error body in the job record;
                # this makes provider-parameter issues diagnosable in the UI.
                detail = response.text.strip()
                if detail:
                    raise httpx.HTTPStatusError(
                        f"{exc} Response: {detail[:1000]}",
                        request=exc.request,
                        response=exc.response,
                    ) from exc
                raise
            data = response.json()
            return data["choices"][0]["message"]["content"]

        raise RuntimeError(
            f"LLM request failed after {self.max_retries} attempts"
        ) from last_exception

    def close(self) -> None:
        self.client.close()

    def __enter__(self) -> "OpenAICompatProvider":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
