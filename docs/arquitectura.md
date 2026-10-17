# Arquitectura

Mavic es un **monolito modular**: una sola aplicación y una sola base de datos,
divididas en módulos por área de negocio (`identity`, y después `portfolio`,
`negotiation`, `voice`...). Cada módulo tiene capas internas con reglas de
dependencia estrictas.

## Capas de un módulo

```text
   HTTP (frontend, agente de voz)
              │
              ▼
   ┌─────────────────────┐
   │ api                 │  rutas, esquemas de entrada/salida, cookies
   └──────────┬──────────┘
              ▼
   ┌─────────────────────┐
   │ application         │  casos de uso: permisos, transacción, orquestación
   └──────────┬──────────┘
              ▼
   ┌─────────────────────┐
   │ infrastructure      │  tablas (ORM), repositorios, hash, proveedores externos
   └──────────┬──────────┘
              ▼
   ┌─────────────────────┐
   │ domain              │  reglas del negocio puras (sin frameworks ni base)
   └─────────────────────┘
```

Una capa puede usar las de abajo, **nunca las de arriba**.

| Capa | Responsabilidad | No puede importar |
| --- | --- | --- |
| `api` | Recibir HTTP, validar formato, llamar al caso de uso, armar la respuesta | Repositorios, ORM, SQLAlchemy |
| `application` | Un caso de uso: verificar permisos, aplicar reglas, confirmar la transacción | FastAPI, `mavic.api` |
| `infrastructure` | Tablas, consultas, librerías técnicas (hash, proveedores externos) | `api`, `application` |
| `domain` | Reglas e invariantes del negocio | FastAPI, SQLAlchemy, Pydantic |

Estas reglas no son una recomendación: se verifican en CI con `import-linter`
(contratos en `backend/pyproject.toml`). Si alguien las rompe, el build falla.

## Dependencias entre módulos

```text
   voice ──► negotiation ──► portfolio ──► identity
   (agente)  (reglas,        (casos,       (dominio: Actor, permisos;
              ofertas)        facturas)     y el nombre de la empresa)
```

- Las flechas van en **un solo sentido**: la cartera no sabe que existe la
  negociación. Así se puede cambiar cómo se negocia sin tocar la cartera.
- Un módulo usa a otro solo por sus **casos de uso** (`application`), nunca
  leyendo sus tablas: la negociación le pide el caso a
  `portfolio.application.cases.case_detail`.
- Los casos de uso tienen dos "puertas": una para personas (verifica el
  permiso del `Actor`) y una interna que recibe la empresa explícitamente. El
  agente de voz usa la interna: no es una persona, se autentica con un token y
  su alcance es el caso de su llamada.

También lo verifica `import-linter`.

## Piezas transversales (`core/`)

| Pieza | Problema que resuelve |
| --- | --- |
| `config.py` | Una sola fuente de configuración, validada al arrancar |
| `db.py` | Conexión a PostgreSQL creada al armar la app, no al importar |
| `errors.py` | Errores del negocio independientes de HTTP |
| `logging.py` | Logs JSON con `request_id` y datos personales enmascarados |
| `clock.py` | “Hoy” en la zona horaria del negocio, y testeable |

## Flujo de un request protegido

```text
request con cookie mavic_session
  → RequestContextMiddleware     asigna request_id, mide duración, loguea
  → CORS
  → get_current_session          valida la cookie contra la tabla user_sessions
                                 (sin sesión válida: 401, y el endpoint ni se ejecuta)
  → endpoint (api)               valida el formato de la entrada (Pydantic)
  → caso de uso (application)    actor.require(permiso), filtra por la empresa del actor,
                                 aplica reglas, session.commit()
  → respuesta
      └─ si hay error: error_handlers lo traduce a {detail, code, request_id}
```

## Tres formas de entrar a la API

| Grupo | Rutas | Cómo se autentica |
| --- | --- | --- |
| Público | `/health`, `/auth/login`, `/auth/logout` | No hace falta |
| Agente | `/agent/tools/...`, `/webhooks/elevenlabs` | Token secreto (`Authorization: Bearer`) o firma HMAC del mensaje |
| Protegido | Todo lo demás | Cookie de sesión de una persona |

El test de protección de rutas recorre todas y verifica que, sin credenciales,
solo respondan las públicas.

## Seguridad de acceso

| Mecanismo | Dónde | Qué evita |
| --- | --- | --- |
| Autenticación por defecto | `api/router.py` | Endpoints abiertos por olvido (test que recorre todas las rutas) |
| Sesión en el servidor | `identity/application/auth.py` | Sesiones que no se pueden cerrar (logout, desactivar usuario) |
| Permisos por rol | `identity/domain/roles.py` | Que un operador cambie reglas o usuarios |
| Empresa desde la sesión | `Actor.require_company()` | Que una empresa vea datos de otra |
| Freno de intentos de login | `identity/api/login_throttle.py` | Fuerza bruta de contraseñas |

## Integridad de los datos

Las reglas más importantes no dependen solo del código: las garantiza
PostgreSQL, así un bug no puede romperlas.

| Regla | Cómo se garantiza | Test |
| --- | --- | --- |
| Un caso solo tiene deudores de su empresa | Clave foránea compuesta `(debtor_id, company_id)` | `integration/test_portfolio_integrity.py` |
| Una factura solo va a un caso de su mismo deudor | Clave foránea compuesta `(case_id, debtor_id)` | ídem |
| Un deudor tiene como máximo un caso pendiente | Índice único parcial (`WHERE status = 'pending'`) | ídem |
| Montos positivos y con 2 decimales exactos | `NUMERIC(14,2)` + `CHECK (amount > 0)` | ídem |
| Dos cargas o generaciones simultáneas no se pisan | Bloqueo por empresa (`pg_advisory_xact_lock`) | ídem (concurrencia) |
| Una sola regla activa por caso | Validación al guardar + bloqueo por empresa (`pg_advisory_xact_lock`) | `integration/test_rules_concurrency.py` |
| Descuentos, interés, cuotas y plazos dentro de rango | Validación en el dominio + `CHECK` en la tabla | `unit/test_negotiation_rules.py` |
| Una llamada no salta de un caso a otro | `conversation_id` único + comparación al usar cada herramienta | `api/test_agent_tools.py` |
| Un acuerdo por llamada, aunque el proveedor reintente | Bloqueo de la conversación (`SELECT ... FOR UPDATE`) + `UNIQUE (conversation_id)` | `integration/test_agent_concurrency.py` |
| Llamadas y acuerdos solo de casos de su empresa | Claves foráneas compuestas `(case_id, company_id)` | — |
