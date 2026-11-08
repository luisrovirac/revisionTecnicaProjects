# ADR 0002 — La capa de seguridad se delega en SecureProjects

- **Estado:** aceptada · 2026-11-08

## Contexto
El plan v0.2 reimplementaba secretos, SAST y CVE (bandit, semgrep, pip-audit, entropía). El usuario ya mantiene SecureProjects (`../ciberSeguridadDeProyectos`, Go): secretos con redacción, SAST, CVE vía OSV offline, IaC, deduplicación, fingerprints sin línea, JSON `schemaVersion 1.x` y SARIF. El servicio `security-audit` de DevSaxAIFloow escanea strings sueltos y es más superficial.

## Decisión
`tec-review` invoca el binario `secureprojects scan <ruta> -f json -o <tmp> --offline --safe --fail-on none` y parsea su informe a hechos tipados. Las reglas `sec.*` del catálogo son `tool_rule` con `severity: inherit`: la herramienta fija la severidad y el catálogo aporta cita y `safe_path`.

- El informe se escribe en un temporal fuera del target (I1).
- Se ignora el estado de triage del informe: una supresión definida en el repo auditado no oculta hallazgos (I10).
- Los hallazgos de secretos se marcan `sensitive`: nunca se copian líneas de código al reporte ni al prompt, solo la evidencia ya redactada.
- Binario ausente → `Gap(tool_unavailable)` en las 4 reglas `sec.*`; nunca se instala (I6).

## Consecuencias
Se elimina del plan la reimplementación de seguridad. Un cambio de esquema mayor en SecureProjects se detecta y se reporta como error de herramienta, no como "sin hallazgos".
