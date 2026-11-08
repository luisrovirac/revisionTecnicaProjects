// "any" en un comentario no cuenta
export function parsear(datos: unknown): string {
  return typeof datos === "string" ? datos : "any";
}
