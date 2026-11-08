# tec-review

Revisión técnica de un proyecto contra las reglas de `Rules/`. Combina **hechos deterministas** con una **interpretación del modelo que se verifica** antes de publicarse.

```
inventario → analizadores (AST, ruff, SecureProjects) → catálogo → triage
           → LLM explica (solo hallazgos seleccionados) → verificación → score → reporte
```

El modelo nunca decide qué está mal, ni dónde, ni con qué severidad. Explica hechos ya comprobados. Si su explicación cita líneas o identificadores que no están en el contexto que recibió, se descarta y se publica una plantilla determinista. Diseño completo en [`docs/planInicial.md`](docs/planInicial.md); decisiones en [`docs/adr/`](docs/adr/).

## Instalación

```powershell
py -3.11 -m venv .venv
.venv\Scripts\pip install -e ".[dev]"
.venv\Scripts\tec-review doctor
```

## Uso

```powershell
# Revisión completa: usa llm-router en http://localhost:8001
tec-review review C:\ruta\al\proyecto

# Solo la capa determinista (sin LLM, reproducible)
tec-review review C:\ruta\al\proyecto --no-llm

# Ruleset de DevSaxAIFloow, nivel rápido (top 10 interpretados)
tec-review review C:\ruta\al\proyecto --ruleset devsaxaiflow --level quick

tec-review rules list
tec-review rules show py.func.max-lines
```

La salida va a `~/.tec-review/out/<proyecto>-<run_id>/` y nunca se escribe dentro del proyecto auditado:

| Archivo | Contenido |
|---|---|
| `report.md` | Reporte para personas: veredicto, scorecard, hallazgos con cita, evidencia, safe path y fix (no aplicado), plan de sprint, reglas no evaluadas, metodología |
| `report.json` | Lo mismo, versionado (`schema_version`) |
| `facts.json` | Hechos deterministas. Idéntico entre ejecuciones con el mismo commit y la misma configuración |
| `interpretations.json` | Salida del modelo y su verificación |
| `judgments.json` | Pista B: candidatos, juicio del modelo, evidencia y motivo de rechazo |
| `manifest.json` | Procedencia: herramientas y versiones, modelos, tokens, latencias, métricas de calidad |

## Configuración (variables de entorno)

| Variable | Por defecto | Uso |
|---|---|---|
| `TEC_REVIEW_LLM_URL` | `http://localhost:8001` | llm-router |
| `TEC_REVIEW_LLM_ROLE` | `tool_coder` | Rol del catálogo de llm-router |
| `TEC_REVIEW_LLM_MODEL` | — | Modelo explícito (anula el rol) |
| `TEC_REVIEW_TOKEN_BUDGET` | `60000` | Presupuesto de tokens por ejecución |
| `TEC_REVIEW_SECUREPROJECTS_BIN` | `secureprojects` del PATH | Binario de SecureProjects |
| `TEC_REVIEW_SECUREPROJECTS_TIMEOUT_S` | `900` | Tope del escaneo de seguridad |
| `TEC_REVIEW_CRITICAL_MODULES` | — | Globs de módulos críticos para la cobertura (p. ej. `src/pagos/*.py`) |
| `TEC_REVIEW_TELEMETRY_URL` | `http://localhost:8005` | Servicio telemetry (con `--telemetry`) |

La configuración del proyecto auditado nunca relaja criterios. ruff corre con `--isolated` y se ignoran las supresiones que traiga el repo (ADR 0005).

## Tests

```powershell
.venv\Scripts\python -m pytest
```

La suite no usa red: el LLM se sustituye por `FakeLLM`. Comprueba que las 30 citas del catálogo existen literalmente en `Rules/`, el protocolo de tres casos por regla, la restricción sobre el repo limpio, la reproducibilidad de `facts.json`, el acceso de solo lectura y la degradación cuando el LLM falla.

## Estado

Las 30 reglas del catálogo tienen evaluador. Las reglas de juicio requieren `--track-b`, y la cobertura requiere `--run-tests` con e2bcito; si no se activan, aparecen como **reglas no evaluadas** con su motivo. Los hallazgos de juicio se reportan aparte y no alteran el score ni el veredicto (ADR 0006).
