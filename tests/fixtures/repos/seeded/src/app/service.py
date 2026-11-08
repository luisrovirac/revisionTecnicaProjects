"""Servicio con violaciones sembradas (fixture de tec-review)."""


def calcular_factura(items, cliente, descuento, impuestos):
    total = 0
    for item in items:
        precio = item["precio"]
        cantidad = item["cantidad"]
        subtotal = precio * cantidad
        if item.get("oferta"):
            subtotal = subtotal * 0.9
        total += subtotal
    if cliente.get("vip"):
        total = total * 0.95
    if descuento:
        total = total - descuento
    if total < 0:
        total = 0
    base = total
    iva = base * impuestos
    total = base + iva
    redondeo = round(total, 2)
    resultado = {"base": base, "iva": iva}
    resultado["total"] = redondeo
    resultado["cliente"] = cliente.get("id")
    return resultado


def descargar(url):
    import requests

    return requests.get(url, timeout=5).text


class GestorPedidos:
    def crear(self):
        return 1

    def leer(self):
        return 2

    def actualizar(self):
        return 3

    def borrar(self):
        return 4

    def listar(self):
        return 5

    def exportar(self):
        return 6
