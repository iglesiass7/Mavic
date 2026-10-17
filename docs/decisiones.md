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

## ADR-012 · Claves foráneas compuestas para aislar empresas

- **Contexto:** en el original se podía crear un caso de una empresa con un
  deudor de otra, y el DNI era único en todo el sistema, así que una empresa
  pisaba los datos del deudor de otra.
- **Decisión:** el deudor es único por `(company_id, document_number)`. Las
  tablas hijas apuntan a `(id, company_id)` del deudor y a `(id, debtor_id)` del
  caso, con claves foráneas compuestas.
- **Alternativas:** validar solo en el código (descartado: un bug o un script
  manual lo saltean).
- **Consecuencias:** índices únicos extra en `debtors` y `cases`. La base
  rechaza cualquier mezcla entre empresas o entre deudores.

## ADR-013 · Importación “todo o nada”, con vista previa

- **Contexto:** en el original una carga con errores dejaba la mitad de las
  filas guardadas, y no había forma de saber cuáles.
- **Decisión:** el archivo se valida completo; si hay un solo error no se guarda
  nada y se devuelven todos los errores con fila y columna (hasta 200). Existe
  `POST /imports/preview`, que hace lo mismo sin escribir. Cada carga exitosa
  queda registrada (quién, cuándo, cuántas filas).
- **Consecuencias:** el usuario corrige el archivo y lo vuelve a subir; como la
  carga es idempotente, subir dos veces el mismo archivo no duplica nada.
  Límites: 5 MB, 5000 filas, y defensa contra archivos Excel “bomba”.

## ADR-014 · Una factura en gestión no se modifica por importación

- **Decisión:** si una factura ya está en un caso y el archivo trae datos
  distintos, se rechaza la carga (`INVOICE_IN_CASE`). Si trae los mismos datos,
  se ignora.
- **Por qué:** el agente pudo haber ofrecido un plan de pago sobre ese monto;
  cambiarlo por debajo dejaría la negociación inconsistente.
- **Consecuencias:** corregir una factura en gestión será una acción explícita
  (pendiente, cuando haya un requisito real).

## ADR-015 · Un caso pendiente por deudor y bloqueo por empresa

- **Decisión:** al generar casos, las facturas vencidas sin caso se suman al
  caso **pendiente** del deudor o crean uno nuevo. Un índice único parcial
  impide dos pendientes. Importar y generar toman un bloqueo de PostgreSQL por
  empresa (`pg_advisory_xact_lock`), que se libera solo al terminar la
  transacción.
- **Por qué el bloqueo:** sin él, dos operadores que generan casos a la vez ven
  las mismas facturas libres y crean casos duplicados. El test de concurrencia
  falla 5 de 5 veces sin el bloqueo y 0 de 5 con él.
- **Consecuencias:** las cargas de una misma empresa se hacen de a una; las de
  empresas distintas no se esperan entre sí.

## ADR-016 · La plata como texto y solo en pesos

- **Decisión:** montos en `NUMERIC(14,2)` y `Decimal` en Python; la API los
  envía como texto (`"18500.50"`). Por ahora solo se acepta `ARS`.
- **Por qué:** los números de punto flotante no representan bien los
  centavos (`0.1 + 0.2 = 0.30000000000000004`); JSON solo tiene ese tipo de
  número. Y sumar deudas en monedas distintas no tiene sentido sin una regla de
  conversión que nadie pidió.
- **Consecuencias:** el frontend no debe convertir montos a número para hacer
  cuentas. Agregar otra moneda es ampliar `parse_currency` (la tabla ya
  acepta cualquier código ISO de 3 letras), con una decisión de negocio detrás.
