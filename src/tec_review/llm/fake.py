"""LLM falso: la suite completa corre sin red y sin coste (planInicial §7.3)."""

from __future__ import annotations

import json
import re
from collections.abc import Callable

from tec_review.domain.ports import LLMError, LLMMessage, LLMResponse

FINGERPRINT = re.compile(r"- fingerprint: (\S+)")
FIRST_LINE = re.compile(r"^\s*(\d+) \|", re.MULTILINE)


def grounded_answer(messages: list[LLMMessage]) -> str:
    """Respuesta válida y anclada a la primera línea del fragmento."""
    user = messages[1].content
    fingerprint = FINGERPRINT.search(user).group(1)
    line_match = FIRST_LINE.search(user)
    line = int(line_match.group(1)) if line_match else 1
    return json.dumps({
        "fingerprint": fingerprint,
        "explanation": "El fragmento incumple la regla citada.",
        "impact": "Aumenta el coste de mantenimiento.",
        "fix": "Aplicar el safe_path indicado.",
        "priority": 2,
        "claims": [{"text": "La regla se incumple en el fragmento.", "evidence_lines": [line]}],
    })


class FakeLLM:
    name = "fake"

    def __init__(self, responder: Callable[[list[LLMMessage]], str] = grounded_answer,
                 fail: bool = False) -> None:
        self.responder, self.fail, self.calls = responder, fail, 0

    def complete(self, messages: list[LLMMessage], max_tokens: int) -> LLMResponse:
        self.calls += 1
        if self.fail:
            raise LLMError("fallo simulado del proveedor")
        return LLMResponse(content=self.responder(messages), model_used="fake-model",
                           prompt_tokens=100, completion_tokens=50, elapsed_ms=1.0)
