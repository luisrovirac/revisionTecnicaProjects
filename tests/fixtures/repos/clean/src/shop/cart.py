"""Carrito limpio: contraejemplos seguros de cada regla del Paso 0."""

import logging

logger = logging.getLogger(__name__)


def total(items):
    """Docstring larga que no cuenta como línea lógica.

    Más texto de documentación.
    """
    import json  # librería estándar: permitido dentro de una función

    acumulado = 0
    for item in items:
        acumulado += item["precio"] * item["cantidad"]
    logger.info("total calculado %s", json.dumps(acumulado))
    return acumulado


def leer_config(ruta):
    try:
        with open(ruta, encoding="utf-8") as handle:
            return handle.read()
    except FileNotFoundError:
        return ""
    except Exception:
        logger.exception("error inesperado leyendo %s", ruta)
        raise


class Carrito:
    def agregar(self, item):
        self._items().append(item)

    def quitar(self, item):
        self._items().remove(item)

    def vaciar(self):
        self._items().clear()

    def total(self):
        return total(self._items())

    def contar(self):
        return len(self._items())

    def _items(self):
        if not hasattr(self, "_datos"):
            self._datos = []
        return self._datos
