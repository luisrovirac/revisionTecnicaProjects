from app.service import calcular_factura


def ejecutar():
    try:
        datos = calcular_factura([], {}, 0, 0.21)
    except:
        datos = None
    print(datos)
    return datos


def cargar(ruta):
    try:
        with open(ruta, encoding="utf-8") as handle:
            return handle.read()
    except Exception:
        return ""
