# QA humano — cómo comprobar a mano que tec-review funciona

Esta guía es para una persona que quiere verificar el software sin leer el código. Cada prueba indica **qué hacer**, **qué deberías recibir** y **cómo saber si falla**. Los resultados esperados salen de una ejecución real del 2026-11-08.

Para entender qué es la herramienta y todas sus opciones, lee primero [`README.md`](README.md).

---

## 0. Preparación (una vez)

Abre PowerShell en la raíz del proyecto (`revisionTecnicaProjects`):

```powershell
# Instalación (si aún no está hecha)
py -3.11 -m venv .venv
.venv\Scripts\pip install -e ".[dev]"

# Carpeta de salida para las pruebas, fuera del proyecto
$out = "$env:TEMP\tec-qa"

# Desactiva SecureProjects para que las pruebas tarden segundos y no minutos.
# Se prueba aparte, en la P13.
$env:TEC_REVIEW_SECUREPROJECTS_BIN = "C:\no-existe\secureprojects.exe"
```

Para abrir el último reporte generado en una carpeta:

```powershell
function Ultimo($dir) { Get-ChildItem $dir -Directory | Sort-Object LastWriteTime | Select-Object -Last 1 }
notepad "$((Ultimo "$out\seeded").FullName)\report.md"
```

El proyecto trae dos repositorios de prueba en `tests\fixtures\repos\`:

| Repo | Qué es |
|---|---|
| `clean` | Código correcto. No debería dar ningún hallazgo |
| `seeded` | Código con 13 problemas sembrados a propósito. Debería encontrarlos todos |

---

## 1. Prueba automática (2 minutos)

```powershell
.venv\Scripts\python -m pytest
```

**Deberías recibir:** `135 passed` en unos 15 segundos.

**Falla si:** aparece algún `failed` o `error`. Sin red ni servicios externos la suite pasa igual, porque el modelo se sustituye por uno falso.

Las pruebas manuales que siguen comprueban lo mismo desde fuera, como lo vería un usuario.

---

## 2. Pruebas manuales

### P1 — Diagnóstico del entorno

```powershell
.venv\Scripts\tec-review doctor
```

**Deberías recibir** una línea por componente:

```
OK   catálogo        30 reglas en ...\catalog
OK   ruff            0.17.4
FALTA  secureprojects  define TEC_REVIEW_SECUREPROJECTS_BIN
OK   llm-router      http://localhost:8001
```

- `secureprojects` sale como `FALTA` porque lo desactivaste en la preparación. Es lo esperado.
- `llm-router` sale `OK` solo si el servicio está arrancado en `:8001`. Si no, `FALTA`, y las pruebas P10 no se pueden hacer.

**Falla si:** el catálogo no muestra 30 reglas, o el comando instala algo. `doctor` nunca instala nada.

### P2 — Catálogo de reglas

```powershell
.venv\Scripts\tec-review rules list
.venv\Scripts\tec-review rules list --ruleset devsaxaiflow
.venv\Scripts\tec-review rules show py.func.max-lines
```

**Deberías recibir:**
- `rules list`: **29** reglas (ruleset `universal`), una por línea, con id, tipo, severidad y título.
- `--ruleset devsaxaiflow`: **30** reglas (añade `py.import-in-method`, que solo existe en `RULES-Plus.md`).
- `rules show`: un JSON con `sources[].quote` (una cita literal de `Rules\RULES - 01.md`), `threshold: 20.0` y un `safe_path`.

**Cómo comprobarlo:** abre `Rules\RULES - 01.md`, busca el texto de `quote` y comprueba que aparece tal cual.

### P3 — Un repo limpio da GO

```powershell
.venv\Scripts\tec-review review tests\fixtures\repos\clean --no-llm --out "$out\clean"
```

**Deberías recibir:**

```
Veredicto: GO  |  score 100.0/100  |  confianza media (12/29 reglas evaluadas)
Hallazgos: 0  |  interpretados: 0
Reporte: ...\report.md
```

**Falla si:** aparece algún hallazgo. Sería un falso positivo.

### P4 — Un repo con problemas sembrados los detecta todos

```powershell
.venv\Scripts\tec-review review tests\fixtures\repos\seeded --no-llm --out "$out\seeded"
```

**Deberías recibir:**

```
Veredicto: CONDITIONAL  |  score 92.7/100  |  confianza media (12/29 reglas evaluadas)
Hallazgos: 13  |  interpretados: 0
```

Abre el `report.md` (sección 3, *Hallazgos priorizados*) y comprueba que están estos 13:

| # | Severidad | Regla | Dónde |
|---|---|---|---|
| 1 | ALTA | `llm.prompt-injection`: un comentario sembrado que intenta dar órdenes a un revisor automático | `src/app/clients.py:7` |
| 2 | MEDIA | `py.func.max-lines`: `calcular_factura` tiene 22 líneas lógicas | `src/app/service.py:4` |
| 3 | MEDIA | `any.bare-except`: `except Exception:` | `src/app/main.py:17` |
| 4 | MEDIA | `any.tests.missing`: `app.service` sin tests | `src/app/service.py:1` |
| 5 | MEDIA | `any.import.cycle`: `app.billing` → `app.clients` | `src/app/billing.py:1` |
| 6 | MEDIA | `any.hardcoded-config`: URL fija | `src/app/clients.py:5` |
| 7 | MEDIA | `any.bare-except`: `except:` | `src/app/main.py:7` |
| 8 | BAJA | `py.no-print`: `print(datos)` | `src/app/main.py:9` |
| 9 | BAJA | `any.class.max-public-methods`: `GestorPedidos` con 6 métodos | `src/app/service.py:35` |
| 10 | BAJA | `ts.no-any`: `datos: any` | `web/api.ts:5` |
| 11 | BAJA | `any.tests.location`: test fuera de `tests/` | `src/app/test_helpers.py` |
| 12 | BAJA | `any.duplication.ratio`: bloque de 10 líneas duplicado | `src/app/billing.py:8` |
| 13 | BAJA | `any.tests.location`: test sin prefijo `test_` | `tests/util_test.py` |

**Cómo comprobarlo:** abre cada archivo en la línea indicada y confirma que el problema está ahí. El campo **Evidencia** de cada hallazgo debe ser texto que existe literalmente en esa línea.

**Por qué CONDITIONAL y no NO-GO:** hay un hallazgo `high` (el nº 1) y ninguno `critical`. Ver la tabla de veredictos en el README.

**Falla si:** falta alguno, sobra alguno, o una línea no coincide.

### P5 — El reporte tiene todas sus partes

En el mismo `report.md` de la P4, comprueba que existen estas secciones:

| Sección | Qué revisar |
|---|---|
| 1. Resumen ejecutivo | Veredicto, score, confianza, recuento por severidad, "Lo que más importa" y **la advertencia en negrita** («Un análisis sin hallazgos no significa…») |
| 2. Scorecard | 5 dimensiones con pesos 30/20/20/20/10 |
| 3. Hallazgos priorizados | Cada uno con regla y cita, *Por qué se marcó*, evidencia, origen (herramienta + versión + fingerprint) y *Safe path* |
| 4. Plan de sprint | Tareas derivadas de los hallazgos |
| 5. Reglas no evaluadas | Cada regla que no se evaluó, con su motivo (ver P11) |
| 6. Anexo de metodología | Tabla de herramientas con versión y estado, uso del modelo y tiempos por nodo |

En la carpeta del run deben estar también `report.json`, `facts.json`, `triage.json` y `manifest.json`. Sin LLM no se generan `interpretations.json` ni `judgments.json`: es lo esperado.

### P6 — Siembra tu propio bug

Copia el repo limpio, añade código malo y comprueba que se detecta:

```powershell
Copy-Item tests\fixtures\repos\clean "$env:TEMP\mio" -Recurse -Force
Add-Content "$env:TEMP\mio\src\shop\cart.py" @'


def depurar(x):
    try:
        return int(x)
    except:
        print("fallo")
'@
.venv\Scripts\tec-review review "$env:TEMP\mio" --no-llm --out "$out\mio"
```

**Deberías recibir** `Hallazgos: 2` y, en el reporte:
- `[MEDIA] Captura genérica de excepciones` en la línea del `except:`
- `[BAJA] Uso de print en lugar de logging` en la línea del `print`

El veredicto sigue en **GO** (≈99/100), porque ningún hallazgo es `high` ni `critical`.

Prueba también otras reglas: una función de más de 20 líneas, una URL fija (`URL = "https://..."`), un `any` en un `.ts`. Cada una debe aparecer con su línea exacta.

### P7 — Nunca escribe dentro del proyecto auditado

```powershell
.venv\Scripts\tec-review review tests\fixtures\repos\seeded --no-llm --out tests\fixtures\repos\seeded\salida
$LASTEXITCODE
```

**Deberías recibir:**

```
Escritura bloqueada (I1): ...\seeded\salida\... está dentro del proyecto auditado ...\seeded. Usa --out fuera del proyecto.
2
```

**Cómo comprobarlo:** `Get-ChildItem tests\fixtures\repos\seeded` muestra solo `src`, `tests` y `web`. No se creó la carpeta `salida`.

**Falla si:** el código de salida es `0` o aparece la carpeta.

### P8 — Los hechos son reproducibles

Repite la P4 en otra carpeta y compara los `facts.json`:

```powershell
.venv\Scripts\tec-review review tests\fixtures\repos\seeded --no-llm --out "$out\seeded2"
$a = "$((Ultimo "$out\seeded").FullName)\facts.json"
$b = "$((Ultimo "$out\seeded2").FullName)\facts.json"
(Get-FileHash $a).Hash -eq (Get-FileHash $b).Hash
```

**Deberías recibir:** `True`. Los dos archivos son idénticos byte a byte, aunque la hora y el `run_id` de cada ejecución sean distintos.

**Ojo:** si cambias opciones (por ejemplo `--track-b`), cambia la lista de reglas evaluadas dentro de `facts.json`. Compara siempre con la misma configuración.

### P9 — Si el modelo no responde, la revisión termina igual

```powershell
$env:TEC_REVIEW_LLM_URL = "http://127.0.0.1:9"     # puerto donde no hay nadie
.venv\Scripts\tec-review review tests\fixtures\repos\seeded --out "$out\caido"
Remove-Item Env:TEC_REVIEW_LLM_URL
```

**Deberías recibir** el mismo veredicto y score que en la P4, más un aviso:

```
Veredicto: CONDITIONAL  |  score 92.7/100  ...
Hallazgos: 13  |  interpretados: 0
  aviso: llm-router no responde en http://127.0.0.1:9: modo degradado sin LLM (I9).
```

**Falla si:** el comando se cuelga, termina con error o el score cambia.

### P10 — Con el modelo: explicaciones verificadas y Pista B

Requiere llm-router en marcha (P1 en `OK`). Tarda en torno a un minuto.

```powershell
.venv\Scripts\tec-review review tests\fixtures\repos\seeded --level quick --track-b --out "$out\llm"
```

**Deberías recibir** (las cifras del modelo pueden variar algo entre ejecuciones):

```
Veredicto: CONDITIONAL  |  score 92.7/100  |  confianza alta (24/29 reglas evaluadas)
Hallazgos: 13  |  interpretados: 10
```

Comprueba:

1. **El score y el veredicto no cambian respecto a la P4.** El modelo explica, pero no puntúa.
2. **`interpretados: 10`**: con `--level quick` solo se explican los 10 primeros.
3. **La confianza sube** de media (12/29) a alta (24/29), porque `--track-b` evalúa las reglas de juicio.
4. En `report.md`, los hallazgos explicados tienen texto del modelo y su fix propuesto. Nunca se aplica nada al código.
5. Aparece una sección **Hallazgos de juicio (Pista B)**. En la prueba de referencia salieron 2:
   - `B.1` operación de red sin reintentos, en `src/app/service.py` (función `descargar`)
   - `B.2` unidad con más de una razón para cambiar (`GestorPedidos`)

   Cada uno lleva evidencia con citas literales. Comprueba en el archivo que el texto citado existe.
6. En `manifest.json`, bloque `metrics`: `hallucination_rate` debe ser `0.0` (o muy bajo) y `claims_grounded` igual a `claims_total`. En `llm` verás las llamadas, los tokens y el modelo usado.
7. En `interpretations.json`, cada entrada tiene `status`: `confirmed` (verificada y publicada) o `unverifiable` (descartada y sustituida por la plantilla). En `judgments.json`, cada candidato de la Pista B tiene `published`, `dismissed` o `rejected` con su motivo.

**Falla si:** el score cambia, un hallazgo de la Pista B cita texto que no existe en el archivo, o una explicación habla de funciones o líneas que no existen y aun así figura como `confirmed`.

### P11 — Lo que no se evalúa se declara

En el `report.md` de la P4, sección **5. Reglas no evaluadas**, comprueba que cada regla tiene su motivo:

| Reglas | Motivo esperado |
|---|---|
| `any.coverage.min` | Requiere `--run-tests` (sandbox e2bcito) |
| 12 reglas de diseño, resiliencia y LLM (`design.*`, `resilience.*`, `llm.output-to-sink`…) | Juicio (Pista B) desactivado: se activa con `--track-b` o `--level deep` |
| `sec.*` (4 reglas) | Herramienta no disponible: secureprojects |

Además aparece **Evaluadas parcialmente**: `any.import.cycle` y `any.tests.missing` sin cubrir TypeScript, porque el repo tiene un `.ts` y esas reglas solo se evalúan en Python.

**Falla si:** una regla aplicable no aparece ni como evaluada ni como no evaluada.

### P12 — Errores de uso

Cada comando debe mostrar un mensaje claro en rojo y terminar con código **2** (compruébalo con `$LASTEXITCODE`):

```powershell
.venv\Scripts\tec-review review C:\no\existe --no-llm --out $out
# -> La ruta no existe o no es un directorio

.venv\Scripts\tec-review review tests\fixtures\repos\clean --no-llm --ruleset inventado --out $out
# -> Ruleset desconocido: 'inventado' (no existe ...\catalog\ruleset.inventado.yaml)

.venv\Scripts\tec-review rules show no.existe
# -> Regla desconocida: no.existe
```

**Falla si:** sale una traza de Python (*Traceback*) en lugar del mensaje, o el código no es 2.

### P13 — Seguridad con SecureProjects (opcional, lento)

Requiere el binario de SecureProjects (`..\ciberSeguridadDeProyectos`).

```powershell
$env:TEC_REVIEW_SECUREPROJECTS_BIN = "C:\ruta\a\secureprojects.exe"
.venv\Scripts\tec-review doctor          # secureprojects debe salir OK
.venv\Scripts\tec-review review tests\fixtures\repos\seeded --no-llm --out "$out\sp"
```

**Deberías recibir:** en el anexo de metodología, `secureprojects` con estado `ok` y su versión. Las reglas `sec.*` ya no figuran como no evaluadas.

**Ojo:** en un proyecto con `.venv` (por ejemplo, al auditar este mismo repo con `review .`), el escaneo tarda unos 10 minutos porque SecureProjects recorre esa carpeta.

### P14 — Cobertura en sandbox (opcional)

Requiere el SDK de e2bcito y una API key:

```powershell
.venv\Scripts\pip install -e ..\e2bcito\sdk\python
$env:E2BCITO_API_KEY = "<tu clave>"
.venv\Scripts\tec-review review tests\fixtures\repos\clean --no-llm --run-tests --out "$out\cov"
```

**Deberías recibir:** `any.coverage.min` deja de figurar como no evaluada. Si algún módulo importante tiene menos del 80% de cobertura, aparece como hallazgo `Cobertura de líneas X% (umbral 80%)`.

**Sin la clave:** la regla figura como no evaluada con el motivo `Falta E2BCITO_API_KEY.` y la revisión termina con normalidad. Eso también es correcto.

**Aviso:** a 2026-11-08 este camino solo se ha probado con un sandbox falso; no se ha ejecutado contra el servicio real. Es la prueba con más valor pendiente.

---

## 3. Hoja de resultados

Copia esta tabla y márcala al terminar:

| Prueba | Qué valida | Resultado |
|---|---|---|
| Suite automática | 135 tests | ☐ |
| P1 doctor | Diagnóstico del entorno sin instalar nada | ☐ |
| P2 rules | 29/30 reglas, citas literales | ☐ |
| P3 clean | GO 100, 0 hallazgos | ☐ |
| P4 seeded | CONDITIONAL 92.7, los 13 hallazgos en su línea | ☐ |
| P5 reporte | 6 secciones, advertencia y artefactos | ☐ |
| P6 bug propio | Detecta lo que siembras | ☐ |
| P7 solo lectura | `--out` dentro bloqueado, código 2 | ☐ |
| P8 reproducible | `facts.json` idéntico | ☐ |
| P9 LLM caído | Mismo resultado + aviso | ☐ |
| P10 LLM | Score intacto, explicaciones verificadas, Pista B con evidencia | ☐ |
| P11 no evaluadas | Cada hueco con su motivo | ☐ |
| P12 errores | Mensaje claro, código 2, sin trazas | ☐ |
| P13 SecureProjects | Reglas `sec.*` evaluadas | ☐ (opcional) |
| P14 cobertura | `any.coverage.min` evaluada | ☐ (opcional) |

## 4. Limpieza

```powershell
Remove-Item "$env:TEMP\tec-qa", "$env:TEMP\mio" -Recurse -Force
Remove-Item Env:TEC_REVIEW_SECUREPROJECTS_BIN
```
