```markdown
# Reglas Generales para el Desarrollo de DevSaxAIFloow

## 1. Arquitectura y Organización del Código

1. **Separación de responsabilidades**: Cada módulo, clase o función debe tener una única responsabilidad bien definida. Por ejemplo, la lógica de construcción de prompts no debe estar dentro de los nodos de LangGraph, sino en clases separadas como `DatabaseContextBuilder`.
2. **Inyección de dependencias**: Utiliza inyección de dependencias (como la que ofrece Theia con Inversify) en lugar de singletons globales. Esto facilita las pruebas unitarias y el desacoplamiento.
3. **Mantén el núcleo del grafo limpio**: Los nodos de LangGraph (`planner_node`, `coder_node`, etc.) deben ser delgados; su función principal es orquestar y delegar en servicios especializados. No deben contener lógica de negocio compleja.
4. **Define tipos claros**: Usa `TypedDict` (como `AgentState`) y clases de datos (Pydantic) para todas las estructuras de datos compartidas. Esto mejora la legibilidad y permite la detección temprana de errores.

## 2. Configuración y Entorno

5. **Toda configuración va en variables de entorno o archivos de configuración**: Nunca hardcodees valores como URLs, credenciales, nombres de modelos o rutas. Usa un archivo `.env` para variables sensibles y un archivo como `agent_config.json` para configuraciones no sensibles (prompts, modelos por defecto).
6. **Valida la configuración al inicio**: Carga y valida todas las variables de entorno y configuraciones al arrancar la aplicación. Si falta alguna variable crítica, la aplicación debe fallar con un mensaje claro.
7. **No uses `print` para logging**: Utiliza el módulo `logging` de Python con niveles apropiados (DEBUG, INFO, ERROR). Configura un formato que incluya timestamp, nivel y nombre del módulo.
8. **Centraliza la gestión de secretos**: Las credenciales (API keys, contraseñas de bases de datos) deben ser leídas desde variables de entorno o un gestor de secretos (como HashiCorp Vault) y nunca expuestas en logs o repositorios.

## 3. Manejo de Errores y Resiliencia

9. **Captura excepciones específicas**: Evita `except Exception:` genérico. Captura las excepciones que esperas manejar (por ejemplo, `RateLimitError` para reintentos) y deja que las inesperadas se propaguen o se registren adecuadamente.
10. **Implementa reintentos con backoff**: Para operaciones que pueden fallar transitoriamente (llamadas a APIs externas, acceso a red), usa mecanismos de reintento con backoff exponencial. La función `call_llm_with_retry` es un buen ejemplo.
11. **Siempre libera recursos**: Usa bloques `try...finally` o gestores de contexto (`with`) para asegurar que archivos, conexiones de red, cursores de bases de datos, etc., se cierren correctamente.
12. **Proporciona mensajes de error útiles**: Cuando ocurra un error, el mensaje debe ser claro para el desarrollador (en logs) y, si es posible, también para el usuario final (con sugerencias de acción).

## 4. Seguridad

13. **No instales paquetes automáticamente sin control**: El auto-healing de pip en el sandbox debe limitarse a una lista de paquetes conocidos y seguros. Evita instalar cualquier módulo que el código solicite.

## 5. Pruebas y Calidad

14. **Escribe pruebas unitarias**: Para cada clase o función importante, debe haber pruebas que verifiquen su comportamiento. Esto es especialmente crítico para la lógica de construcción de prompts, el parser de diffs y los reintentos.
15. **Mantén una cobertura de código saludable**: Apunta al menos al 80% de cobertura en los módulos principales.
16. **Usa linters y formateadores**: Configura herramientas como `pylint`, `flake8`, `black` (para Python) y `eslint`/`prettier` (para TypeScript) para mantener un estilo consistente y detectar errores temprano.
17. **Realiza pruebas de integración**: El flujo completo debe probarse.

## 6. Frontend (Theia/TypeScript)

18. **Usa TypeScript estrictamente**: Si usas typescript define interfaces para todas las estructuras de datos y evita el uso de `any`.

## 7. Principio General

19. **No solamente hay que hacer que las cosas funcionen, sino hacerlo de manera profesional y standard**: Toda solución debe seguir las mejores prácticas de la industria, ser mantenible, escalable y legible. Evita parches rápidos o soluciones ad-hoc que solo "hagan que funcione". El objetivo siempre es código de calidad profesional.
20. **Antes de contestar la primera consulta del usuario, debo leer RULES.md y tenerlo presente a partir de allí, para poner en práctica dichas reglas**: Este archivo debe ser leído al inicio de cada nueva conversación como paso obligatorio antes de cualquier acción o respuesta.

## 8. Tests

21. **Todos los tests deben ubicarse en un directorio tests, nunca crear archivos de test en la raíz. Todo nuevo archivo de test debe crearse con el prefijo `test_` (ejemplo: `tests/test_nueva_funcionalidad.py`).

## 9. Principios SOLID (Aplicación estricta)

Estos principios son fundamentales para lograr un código mantenible, extensible y con baja cohesión accidental. Todo código generado o modificado debe respetarlos:

22. **S – Principio de Responsabilidad Única (SRP)**: Una clase, módulo o función debe tener una única razón para cambiar. Si identificas más de una responsabilidad (ejemplo: una clase que construye prompts y además llama a la API), divídelas en entidades separadas.

23. **O – Principio de Abierto/Cerrado (OCP)**: Las entidades deben estar abiertas para la extensión, pero cerradas para la modificación. Prefiere herencia, composición o estrategias (patrón Strategy) antes que modificar código existente y probado. Por ejemplo, para añadir un nuevo tipo de nodo LangGraph, crea una subclase o un nuevo componente, no edites el grafo principal.

24. **L – Principio de Sustitución de Liskov (LSP)**: Las subclases deben poder ser usadas en lugar de sus clases base sin alterar el correcto funcionamiento del programa. Al sobrescribir métodos, respeta el contrato (parámetros, tipo de retorno, excepciones, comportamiento esperado). Evita lanzar excepciones no declaradas o cambiar la semántica del método.

25. **I – Principio de Segregación de Interfaces (ISP)**: Es mejor tener varias interfaces pequeñas y específicas que una interfaz general con muchos métodos opcionales. En Python, usa protocolos (`typing.Protocol`) o clases base abstractas (`ABC`) con métodos bien acotados. En TypeScript, define interfaces pequeñas y compónlas.

26. **D – Principio de Inversión de Dependencias (DIP)**: Los módulos de alto nivel no deben depender de módulos de bajo nivel, sino de abstracciones. Las abstracciones no deben depender de detalles, sino los detalles de las abstracciones. Aplica inyección de dependencias (Inversify en Theia, o inyección manual en Python) y programa contra interfaces, no contra implementaciones concretas.

## 10. Estrategia para que los Agentes de IA implementen SOLID

Para garantizar que el código generado por asistentes o agentes de IA cumpla con SOLID y las demás reglas, se deben seguir estas prácticas:

27. **Análisis automático de cumplimiento**: Antes de entregar cualquier fragmento de código, el agente debe ejecutar (o simular) un análisis estático con herramientas como `pylint --check-qualities`, `mypy` (para tipado) y `radon` (para métricas de complejidad). Si se detecta violación de SRP o alta cohesión, debe refactorizar.

28. **Generación de código orientada a interfaces**: Al crear una nueva clase, el agente debe primero definir una interfaz (protocolo o ABC) que describa su comportamiento público. Luego implementar la clase concreta. Esto fuerza el cumplimiento de ISP y DIP.

29. **Verificación de inyección de dependencias**: El agente debe revisar que ninguna clase instancie directamente sus dependencias (ej. `api = OpenAIClient()`). En su lugar, debe recibirlas por constructor o método, y el ensamblado debe ocurrir en un punto central (contenedor IoC o fábrica). Cualquier `import` dentro de un método que no sea para librería estándar es sospechoso.

30. **Refactorización de métodos largos y clases grandes**: Si una función supera las 20 líneas (sin contar docstring) o una clase tiene más de 5 métodos públicos, el agente debe evaluar si viola SRP y proponer división. Herramientas como `flake8` con `max-complexity` pueden ayudar.

31. **Pruebas de sustitución (LSP)**: Al generar una jerarquía de herencia, el agente debe incluir pruebas unitarias que demuestren que cualquier instancia de la subclase puede reemplazar a la superclase sin alterar los tests existentes. Ejemplo: si `PlannerNode` hereda de `BaseNode`, los tests de `BaseNode` deben pasar con `PlannerNode`.

32. **Uso de patrones de diseño alineados con OCP**: El agente debe favorecer patrones como Strategy, Factory Method, Template Method o Decorator en lugar de `if/elif` que dispersan lógica. Por ejemplo, para diferentes estrategias de construcción de prompts, usar un diccionario de estrategias registradas.

33. **Checklist de revisión de código automatizada**: El agente debe generar un reporte de cumplimiento SOLID para cada módulo, con preguntas como:
    - ¿Cada clase tiene una única responsabilidad? (SRP)
    - ¿Se puede extender sin modificar el original? (OCP)
    - ¿Se pueden intercambiar subclases sin romper nada? (LSP)
    - ¿Las interfaces son específicas y pequeñas? (ISP)
    - ¿Las dependencias apuntan hacia abstracciones? (DIP)

