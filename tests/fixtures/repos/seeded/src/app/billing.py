from app import clients


def sumar(valores):
    return sum(valores)


def limpiar(registros):
    salida = []
    for registro in registros:
        nombre = registro.get("nombre", "").strip().lower()
        importe = float(registro.get("importe", 0)) * 1.21
        salida.append({"nombre": nombre, "importe": round(importe, 2)})
    return salida


def origen():
    return clients.API_URL
