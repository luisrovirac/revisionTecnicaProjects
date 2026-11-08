# tec-review — guía del proyecto

`tec-review` es una herramienta de línea de comandos que hace una **revisión técnica de un proyecto de software** contra las reglas escritas en [`Rules/`](../Rules/) y genera un reporte accionable: veredicto, puntuación, hallazgos con su evidencia, cómo corregirlos y un plan de sprint.

Esta guía explica en qué consiste, qué stack usa, cómo se activa y cómo se usa. El diseño completo está en [`planInicial.md`](planInicial.md) y las decisiones de arquitectura en [`adr/`](adr/).

---

## 1. En qué consiste

### La idea

No es "un LLM que opina del código". El orden de trabajo es:

1. **Extraer hechos objetivos** con herramientas deterministas (AST, ruff, grafo de imports, duplicación, SecureProjects). Sin modelo, reproducible.
2. **Seleccionar** qué hallazgos merecen explicación (triage por severidad e impacto, con presupuesto de tokens).
3. **Interpretar**: el modelo explica, prioriza y propone un arreglo para hechos ya comprobados.
4. **Verificar** cada afirmación del modelo contra los hechos. Si cita líneas o identificadores que no estaban en su contexto, se descarta y se publica una plantilla determinista.
5. **Reportar** con la procedencia de cada hallazgo (herramienta y versión, o modelo y hash del prompt).

```
inventario → analizadores → catálogo → triage → LLM explica → verificación → score → reporte
```

### Garantías principales

| Garantía | Qué significa |
|---|---|
| Solo lectura | Nunca escribe dentro del proyecto auditado. La salida va fuera y `--out` dentro del proyecto se rechaza |
| No ejecuta el código auditado | Salvo con `--run-tests`, y entonces solo dentro del sandbox e2bcito |
| El modelo no inventa hechos | No decide qué está mal, ni dónde, ni con qué severidad. Solo explica |
| Score determinista | El modelo no cambia el número. `facts.json` es idéntico entre ejecuciones con el mismo commit y configuración |
| Degradación segura | Si el LLM falla o no responde, la revisión termina igual, con explicaciones de plantilla |
| El proyecto no se juzga a sí mismo | Su configuración (ruff, `# noqa`, etc.) no relaja criterios: ruff corre con `--isolated` |

### Las dos pistas

- **Pista A (por defecto):** el hecho lo detecta una herramienta; el modelo solo lo explica. Afecta al score.
- **Pista B (`--track-b`, implícita en `--level deep`):** reglas de juicio (SRP, DIP, reintentos, secretos en prompts…). Un selector determinista propone regiones candidatas y el modelo decide, pero solo se publica si aporta toda la evidencia que la regla exige, con citas literales. Estos hallazgos se reportan aparte y **no alteran el score ni el veredicto**.

### Reglas y rulesets

El catálogo (`catalog/rules/*.yaml`) tiene 30 reglas en cinco grupos: diseño, LLM, mantenibilidad, seguridad, y pruebas y configuración. Cada regla cita literalmente su fuente en `Rules/` (un test lo comprueba) y declara una alternativa segura (`safe_path`).

| Ruleset | Documentos | Uso |
|---|---|---|
| `universal` (por defecto) | `RULES - 01.md`, `baseForRules.md` | Cualquier repositorio |
| `devsaxaiflow` | Los anteriores + `RULES-Plus.md` | Proyectos del ecosistema DevSaxAIFloow |

### Puntuación y veredicto

El score (0–100) pondera cinco dimensiones: seguridad 30, pruebas 20, diseño 20, mantenibilidad 20 y configuración/observabilidad 10. La penalización crece con `log1p(n)`, así que cien problemas menores no equivalen a uno crítico. Los hallazgos en tests, documentación o fixtures pesan ×0.3.

| Condición | Veredicto |
|---|---|
| Algún hallazgo `critical`, o score < 50 | **NO-GO** |
| Algún `high`, o score entre 50 y 74 | **CONDITIONAL** |
| Score ≥ 75 sin `high` ni `critical` | **GO** |

Junto al score se publica una **confianza**, según cuántas reglas aplicables se pudieron evaluar. Las que no se evalúan aparecen como *reglas no evaluadas*, con su motivo.

> Un análisis sin hallazgos no significa que el código esté libre de errores o de vulnerabilidades. Cada reporte incluye esta advertencia.

---

## 2. Stack

### Núcleo (Python ≥ 3.11)

| Componente | Uso |
|---|---|
| `typer` | CLI |
| `pydantic` | Modelos del dominio, configuración y validación de la salida del LLM |
| `httpx` | Cliente HTTP para llm-router y telemetry |
| `jinja2` | Plantillas del reporte Markdown |
| `pyyaml` | Catálogo de reglas y rulesets |
| `pathspec` | Respeta `.gitignore` (también los anidados) en el inventario |
| `ruff` 0.17.4 | Analizador de Python, con versión fijada para que los resultados sean reproducibles |
| `tree-sitter` + `tree-sitter-language-pack` | Análisis de TypeScript/TSX |
| `ast` y `tokenize` (stdlib) | Métricas de funciones y clases, grafo de imports, duplicación |
| `pytest` | Tests (sin red: el LLM se sustituye por `FakeLLM`) |

Todas las versiones están fijadas en [`pyproject.toml`](../pyproject.toml).

### Servicios externos que se reutilizan

`tec-review` no reimplementa lo que ya existe en el ecosistema: se conecta a estos servicios a través de interfaces internas (*ports*), y cada uno es opcional.

| Servicio | Papel | Si no está disponible |
|---|---|---|
| **SecureProjects** (`../ciberSeguridadDeProyectos`, Go) | Secretos, SAST, CVE, IaC | Las reglas `sec.*` quedan como no evaluadas |
| **llm-router** (`:8001`) | Acceso al modelo por rol, con failover | Modo degradado: explicaciones de plantilla |
| **e2bcito** | Ejecuta tests y mide cobertura en sandbox gVisor (`--run-tests`) | La cobertura queda como no evaluada |
| **telemetry** (`:8005`) | Eventos por nodo y por llamada (`--telemetry`) | No se envía nada |

### Estructura del código

```
src/tec_review/
  cli.py            CLI y composición raíz (único sitio donde se crean las implementaciones)
  pipeline.py       Pipeline de nodos: inventory → collect → normalize → triage → interpret → score → render
  config.py         Settings desde TEC_REVIEW_* y opciones de CLI
  domain/           Modelos (Hallazgo, Gap, Interpretacion…) y puertos (Analyzer, LLMPort, SandboxPort…)
  facts/            Capa determinista: inventario, AST, grafo, duplicación, patrones, TS, cobertura, adaptadores
  rules/            Carga del catálogo y matriz de capacidades por lenguaje
  agentic/          Pista A (interpret, verify, prompts) y Pista B (candidates, track_b)
  llm/              Adaptador de llm-router
  sandbox/          Adaptador de e2bcito
  telemetry/        Cliente de telemetry
  report/           Render de report.md / report.json y artefactos
catalog/            Reglas (rules/*.yaml), rulesets y backlog de candidatas
Rules/              Fuente de verdad normativa (no se modifica)
tests/              Suite y fixtures (repos "clean" y "seeded")
```

---

## 3. Cómo se activa

### Instalación

Desde la raíz del proyecto, en PowerShell:

```powershell
py -3.11 -m venv .venv
.venv\Scripts\pip install -e ".[dev]"
```

### Comprobar qué está disponible

```powershell
.venv\Scripts\tec-review doctor
```

`doctor` muestra el estado del catálogo, ruff, SecureProjects y llm-router. Nunca instala nada: lo que falte aparece como `FALTA`.

### Activar cada servicio (opcional)

| Para | Haz esto |
|---|---|
| Seguridad (SecureProjects) | Pon `secureprojects` en el PATH o define `TEC_REVIEW_SECUREPROJECTS_BIN` con la ruta del binario |
| Explicaciones del modelo | Arranca llm-router en `http://localhost:8001`, o define `TEC_REVIEW_LLM_URL` |
| Cobertura de tests | `pip install -e ../e2bcito/sdk/python`, define `E2BCITO_API_KEY` (y `E2BCITO_BASE_URL` si no usas la URL por defecto) y ejecuta con `--run-tests` |
| Telemetría | Arranca el servicio telemetry en `:8005` y ejecuta con `--telemetry` |

### Variables de entorno

| Variable | Por defecto | Uso |
|---|---|---|
| `TEC_REVIEW_LLM_URL` | `http://localhost:8001` | URL de llm-router |
| `TEC_REVIEW_LLM_ROLE` | `tool_coder` | Rol del catálogo de llm-router |
| `TEC_REVIEW_LLM_MODEL` | — | Modelo explícito (anula el rol) |
| `TEC_REVIEW_LLM_TIMEOUT_S` | `180` | Tope por llamada al modelo |
| `TEC_REVIEW_TOKEN_BUDGET` | `60000` | Presupuesto de tokens por ejecución |
| `TEC_REVIEW_SECUREPROJECTS_BIN` | `secureprojects` del PATH | Binario de SecureProjects |
| `TEC_REVIEW_SECUREPROJECTS_TIMEOUT_S` | `900` | Tope del escaneo de seguridad |
| `TEC_REVIEW_CRITICAL_MODULES` | — | Globs de módulos críticos para la cobertura, separados por comas (p. ej. `src/pagos/*.py`) |
| `TEC_REVIEW_TELEMETRY_URL` | `http://localhost:8005` | Servicio telemetry |
| `TEC_REVIEW_CATALOG_DIR` | `catalog/` del proyecto | Catálogo de reglas alternativo |
| `TEC_REVIEW_RULES_DIR` | `Rules/` del proyecto | Documentos de reglas alternativos |

---

## 4. Cómo se usa

Si es tu primera vez y prefieres un recorrido completo, paso a paso —activar el entorno y auditar un proyecto concreto de principio a fin—, sigue [`como-usar.md`](como-usar.md).

### Revisar un proyecto

```powershell
# Revisión completa (capa determinista + explicaciones del modelo)
tec-review review C:\ruta\al\proyecto

# Solo la capa determinista: sin LLM, rápida y reproducible
tec-review review C:\ruta\al\proyecto --no-llm

# Ruleset de DevSaxAIFloow, nivel rápido
tec-review review C:\ruta\al\proyecto --ruleset devsaxaiflow --level quick

# Todo: reglas de juicio y cobertura en sandbox
tec-review review C:\ruta\al\proyecto --level deep --run-tests
```

Al terminar, la consola muestra el veredicto, el score, la confianza, el número de hallazgos y la ruta del reporte.

### Opciones de `review`

| Opción | Efecto |
|---|---|
| `--ruleset universal\|devsaxaiflow` | Conjunto de reglas (por defecto `universal`) |
| `--level quick\|standard\|deep` | Cuántos hallazgos explica el modelo: 10, 40 o todos. `deep` activa también la Pista B |
| `--no-llm` | Solo la capa determinista |
| `--track-b` | Activa las reglas de juicio sin pasar a `deep` |
| `--run-tests` | Mide la cobertura ejecutando los tests en e2bcito |
| `--budget N` | Presupuesto de tokens de esta ejecución |
| `--llm-url`, `--llm-role`, `--llm-model` | Anulan la configuración del LLM |
| `--out DIR` | Directorio de salida (debe estar fuera del proyecto) |
| `--telemetry` | Envía eventos al servicio telemetry |

### Consultar las reglas

```powershell
tec-review rules list                        # reglas activas del ruleset universal
tec-review rules list --ruleset devsaxaiflow
tec-review rules show py.func.max-lines      # regla completa: cita literal, umbral, safe_path
```

### Qué se genera

La salida va a `~/.tec-review/out/<proyecto>-<run_id>/` (o a `--out`):

| Archivo | Contenido |
|---|---|
| `report.md` | Reporte para personas: veredicto, scorecard, hallazgos con cita y evidencia, safe path y fix propuesto (no aplicado), plan de sprint, reglas no evaluadas y metodología |
| `report.json` | Lo mismo en formato máquina, versionado (`schema_version`) |
| `facts.json` | Hechos deterministas, reproducibles entre ejecuciones |
| `interpretations.json` | Salida del modelo y su verificación |
| `judgments.json` | Pista B: candidatos, juicio, evidencia y motivo de rechazo |
| `manifest.json` | Procedencia: herramientas y versiones, modelos, tokens, latencias y métricas de calidad |

### Códigos de salida

| Código | Significado |
|---|---|
| `0` | La revisión terminó (sea cual sea el veredicto) |
| `2` | Error de uso o de herramienta: ruta inexistente, `--out` dentro del proyecto, configuración o ruleset inválidos, regla desconocida |

El veredicto no cambia el código de salida: una revisión informa, no bloquea.

### Consejos

- **SecureProjects tarda en proyectos con `.venv`:** escanea esa carpeta aunque luego se ignore. Para una pasada rápida, usa `--no-llm` y apunta `TEC_REVIEW_SECUREPROJECTS_BIN` a una ruta inexistente; la seguridad quedará como no evaluada.
- **Autoauditoría:** `tec-review review .` funciona, pero necesita un `--out` fuera del proyecto (la salida por defecto ya lo está).
- **Reproducibilidad:** para comparar dos ejecuciones, compara `facts.json`, no `report.md` (las explicaciones del modelo pueden variar).

---

## 5. Desarrollo

```powershell
.venv\Scripts\python -m pytest
```

Para comprobar el software a mano, con los resultados esperados de cada prueba, sigue [`qahumano.md`](qahumano.md).

La suite no usa red. Comprueba entre otras cosas que las 30 citas del catálogo existen literalmente en `Rules/`, el protocolo de tres casos por regla (un caso que debe dispararla, un contraejemplo seguro y un cambio no relacionado), la reproducibilidad de `facts.json`, el acceso de solo lectura y la degradación cuando fallan el LLM o el sandbox.

Para añadir una regla: defínela en `catalog/rules/<grupo>.yaml` con su cita literal y su `safe_path`, implementa o mapea su evaluador en `facts/` (o su selector en `agentic/candidates.py` si es de juicio) y añade sus tres casos en `tests/test_rules_three_cases.py`. El criterio de admisión está en [`planInicial.md` §5.2](planInicial.md).
