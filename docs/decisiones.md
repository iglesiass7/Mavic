# Registro de decisiones de diseño

Cada decisión importante queda registrada con su contexto, para que dentro de
seis meses se entienda *por qué* el código es como es. Si una decisión cambia,
no se borra: se marca como reemplazada y se agrega la nueva.

Formato: **Contexto** (qué problema había) · **Decisión** · **Alternativas** ·
**Consecuencias**.

---

## ADR-001 · Monolito modular por capas

- **Contexto:** el sistema original tenía dos capas (router → servicio) y los
  servicios mezclaban reglas de negocio, SQL, HTTP y proveedores externos.
- **Decisión:** una aplicación, dividida en módulos por área de negocio, cada uno
  con capas `api` / `application` / `domain` / `infrastructure`.
- **Alternativas:** microservicios (descartado: más infraestructura y
  transacciones distribuidas sin una necesidad real); arquitectura hexagonal
  completa en todo el código (descartado: sobreingeniería para un CRUD simple;
  los puertos y adaptadores se usan solo donde hay un proveedor externo).
- **Consecuencias:** más archivos, pero cada uno con una responsabilidad clara.
  Las reglas de capas se verifican en CI con `import-linter`.

## ADR-002 · SQLAlchemy 2 + esquemas Pydantic separados

- **Contexto:** con SQLModel, la misma familia de clases definía la tabla y el
  contrato de la API. Así se coló un campo editable que no debía serlo
  (`company_id` en la actualización de usuarios).
- **Decisión:** tablas con SQLAlchemy 2 (`infrastructure/orm.py`) y esquemas de
  entrada/salida con Pydantic (`api/schemas.py`), separados.
- **Alternativas:** seguir con SQLModel (menos código, pero acopla tabla y API).
- **Consecuencias:** hay que mapear entre modelo y esquema; a cambio, lo que la
  API acepta es explícito y no depende de las columnas.

## ADR-003 · Errores del negocio independientes de HTTP

- **Contexto:** los servicios lanzaban `HTTPException` y algunos fallos se
  respondían como éxito (HTTP 200 con un campo `"status": "error"`).
- **Decisión:** jerarquía `AppError` con un `code` estable por tipo de error;
  un único manejador global la traduce a HTTP con el formato
  `{detail, code, request_id}`. Los errores inesperados devuelven un 500
  genérico, sin trazas ni detalles internos.
- **Consecuencias:** la lógica del negocio se puede reutilizar fuera de HTTP
  (por ejemplo, desde el procesamiento del webhook del agente de voz).

## ADR-004 · SQLAlchemy síncrono y endpoints `def`

- **Contexto:** el original declaraba endpoints `async def` que hacían trabajo
  bloqueante (consultas síncronas, lectura de Excel), lo que frena a todos los
  demás requests.
- **Decisión:** acceso a datos síncrono y endpoints `def`; FastAPI los ejecuta en
  un pool de hilos.
- **Alternativas:** SQLAlchemy asíncrono con un driver async. Descartado por
  ahora: más complejidad sin un beneficio visible con el volumen esperado.
- **Consecuencias:** `async def` queda reservado para código que realmente no
  bloquea.

## ADR-005 · Tests contra PostgreSQL real

- **Contexto:** los tests del original usaban SQLite mientras producción usaba
  PostgreSQL, y la suite completa terminó sin poder ejecutarse.
- **Decisión:** los tests que tocan la base usan PostgreSQL, en una base
  separada (`mavic_test`). CI levanta el mismo motor.
- **Consecuencias:** hay que tener la base levantada para correr esos tests; a
  cambio, prueban el comportamiento real (tipos, restricciones, bloqueos).

## ADR-006 · Todo corre localmente con Docker Compose

- **Contexto:** el objetivo es una versión demostrable, sin costos de nube.
- **Decisión:** `docker compose up` levanta base y backend. La integración con
  el agente de voz se expone con un túnel (ngrok) cuando haga falta.
- **Consecuencias:** el backend no depende de ningún proveedor de nube: es una
  imagen Docker configurada por variables de entorno, desplegable en cualquier
  plataforma si en algún momento se quiere publicar.

## ADR-007 · Orden de capas y repositorios concretos

- **Contexto:** hay que decidir cómo los casos de uso acceden a la base. La
  opción "de manual" es definir una interfaz (puerto) por repositorio y una
  implementación aparte, pero para consultas simples duplica código sin
  beneficio.
- **Decisión:** orden de capas `api → application → infrastructure → domain`.
  Los casos de uso usan repositorios concretos (clases en `infrastructure`) y
  la sesión de SQLAlchemy como unidad de trabajo. Las interfaces (`Protocol`)
  se reservan para proveedores externos intercambiables (por ejemplo, el agente
  de voz), donde sí aportan: permiten probar sin red y cambiar de proveedor.
- **Alternativas:** puertos para todo (descartado: sobreingeniería en un CRUD).
- **Consecuencias:** el dominio sigue sin depender de nada; los repositorios son
  el único lugar con consultas SQL. Las reglas se verifican con `import-linter`.

## ADR-008 · Sesiones guardadas en el servidor (no JWT)

- **Contexto:** el original usaba un JWT en una cookie con `SameSite=None`. Un
  JWT es válido hasta que vence: no se puede cerrar desde el servidor (logout,
  usuario desactivado, contraseña cambiada).
- **Decisión:** al iniciar sesión se genera un token aleatorio de 256 bits. El
  navegador lo recibe en una cookie `HttpOnly` + `SameSite=Lax`; la base guarda
  solo su hash SHA-256, con vencimiento (8 horas) y fecha de revocación. Cada
  request protegido valida la cookie contra la tabla `user_sessions`.
- **Alternativas:** JWT con lista negra (descartado: suma la complejidad de las
  dos opciones); sesiones en Redis (innecesario con una sola instancia).
- **Consecuencias:** una consulta extra por request (indexada, barata). A
  cambio, cerrar sesión, cambiar contraseña o desactivar un usuario corta el
  acceso al instante. `SameSite=Lax` protege contra CSRF.

## ADR-009 · Roles como paquetes de permisos; autorización en los casos de uso

- **Contexto:** en el original existía una tabla de roles, pero ningún endpoint
  la consultaba.
- **Decisión:** cuatro roles fijos en código (`admin`, `operator`,
  `supervisor`, `platform_admin`), cada uno con un conjunto de permisos
  (`ROLE_PERMISSIONS`). El código pregunta por permisos, nunca por roles. Cada
  caso de uso recibe un `Actor` y verifica el permiso (`actor.require(...)`);
  la empresa del actor sale de la sesión y filtra todas las consultas.
- **Alternativas:** roles editables desde la base (descartado: no hay un
  requisito que lo pida; sumaría pantallas y migraciones).
- **Consecuencias:** agregar un rol es una línea en `ROLE_PERMISSIONS`. La
  autorización vale igual desde la API, la consola o un test.

## ADR-010 · Autenticación por defecto

- **Contexto:** en el original la sesión se pedía endpoint por endpoint y quedó
  sin pedir en 62 de 71.
- **Decisión:** todos los routers se registran como protegidos salvo una lista
  pública explícita (`PUBLIC_PATHS`). Un test recorre todas las rutas de la
  documentación OpenAPI y falla si alguna no pública responde sin sesión.
- **Consecuencias:** un endpoint nuevo nace protegido; abrirlo requiere una
  decisión consciente y queda a la vista en la revisión del código.

## ADR-011 · Contraseñas con Argon2id y freno de intentos

- **Decisión:** hash Argon2id (recomendación de OWASP), política de largo mínimo
  de 10 caracteres (recomendación de NIST SP 800-63B), mismo mensaje y mismo
  tiempo de respuesta exista o no el email, y bloqueo temporal de 15 minutos
  tras 5 intentos fallidos para un mismo email.
- **Consecuencias:** el freno guarda los intentos en memoria del proceso;
  alcanza con una sola instancia. Con varias, habría que moverlo a Redis o a la
  base.
