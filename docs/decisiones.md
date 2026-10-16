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
