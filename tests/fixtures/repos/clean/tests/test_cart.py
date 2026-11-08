from shop.cart import Carrito


def test_carrito_vacio():
    assert Carrito().contar() == 0
