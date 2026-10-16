# Arquitectura

Mavic es un **monolito modular**: una sola aplicación y una sola base de datos,
divididas en módulos por área de negocio. Cada módulo tiene capas internas con
reglas de dependencia estrictas.

## Capas

```text
   HTTP (frontend, agente de voz)
              │
              ▼
   ┌─────────────────────┐
   │ api                 │  rutas, esquemas, sesión, errores -> HTTP
   └──────────┬──────────┘
              ▼
   ┌─────────────────────┐   implementa puertos   ┌──────────────────────┐
   │ application         │◄───────────────────────│ infrastructure       │
   │ casos de uso        │                        │ repositorios SQL,    │
   └──────────┬──────────┘                        │ adaptadores externos │
              ▼                                   └──────────┬───────────┘
   ┌─────────────────────┐        usa el dominio             │
   │ domain              │◄──────────────────────────────────┘
   │ reglas del negocio  │
   └─────────────────────┘
```

| Capa | Responsabilidad | No puede importar |
| --- | --- | --- |
| `api` | Recibir HTTP, validar entrada, autenticar, invocar casos de uso | ORM, SDKs externos |
| `application` | Orquestar un caso de uso y su transacción | FastAPI, SDKs externos |
| `domain` | Reglas e invariantes del negocio | Nada fuera de la librería estándar |
| `infrastructure` | Base de datos, proveedores externos | `api` |

**Regla de oro:** las dependencias apuntan hacia el dominio. Se verifica
automáticamente con `import-linter` en CI (contratos en `backend/pyproject.toml`).

## Piezas transversales (`core/`)

| Pieza | Problema que resuelve |
| --- | --- |
| `config.py` | Una sola fuente de configuración, validada al arrancar |
| `db.py` | Conexión a PostgreSQL creada al armar la app, no al importar |
| `errors.py` | Errores del negocio independientes de HTTP |
| `logging.py` | Logs JSON con `request_id` y datos personales enmascarados |
| `clock.py` | “Hoy” en la zona horaria del negocio, y testeable |

## Flujo de un request

```text
request
  → RequestContextMiddleware   asigna request_id, mide duración, loguea
  → CORS
  → router del módulo          valida entrada (Pydantic)
  → caso de uso                abre transacción, aplica reglas
  → respuesta
      └─ si hay error: error_handlers lo traduce a {detail, code, request_id}
```
