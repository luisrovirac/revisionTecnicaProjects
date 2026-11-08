export interface Pedido {
  id: string;
}

export function parsear(datos: any): Pedido {
  return datos as Pedido;
}
