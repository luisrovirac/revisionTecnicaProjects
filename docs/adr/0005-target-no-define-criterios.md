# ADR 0005 — El proyecto auditado nunca define ni relaja sus criterios (I10)

- **Estado:** aceptada · 2026-11-08

## Contexto
Claude Code lee `REVIEW.md` desde la rama base, nunca desde el PR: si el evaluado puede editar su propio pliego de condiciones, el veredicto no vale nada.

## Decisión
- La configuración del operador vive en variables de entorno `TEC_REVIEW_*` y en el catálogo de este repositorio.
- ruff se ejecuta con `--isolated`, que ignora `pyproject.toml`, `ruff.toml` y `# ruff: noqa` de fichero del target.
- Se ignora el triage o las supresiones que traiga SecureProjects desde el repo auditado.
- El `.gitignore` del target solo restringe el alcance; nunca desactiva reglas, rebaja severidades ni toca pesos.
- Las supresiones futuras (`tec-review suppress`) serán del operador, exigirán motivo y quedarán en el manifiesto.

## Consecuencias
Un `pyproject.toml` malicioso en el target no puede apagar `T201` ni `BLE001`.
