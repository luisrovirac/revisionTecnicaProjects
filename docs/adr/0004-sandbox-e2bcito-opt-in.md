# ADR 0004 — Ejecución de código del target solo vía e2bcito, opt-in

- **Estado:** aceptada (implementación en Paso 2) · 2026-11-08

## Contexto
Los tests y la cobertura requieren ejecutar código del proyecto auditado, y ese código no es confiable. El usuario opera e2bcito (`https://aisandbox.lusaxweb.com`, gVisor, SDK Python `e2bcito` 0.2.0), que ya usa el orchestrator de DevSaxAIFloow.

## Decisión
- Puerto `SandboxPort` en el dominio. El único adaptador real usará el SDK `e2bcito`: `Sandbox.create`, `files.upload_folder`, `exec`, `files.read`, `kill`, con `E2BCITO_API_KEY`.
- Opt-in mediante `--run-tests`. Por defecto el análisis es estático.
- Nunca habrá `subprocess` contra código del target (I2).
- Si el sandbox no está disponible, el reporte se degrada: la cobertura pasa a `Gap`.

## Consecuencias
`any.coverage.min` queda como `Gap(capability_missing)` hasta el Paso 2.
