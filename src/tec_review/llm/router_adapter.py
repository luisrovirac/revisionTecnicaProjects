"""Adaptador de llm-router (DevSaxAIFloow Services, ADR 0003).

Contrato: POST {base}/v1/chat/completions con {messages, role|model, temperature, max_tokens}
-> {model_used, content, usage{prompt_tokens, completion_tokens}, elapsed_ms, attempts}.
Patrón tomado de orchestrator/app/clients/http_clients.py (HttpLLMRouter.chat).
"""

from __future__ import annotations

import httpx
from pydantic import BaseModel, ConfigDict, ValidationError

from tec_review.domain.ports import LLMError, LLMMessage, LLMResponse


class _Usage(BaseModel):
    model_config = ConfigDict(extra="ignore")
    prompt_tokens: int = 0
    completion_tokens: int = 0


class _RouterResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    model_used: str
    content: str
    usage: _Usage = _Usage()
    elapsed_ms: float = 0.0


class LlmRouterAdapter:
    name = "llm-router"

    def __init__(self, base_url: str, timeout_s: float, role: str | None, model: str | None,
                 client: httpx.Client | None = None) -> None:
        if not role and not model:
            raise ValueError("llm-router exige role o model (TEC_REVIEW_LLM_ROLE / TEC_REVIEW_LLM_MODEL)")
        self.base_url, self.role, self.model = base_url.rstrip("/"), role, model
        self._client = client or httpx.Client(timeout=timeout_s)

    def _payload(self, messages: list[LLMMessage], max_tokens: int) -> dict:
        payload = {"messages": [m.model_dump() for m in messages], "temperature": 0.0,
                   "max_tokens": max_tokens, "node_label": "tec-review"}
        payload.update({"model": self.model} if self.model else {"role": self.role})
        return payload

    def complete(self, messages: list[LLMMessage], max_tokens: int) -> LLMResponse:
        url = f"{self.base_url}/v1/chat/completions"
        try:
            response = self._client.post(url, json=self._payload(messages, max_tokens))
        except httpx.HTTPError as exc:
            raise LLMError(f"llm-router inaccesible en {self.base_url}: {exc}") from exc
        if response.status_code != 200:
            raise LLMError(f"llm-router HTTP {response.status_code}: {response.text[:300]}")
        try:
            data = _RouterResponse.model_validate(response.json())
        except (ValueError, ValidationError) as exc:
            raise LLMError(f"Respuesta de llm-router inválida: {exc}") from exc
        return LLMResponse(content=data.content, model_used=data.model_used,
                           prompt_tokens=data.usage.prompt_tokens,
                           completion_tokens=data.usage.completion_tokens,
                           elapsed_ms=data.elapsed_ms)

    def health(self) -> bool:
        try:
            return self._client.get(f"{self.base_url}/v1/models").status_code == 200
        except httpx.HTTPError:
            return False
