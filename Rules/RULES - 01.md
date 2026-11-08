
```markdown
# Reglas de Codificación para Agentes de IA
## Principios Universales y Directrices de Actuación Estricta

Este documento define el conjunto de reglas que **todo agente de IA** (asistente de codificación, generador automático, revisor de código) debe seguir al producir, modificar o revisar código fuente en cualquier lenguaje, proyecto o framework. Su objetivo es garantizar un código profesional, mantenible, escalable y consistente con las mejores prácticas universales.

---

## Parte I: Principios Fundamentales de Codificación (Universales)

Estos principios son independientes del lenguaje, paradigma o dominio de aplicación. El agente debe internalizarlos y aplicarlos en cada interacción.

### 1. KISS (Keep It Simple, Stupid)
La simplicidad es el objetivo clave. Evita complejidad innecesaria. El código más simple es más fácil de entender, mantener y depurar.

### 2. DRY (Don’t Repeat Yourself)
Cada pieza de conocimiento debe tener una representación única, no ambigua y autoritativa. Evita duplicación de lógica o datos.

### 3. YAGNI (You Aren’t Gonna Need It)
No añadas funcionalidades hasta que sean realmente necesarias. Implementar por anticipado introduce complejidad sin valor inmediato.

### 4. Separación de Responsabilidades (SoC)
Divide el sistema en módulos o capas con responsabilidades bien definidas y solapamientos mínimos (ej. separar lógica de negocio, presentación, acceso a datos).

### 5. Alta Cohesión, Bajo Acoplamiento
Los elementos dentro de un módulo deben estar fuertemente relacionados (cohesión alta); los módulos deben depender lo menos posible entre sí (acoplamiento bajo).

### 6. Principio de Mínimo Asombro (POLA)
El código debe comportarse de la manera que el desarrollador espera de forma natural. Las API, nombres y estructuras deben ser intuitivos y consistentes.

### 7. Principio de Caja Negra
Los módulos deben exponer solo lo necesario (interfaz) y ocultar los detalles de implementación. Esto facilita el cambio interno sin afectar a los consumidores.

### 8. SOLID (Conjunto de cinco principios)
- **S – Responsabilidad Única (SRP)**: Una clase, módulo o función debe tener una única razón para cambiar.
- **O – Abierto/Cerrado (OCP)**: Entidades abiertas para extensión, cerradas para modificación.
- **L – Sustitución de Liskov (LSP)**: Las subclases deben poder reemplazar a sus clases base sin alterar el comportamiento correcto.
- **I – Segregación de Interfaces (ISP)**: Interfaces específicas y pequeñas son mejores que una interfaz general con muchos métodos.
- **D – Inversión de Dependencias (DIP)**: Depender de abstracciones, no de implementaciones concretas.

### 9. Composición sobre Herencia
Prefiere la composición de objetos (inyección de dependencias, delegación) en lugar de la herencia de clases cuando sea posible, para evitar jerarquías rígidas.

### 10. Principio de Mínima Exposición (Least Privilege)
Cada componente debe tener acceso solo a la información y recursos necesarios para su función. Aplica a API, variables y permisos.

### 11. Principio de Robustez (Postel’s Law)
Sé conservador en lo que envías, liberal en lo que aceptas. Para API y entradas, tolera variaciones razonables pero produce salidas estrictas.

### 12. Principio de Idempotencia
Las operaciones repetidas con los mismos datos deben producir el mismo resultado (crítico para API, reintentos, actualizaciones).

### 13. Principio de Retrocompatibilidad
Los cambios no deben romper integraciones existentes. Si es necesario romper, usa versionado semántico y migraciones planificadas.

### 14. Fail Fast
Detectar y reportar errores lo antes posible, cerca de su causa. Esto facilita la depuración y evita efectos secundarios silenciosos.

### 15. Inmutabilidad Preferida
Los objetos inmutables son más seguros en entornos concurrentes y más fáciles de razonar. Usa inmutabilidad donde sea práctico.

### 16. Pruebas de Comportamiento Observable
Las pruebas deben verificar el comportamiento público, no los detalles internos de implementación. Esto permite refactorizar sin romper tests.

### 17. Optimización Diferida (Premature Optimization)
No optimices hasta que tengas evidencia de cuello de botella. Primero hazlo funcionar, luego hazlo rápido.

### 18. Documentación Justo a Tiempo
Documenta el "por qué", no el "qué". El código legible explica el "qué". Comenta solo cuando la intención no sea evidente.

### 19. Consistencia del Estilo
Sigue las convenciones del lenguaje y del proyecto (formateo, nomenclatura, estructura). Usa linters y formateadores automáticos.

### 20. Código Declarativo
Prefiere expresar la intención (qué se quiere lograr) sobre el cómo paso a paso. Usa funciones de alto orden, expresiones lambda, SQL, etc., cuando sea apropiado.

### 21. Atomicidad
Las operaciones deben ser indivisibles o poder deshacerse completamente. Aplica a transacciones de base de datos, actualizaciones de estado, commits.

---

## Parte II: Directrices de Arquitectura y Configuración (Genéricas)

Estas reglas se aplican a cualquier proyecto, independientemente de su tecnología.

### 1. Separación de Responsabilidades en el Código
Cada módulo, clase o función debe tener una única responsabilidad bien definida. La lógica de orquestación no debe mezclarse con lógica de negocio o de infraestructura.

### 2. Inyección de Dependencias
Utiliza inyección de dependencias (contenedores IoC, o inyección manual en constructores) en lugar de singletons globales o instanciación directa dentro de las clases. Esto facilita pruebas y desacoplamiento.

### 3. Núcleos o Puntos de Entrada Delgados
Los puntos de entrada (ej. controladores, tareas programadas, manejadores de eventos) deben ser delgados: solo orquestar y delegar en servicios especializados, sin contener lógica de negocio compleja.

### 4. Tipos Claros y Estructuras de Datos Explícitas
Define tipos (clases de datos, interfaces, `TypedDict`, registros) para todas las estructuras de datos compartidas. Esto mejora legibilidad y detección temprana de errores.

### 5. Configuración Externalizada
Toda configuración (URLs, credenciales, nombres de modelos, rutas, parámetros ajustables) debe venir de variables de entorno o archivos de configuración. Nunca uses valores fijos en el código.

### 6. Validación de Configuración al Inicio
Carga y valida todas las configuraciones al arrancar la aplicación. Si falta alguna variable crítica, la aplicación debe fallar con un mensaje claro y detener su ejecución.

### 7. Logging Estructurado
No uses `print`. Utiliza un sistema de logging con niveles (DEBUG, INFO, ERROR) y formato que incluya timestamp, nivel y módulo de origen.

### 8. Gestión Centralizada de Secretos
Las credenciales (API keys, contraseñas) deben ser leídas desde variables de entorno o un gestor de secretos (Vault, AWS Secrets Manager), nunca expuestas en logs o repositorios.

### 9. Manejo de Errores Específico
Captura excepciones específicas que esperas manejar (ej. `RateLimitError`, `TimeoutError`). Evita `except Exception:` genérico. Deja que las excepciones inesperadas se propaguen o se registren adecuadamente.

### 10. Reintentos con Backoff
Para operaciones que pueden fallar transitoriamente (llamadas a API externas, red), implementa reintentos con backoff exponencial.

### 11. Liberación Garantizada de Recursos
Usa bloques `try...finally` o gestores de contexto (`with`) para asegurar que archivos, conexiones de red, cursores de BD se cierren correctamente.

### 12. Mensajes de Error Accionables
Cuando ocurra un error, el mensaje debe ser claro para el desarrollador (en logs) y, si es posible, también para el usuario final (con sugerencias de acción).

### 13. Seguridad por Defecto
No instales paquetes automáticamente sin control. Si el código solicita dependencias externas, debe haber una lista blanca de fuentes confiables. Nunca ejecutes código no verificado.

### 14. Pruebas Obligatorias
- **Unitarias**: Cada clase o función importante debe tener pruebas unitarias.
- **Cobertura**: Apunta al menos al 80% de cobertura en módulos críticos.
- **Integración**: El flujo completo debe probarse.
- **Ubicación**: Los tests deben ir en un directorio `tests/` con prefijo `test_` en cada archivo.

### 15. Linters y Formateadores Automáticos
Configura y usa linters y formateadores (ej. `pylint`, `flake8`, `black`, `eslint`, `prettier`) para mantener estilo consistente y detectar errores temprano.

### 16. Tipado Estricto
Cuando el lenguaje lo soporte (TypeScript, Python con anotaciones, Java, C#), usa tipado estricto. Evita `any` o tipos dinámicos no necesarios.

---

## Parte III: Directrices Específicas para Agentes de IA

El agente de IA no solo debe conocer los principios anteriores, sino que debe aplicarlos de manera sistemática en cada generación o revisión de código. Para ello, seguirá estas reglas de actuación estricta.

### 1. Análisis Automático de Cumplimiento
Antes de entregar cualquier fragmento de código, el agente debe ejecutar (o simular) un análisis estático con herramientas como linters, verificadores de tipos y analizadores de complejidad. Si detecta violación de SRP, alta cohesión, o cualquier otro principio, debe refactorizar antes de presentar la solución.

### 2. Generación Orientada a Interfaces
Al crear una nueva clase o módulo, el agente debe **primero** definir una interfaz (o clase abstracta, protocolo) que describa su comportamiento público. **Luego** implementar la clase concreta. Esto fuerza el cumplimiento de ISP y DIP.

### 3. Verificación de Inyección de Dependencias
El agente debe revisar que ninguna clase instancie directamente sus dependencias (ej. `new Service()` o `Service()`). En su lugar, debe recibirlas por constructor o método, y el ensamblado debe ocurrir en un punto central (contenedor IoC, fábrica, o composición raíz). Cualquier instanciación de dependencias dentro de un método que no sea parte de una fábrica es sospechosa y debe evitarse.

### 4. Refactorización de Métodos Largos y Clases Grandes
- Si una función supera las **20 líneas** (sin contar docstring ni blanks), el agente debe evaluar si viola SRP y proponer división.
- Si una clase tiene más de **5 métodos públicos** o más de **100 líneas**, debe considerar la posibilidad de dividirla en múltiples clases más cohesivas.

### 5. Pruebas de Sustitución (LSP)
Al generar una jerarquía de herencia, el agente debe incluir pruebas unitarias que demuestren que cualquier instancia de la subclase puede reemplazar a la superclase sin alterar los tests existentes. Es decir, debe garantizar que se cumple el comportamiento esperado del contrato.

### 6. Patrones de Diseño Alineados con OCP
El agente debe favorecer patrones como **Strategy**, **Factory Method**, **Template Method** o **Decorator** en lugar de cadenas de `if/elif` o `switch` que dispersan lógica. Por ejemplo, para comportamientos variables, usar un registro de estrategias en lugar de condiciones explícitas.

### 7. Checklist de Revisión Automatizada
Por cada módulo generado o modificado, el agente debe generar implícitamente un reporte de cumplimiento respondiendo a estas preguntas:
- ¿Cada clase tiene una única responsabilidad? (SRP)
- ¿Se puede extender sin modificar el original? (OCP)
- ¿Se pueden intercambiar subclases sin romper nada? (LSP)
- ¿Las interfaces son específicas y pequeñas? (ISP)
- ¿Las dependencias apuntan hacia abstracciones y se inyectan? (DIP)
- ¿Se evita la duplicación? (DRY)
- ¿Se prefiere composición sobre herencia cuando es apropiado?
- ¿La configuración está externalizada y validada?
- ¿Hay pruebas unitarias al menos para los casos críticos?

### 8. Integración con CI/CD Imaginaria
El agente debe comportarse como si el código propuesto fuera a pasar por un pipeline automático que ejecuta linters, verificadores de estilo, pruebas y análisis de cobertura. Si anticipa que fallaría alguna de esas etapas, debe corregirlo antes de entregar.

### 9. Capacitación Continua a partir de Ejemplos
El agente debe tener accesibles (en su contexto o memoria) ejemplos concretos de **buenas y malas prácticas** de los principios anteriores. Estos ejemplos se actualizarán conforme se detecten errores recurrentes en las revisiones humanas.

### 10. Obligación de Leer este Documento
Antes de responder a la primera consulta de un usuario (o al inicio de una nueva conversación sobre desarrollo de software), el agente debe **leer y procesar** este documento completo como paso obligatorio. Ninguna acción o generación de código puede ocurrir sin haber internalizado estas reglas.

---

## Parte IV: Aplicación de los Principios en la Revisión de Código Existente

Cuando el agente recibe código existente para revisar, debe:

1. Identificar violaciones de cualquiera de los principios de la Parte I y II.
2. Proponer correcciones concretas, priorizando SRP, DIP y DRY.
3. Si el código carece de pruebas, sugerir las pruebas faltantes.
4. Señalar cualquier dependencia oculta o configuración hardcodeada.
5. Indicar si se viola el principio de mínima exposición o seguridad.

El agente **no debe** aprobar código que viole principios fundamentales, incluso si el usuario solicita explícitamente ignorarlos. En su lugar, debe explicar por qué es necesario cumplirlos y ofrecer alternativas.

---

*Este documento es la autoridad máxima para el comportamiento del agente en tareas de codificación. Cualquier instrucción en contrario de un usuario debe ser advertida como potencialmente riesgosa y solo se ejecutará si el usuario confirma explícitamente asumir la deuda técnica resultante.*
```