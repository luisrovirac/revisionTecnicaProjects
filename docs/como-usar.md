# Cómo usar tec-review — recorrido completo de un usuario

Esta guía es el camino de una persona que quiere **activar el entorno y auditar un proyecto concreto**, de principio a fin. Para instalar desde cero o ver todas las opciones, usa [`README.md`](README.md); para comprobar a mano que el software funciona, usa [`qahumano.md`](qahumano.md).

Ejemplo que se sigue en todo el documento: auditar `C:\Users\User\Projects\SaxNew\scraper-app` partiendo del directorio de trabajo `C:\Users\User\Projects\SaxNew\revisionTecnicaProjects`.

---

## 0. Estado de partida

Antes de empezar, comprueba qué hay ya en la máquina:

| Pieza | Cómo se comprueba | Qué debe salir |
|---|---|---|
| Python 3.11 o superior | `py -3.11 --version` | `Python 3.11.x` |
| Entorno virtual | `Test-Path .\.venv\Scripts\python.exe` | `True` |
| `tec-review` instalado | `Test-Path .\.venv\Scripts\tec-review.exe` | `True` |
| Proyecto a auditar | `Test-Path 'C:\Users\User\Projects\SaxNew\scraper-app'` | `True` |

Si las tres primeras dan `True`, **no instales nada**: salta al paso 2.

---

## 1. Abrir la terminal en el directorio de trabajo

Abre **PowerShell** y sitúate en la carpeta de la herramienta:

```powershell
cd C:\Users\User\Projects\SaxNew\revisionTecnicaProjects
Get-Location
```

Debe imprimir:

```
Path
----
C:\Users\User\Projects\SaxNew\revisionTecnicaProjects
```

Todos los comandos de esta guía se lanzan desde esa carpeta.

---

## 2. Activar el entorno virtual

```powershell
.\.venv\Scripts\Activate.ps1
```

Al principio del prompt debe aparecer `(.venv)`:

```
(.venv) PS C:\Users\User\Projects\SaxNew\revisionTecnicaProjects>
```

Comprueba que el comando queda disponible:

```powershell
Get-Command tec-review | Select-Object Name, Source
```

Debe mostrar `tec-review` y la ruta `...\revisionTecnicaProjects\.venv\Scripts\tec-review.exe`.

**Si PowerShell bloquea el script** (*no se puede cargar el archivo ... Activate.ps1 porque la ejecución de scripts está deshabilitada*), ejecuta una vez:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

Responde `S` y repite la activación.

**En cmd** el comando equivalente es:

```bat
.venv\Scripts\activate.bat
```

La activación solo dura en esa ventana. Si abres otra, repite los pasos 1 y 2. Sin activar, todo funciona igual usando la ruta completa: `.\.venv\Scripts\tec-review ...`.

---

## 3. Instalar (solo si falta)

Salta este paso si el paso 4 sale bien. Si `.venv` o `tec-review` no existieran:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[dev]"
```

Debe terminar con `Successfully installed ...`. No hace falta activar antes: se llama al Python del `.venv` por ruta completa. Más detalle en [`README.md`](README.md) §Instalación.

---

## 4. Diagnóstico del entorno

```powershell
tec-review doctor
```

Salida de referencia en esta máquina (2026-11-08):

```
OK   catálogo        30 reglas en C:\Users\User\Projects\SaxNew\revisionTecnicaProjects\catalog
OK   ruff            0.17.4
OK   secureprojects  C:\Users\User\Projects\SaxNew\ciberSeguridadDeProyectos\bin\secureprojects.EXE
OK   llm-router      http://localhost:8001
```

Qué es obligatorio y qué no:

| Componente | Si sale `FALTA` |
|---|---|
| `catálogo` | No se puede revisar: falta la fuente de reglas |
| `ruff` | No se puede revisar Python |
| `secureprojects` | La revisión funciona; las reglas `sec.*` quedan como no evaluadas |
| `llm-router` | La revisión funciona en modo degradado (plantillas); solo podrás usar `--no-llm` |

`doctor` nunca instala nada: solo informa.

---

## 5. Decidir si escaneas seguridad o vas rápido

Importa cuando el proyecto auditado contiene un `venv/`: SecureProjects recorre esa carpeta aunque luego se ignore, y el escaneo puede tardar **unos 10 minutos**.

**Opción A — rápida (recomendada para la primera pasada).** Desactiva SecureProjects solo en esa ventana:

```powershell
$env:TEC_REVIEW_SECUREPROJECTS_BIN = "C:\no-existe\secureprojects.exe"
```

Las 4 reglas `sec.*` aparecerán como *no evaluadas* con su motivo. Es lo esperado, no un fallo.

**Opción B — completa.** No ejecutes nada: deja el binario real y asume la espera.

Deshacer la Opción A en esa ventana:

```powershell
Remove-Item Env:TEC_REVIEW_SECUREPROJECTS_BIN
```

---

## 6. Lanzar la revisión

Primera pasada sin modelo (rápida, reproducible, sin depender de servicios externos):

```powershell
tec-review review "C:\Users\User\Projects\SaxNew\scraper-app" --no-llm --out "$env:TEMP\tec-demo"
```

Sobre la orden:

- La ruta del proyecto va entre comillas (aunque no tenga espacios).
- `--no-llm` = solo capa determinista: el mismo código y la misma configuración dan el mismo resultado.
- `--out` **debe estar fuera del proyecto auditado**. Si lo omites, la salida va a `C:\Users\User\.tec-review\out\`. Si apunta dentro del proyecto, la herramienta lo rechaza con código 2 (garantía de solo lectura).
- `--quiet` (o `-q`) oculta el progreso paso a paso y deja solo el resumen final.

Mientras corre, la herramienta muestra dos barras en vivo:

```
⠧ [2/9] Ejecutando analizadores · 8/8 secureprojects        22% 0:06:41
⠧   └ secureprojects · 4/6 en curso: trivy        ━━━━━━━   67% 0:06:12 esperando 2m 05s
```

- Fila 1: el paso global (`[N/9]`), el elemento actual, % total y tiempo total.
- Fila 2: lo que hace ese elemento por dentro (las herramientas internas de secureprojects, el hallazgo que interpreta el LLM…), su propio avance y tiempo. `esperando …` indica cuánto lleva sin novedades: la herramienta sigue trabajando, no está colgada.
- Encima de las barras quedan fijas las líneas de lo ocurrido: cada herramienta de secureprojects que arranca o termina, cada analizador con sus hechos, y al cerrar cada paso:

```
✓ [2/9] Ejecutando analizadores — 8 analizadores, 13 hechos (7m 02s)
```

Si rediriges la salida a un archivo (`> log.txt 2>&1`), el progreso sale como texto plano, una línea por evento, y cada 15 s sin novedades escribe `… sigue trabajando: <qué> (lleva <tiempo>)`. Los avisos (p. ej. llm-router no responde) aparecen en el momento, no solo al final.

secureprojects es lo más lento en proyectos grandes (trivy y semgrep pueden tardar varios minutos la primera vez; luego usa caché). Si pasa de 15 min se corta y el reporte lo marca como no evaluado.

Resumen final de referencia (ejecución real del 2026-11-08 sobre `scraper-app`, sin las líneas de progreso):

```
tec-review 0.1.0 - auditando C:\Users\User\Projects\SaxNew\scraper-app

Veredicto: GO  |  score 94.0/100  |  confianza baja (11/28 reglas evaluadas)
Hallazgos: 37  |  interpretados: 0
Reporte: C:\Users\User\AppData\Local\Temp\tec-demo\scraper-app-20261108-171119-edce25\report.md
```

Cómo leerlo:

| Campo | Significado |
|---|---|
| **Veredicto** | `GO` (score ≥ 75 sin `high` ni `critical`), `CONDITIONAL` (algún `high` o score 50–74), `NO-GO` (algún `critical` o score < 50) |
| **score** | 0–100, media ponderada de 5 dimensiones: seguridad 30, pruebas 20, diseño 20, mantenibilidad 20, configuración/observabilidad 10 |
| **confianza** | Cuántas reglas aplicables se pudieron evaluar; las que no, aparecen en el reporte con su motivo |
| **Hallazgos** | Total detectado, con el desglose por severidad en el reporte |
| **interpretados** | Cuántos explicó el modelo; `0` es lo normal con `--no-llm` |

Comprueba el código de salida:

```powershell
$LASTEXITCODE
```

`0` = la revisión terminó (sea cual sea el veredicto). `2` = error de uso o de herramienta. El veredicto nunca cambia el código de salida: la revisión informa, no bloquea.

Un resultado sin hallazgos no demuestra que el código esté libre de errores ni de vulnerabilidades: cada reporte incluye esa advertencia y declara qué reglas y lenguajes cubrió.

---

## 7. Abrir el reporte

Cada ejecución crea una carpeta `<proyecto>-<fecha>-<run_id>`. Para localizar la última:

```powershell
$run = Get-ChildItem "$env:TEMP\tec-demo" -Directory | Sort-Object LastWriteTime | Select-Object -Last 1
$run.FullName
```

Debe imprimir algo como:

```
C:\Users\User\AppData\Local\Temp\tec-demo\scraper-app-20261108-171119-edce25
```

Ábrelo:

```powershell
notepad "$($run.FullName)\report.md"
```

Si usaste la salida por defecto en lugar de `--out`:

```powershell
dir $env:USERPROFILE\.tec-review\out
notepad "$env:USERPROFILE\.tec-review\out\<proyecto>-<run_id>\report.md"
```

Abre el `.md` con `notepad`, VS Code o similar. Si lo lees con `Get-Content` en la consola verás los acentos rotos (`RevisiA3n`): el archivo está bien, es la codificación de la consola.

Contenido de la carpeta del run:

| Archivo | Contenido |
|---|---|
| `report.md` | El informe para leer |
| `report.json` | El mismo informe para máquina (`schema_version`) |
| `facts.json` | Hechos deterministas; **esto** se compara entre ejecuciones |
| `triage.json` | Qué hallazgos se seleccionaron para explicar |
| `manifest.json` | Procedencia: herramientas, versiones, tiempos, tokens |
| `interpretations.json` | Solo con LLM: explicaciones y su verificación |
| `judgments.json` | Solo con Pista B: juicios, evidencia y motivos de rechazo |

---

## 8. Qué revisar dentro del `report.md`

| Sección | Qué comprobar |
|---|---|
| 1. Resumen ejecutivo | Veredicto, score, confianza, recuento por severidad y la advertencia en negrita |
| 2. Scorecard | Las 5 dimensiones con pesos 30/20/20/20/10 |
| 3. Hallazgos priorizados | Regla y cita literal, *por qué se marcó*, **evidencia**, origen (herramienta + versión + fingerprint) y *safe path* |
| 4. Plan de sprint | Tareas derivadas de los hallazgos |
| 5. Reglas no evaluadas | Cada regla que no se evaluó, con su motivo |
| 6. Anexo de metodología | Herramientas con versión y estado, uso del modelo y tiempos por nodo |

La **evidencia** de cada hallazgo es texto que debe existir literalmente en la línea indicada. Se puede verificar sin abrir el archivo entero:

```powershell
Select-String -Path "C:\Users\User\Projects\SaxNew\scraper-app\backend\probar_parser.py" -Pattern "tu-pagina-de-ajedrez"
```

El *safe path* explica cómo corregir; nada se aplica automáticamente sobre el código.

---

## 9. (Opcional) Segunda pasada con el modelo

Requiere `llm-router` en `OK` (paso 4). Tarda en torno a un minuto.

```powershell
tec-review review "C:\Users\User\Projects\SaxNew\scraper-app" --level quick --out "$env:TEMP\tec-demo-llm"
```

Qué cambia y qué no:

- El **score y el veredicto deben ser los mismos** que en el paso 6: el modelo explica, no puntúa.
- Sube `interpretados` (hasta 10 con `--level quick`; 40 con `standard`; todos con `deep`).
- La **confianza sube** si además activas la Pista B (`--track-b` o `--level deep`), porque entonces sí se evalúan las reglas de juicio.
- Aparecen `interpretations.json` y, si activas la Pista B, `judgments.json`.
- En `manifest.json`, bloque `metrics`: `hallucination_rate` debe ser `0.0` o muy bajo, y `claims_grounded` igual a `claims_total`.
- En `interpretations.json`, cada entrada es `confirmed` (verificada y publicada) o `unverifiable` (descartada y sustituida por la plantilla).

Reglas de juicio (SRP, DIP, reintentos, secretos en prompts…):

```powershell
tec-review review "C:\Users\User\Projects\SaxNew\scraper-app" --track-b --out "$env:TEMP\tec-demo-b"
```

Esos hallazgos se reportan en una sección aparte y **no alteran el score ni el veredicto**.

---

## 10. Repetir otro día

```powershell
deactivate
```

O simplemente cierra la ventana.

La próxima vez solo hacen falta tres comandos:

```powershell
cd C:\Users\User\Projects\SaxNew\revisionTecnicaProjects
.\.venv\Scripts\Activate.ps1
tec-review review "C:\ruta\al\proyecto" --no-llm
```

---

## 11. Errores típicos

| Síntoma | Causa | Solución |
|---|---|---|
| `"tec-review" no se reconoce como un comando` | Entorno no activado | Paso 2, o usa `.\.venv\Scripts\tec-review ...` |
| `no se puede cargar el archivo ... Activate.ps1` | ExecutionPolicy | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |
| `Escritura bloqueada (I1): ... está dentro del proyecto auditado`, código 2 | `--out` apunta dentro del proyecto | Usa `%TEMP%` o `~\.tec-review\out` |
| `La ruta no existe o no es un directorio`, código 2 | Ruta mal escrita o es un archivo | Revisa la ruta y las comillas |
| Tarda muchísimo | SecureProjects recorriendo `venv/` | Paso 5, Opción A |
| `aviso: llm-router no responde ...: modo degradado sin LLM` | Servicio caído | Es normal: el informe sale igual, con plantillas |
| Acentos raros en pantalla | Codificación de la consola | Abre el `.md` en notepad o VS Code |
| `Ruleset desconocido`, `Regla desconocida` | Nombre mal escrito | `tec-review rules list` para ver los válidos |

---

## 12. Para ir más allá

- Todas las opciones de `review`: [`README.md`](README.md) §4.
- Catálogo de reglas: `tec-review rules list` y `tec-review rules show <id>`.
- Comprobar el software a mano, con resultados esperados de cada prueba: [`qahumano.md`](qahumano.md).
- Diseño y garantías: [`planInicial.md`](planInicial.md) y [`adr/`](adr/).
