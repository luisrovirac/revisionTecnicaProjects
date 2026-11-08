# ADR 0006 — Pista B: candidatos deterministas, evidencia obligatoria y fuera del score

- **Estado:** aceptada · 2026-11-08

## Contexto
Las 12 reglas de juicio (SRP, DIP, OCP, ISP, LSP, puntos de entrada delgados, validación de configuración, reintentos, liberación de recursos y 3 de seguridad de LLM) no se pueden detectar con un linter. Es también donde vive casi todo el riesgo de alucinación: aquí el modelo **encuentra**, no solo explica.

## Decisión
1. **El modelo no recorre el repositorio.** Cada regla tiene un selector determinista y explicable (`agentic/candidates.py`) que propone regiones con un motivo (`hint`). Ejemplos: funciones de 25 o más líneas para SRP, instanciaciones `CapWords()` dentro de métodos para DIP, llamadas a LLM sin `max_tokens`. Hay un tope por regla (`track_b_max_per_rule`, 6 por defecto) y el presupuesto de tokens se comparte con la Pista A, que va primero.
2. **Juicio conservador.** El prompt exige responder `violates: false` ante la duda.
3. **Evidencia obligatoria.** Un juicio se publica solo si cumple todo esto:
   - Trae una entrada por cada campo de `evidence_required` de la regla.
   - Cada línea de cada cita aparece literalmente en la región examinada, y los números de línea citados pertenecen a ella. Se tolera un número de línea impreciso, pero no un texto que no existe: las paráfrasis se rechazan.
   - No nombra identificadores que no estén en la región.
   Si falla, el juicio queda `rejected` y se cuenta.
4. **Fuera del score y del veredicto.** Los hallazgos de juicio no son deterministas, así que meterlos en el score rompería I5. Se reportan en su propia sección, con confianza 0,6 y la etiqueta "requiere revisión humana".
5. **Activación:** `--track-b` o `--level deep`. Si se pide sin LLM disponible, la Pista B queda como herramienta no disponible y sus reglas aparecen como gap con ese motivo.

## Consecuencias
- Con la Pista B activa, las 12 reglas cuentan como evaluadas para Python. La cobertura refleja lo que se examinó de verdad.
- Un selector que no encuentra candidatos deja la regla evaluada sin hallazgos. Los selectores son heurísticos, y por eso la advertencia de no-exhaustividad sigue siendo obligatoria.
- Métrica propia: `rejection_rate` = rechazados por verificación / propuestos por el modelo. Mide cuánto intenta inventar el modelo.

## Evidencia (2026-11-08, `Services/llm-router`, nivel quick)
- 19 candidatos juzgados: 12 publicados en la primera versión, 1 descartado por el modelo y 6 rechazados (33 %).
- Al revisar los rechazos, 5 eran citas reales con números de línea imprecisos. Con la tolerancia de línea solo queda rechazada 1 de 18 (6 %), una paráfrasis.
- Con la Pista B activa, la cobertura pasó de 12/30 a 25/30. Las 5 restantes eran las 4 reglas `sec.*`, porque SecureProjects estaba desactivado en esa prueba, y la de cobertura (sin `E2BCITO_API_KEY`).
