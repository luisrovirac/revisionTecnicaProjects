"""Telemetría opcional hacia el servicio `telemetry` de DevSaxAIFloow (POST /v1/events).

Fire-and-forget: un fallo de telemetría nunca afecta a la ejecución ni al reporte.
"""

from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)


class NullTelemetry:
    def publish(self, event_type: str, **payload: object) -> None:
        return None


class HttpTelemetry:
    def __init__(self, base_url: str, session_id: str, timeout_s: float = 2.0) -> None:
        self.url = f"{base_url.rstrip('/')}/v1/events"
        self.session_id = session_id
        self._client = httpx.Client(timeout=timeout_s)

    def publish(self, event_type: str, **payload: object) -> None:
        body = {"session_id": self.session_id, "event_type": event_type, "payload": payload}
        try:
            self._client.post(self.url, json=body)
        except httpx.HTTPError as exc:
            logger.debug("Telemetría no disponible: %s", exc)
