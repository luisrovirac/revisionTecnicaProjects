# ADR 0003 — Vía LLM: llm-router de DevSaxAIFloow tras un puerto propio

- **Estado:** aceptada · 2026-11-08

## Contexto
El plan v0.2 dejaba el contrato del LLM "pendiente". El usuario ya opera `Services/llm-router` (puerto 8001): selección de modelo por rol, failover entre proveedores (incluido modelo local vía `local/<modelo>`), circuit breaker, y devuelve `model_used`, tokens y latencia.

## Decisión
- Puerto `LLMPort.complete(messages, max_tokens) -> LLMResponse` en el dominio; el núcleo no conoce al proveedor.
- Adaptador `LlmRouterAdapter` (httpx) sobre `POST /v1/chat/completions`, patrón tomado de `orchestrator/app/clients/http_clients.py`. Rol por defecto `tool_coder`, `temperature=0`. Se descartó `validator`: en el perfil Plus apunta a `deepseek-r1`, un modelo de razonamiento. Medido sobre el repo sembrado: `validator` tardó 10 min 17 s con un 37,5 % confirmado; `tool_coder` (`deepseek-chat-v3`) tardó 63 s con un 87,5 % confirmado. En ambos casos la alucinación fue del 0 %.
- llm-router **no ofrece salida estructurada**: el JSON se pide en el prompt, se parsea con Pydantic (`extra="forbid"`) y se reintenta hasta 2 veces con el error como feedback.
- `FakeLLM` permite correr toda la suite sin red.
- Si el router no responde al inicio, la ejecución sigue sin LLM y lo declara (I9).

## Consecuencias
- Modelo, tokens y latencia quedan en `manifest.json` (I8).
- Mejora propuesta para el router (fuera de este repo): un passthrough de `response_format`, que LiteLLM ya soporta.
