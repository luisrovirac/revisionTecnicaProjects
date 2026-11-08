# ADR 0001 — Pipeline híbrido: hechos deterministas antes que el modelo

- **Estado:** aceptada · 2026-11-08

## Contexto
Un agente que recibe código y "opina" alucina ubicaciones, reglas y severidades, y no es reproducible. CodeRabbit, Codex y Claude Code coinciden: el valor está en el sistema que rodea al modelo (ver `docs/resumenInspirador.md`).

## Decisión
El orquestador es un workflow determinista de nodos tipados `(RunState, Dependencies) -> RunState`:
`inventory → collect → normalize → triage → interpret(+verify) → score → render`.
El único loop agéntico vive en `interpret`, acotado por reintentos (2) y presupuesto de tokens. El modelo recibe un `ContextBundle` construido por código (RAG estructurado por clave: `rule_id` → cita + `safe_path`; ubicación → fragmento numerado). Sin embeddings ni LangGraph en v1.

## Consecuencias
- `--no-llm` produce un reporte completo y útil.
- El score, el veredicto y `facts.json` son reproducibles (I5); solo las interpretaciones varían.
- Cada nodo persiste su artefacto (`facts.json`, `triage.json`, `interpretations.json`), base del futuro `--replay`.
