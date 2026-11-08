"""Pista A: el hecho existe, el modelo lo explica. Loop agéntico acotado por reintentos y presupuesto.

Un fallo del modelo nunca tumba la ejecución (I9): se degrada a plantilla y se marca
`unverifiable`. El modelo no puede alterar el hallazgo (I3/I4): su salida es otra entidad.
"""

from __future__ import annotations

import json

from pydantic import BaseModel, ValidationError

from tec_review.agentic.prompts import build_messages, messages_hash
from tec_review.agentic.verify import Verification, verify
from tec_review.domain.models import (
    ContextBundle,
    Hallazgo,
    Interpretacion,
    LLMInterpretation,
    LLMUsage,
)
from tec_review.domain.ports import LLMError, LLMMessage, LLMPort, LLMResponse

MAX_RETRIES = 2


class ParseFailure(ValueError):
    """La respuesta del modelo no cumple el esquema."""


def parse_llm_json(content: str) -> LLMInterpretation:
    start, end = content.find("{"), content.rfind("}")
    if start < 0 or end <= start:
        raise ParseFailure("la respuesta no contiene un objeto JSON")
    try:
        return LLMInterpretation.model_validate(json.loads(content[start : end + 1]))
    except (json.JSONDecodeError, ValidationError) as exc:
        raise ParseFailure(str(exc)[:600]) from exc


def fallback(h: Hallazgo, bundle: ContextBundle, status: str, reasons: list[str],
             verification: Verification | None = None, model: str = "") -> Interpretacion:
    """Plantilla determinista: el reporte siempre tiene explicación, regla y safe_path."""
    return Interpretacion(
        fingerprint=h.fingerprint, status=status, explanation=h.message,
        impact=f"Incumple {bundle.rule_ref}: «{bundle.rule_quote}»", fix=bundle.safe_path,
        fix_valid=True, claims_total=verification.claims_total if verification else 0,
        claims_grounded=verification.claims_grounded if verification else 0,
        rejection_reasons=tuple(reasons), model_used=model,
    )


class Budget(BaseModel):
    limit: int
    used: int = 0

    @property
    def exhausted(self) -> bool:
        return self.used >= self.limit


class MeteredLLM:
    """Llamadas al modelo que descuentan del presupuesto y registran el uso (Pistas A y B)."""

    def __init__(self, llm: LLMPort, max_tokens: int, budget: Budget, usage: LLMUsage) -> None:
        self.llm, self.max_tokens, self.budget, self.usage = llm, max_tokens, budget, usage

    def _call(self, messages: list[LLMMessage]) -> LLMResponse:
        self.usage.calls += 1
        try:
            response = self.llm.complete(messages, max_tokens=self.max_tokens)
        except LLMError:
            self.usage.failed_calls += 1
            raise
        self._account(response)
        return response

    def _account(self, response: LLMResponse) -> None:
        self.budget.used += response.prompt_tokens + response.completion_tokens
        self.usage.prompt_tokens += response.prompt_tokens
        self.usage.completion_tokens += response.completion_tokens
        self.usage.elapsed_ms += response.elapsed_ms
        if response.model_used and response.model_used not in self.usage.models_used:
            self.usage.models_used.append(response.model_used)


class Interpreter(MeteredLLM):

    def interpret(self, h: Hallazgo, bundle: ContextBundle) -> Interpretacion:
        if self.budget.exhausted:
            return fallback(h, bundle, "skipped_budget", ["presupuesto de tokens agotado"])
        messages = build_messages(bundle)
        prompt_hash = messages_hash(messages)
        try:
            output, model = self._ask_until_valid(messages)
        except (LLMError, ParseFailure) as exc:
            return fallback(h, bundle, "unverifiable", [str(exc)[:300]]).model_copy(
                update={"prompt_hash": prompt_hash})
        return self._publish(h, bundle, output, model, prompt_hash)

    def _publish(self, h, bundle, output: LLMInterpretation, model: str, prompt_hash: str):
        result = verify(output, bundle)
        if not result.confirmed:
            return fallback(h, bundle, "unverifiable", result.reasons, result, model).model_copy(
                update={"prompt_hash": prompt_hash})
        return Interpretacion(
            fingerprint=h.fingerprint, status="confirmed", explanation=output.explanation,
            impact=output.impact, fix=output.fix if result.fix_valid else bundle.safe_path,
            fix_valid=result.fix_valid, priority=output.priority,
            claims_total=result.claims_total, claims_grounded=result.claims_grounded,
            model_used=model, prompt_hash=prompt_hash,
        )

    def _ask_until_valid(self, messages: list[LLMMessage]) -> tuple[LLMInterpretation, str]:
        error: ParseFailure | None = None
        for _ in range(1 + MAX_RETRIES):
            response = self._call(messages)
            try:
                return parse_llm_json(response.content), response.model_used
            except ParseFailure as exc:
                error = exc
                messages = [*messages, LLMMessage(role="assistant", content=response.content),
                            LLMMessage(role="user", content=f"Tu respuesta no cumple el esquema: "
                                       f"{exc}. Devuelve solo el JSON corregido.")]
            if self.budget.exhausted:
                break
        raise error or ParseFailure("sin respuesta válida")
