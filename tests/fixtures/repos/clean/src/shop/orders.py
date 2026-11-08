from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from shop.invoices import Factura


def crear(factura: "Factura") -> dict:
    return {"factura": factura}
