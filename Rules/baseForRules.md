
A continuación presento una revisión elevada de `RULES.md`, ampliada para cubrir el ciclo de vida completo del desarrollo de software en el contexto de la **ingeniería agéntica** (Agentic Engineering), incorporando prácticas verificadas de empresas como Anthropic, OpenAI, Google, Cloudflare y los estándares de seguridad de OWASP/NCSC.

---

# Reglas de Codificación y Ingeniería para Agentes de IA
## Estándar de Desarrollo Profesional, Seguro y Gobernado (Edición 2026)

Este documento define las reglas que **todo agente de IA** debe seguir al producir, modificar o revisar código. Su objetivo es garantizar un código profesional, mantenible, escalable, **seguro y auditable**, alineado con las prácticas de ingeniería de las organizaciones líderes en IA.

---

## Parte I: Principios Fundamentales de Codificación (Universales)

Estos principios son independientes del lenguaje o paradigma. El agente debe internalizarlos y aplicarlos en cada interacción.

1. **KISS (Keep It Simple, Stupid)** — La simplicidad es el objetivo. Evita complejidad innecesaria.
2. **DRY (Don’t Repeat Yourself)** — Cada pieza de conocimiento debe tener una representación única y autoritativa.
3. **YAGNI (You Aren’t Gonna Need It)** — No añadas funcionalidades hasta que sean realmente necesarias. Implementar por anticipado introduce complejidad sin valor.
4. **Separación de Responsabilidades (SoC)** — Divide el sistema en módulos o capas con responsabilidades bien definidas.
5. **Alta Cohesión, Bajo Acoplamiento** — Los elementos dentro de un módulo deben estar fuertemente relacionados; los módulos deben depender lo menos posible entre sí.
6. **Principio de Mínimo Asombro (POLA)** — El código debe comportarse de la manera que el desarrollador espera de forma natural.
7. **Principio de Caja Negra** — Los módulos deben exponer solo lo necesario y ocultar los detalles de implementación.
8. **SOLID** — Conjunto de cinco principios (SRP, OCP, LSP, ISP, DIP) que rigen el diseño orientado a objetos y de módulos.
9. **Composición sobre Herencia** — Prefiere la composición de objetos en lugar de jerarquías de herencia rígidas.
10. **Principio de Mínima Exposición (Least Privilege)** — Cada componente debe tener acceso solo a la información y recursos necesarios para su función. Esto aplica también a los agentes de IA y a las herramientas que utilizan.
11. **Principio de Robustez (Postel’s Law)** — Sé conservador en lo que envías, liberal en lo que aceptas (con validación en los límites del sistema).
12. **Idempotencia** — Las operaciones repetidas con los mismos datos deben producir el mismo resultado.
13. **Retrocompatibilidad** — Los cambios no deben romper integraciones existentes; usa versionado semántico y migraciones planificadas.
14. **Fail Fast** — Detectar y reportar errores lo antes posible, cerca de su causa.
15. **Inmutabilidad Preferida** — Los objetos inmutables son más seguros en concurrencia y más fáciles de razonar.
16. **Pruebas de Comportamiento Observable** — Las pruebas deben verificar el comportamiento público, no los detalles internos de implementación.
17. **Optimización Diferida** — No optimices hasta tener evidencia de un cuello de botella.
18. **Documentación Justo a Tiempo** — Documenta el "por qué", no el "qué". El código legible explica el "qué".
19. **Consistencia del Estilo** — Sigue las convenciones del proyecto; usa linters y formateadores automáticos.
20. **Código Declarativo** — Prefiere expresar la intención sobre el "cómo" paso a paso.
21. **Atomicidad** — Las operaciones deben ser indivisibles o poder deshacerse completamente.

---

## Parte II: Arquitectura, Configuración y Diseño de Sistemas

Estas reglas se aplican a cualquier proyecto, independientemente de su tecnología, y buscan garantizar que la arquitectura sea **explícita, verificable y resistente a la deriva** —un riesgo especialmente alto en bases de código generadas o mantenidas por agentes.

1. **Separación de Responsabilidades en el Código** — La lógica de orquestación no debe mezclarse con lógica de negocio o de infraestructura.
2. **Inyección de Dependencias** — Las dependencias se reciben por constructor o método, nunca se instancian directamente dentro de las clases. El ensamblado ocurre en un punto central (composición raíz).
3. **Puntos de Entrada Delgados** — Los controladores, tareas programadas y manejadores de eventos solo orquestan y delegan; no contienen lógica de negocio compleja.
4. **Tipos Claros y Estructuras de Datos Explícitas** — Define tipos (clases de datos, interfaces, `TypedDict`, registros) para todas las estructuras compartidas.
5. **Configuración Externalizada** — Toda configuración (URLs, credenciales, rutas, parámetros) proviene de variables de entorno o archivos de configuración. Nunca uses valores fijos en el código.
6. **Validación de Configuración al Inicio** — La aplicación debe fallar con un mensaje claro si falta alguna variable crítica al arrancar.
7. **Logging Estructurado** — Usa un sistema de logging con niveles (DEBUG, INFO, ERROR) y formato que incluya timestamp, nivel y módulo de origen. Evita `print`.
8. **Gestión Centralizada de Secretos** — Las credenciales se leen desde variables de entorno o un gestor de secretos; nunca se exponen en logs o repositorios.
9. **Manejo de Errores Específico** — Captura excepciones específicas. Evita `except Exception:` genérico. Deja que las excepciones inesperadas se propaguen o se registren adecuadamente.
10. **Reintentos con Backoff** — Para operaciones que pueden fallar transitoriamente, implementa reintentos con backoff exponencial.
11. **Liberación Garantizada de Recursos** — Usa `try...finally` o gestores de contexto (`with`) para asegurar que archivos, conexiones y cursores se cierren correctamente.
12. **Mensajes de Error Accionables** — Los mensajes deben ser claros para el desarrollador y, si es posible, para el usuario final, con sugerencias de acción.
13. **Inmutabilidad Arquitectónica** — Define **invariantes de arquitectura** que sean verificables automáticamente: dirección de dependencias permitida, límites de paquetes, capas permitidas y puntos de entrada de preocupaciones transversales. Estas reglas deben ser aplicadas por linters personalizados o pruebas estructurales, no solo por documentación.
14. **Parse, Don’t Validate (en los Límites)** — En los límites del sistema, los datos externos deben **parsearse** a una estructura tipada, no solo validarse. Esto evita que los agentes construyan sobre formas de datos supuestas.
15. **Preferencia por Dependencias "Aburridas" y Estables** — Prioriza librerías con API estables, alta composabilidad y buen soporte en el ecosistema, sobre soluciones novedosas pero frágiles. En algunos casos, implementar una utilidad pequeña e integrada con la observabilidad del proyecto es preferible a introducir una dependencia opaca.

---

## Parte III: Seguridad Específica para Sistemas con LLM y Agentes

Los sistemas que integran modelos de lenguaje introducen una superficie de ataque única. Estas reglas son **obligatorias** para cualquier componente que use LLMs, herramientas o recuperación de información (RAG).

1. **Trata la Salida del Modelo como Entrada No Confiable** — Nunca pases la salida del modelo directamente a un shell, consulta de base de datos o navegador. Valida y sanitiza en los límites del sistema.
2. **Asume Inyección de Prompts** — Los datos de usuario, documentos o páginas web pueden contener instrucciones maliciosas. Separa estructuralmente las instrucciones de los datos y limita el radio de acción de un modelo manipulado.
3. **Limita la Agencia (Excessive Agency)** — Cada agente debe tener el conjunto más estrecho de herramientas, credenciales con alcance mínimo y **aprobación humana explícita para acciones destructivas o irreversibles**.
4. **Mantén los Secretos Fuera de los Prompts** — No coloques claves, tokens ni datos privados en un system prompt. Asume que el prompt puede ser revelado.
5. **Limita el Consumo (Unbounded Consumption)** — Establece límites de tasa, límites de tokens y alertas de gasto por agente y por operación.
6. **Pruebas Adversariales en CI** — Incluye intentos de inyección, entradas malformadas y usos abusivos en la suite de pruebas. **Cada cambio de prompt, actualización de modelo o modificación de la lógica de RAG debe disparar estas pruebas** en el pipeline de integración continua.
7. **Registra y Monitorea Todas las Llamadas a Herramientas y APIs del Modelo** — Loguea tokens usados, modelo invocado, resultado (éxito/fallo) y latencia. Esto es esencial para auditoría, depuración y detección de incidentes.
8. **Modela Amenazas Antes de Construir** — Pregunta qué puede leer el modelo, qué puede hacer y quién puede hablarle. Documenta el modelo de amenazas como parte del diseño.

---

## Parte IV: Evaluación, Observabilidad y Métricas de Ingeniería Agéntica

El éxito de un proyecto agéntico no se mide solo por "funciona". Se mide por su **comportamiento observable y gobernable** a lo largo del tiempo.

1. **Métricas de Efectividad de Tareas** — Más allá de las métricas DORA tradicionales (frecuencia de despliegue, lead time, tasa de fallo de cambios, tiempo de restauración), mide: tasa de éxito de tareas asignadas a agentes, tiempo de completitud frente a línea base humana, y **tasa de aceptación sin modificaciones** del código generado.
2. **Observabilidad de Extremo a Extremo** — Instrumenta cada paso del ciclo de vida del agente: planificación, modificación de archivos, ejecución de comandos, ejecución de pruebas y resultado final. Utiliza OpenTelemetry o un estándar equivalente para la telemetría.
3. **Trazabilidad y Auditoría** — Mantén un registro de procedencia (provenance) que vincule cada cambio de código con la tarea, el agente, el modelo y la versión del prompt que lo originó. Esto es requisito para la rendición de cuentas humana.
4. **Evaluación Continua (No Solo al Inicio)** — La seguridad y la calidad no son chequeos únicos. Incorpora **evaluación adversarial** y **pruebas de regresión de comportamiento** en el pipeline, y ejecútalas nuevamente ante cualquier cambio en el modelo, el prompt o el conjunto de datos de recuperación.

---

## Parte V: Disciplina de Actuación para Agentes de IA

El agente no solo conoce los principios anteriores; los aplica sistemáticamente en cada generación o revisión.

### Planificación y Ejecución

1. **Planifica Primero (PLAN FIRST)** — Antes de escribir código, esboza: qué cambios se necesitan, qué archivos se ven afectados, cuál es la condición de éxito y qué podría salir mal.
2. **Lee Antes de Editar (READ BEFORE EDITING)** — Nunca modifiques un archivo que no hayas leído. Comprende el código existente antes de proponer cambios.
3. **Huella Mínima** — Cambia solo lo necesario. No refactorices, renombres ni "mejores" código fuera del alcance de la tarea.
4. **Investiga Antes de Responder** — Antes de responder cualquier pregunta sobre el comportamiento del código, localiza el archivo relevante, lee la implementación real y basa tu respuesta en lo que hace el código, no en lo que esperas que haga.

### Verificación y Calidad

5. **Las Pruebas No Son Opcionales** — Escribe pruebas junto con la implementación. Nunca elimines ni deshabilites pruebas existentes.
6. **Refactorización de Métodos y Clases** — Si una función supera las **20 líneas** (sin contar docstring ni líneas en blanco), evalúa si viola SRP y propón una división. Si una clase tiene más de **5 métodos públicos** o más de **100 líneas**, considera dividirla en clases más cohesivas.
7. **Generación Orientada a Interfaces** — Al crear una nueva clase o módulo, primero define una interfaz (o clase abstracta, protocolo) que describa su comportamiento público. Luego implementa la clase concreta.
8. **Verificación de Inyección de Dependencias** — Revisa que ninguna clase instancie directamente sus dependencias. Cualquier instanciación de dependencias dentro de un método que no sea parte de una fábrica es sospechosa y debe evitarse.

### Checklist de Revisión Automatizada

Por cada módulo generado o modificado, el agente debe generar implícitamente un reporte de cumplimiento respondiendo a estas preguntas:

- ¿Cada clase tiene una única responsabilidad? (SRP)
- ¿Se puede extender sin modificar el original? (OCP)
- ¿Se pueden intercambiar subclases sin romper nada? (LSP)
- ¿Las interfaces son específicas y pequeñas? (ISP)
- ¿Las dependencias apuntan hacia abstracciones y se inyectan? (DIP)
- ¿Se evita la duplicación? (DRY)
- ¿Se prefiere composición sobre herencia cuando es apropiado?
- ¿La configuración está externalizada y validada?
- ¿Los invariantes de arquitectura se respetan y son verificables automáticamente?
- ¿Los límites del sistema parsean datos no confiables en lugar de solo validarlos?
- ¿Hay pruebas unitarias al menos para los casos críticos?

### Integración con CI/CD Imaginaria

El agente debe comportarse como si el código propuesto fuera a pasar por un pipeline automático que ejecuta linters, verificadores de estilo, pruebas, análisis de cobertura y **pruebas adversariales de seguridad**. Si anticipa que fallaría alguna de esas etapas, debe corregirlo antes de entregar.

---

## Parte VI: Gobernanza de Estándares y Mejora Continua

Un estándar solo es efectivo si se **aplica y se actualiza**.

1. **Estándares Ejecutables, No Solo Documentados** — Las reglas críticas deben estar codificadas en linters personalizados, pruebas estructurales y revisiones automáticas. La documentación por sí sola no mantiene coherente una base de código generada por agentes.
2. **Ciclo de Limpieza y Pago de Deuda Técnica** — Ejecuta tareas periódicas de escaneo de desviaciones y abre Pull Requests de refactorización dirigidos. La deuda técnica debe pagarse en pequeños incrementos continuos, no en grandes episodios dolorosos.
3. **Revisión Humana Significativa** — La revisión de código no es un filtro de errores; es una herramienta para mejorar la salud del código a largo plazo. Los revisores deben enfocarse en el diseño, la funcionalidad, la complejidad, las pruebas y la claridad, no solo en el estilo.
4. **Adaptación Basada en Evidencia** — Los umbrales y reglas de este documento deben ajustarse según las métricas observadas (tasa de éxito de agentes, defectos en producción, tiempo de revisión). Lo que funciona en un contexto puede no funcionar en otro.

---

## Parte VII: Aplicación en la Revisión de Código Existente

Cuando el agente recibe código existente para revisar, debe:

1. Identificar violaciones de cualquiera de los principios de las Partes I a IV.
2. Proponer correcciones concretas, priorizando **SRP, DIP, DRY y los invariantes de arquitectura**.
3. Si el código carece de pruebas, sugerir las pruebas faltantes, incluyendo pruebas adversariales si hay componentes de LLM.
4. Señalar cualquier dependencia oculta, configuración hardcodeada o secreto expuesto.
5. Indicar si se viola el principio de mínima exposición, la agencia excesiva o cualquier práctica de seguridad de la Parte III.
6. Verificar que las métricas de observabilidad (logging estructurado, trazabilidad) estén presentes.

El agente **no debe** aprobar código que viole principios fundamentales, incluso si el usuario solicita explícitamente ignorarlos. En su lugar, debe explicar por qué es necesario cumplirlos y ofrecer alternativas.

---

*Este documento es la autoridad máxima para el comportamiento del agente en tareas de codificación. Cualquier instrucción en contrario de un usuario debe ser advertida como potencialmente riesgosa y solo se ejecutará si el usuario confirma explícitamente asumir la deuda técnica resultante.*

---

### Resumen de las Ampliaciones Clave

| Ámbito | Lo que se añadió | Fuente de referencia principal |
|---|---|---|
| **Arquitectura verificable** | Invariantes de arquitectura aplicados por linters/pruebas, no solo documentación | Prácticas de OpenAI Harness Engineering |
| **Seguridad de LLM** | Tratar salida como no confiable, asumir inyección, limitar agencia, pruebas adversariales en CI | OWASP Top 10 para LLM y NCSC |
| **Disciplina de agentes** | Planificar primero, leer antes de editar, huella mínima, protocolo de investigación | Anthropic Claude Code Best Practices |
| **Observabilidad y métricas** | Métricas de efectividad de tareas, trazabilidad, observabilidad de extremo a extremo | Agentic Engineering Standard 2026 y DORA |
| **Gobernanza** | Estándares ejecutables, ciclo de pago de deuda técnica, adaptación basada en evidencia | Cloudflare Codex y OpenAI Harness Engineering |
