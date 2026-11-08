# Plan Inicial — `tec-review`

> **Estado:** Paso 0 completo. Las 30 reglas del catálogo v1 tienen evaluador (v0.4).
> **Ubicación en el proyecto:** `docs/planInicial.md`.
> **Versión:** 0.4 — documento vivo. Las decisiones se formalizan como ADRs en `docs/adr/` (0001–0006).

### Registro de cambios

| Versión | Cambio |
|---|---|
| 0.1 | Arquitectura de referencia, decisiones D1–D8, invariantes, pasos 0–4 |
| 0.2 | Seis correcciones derivadas de la lectura de las fuentes primarias (ver `resumenInspirador.md`): catálogo reducido y con `safe_path` obligatorio; invariante I10 (el target no define sus criterios); separación Pista A / Pista B; nodo de Triage; niveles de profundidad; metodología de evaluación con cuatro dimensiones; grafo superficial adelantado al Paso 2 |
| 0.4 | Evaluadores para las 19 reglas que faltaban: patrones, grafo de imports, duplicación, TypeScript (tree-sitter), cobertura vía e2bcito (`--run-tests`) y Pista B con 12 selectores y evidencia obligatoria (ADR 0006). Cobertura honesta por lenguaje (evaluación parcial). `.gitignore` anidados |
| 0.3 | Diez correcciones (C1–C10) y cinco huecos cubiertos (H1–H5), ver §0. Reutilización del ecosistema existente (SecureProjects, llm-router, e2bcito, telemetry). Orquestador concreto. RAG estructurado explícito. Catálogo movido a `catalog/`. Paso 0 implementado |

---

## 0. Revisión v0.3: qué se corrigió y por qué

### 0.1 Contradicciones y errores de v0.2

| # | Problema en v0.2 | Corrección v0.3 |
|---|---|---|
| C1 | El filtro 4 ("no redundante con CI → no entra") excluía `py.no-print`, `any.bare-except` y `ts.no-any`, que las reglas exigen explícitamente. El filtro de Codex se pensó para reglas de revisión de PR **con CI existente**, y un repo auditado puede no tener CI | Se reinterpreta como **"no reimplementar lo que una herramienta ya detecta: mapear la regla a esa herramienta"** (`check.kind: tool_rule`, p. ej. ruff `T201`). El filtro decide qué llega al **LLM**, no qué entra al catálogo (§5.2) |
| C2 | Se reimplementaban secretos, SAST y CVE ignorando **SecureProjects** (`../ciberSeguridadDeProyectos`), que ya los cubre con deduplicación, fingerprints, JSON versionado y SARIF | La capa de seguridad se **delega** (ADR 0002): reglas `sec.*` de tipo `tool_rule` contra SecureProjects |
| C3 | El Paso 0 necesitaba un LLM cuyo contrato estaba "pendiente" | Se usa `llm-router` de DevSaxAIFloow, cuyo contrato ya existe (ADR 0003) |
| C4 | Contrato del sandbox "pendiente" | e2bcito ya está desplegado y en uso; se adopta su SDK en el Paso 2 (ADR 0004) |
| C5 | `RULES-Plus.md` figuraba como "truncado a media checklist" | Falso: termina completo en la regla 33. Es **referencia** porque es específico de DevSaxAIFloow, no porque esté incompleto |
| C6 | `baseForRules.md` incluye un preámbulo y una tabla-resumen que no son norma | El test de citas solo acepta el cuerpo normativo (Partes I–VII) |
| C7 | Se prometía reproducibilidad "byte a byte" sin fijar las versiones de los analizadores | Versiones fijadas en `pyproject.toml` y registradas en el manifiesto. I6 se aclara: se prohíbe instalar **en tiempo de ejecución**, no declarar dependencias del paquete |
| C8 | "20 líneas lógicas" no tenía definición operativa | Definición única en §5.1, implementada con `ast` + `tokenize` |
| C9 | La fórmula de scoring no definía `n` ni contemplaba el tamaño del repo | `n` = ocurrencias por (regla, severidad). Los pesos son provisionales y se calibran en el Paso 1; la normalización por KLOC se decide con esa calibración (§9.2) |
| C10 | `hallucination_rate` no era medible porque no se definía qué es una "afirmación" | El modelo devuelve `claims[{text, evidence_lines}]` y el verificador comprueba líneas e identificadores de forma determinista (§7.7) |

### 0.2 Huecos cubiertos

| # | Hueco | Dónde |
|---|---|---|
| H1 | No había un orquestador concreto | §4.1 |
| H2 | El RAG que pide el enfoque no aparecía explícito | §7.5 |
| H3 | El ecosistema existente no aparecía | §4.2 |
| H4 | El contrato del dominio solo estaba en prosa | §4.1 (tipos) |
| H5 | El Paso 0 no tenía presupuesto de LLM | §7.4 (`--budget`) |

### 0.3 Hallazgo operativo: colisión `rules/` vs `Rules/`
En Windows (NTFS sin distinción de mayúsculas) `rules/` y `Rules/` son **la misma carpeta**. La estructura de v0.2 habría mezclado el catálogo con la fuente de verdad. El catálogo vive en **`catalog/`**; `Rules/` queda intacta.

---

## 1. Propósito

Construir una herramienta de línea de comandos que reciba la ruta de un proyecto, lo evalúe contra las reglas de `Rules/` y genere un **reporte técnico accionable y trazable**.

El sistema se concibe como **ingeniería agéntica**, no como "un LLM que opina del código". La lección que confirman CodeRabbit, OpenAI Codex y Claude Code es que el orden correcto es:

1. **Extraer hechos objetivos** (determinista, reproducible, sin alucinación posible).
2. **Seleccionar** qué merece juicio (determinista, por impacto y coste).
3. **Interpretar, priorizar y explicar** esos hechos (agéntico, acotado por esquema).
4. **Verificar** cada afirmación del modelo contra los hechos antes de publicarla.
5. **Reportar** con procedencia completa.

Un agente que recibe código y "opina" es frágil. Un sistema donde el modelo **no puede** inventar ubicaciones, severidades ni reglas es robusto por construcción.

### 1.1 Alcance

| Dentro | Fuera (por ahora) |
|---|---|
| Análisis estático de un repositorio local | Modificar el código auditado |
| Catálogo de reglas derivado de `Rules/` | Escribir o aplicar fixes automáticamente |
| Reporte Markdown, JSON y SARIF | Interfaz web / SaaS multi-tenant |
| Ejecución opcional de tests en sandbox externo | Ejecución de código del target fuera del sandbox |
| Integración CI/CD (GitHub Actions, GitLab CI) | Gestión de identidades, facturación, RBAC |

### 1.2 No objetivos explícitos

- No sustituye a la revisión humana: la alimenta y la ordena.
- No es un chat sobre el código.
- No promete cobertura total de reglas en todos los lenguajes; **declara explícitamente** lo que no pudo evaluar.

---

## 2. Decisiones adoptadas

| # | Decisión | Valor |
|---|---|---|
| D1 | Stack | **Python 3.11 + Typer** |
| D2 | Ejecución de código del target | **Solo a través de e2bcito**, opt-in. Por defecto: nunca (ADR 0004) |
| D3 | Capa LLM | **Agnóstica de proveedor** tras `LLMPort`. Vía real: **llm-router** (modelos locales y remotos por rol). Rol por defecto `tool_coder` (ADR 0003) |
| D4 | Lenguajes objetivo | Python, JavaScript, TypeScript, SQL, Java, Go, Rust, PHP, Swift, Kotlin (C#, C/C++ en fase posterior). Se excluyen lenguajes obsoletos o de nicho |
| D5 | Nombre | Paquete `tec_review`, comando `tec-review` |
| D6 | Ruleset por defecto | **`universal`** = `RULES - 01.md` + `baseForRules.md`. `--ruleset devsaxaiflow` añade `RULES-Plus.md` |
| D7 | Idioma del reporte | **Español** por defecto, `--lang en` para clientes |
| D8 | Secuencia de entrega | Paso 0 (walking skeleton) → 1 determinista → 2 agéntico → 3 contexto → 4 producto |
| D9 | Tamaño del catálogo v1 | **30 reglas** (≈18 deterministas, ≈12 de juicio). Crece solo con evidencia |
| D10 | Arquitectura agéntica | **Dos pistas separadas**: A (respaldada por hechos) y B (respaldada por juicio). B apagada por defecto |
| D11 | Política de ruido | Supresiones explícitas, versionadas y con motivo escrito. Sin memoria opaca del modelo |
| D12 | Reutilización | **Reusar antes que construir**: SecureProjects (seguridad), llm-router (LLM), e2bcito (sandbox), telemetry (eventos). Todos tras puertos, con fakes |

### 2.1 Sobre los documentos de reglas

| Documento | Estatus | Uso |
|---|---|---|
| `RULES - 01.md` | **Autoridad** | Base del ruleset `universal`. Principios, arquitectura, actuación, protocolo de revisión |
| `baseForRules.md` | **Autoridad** | Edición 2026. Aporta seguridad de LLM, observabilidad, gobernanza, invariantes verificables |
| `RULES-Plus.md` | **Referencia** | Contexto del proyecto DevSaxAIFloow. Aporta umbrales concretos y verificables. Se incorpora vía `--ruleset devsaxaiflow`. Es referencia por ser específico de un proyecto (C5) |

**Cuerpo normativo (C6):** de `baseForRules.md` solo cuentan las Partes I–VII. El preámbulo ("A continuación presento…") y la tabla "Resumen de las Ampliaciones Clave" no son citables.

**Regla de precedencia en caso de conflicto:** la regla más específica gana sobre la genérica; a igual especificidad, la edición más reciente gana. Todo conflicto resuelto queda registrado en el catálogo con la justificación.

---

## 3. Invariantes del sistema

Estos invariantes son el contrato de diseño. Cualquier implementación que los viole se rechaza en revisión, y cada uno tiene una prueba automatizada asociada.

| # | Invariante | Mecanismo de cumplimiento |
|---|---|---|
| I1 | **Read-only sobre el proyecto auditado** | `PathGuard` resuelve symlinks y rechaza cualquier escritura bajo la raíz del target. Test con filesystem espía |
| I2 | **Sin ejecución de código del target por defecto** | Único camino: puerto `SandboxPort` con el servicio externo. Nunca `subprocess` contra el proyecto |
| I3 | **El modelo no puede fabricar hechos** | El esquema de salida del LLM no posee campos `file`, `line`, `severity`, `rule_id` libres. Solo `fingerprint`, `explanation`, `impact`, `fix`, `priority` |
| I4 | **Los hallazgos deterministas son inmutables** | `Hallazgo` es `frozen`. El modelo produce `Interpretacion` separada, unida por fingerprint |
| I5 | **El score es determinista** | El modelo redacta y ordena; no altera el número. Ejecuciones reproducibles |
| I6 | **No se instalan analizadores en tiempo de ejecución** | `tec-review doctor` detecta binarios. Si faltan, se reportan como `Gap`. Las dependencias propias del paquete (p. ej. ruff) sí se declaran y fijan en `pyproject.toml` (C7) |
| I7 | **El contenido del repo es dato no confiable** | Delimitadores estructurales, jerarquía instrucción/dato explícita y detección activa de inyección de prompts como hallazgo de seguridad |
| I8 | **Todo hallazgo es trazable** | Procedencia: herramienta + versión + regla original, o modelo + hash de prompt + ejecución |
| I9 | **Un fallo del modelo no tumba la ejecución** | Degradación a plantilla + estado `unverifiable`. El reporte determinista siempre se produce |
| I10 | **El proyecto auditado nunca define ni relaja sus propios criterios** | La configuración del target solo puede **restringir alcance** (exclusiones, rutas) o **añadir** requisitos. Nunca desactivar una regla del ruleset, rebajar una severidad ni alterar pesos de scoring. Toda relajación vive en la configuración del operador y queda auditada |

**Nota sobre I10.** Es la adaptación de la salvaguarda de Claude Code, que lee `REVIEW.md` de la rama base protegida y **nunca de los cambios del PR**. La misma lógica aplica a un auditor de repositorio: si el evaluado puede editar su propio pliego de condiciones, el veredicto no vale nada. Un `review.yaml` malicioso en el repo auditado podría desactivar reglas y producir un GO falso.

**Nota sobre I9 + I5.** Verificadas juntas, implican que **`facts.json` es reproducible byte a byte** a igual commit, configuración y versiones de herramientas (C7). Solo la sección interpretativa cambia entre ejecuciones. Hay un test que lo comprueba.

---

## 4. Arquitectura de referencia

```
[Entrada: ruta del proyecto]
        │
        ▼
┌──────────────────────────────────────────────────────────┐
│ FASE 1 — RECOLECCIÓN DETERMINISTA (hechos)               │
│  · Inventario de archivos (lenguaje, tamaño, binarios)   │
│  · Perfiles de lenguaje y capacidades disponibles         │
│  · Analizadores estáticos (lint, SAST, dependencias)      │
│  · Métricas de forma vía AST (tree-sitter)                │
│  · Grafo de imports, ciclos, fan-in/fan-out               │
│  · Duplicación por n-gramas de tokens                     │
│  · Cobertura (opcional, vía sandbox)                      │
└───────────────────────────┬──────────────────────────────┘
                            │ Hechos tipados + Gaps
                            ▼
┌──────────────────────────────────────────────────────────┐
│ TRIAGE (determinista, en código)                          │
│  · Prioriza por severidad × radio de impacto × novedad    │
│  · Decide qué recibe juicio del modelo y qué no           │
│  · Aplica el presupuesto y el nivel de profundidad         │
└───────────────────────────┬──────────────────────────────┘
                            │ Subconjunto seleccionado
                            ▼
┌──────────────────────────────────────────────────────────┐
│ FASE 2 — CAPA AGÉNTICA (juicio acotado)                   │
│  Pista A: el hecho existe → el modelo explica             │
│  Pista B: el modelo propone → debe anclar la evidencia    │
│  · ContextBundle por hallazgo (presupuesto de tokens)     │
│  · Especialistas en paralelo                              │
│  · Verificación anti-alucinación                          │
│  · Validación de fixes por parseo (nunca aplicación)      │
└───────────────────────────┬──────────────────────────────┘
                            │ Interpretaciones verificadas
                            ▼
┌──────────────────────────────────────────────────────────┐
│ FASE 3 — SCORING, REPORTE Y SALIDA                        │
│  · Scorecard determinista + confianza (cobertura)         │
│  · Veredicto GO / CONDITIONAL / NO-GO                     │
│  · Reporte MD, JSON versionado, SARIF                     │
│  · Plan de sprint y anexo de procedencia                  │
└──────────────────────────────────────────────────────────┘
```

**Principio de separación:** la Fase 1 nunca importa nada de la Fase 2. La Fase 2 nunca accede al sistema de archivos del target directamente: solo consume `ContextBundle` construidos por código.

### 4.1 El orquestador (H1)

El workflow es el rey: un pipeline determinista de nodos tipados con **un único loop agéntico acotado**.

```
inventory → collect → normalize → triage → interpret(+verify) → score → render
                         │            │             │
                     facts.json   triage.json  interpretations.json      (+ report.*, manifest.json)
```

- Cada nodo es una función `(RunState, Dependencies) -> RunState` (`src/tec_review/pipeline.py`).
- Cada nodo persiste su artefacto. Esto es la base de `--replay` y de la reanudación.
- `Dependencies` (analizadores, `LLMPort`, `TelemetryPort`) se ensamblan en un único punto, la composición raíz (`cli.py`).
- **Loop agéntico acotado:** solo en `interpret`, con un máximo de 2 reintentos por hallazgo (el error de esquema vuelve al modelo como feedback) y un presupuesto de tokens por ejecución.
- Sin LangGraph en v1: el grafo es lineal y una dependencia más no aporta nada (baseForRules Parte II §15).

**Tipos del dominio (H4)** — `src/tec_review/domain/models.py`:

| Tipo | Naturaleza |
|---|---|
| `RawFact` | Salida cruda de un analizador, antes del catálogo |
| `Hallazgo` | Hecho normalizado, **inmutable** (I4), con fingerprint sin número de línea |
| `Gap` | Regla aplicable no evaluada, con razón |
| `ContextBundle` | Contexto curado para el modelo |
| `LLMInterpretation` | Esquema de salida del modelo (`extra="forbid"`, sin ubicación ni severidad: I3) |
| `Interpretacion` | Resultado verificado (`confirmed` / `unverifiable` / `skipped_budget`) |

### 4.2 Reutilización del ecosistema (H3, D12)

| Servicio | Papel en tec-review | Puerto | Estado |
|---|---|---|---|
| **SecureProjects** (`../ciberSeguridadDeProyectos`) | Secretos, SAST, CVE (OSV offline), IaC | `Analyzer` | Paso 0 ✅ |
| **llm-router** (DevSaxAIFloow `Services/llm-router`, :8001) | Vía LLM: rol → cadena de modelos con failover | `LLMPort` | Paso 0 ✅ |
| **telemetry** (DevSaxAIFloow `Services/telemetry`, :8005) | Eventos por nodo y por llamada (`--telemetry`) | `TelemetryPort` | Paso 0 ✅ (opt-in) |
| **e2bcito** (`aisandbox.lusaxweb.com`) | Tests y cobertura en sandbox gVisor | `SandboxPort` | Paso 2 |
| `security-audit` (DevSaxAIFloow) | — | — | No se reutiliza: analiza strings sueltos, no repos |

---

## 5. Artefacto rector: el catálogo de reglas

El catálogo es el contrato del sistema y el mecanismo principal contra la alucinación. Sin él, el LLM improvisa criterios; con él, solo puede citar reglas que existen.

### 5.1 Anatomía de una regla

```yaml
- id: py.func.max-lines
  title: "Funciones de más de 20 líneas lógicas"
  category: maintainability
  severity: medium
  scope: ["**/*.py"]            # a qué código aplica
  check:
    kind: ast                    # ast | tool_rule | regex | graph | sandbox | manual
    lang: python
    metric: function_logical_lines
    threshold: 20
  sources:
    - doc: "RULES - 01.md"
      ref: "Parte III §4"
      quote: "Si una función supera las **20 líneas** (sin contar docstring ni blanks)..."
  safe_path: >                   # OBLIGATORIO: qué hacer en su lugar
    Extrae bloques con nombre propio por intención ("calcular_descuento"),
    no por paso ("parte_2"). Si el bloque no tiene nombre posible, es que
    la función hace más de una cosa.
  agent_required: false
  evidence_required: []          # para Pista B: qué debe citarse para publicar
```

**Propiedades exigidas**

- **ID estable y semántico** (`categoría.sujeto.aspecto`). Nunca se reutiliza ni se renombra sin migración.
- **`quote` literal** con `doc` y `ref`, verificado por test contra `Rules/`.
- **`safe_path` obligatorio.** No es un consejo libre: es la alternativa concreta. Sin él, el modelo rellena con genéricos ("considera refactorizar") y el reporte pierde utilidad. Es la aplicación directa del principio de Codex *"state the invariant and the safe path"*.
- **`scope` explícito.** Las reglas se acotan al código que gobiernan. Las reglas de repo van a la raíz; las de un módulo, a ese módulo.
- **`severity: inherit`** solo en reglas delegadas (`sec.*`): la severidad la fija la herramienta (p. ej. CVSS en SecureProjects).

**Definición operativa de "línea lógica" (C8).** Una línea del cuerpo de la función o clase que contiene al menos un token de código. Se excluyen los blancos, los comentarios y el docstring; la firma y los decoradores no cuentan. En el Paso 0 se mide con `ast` + `tokenize` y en el Paso 1 con tree-sitter, con la misma definición.

### 5.2 Criterio de admisión de una regla

Una regla entra al catálogo solo si pasa **los seis filtros**:

| Filtro | Pregunta | Origen |
|---|---|---|
| Consecuencial | ¿Quitarla cambiaría una decisión real? | Codex |
| No obvia | ¿Es algo que un revisor humano tendría que repetir? | Codex |
| Verificable | ¿Hay evidencia objetiva o protocolo de verificación claro? | Claude Code |
| No reimplementar (C1) | ¿Ya lo detecta una herramienta? Entonces la regla **se mapea** a ella (`tool_rule`) y no consume juicio del modelo. Lo puramente cosmético (formato) no entra | Codex, reinterpretado |
| `safe_path` nombrable | ¿Existe una alternativa concreta y escribible? | Codex |
| Bajo ruido demostrado | ¿Supera el protocolo de tres casos en fixtures? | Codex |

**Consecuencia de D9:** el catálogo v1 tiene **30 reglas**, no 60. Una regla que produce ruido se estrecha o se elimina; el catálogo se adapta con evidencia, no con entusiasmo (baseForRules Parte VI §4).

### 5.3 Protocolo de validación de una regla

Trivial, obligatorio y automatizado. Tres casos por regla:

1. Un cambio **que debe dispararla** → produce exactamente un hallazgo, en la línea correcta.
2. Un **contraejemplo seguro** (excepción legítima) → no produce hallazgo.
3. Un **cambio no relacionado** → no produce hallazgo.

Si el caso 2 o el 3 fallan, la regla no entra. Este protocolo es el que convierte "creo que esta regla es buena" en un hecho verificable.

### 5.4 Composición del catálogo v1 (redactado)

`catalog/rules/*.yaml` contiene **30 reglas: 18 deterministas y 12 de juicio**. Las 30 citas se verifican literalmente contra `Rules/` en cada ejecución de la suite (`tests/test_catalog.py`).

| Grupo | Reglas | Evaluador | Paso |
|---|---|---|---|
| Forma (Python) | `py.func.max-lines`, `any.class.max-public-methods`, `any.class.max-lines`, `py.import-in-method`¹ | AST propio | 0 ✅ |
| Mapeadas a ruff | `py.no-print` (T201), `any.bare-except` (E722, BLE001) | ruff `--isolated` | 0 ✅ |
| Rutas | `any.tests.location` | rutas | 0 ✅ |
| Seguridad delegada | `sec.secret-exposed`, `sec.dep.vulnerable`, `sec.sast`, `sec.iac-misconfig` | SecureProjects | 0 ✅ |
| Estructura | `any.import.cycle`, `any.tests.missing`, `any.duplication.ratio` | grafo / n-gramas | 1 |
| Patrones | `any.hardcoded-config`, `llm.prompt-injection` | regex + entropía | 1–2 |
| Otros lenguajes | `ts.no-any` | eslint | 1 |
| Cobertura | `any.coverage.min` | e2bcito | 2 |
| **Juicio (Pista B)** | `design.srp`, `design.dip.direct-instantiation`, `design.ocp.conditional-dispatch`, `design.isp.fat-interface`, `design.lsp.contract-break`, `design.thin-entrypoints`, `config.startup-validation`, `resilience.retry-backoff`, `resilience.resource-release`, `llm.output-to-sink`, `llm.secrets-in-prompt`, `llm.unbounded-consumption` | agente con evidencia | 2 |

¹ Su única fuente es `RULES-Plus.md`, así que solo está activa en `devsaxaiflow`.

El banco de candidatas (`catalog/backlog/candidates.yaml`) recoge las reglas descartadas con su motivo. Por ejemplo, `any.func.max-params` no tiene fuente literal en `Rules/` y no puede citarse.

### 5.4.1 Estado v0.4: las 30 reglas tienen evaluador

| Grupo | Evaluador | Lenguajes | Activación |
|---|---|---|---|
| Forma, rutas, ruff | AST propio, ruff `--isolated` | Python | siempre |
| `ts.no-any` | tree-sitter en proceso (no ejecuta eslint ni plugins del target) | TypeScript | siempre |
| `any.hardcoded-config` | literales de `ast` en Python; literales entre comillas en lenguajes tipo C. Excepciones: módulos de configuración y tests | Python + tipo C | siempre |
| `llm.prompt-injection` | frases dirigidas a un LLM. Excepción: material adversarial (fixtures, red team) | todos | siempre |
| `any.import.cycle`, `any.tests.missing` | grafo de imports de nivel de módulo (sin `TYPE_CHECKING`); alcance transitivo desde los tests | Python | siempre |
| `any.duplication.ratio` | n-gramas de 50 tokens, bloques de 5 o más líneas, un hallazgo por par de archivos, sin tests | Python + tipo C | siempre |
| `sec.*` | SecureProjects | todos | si está instalado |
| `any.coverage.min` | pytest-cov dentro de e2bcito | Python | `--run-tests` + `E2BCITO_API_KEY` |
| 12 reglas de juicio | selectores deterministas + juicio con evidencia (ADR 0006) | Python | `--track-b` o `--level deep` |

**Cobertura parcial.** Si un evaluador no cubre todos los lenguajes del proyecto, la regla cuenta como evaluada, pero el reporte lista los lenguajes sin cubrir. "Soportado" nunca significa "bien analizado".

**Medición de ruido (llm-router + orchestrator, sin LLM).** La primera versión de duplicación y patrones dio 85 y 228 hallazgos, sobre todo por artefactos de build (`.nuxt/`, `.output/`) excluidos solo en `.gitignore` de subcarpetas, y por duplicación en tests. Tras respetar los `.gitignore` anidados, agrupar la duplicación por par de archivos y excluir los tests, quedaron 20 y 85: violaciones legítimas de las reglas.

### 5.5 Rulesets

| Ruleset | Contenido | Uso |
|---|---|---|
| `universal` (por defecto) | `RULES - 01.md` + `baseForRules.md` | Cualquier repositorio |
| `devsaxaiflow` | `universal` + `RULES-Plus.md` | Proyectos con stack LangGraph/Theia |

### 5.6 Nota sobre severidades

Claude Code usa tres niveles: **Important** (bug que debe corregirse antes de fusionar), **Nit** (menor, no bloqueante) y **Pre-existing** (bug que ya existía y no introduce el PR).

Ese tercer nivel no aplica a nuestro caso: **en una auditoría de repositorio, todo es pre-existente por definición**. Nuestro equivalente es el eje **nuevo vs. baseline** (`--baseline`), que cumple la misma función: separar lo que el equipo introdujo de lo que ya estaba.

---

## 6. Fase 1 — Capa determinista

### 6.1 Componentes

| Componente | Responsabilidad |
|---|---|
| `inventory` | Recorrido de archivos, respeto de `.gitignore`, detección de binarios, tamaños, límites |
| `language` | `LanguageProfile`: capacidades reales por lenguaje (¿hay AST? ¿hay linter? ¿hay grafo?) |
| `adapters` | Invocación de herramientas externas → JSON. Sin `shell=True`, UTF-8 con reemplazo |
| `parsers` | JSON de herramienta → `Hallazgo` tipado. **Parse, don't validate** |
| `ast` | Consultas tree-sitter por lenguaje: forma de funciones y clases, símbolos, imports |
| `graph` | Grafo de imports y llamadas, ciclos, fan-in/fan-out, violaciones de capas declaradas |
| `duplication` | Detección de clones por n-gramas de tokens normalizados |
| `coverage` | Opcional. Vía `SandboxPort` únicamente |

### 6.2 Cobertura multi-lenguaje: matriz de capacidades

Tres niveles explícitos. **"Soportado" nunca significa "bien analizado"**: el reporte declara el nivel aplicado.

| Nivel | Lenguajes | Garantía |
|---|---|---|
| **T1 — profundo** | Python, TypeScript, JavaScript | AST propio + linters + SAST + grafo + duplicación. Reglas de forma completas |
| **T2 — estructural** | Java, Go, PHP, Rust, SQL | AST tree-sitter + reglas de forma agnósticas + herramienta nativa si está instalada |
| **T3 — superficial** | Swift, Kotlin, C#, C/C++ | Inventario + patrones + métricas de archivo. Reglas de forma limitadas y etiquetadas |

Mapa de herramientas (todas se **detectan**, ninguna se instala):

| Lenguaje | Lint | SAST | Forma (AST) | Cobertura (sandbox) |
|---|---|---|---|---|
| Python | ruff | bandit | tree-sitter, radon | pytest-cov |
| TypeScript / JavaScript | eslint, tsc | semgrep | tree-sitter | c8 |
| Java | checkstyle, PMD | semgrep | tree-sitter | jacoco |
| Go | go vet, staticcheck | gosec | tree-sitter | go test |
| PHP | phpstan, phpcs | semgrep | tree-sitter | phpunit |
| Rust | clippy | — | tree-sitter | tarpaulin |
| SQL | sqlfluff | — | tree-sitter-sql | — |
| Swift | swiftlint | — | tree-sitter | — |
| Kotlin | detekt | — | tree-sitter | — |

### 6.3 Banco de reglas deterministas candidatas

Candidatas, no catálogo. La selección final de las ~18 que entran en v1 sale de aplicar los seis filtros y el protocolo de tres casos.

| ID | Regla | Mecanismo |
|---|---|---|
| `py.func.max-lines` | > 20 líneas lógicas | AST |
| `any.func.max-params` | > 5 parámetros | AST |
| `any.class.max-public-methods` | > 5 métodos públicos | AST |
| `any.class.max-lines` | > 100 líneas | AST |
| `any.func.max-nesting` | Anidamiento excesivo | AST |
| `any.cyclomatic.max` | Complejidad > umbral | radon / eslint / AST |
| `any.duplication.ratio` | Duplicación > umbral | n-gramas |
| `py.no-print` | `print` en lugar de logging | AST |
| `any.bare-except` | `except Exception` genérico | AST / linter |
| `any.hardcoded-config` | URLs, rutas, credenciales literales | patrón + entropía |
| `any.secret-exposed` | Posible secreto (valor redactado) | entropía + patrones |
| `py.di.direct-instantiation` | Dependencia instanciada dentro de método | AST |
| `py.import-in-method` | Import no estándar dentro de función | AST |
| `ts.no-any` | Uso de `any` | tsc / eslint |
| `any.tests.location` | Tests fuera de `tests/` o sin prefijo `test_` | rutas |
| `any.tests.missing` | Módulo sin test asociado | mapeo símbolo ↔ test |
| `any.coverage.min` | Cobertura < 80% en módulos críticos | sandbox o proxy estático |
| `any.dep.vulnerable` | Dependencia con CVE conocida | pip-audit / osv-scanner |
| `any.import.cycle` | Ciclo de dependencias | grafo |
| `any.layer.violation` | Dependencia en dirección no permitida | grafo + capas declaradas |
| `any.dead-code` | Símbolo sin referencias | vulture / AST |
| `any.prompt-injection` | Intento de inyección en comentarios o strings | patrón |

**Nota v0.3 (C2):** `any.secret-exposed` y `any.dep.vulnerable` ya no se implementan; pasan a `sec.secret-exposed` y `sec.dep.vulnerable`, delegadas en SecureProjects. La lista definitiva está en §5.4.

### 6.4 Gaps y confianza

Cada regla no evaluada produce un `Gap` con razón explícita:

```
{ rule_id, language, reason: "tool_unavailable" | "capability_missing" | "parse_error" | "excluded" }
```

Los gaps alimentan el indicador de **confianza** del reporte. Un proyecto con 6 de 30 reglas evaluadas no puede lucir un 95/100: muestra `score=95, confianza=baja, cobertura=20%`.

---

## 7. Fase 2 — Capa agéntica

### 7.1 Dos pistas, dos economías

La distinción más importante de esta fase. Mezclarlas es lo que hace inviable el sistema, tanto en coste como en calidad.

| | **Pista A — respaldada por hechos** | **Pista B — respaldada por juicio** |
|---|---|---|
| Origen del hallazgo | Linter, AST, grafo, sandbox | El agente inspecciona una región y propone |
| Volumen | Alto (cientos) | Bajo (decenas) |
| Papel del modelo | Explicar, priorizar, proponer fix | **Encontrar** y justificar |
| Verificación | Estructural (barata) + entailment | Entailment obligatorio (caro) |
| Riesgo de alucinación | Nulo en el hecho; posible en la explicación | **Alto en el hecho mismo** |
| Estado por defecto | Siempre activa | **Apagada**. Se activa con `--level deep` o por regla |

**Regla de oro:** la Pista B solo puede publicar un hallazgo si adjunta evidencia verificable (archivo, línea, fragmento, regla citada). Sin evidencia, se descarta. Es el único camino por el que el modelo puede *crear* un hallazgo, y está diseñado para que sea difícil.

### 7.2 Triage

Nodo determinista entre los hechos y el modelo. Decide **qué merece juicio**:

```
prioridad = severidad_base × radio_impacto × novedad × confianza_del_check
selección = top-N dentro del presupuesto de tokens del nivel activo
```

- **Radio de impacto**: fan-in/fan-out del símbolo y si está en un módulo crítico.
- **Novedad**: si el fingerprint ya estaba en el baseline, baja (o se omite en modo CI).
- **Sin triage**, el Paso 2 es económicamente inviable y el reporte ilegible.

### 7.3 Puerto LLM

El sistema es agnóstico de proveedor. Dos vías, elegidas por ejecución:

| Vía | Descripción |
|---|---|
| **LLM local** | Modelo servido en la máquina del usuario. Privacidad total, coste cero de desarrollo |
| **Servicio de LLM existente** | Servicio propio que centraliza el acceso a modelos. El usuario indica cuál usar |

**Requisito de implementación:** ambas vías existen como adaptadores tras un mismo puerto, con la misma interfaz de dominio (petición tipada → respuesta tipada + contabilidad de tokens y latencia). Ninguna parte del núcleo conoce al proveedor.

**Requisito de implementación:** debe existir un adaptador falso, de modo que la suite completa corra sin red y sin coste. ✅ `FakeLLM`.

**Implementación (v0.3, ADR 0003):** `LlmRouterAdapter` sobre `POST /v1/chat/completions` de llm-router. El router no ofrece salida estructurada, así que el JSON se pide en el prompt, se parsea con Pydantic y se reintenta.

**Lección medida:** con el rol `validator` (perfil Plus → `deepseek-r1`, un modelo de razonamiento), 8 hallazgos tardaron 10 min 17 s y solo se confirmó el 37,5 %: el razonamiento agotaba `max_tokens` antes de emitir el JSON. Con `tool_coder` (`deepseek-chat-v3`) la misma ejecución tardó 63 s, con un 87,5 % confirmado y un 0 % de alucinación. **Para interpretar hechos hace falta un modelo que siga el formato, no uno que razone más.**

### 7.4 Niveles de profundidad

Control único de coste y exhaustividad. Los tres productos líderes lo tienen porque el coste es el problema real.

| Nivel | Analizadores | Hallazgos interpretados | Verificación | Pista B |
|---|---|---|---|---|
| `quick` | Solo lint + SAST | Top 10 | Estructural | No |
| `standard` (defecto) | Todos los deterministas | Top 40 | Estructural + entailment | No |
| `deep` | Todos + grafo completo + cobertura | Todos los del presupuesto | Estructural + entailment + segunda pasada | Sí, acotada |

### 7.5 Contexto curado

El modelo nunca recibe "todo el código". Recibe un `ContextBundle` construido por código:

- el hallazgo con su evidencia,
- el fragmento de código con números de línea (±N alrededor),
- la firma del símbolo contenedor,
- **los llamadores y llamados directos** del símbolo (índice superficial de símbolos),
- la cita literal de la regla y su `safe_path`.

Con presupuesto de tokens por bundle y por ejecución.

**Esto es RAG, en su forma estructurada (H2).** La recuperación es determinista y por clave, no por similitud:

| Clave | Se recupera | Fuente |
|---|---|---|
| `rule_id` | cita literal, referencia, `safe_path` | catálogo |
| ubicación del hallazgo | fragmento numerado ±N líneas (máx. 60 de cuerpo) | archivo del target |
| símbolo (Paso 2) | llamadores y llamados directos | índice de símbolos |

No se usan embeddings en v1: no aportan nada que la clave exacta no dé, y añaden infraestructura y una fuente de no determinismo. La búsqueda semántica entra en el Paso 3 solo si las evaluaciones la justifican.

**Hallazgos sensibles:** si un hallazgo está marcado `sensitive` (secretos), el bundle no lleva líneas de código, solo la evidencia que SecureProjects ya redactó. Un secreto nunca llega al prompt ni al reporte.

**Corrección respecto a 0.1:** el grafo superficial (llamadores/llamados) entra en el **Paso 2**, no en el Paso 3. CodeRabbit lo señala como el mínimo viable —"si un PR cambia una función, puede inspeccionar un llamador en otro archivo"— y es barato: un índice de símbolos, no un grafo completo.

### 7.6 Especialistas

| Especialista | Recibe | Produce |
|---|---|---|
| `seguridad` | Hallazgos de seguridad, secretos, patrones de inyección | Explicación de explotabilidad e impacto |
| `diseno` | Hallazgos de forma, duplicación, DIP/SRP/OCP | Explicación de la violación y refactor propuesto |
| `pruebas` | Gaps y hallazgos de cobertura | Tests faltantes priorizados |
| `mantenibilidad` | Configuración, observabilidad, logging | Correcciones concretas |

Cada especialista ve **solo su subconjunto de reglas** y **solo sus hallazgos**. Salida validada por esquema; si falla tras reintentos, se degrada a plantilla y se marca `unverifiable`.

### 7.7 Verificación (anti-alucinación)

Adaptación del ciclo **Find → Verify → Rank → Post** de Claude Code:

1. **Estructural:** el fingerprint existe, el archivo existe, la línea existe, el hash del fragmento coincide, el `rule_id` está en el catálogo.
2. **Entailment:** una segunda pasada barata comprueba que la afirmación se sostiene con la evidencia adjunta.
3. **Fixes:** el código sugerido se parsea con tree-sitter. Si no parsea, se descarta el fix y se conserva la explicación.
4. **Descarte contabilizado:** lo no soportado se elimina y se cuenta. Esa cuenta es la métrica de calidad del propio sistema.

**Métrica impresa en cada ejecución (C10, operativa):**

```
claim grounded ⇔ todas sus evidence_lines ∈ ContextBundle.lines
                 ∧ todo `identificador` citado aparece literalmente en el bundle
hallucination_rate = claims_no_grounded / claims_totales
confirmed_rate     = interpretaciones confirmadas / interpretaciones intentadas
```

Una interpretación se publica (`confirmed`) si cumple tres condiciones: el fingerprint coincide, tiene al menos una afirmación con respaldo, y la explicación y el impacto no citan identificadores ausentes del bundle. Las afirmaciones sin respaldo se descartan y se cuentan. Si no se cumplen las condiciones, se publica la plantilla determinista (mensaje de la herramienta + cita + `safe_path`) con estado `unverifiable`.

**Límite conocido:** esta verificación es estructural. Detecta invenciones de ubicación e identificadores, pero no un razonamiento incorrecto sobre código real. Para eso está el entailment del Paso 2.

---

## 8. Integración con el servicio de sandbox

**Requisito de implementación:** la ejecución de código del proyecto auditado (tests, cobertura) se realiza **exclusivamente** a través del servicio de sandbox existente. No se implementará ejecución local de código del target bajo ninguna circunstancia.

Implicaciones de diseño que sí se fijan aquí:

- Existe un puerto `SandboxPort` en el dominio, y el núcleo solo lo conoce a él.
- Existe una implementación falsa para pruebas, que devuelve resultados controlados.
- El adaptador real vive aislado en un único módulo, sustituible sin tocar el resto del sistema.
- Es una capacidad **opt-in**: por defecto el análisis es puramente estático.
- La indisponibilidad del sandbox **degrada** el reporte (cobertura pasa a estimación estática y se marca como tal), no lo rompe.

*Detalles de protocolo, contrato y ciclo de vida del sandbox: fuera de este documento.*

---

## 9. Scoring y veredicto

### 9.1 Dimensiones y pesos

| Dimensión | Peso |
|---|---|
| Seguridad | 30 |
| Pruebas | 20 |
| Arquitectura y diseño | 20 |
| Mantenibilidad | 20 |
| Configuración y observabilidad | 10 |

### 9.2 Cálculo

```
penalización_dimensión = Σ  peso_sev × confianza × factor_alcance × log1p(n)

peso_sev:        critical 40 · high 15 · medium 5 · low 1 · info 0
factor_alcance:  módulo crítico ×1.5 · global ×1.0 · solo tests o docs ×0.3

score_dimensión = clamp(100 − penalización, 0, 100)
score_global    = Σ (score_dimensión × peso) / 100
```

El uso de `log1p(n)` evita la "muerte por mil hallazgos menores": cien problemas de estilo no equivalen a uno crítico.

**Precisiones v0.3 (C9):**
- `n` = ocurrencias de la misma (regla, severidad) dentro de la dimensión; `confianza × factor_alcance` se promedia en el grupo.
- `factor_alcance` en el Paso 0: tests/docs/examples/fixtures ×0.3; resto ×1.0. El ×1.5 de módulo crítico requiere declarar los módulos críticos en la configuración del operador (Paso 1).
- **Pesos provisionales.** Se calibran en el Paso 1 con un repo de referencia "bueno" y uno "malo". La normalización por KLOC se decide con esa evidencia, no antes.

### 9.3 Veredicto

| Condición | Veredicto |
|---|---|
| Algún `critical`, o score < 50 | **NO-GO** |
| Algún `high`, o score entre 50 y 74 | **CONDITIONAL** |
| Score ≥ 75 sin `high` ni `critical` | **GO** |

### 9.4 Semántica del veredicto según el modo

| Modo | Naturaleza del veredicto |
|---|---|
| **Reporte** (entregable) | Contractual: es el resultado del informe |
| **CI** | **Advisory por defecto.** El check nunca falla por hallazgos. `--fail-on` es opt-in explícito |

Esto replica la decisión de Claude Code: *"a review never approves or blocks the pull request"* y su check run *"never concludes as a failure"*. Bloquear un merge es una política del equipo, no una consecuencia automática de un análisis.

### 9.5 Confianza y advertencia obligatoria

Indicador independiente del score, derivado de la cobertura real de reglas por lenguaje. Se publica siempre junto al número.

Todo reporte incluye, en el resumen ejecutivo y sin excepción:

> **Un análisis sin hallazgos no significa que el código esté libre de errores o de vulnerabilidades.** Este informe cubre las reglas y los lenguajes indicados en el anexo, con las limitaciones allí declaradas.

Sin esa frase, un "GO 92/100" es una bomba de relojería en manos de un cliente.

---

## 10. Salidas

```
out/<run_id>/
├── report.md              # para personas
├── report.json            # versionado, con schema_version
├── results.sarif          # GitHub code scanning / GitLab
├── facts.json             # hechos deterministas completos
├── interpretations.json   # salida del modelo + verificación
└── manifest.json          # procedencia, gaps, tokens, latencias, versiones
```

### 10.1 Estructura del reporte

1. **Resumen ejecutivo** — veredicto, score, confianza, advertencia de no-exhaustividad, y los tres problemas que más importan.
2. **Scorecard** por dimensión, con cobertura de reglas por lenguaje.
3. **Hallazgos priorizados** — archivo y línea, regla citada, **por qué se marcó** (evidencia y verificación, al estilo de *Why this was flagged*), por qué importa, `safe_path`, fix sugerido (marcado como **no aplicado**), origen y estado de verificación.
4. **Plan de sprint** — cada hallazgo como tarea, con esfuerzo derivado de severidad y radio de impacto, agrupado por capacidad.
5. **Anexo de metodología** — herramientas y versiones ejecutadas, reglas no evaluadas y por qué, modelos usados, tokens, latencias, hash de configuración y de prompts.

### 10.2 CLI

```
tec-review review <ruta> [opciones]   # v0.3: subcomando explícito (Typer no combina bien
                                      # un argumento posicional por defecto con subcomandos)
tec-review doctor                 # analizadores disponibles por lenguaje
tec-review rules list|show <id>   # introspección del catálogo
tec-review diff <a.json> <b.json> # regresiones entre ejecuciones
tec-review suppress <fingerprint> --reason "..."   # ruido gestionado y auditable

Opciones principales:
  --ruleset universal|devsaxaiflow
  --languages auto
  --level quick|standard|deep
  --no-llm
  --llm <vía>
  --out <dir>  --format md,json,sarif
  --baseline <report.json>   --fail-on <severidad>
  --run-tests                 (requiere sandbox)
  --budget <tokens>           --replay
  --lang es|en                --verbose
```

**Códigos de salida para CI:** `0` correcto · `1` violación de política (`--fail-on`) · `2` error de herramienta · `3` análisis parcial (gaps por encima del umbral). En el Paso 0 solo existen `0` y `2`; `1` y `3` llegan con `--fail-on` en el Paso 4.

**Salida por defecto (I1):** `~/.tec-review/out/<proyecto>-<run_id>/`. `PathGuard` rechaza cualquier `--out` dentro del proyecto auditado, incluido el caso de autoauditoría (`tec-review review .`).

**Idempotencia:** los fingerprints son estables entre ejecuciones. Un segundo run sobre el mismo commit produce el mismo `facts.json` y los mismos fingerprints. Esto habilita `--baseline` (solo lo nuevo), `diff` (regresiones) y supresiones que no se rompen al mover código de sitio.

---

## 11. Estructura del repositorio

```
revisionTecnicaProjects/
├── pyproject.toml
├── README.md
├── .gitignore
├── docs/
│   ├── planInicial.md
│   ├── resumenInspirador.md
│   └── adr/                      # decisiones de arquitectura
├── Rules/                        # fuente de verdad (intacta)
├── catalog/                      # v0.3: NO "rules/" (colisiona con Rules/ en Windows)
│   ├── ruleset.universal.yaml
│   ├── ruleset.devsaxaiflow.yaml
│   ├── rules/*.yaml              # catálogo v1 (30 reglas)
│   └── backlog/candidates.yaml   # candidatas no aplicadas, con motivo
├── src/tec_review/
│   ├── cli.py
│   ├── config.py
│   ├── domain/
│   ├── facts/
│   ├── rules/
│   ├── triage.py
│   ├── agentic/
│   │   ├── tracks/               # Pista A y Pista B, separadas
│   │   └── ...
│   ├── llm/                      # router_adapter.py (llm-router), fake.py
│   ├── telemetry/                # cliente opcional del servicio telemetry
│   ├── pipeline.py               # orquestador (§4.1)
│   ├── scoring.py
│   └── report/                   # view, render, artifacts, templates/report.md.j2
├── tests/
│   ├── fixtures/repos/           # repos sintéticos con violaciones sembradas
│   ├── fixtures/rules/           # 3 casos por regla
│   ├── test_parsers_*.py
│   ├── test_rules_*.py
│   ├── test_scoring.py
│   └── test_e2e_golden.py
└── tools/
    └── eval_llm.py               # evaluación de calidad del modelo (manual)
```

**Convención obligatoria del propio proyecto:** tests en `tests/`, archivos con prefijo `test_`. La herramienta se audita a sí misma en CI.

**Supresiones:** viven en la configuración del operador, nunca en el repo auditado (I10). Cada una exige `--reason` escrito y queda en el manifiesto de la ejecución.

---

## 12. Plan por pasos

### Paso 0 — Walking skeleton · ~2-3 días

CLI → inventario → ruff + bandit → parseo tipado → **una** llamada al LLM que interpreta → verificación mínima → `report.md`.

No se construye: grafo, RAG, multi-agente, AST.

**Criterios de aceptación**
- `--no-llm` produce un reporte válido.
- `hallucination_rate < 10%` sobre los fixtures sembrados.
- El esquema de salida del modelo no admite ubicaciones ni severidades.
- Sin LLM configurado, la ejecución termina correctamente en modo degradado.

**Nota de alcance:** el Paso 0 es Python-only por construcción. La promesa multi-lenguaje entra en el Paso 1 vía perfiles de lenguaje.

**Estado (2026-11-08): ✅ completado.** Además del alcance previsto incluye SecureProjects, el AST de Python (adelantado del Paso 1), el triage determinista, el scoring completo y la telemetría opcional.

| Criterio | Resultado |
|---|---|
| `--no-llm` produce un reporte válido | ✅ |
| `hallucination_rate < 10%` sobre fixtures sembrados | ✅ 0,0 % con llm-router real (9/9 afirmaciones con respaldo) |
| El esquema del modelo no admite ubicaciones ni severidades | ✅ test |
| Sin LLM, ejecución correcta en modo degradado | ✅ test + chequeo de salud al inicio |
| Precisión de ubicación sobre el repo sembrado | ✅ 8/8 en archivo:línea exactos |
| Restraint sobre el repo limpio | ✅ 0 hallazgos |
| Tres casos por cada regla evaluable | ✅ 7 reglas × 3 casos |
| `facts.json` idéntico entre ejecuciones | ✅ test |
| Read-only sobre el target | ✅ test con snapshot de bytes |

**Primera ejecución sobre un proyecto real** (`Services/llm-router`, nivel `quick`): 142 hallazgos (6 críticos), NO-GO 67,5, confianza baja (11/30 reglas). 10/10 interpretaciones confirmadas con un 0 % de alucinación, 48 s de LLM. Se verificó que ningún valor del `.env` auditado aparece en los artefactos de salida. El cuello de botella fue SecureProjects (200 s de 250).

### Paso 1 — Endurecer lo determinista · ~1-2 semanas

Catálogo v1 (30 reglas) con `safe_path`, citas y test de sincronización · protocolo de tres casos · perfiles T1/T2/T3 · tree-sitter · grafo de imports y ciclos · duplicación · gaps y confianza · JSON versionado + SARIF · scoring completo.

**Criterios de aceptación**
- `--no-llm` entrega un reporte accionable de valor autónomo.
- Precisión de ubicación > 95% sobre fixtures sembrados.
- **Restraint**: cero falsos positivos en los fixtures limpios.
- Toda regla no evaluada aparece como gap con razón.
- Cada regla del catálogo tiene sus tres casos y pasan.

### Paso 2 — Profundizar lo agéntico · ~1-2 semanas

Triage determinista · separación explícita Pista A / Pista B · `ContextBundle` con presupuesto · índice superficial de símbolos (llamadores/llamados) · cuatro especialistas en paralelo · verificación completa con entailment · validación de fixes por parseo · `--level` · caché y replay · suite anti-inyección de prompts.

**Criterios de aceptación**
- `confirmed_rate > 80%`.
- Reducción medible de falsos positivos respecto al Paso 0.
- Inyección de prompt en un comentario detectada y reportada como hallazgo.
- Coste por ejecución dentro del presupuesto del nivel activo.
- La Pista B está apagada en `standard` y no emite nada sin evidencia adjunta.

### Paso 3 — Escalar contexto · ~2-3 semanas

Grafo de llamadas completo y radio de impacto · índice léxico de símbolos · agente de arquitectura con invariantes declarados en configuración del operador (capas y direcciones permitidas) · completar T3 · búsqueda semántica solo si las evaluaciones la justifican.

**Criterios de aceptación**
- Al menos tres tipos de hallazgo arquitectónico que ningún linter detecta.
- p95 < 3 minutos en repositorio mediano.
- El radio de impacto explica por qué un hallazgo importa más que otro.

### Paso 4 — Producto · ~1-2 semanas

GitHub Action y job de GitLab CI · baseline, `--fail-on` y supresiones · logging estructurado y trazas · métricas de efectividad · ADRs · dogfooding en CI.

**Criterios de aceptación**
- Un pull request de prueba dispara la revisión y comenta resultados.
- Ejecución en CI < 5 minutos para repositorios medianos.
- El propio repositorio pasa su gate.

---

## 13. Estrategia de evaluación

Sin instrumentos de medida, las métricas de los pasos son decorativas. La suite se construye desde el Paso 0.

### 13.1 Dimensiones de evaluación

Adoptadas de la metodología que OpenAI publica para las reglas de revisión de Codex:

| Dimensión | Pregunta | Cómo se mide |
|---|---|---|
| **Coverage** | ¿Detecta las violaciones previstas cuando hay muchas reglas compitiendo? | Recall sobre fixtures sembrados |
| **Restraint** | ¿Los cambios limpios y las excepciones legítimas **no** generan hallazgos? | Falsos positivos sobre fixtures limpios y contraejemplos |
| **Retention** | ¿Sigue detectando bugs normales fuera de las reglas? | Bugs sembrados que ninguna regla del catálogo cubre |
| **Actionability** | ¿Cada hallazgo identifica guía, ubicación y prioridad? | Porcentaje de hallazgos con regla + archivo:línea + `safe_path` |

`Retention` es la que se olvida siempre: mide si, al enfocarnos en tus reglas, perdemos la capacidad de ver lo que un revisor humano vería.

### 13.2 Instrumentos

| Instrumento | Contenido | Cuándo corre |
|---|---|---|
| Tests unitarios | Parsers con JSON real de cada herramienta, evaluadores, deduplicación, scoring, guardas de rutas, redacción de secretos | CI |
| Golden E2E | Repos sintéticos con violaciones sembradas y fingerprint esperado | CI |
| Fixtures limpios | Código correcto que **no** debe generar hallazgos | CI |
| Casos por regla | Dispara / contraejemplo seguro / no relacionado | CI |
| Evals de LLM | Las cuatro dimensiones + alucinación, con modelo real | Manual / nocturno |
| Red team | Inyección de prompts, secretos falsos, binarios, symlinks, rutas largas | CI |

### 13.3 Métricas de referencia

| Métrica | Definición | Objetivo |
|---|---|---|
| Tasa de alucinación | Afirmaciones del modelo sin grounding / total | < 10% (Paso 0), < 5% (Paso 2) |
| Precisión de ubicación | Hallazgos con archivo:línea correctos / sembrados | > 95% |
| Tasa de confirmación | Interpretaciones que pasan el verificador / total | > 80% |
| Restraint | Hallazgos en fixtures limpios | 0 |
| Cobertura de reglas | Reglas evaluadas / aplicables por lenguaje | Publicada siempre |
| Coste por ejecución | Tokens y latencia agregados | Dentro del presupuesto del nivel |

---

## 14. Riesgos y mitigaciones

| Riesgo | Impacto | Mitigación |
|---|---|---|
| **Catálogo demasiado grande genera ruido** | Alto | D9: 30 reglas con seis filtros de admisión. Una regla ruidosa se estrecha o se elimina |
| **El target manipula sus criterios de evaluación** | Alto | I10. Configuración de relajación solo del lado del operador |
| Amplitud de diez lenguajes desborda el cronograma | Alto | Niveles T1/T2/T3. Entregar T1 profundo y T3 honestamente etiquetado |
| Analizadores ausentes en la máquina del usuario | Medio | `doctor`, gaps explícitos, dependencias opcionales, nunca instalación automática |
| Nondeterminismo del modelo rompe la comparabilidad | Alto | Temperatura cero, salida por esquema, caché por hash, modo replay |
| Alucinación estructural (ubicaciones inventadas) | Alto | Imposible por tipos + gate de verificación + tasa medida por ejecución |
| Inyección de prompts desde el repositorio auditado | Alto | Jerarquía instrucción/dato, delimitadores, detección activa como hallazgo |
| Desbordamiento de tokens y coste | Medio | Triage, `--level`, presupuesto por bundle y por ejecución |
| Diferencias de plataforma (Windows: encoding, rutas largas, symlinks) | Medio | UTF-8 con reemplazo, sin `shell=True`, resolución previa de rutas, CI multiplataforma |
| Falsos positivos erosionan la confianza del usuario | Alto | Baseline, deduplicación por fingerprint, fixtures limpios, supresiones con motivo |
| Sobreconfianza en un GO | Alto | Advertencia obligatoria + confianza separada del score + gaps visibles |
| El catálogo se desincroniza de `Rules/` | Medio | Test que verifica las citas literales en CI |

---

## 15. Referencias de diseño

Detalle completo, con citas y análisis, en `docs/resumenInspirador.md`.

| Fuente | Aporta | Qué tomamos |
|---|---|---|
| **OpenAI Codex** | El contrato de las reglas y la metodología de evaluación | `AGENTS.md` como archivo versionado; reglas acotadas por ruta; *"state the invariant and the safe path"*; seis filtros de admisión; cuatro dimensiones de eval; protocolo de tres casos |
| **Claude Code** | El pipeline y las salvaguardas | Find → Verify → Rank → Post; verificación para descartar falsos positivos; deduplicación antes de publicar; niveles Quick/Standard/Deep; read-only; veredicto advisory; `REVIEW.md` desde rama base (→ I10); *Why this was flagged* (→ "por qué se marcó"); advertencia de no-exhaustividad |
| **CodeRabbit** | El producto y el contexto | Contexto más allá del diff (llamadores); incremental vs full review (→ `--baseline`); 50+ analizadores estáticos + SAST; agentes especializados en paralelo; sandbox de ejecución |

---

## 16. Estado y siguientes acciones

**Hecho**
- Lectura y análisis de los tres documentos de `Rules/`.
- Lectura de las fuentes primarias: CodeRabbit (quickstart, FAQ, arquitectura), OpenAI Codex (blog de reglas de revisión y `AGENTS.md` real), Claude Code (code review, customize, pull requests).
- Arquitectura de referencia y decisiones D1–D11.
- Plan v0.2 con las seis correcciones integradas.

- v0.3: revisión crítica del plan (C1–C10, H1–H5), catálogo v1 de 30 reglas con citas verificadas, ADRs 0001–0005, Paso 0 implementado con 64 tests.

**Siguiente (Paso 1)**
1. tree-sitter + perfiles T1/T2/T3; activar `ts.no-any` (eslint) y las reglas de forma en JS/TS.
2. Grafo de imports: `any.import.cycle`, `any.tests.missing`.
3. Duplicación por n-gramas y `any.hardcoded-config`.
4. SARIF y `--baseline`.
5. Calibrar los pesos del scoring con un repo "bueno" y uno "malo".
6. Replay de interpretaciones por hash de prompt (caché).

**Mejoras propuestas en otros repos (fuera de alcance)**
- SecureProjects: gitleaks y trivy no reciben las exclusiones por defecto (`**/.venv/**`, `**/node_modules/**`). Reproducido con un secreto sembrado en `.venv/`: lo reportan ambos y el escáner nativo no. En `tec-review` no produce falsos positivos (se filtra por inventario), pero multiplica el tiempo de escaneo.
- llm-router: passthrough de `response_format` (salida estructurada nativa) y un rol dedicado a revisión que use un modelo no razonador.

**Pendiente de definición externa**
- Confirmación del nombre definitivo del repositorio.
