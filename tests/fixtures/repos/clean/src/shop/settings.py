"""Módulo de configuración: lugar legítimo para valores por defecto (https://docs.example.com)."""

import os

PAYMENTS_URL = os.environ.get("PAYMENTS_URL", "https://api.pagos.local/v1")
