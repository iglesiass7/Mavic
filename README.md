# Mavic

Plataforma de gestión de cobranzas con un agente de voz con IA. Contacta a
deudores, les informa la deuda y negocia un pago (único o en cuotas) dentro de
reglas que define cada empresa.

Mavic es una versión rediseñada de **Rynx**, construida desde cero con foco en
arquitectura por capas, seguridad, consistencia de datos y testing automatizado.

> **Estado:** en construcción, por etapas. Ver [Hoja de ruta](#hoja-de-ruta).

---

## Requisitos

| Herramienta | Para qué |
| --- | --- |
| [Docker Desktop](https://docs.docker.com/desktop/) | Levantar la base de datos y el backend |
| [Git](https://git-scm.com/) | Control de versiones |
| [Python 3.12](https://www.python.org/downloads/) | *Opcional:* correr los tests fuera de Docker |

## Levantar la aplicación

```bash
docker compose up --build
```

La primera vez tarda unos minutos (descarga imágenes e instala dependencias).
Cuando veas `Iniciando servidor en el puerto 8000...`:

| URL | Qué es |
| --- | --- |
| http://localhost:8000/health | ¿Está vivo el backend? |
| http://localhost:8000/health/ready | ¿Responde la base de datos? |
| http://localhost:8000/docs | Documentación interactiva de la API (Swagger) |

Para apagar: `Ctrl + C`, y después `docker compose down`.
Para borrar también los datos y empezar de cero: `docker compose down -v`.

## Probar la app con datos de ejemplo

Con la app levantada, en **otra** terminal:

```bash
docker compose exec backend python -m mavic.cli seed-demo
```

Crea la empresa ficticia **FibraSur** y estos usuarios (contraseña de todos:
`demo-mavic-2026`):

| Email | Rol | Puede |
| --- | --- | --- |
| `dueno@mavic-demo.com` | Dueño de la plataforma | Dar de alta empresas |
| `laura@fibrasur.com` | Administradora | Todo en FibraSur, incluidos usuarios y reglas |
| `pablo@fibrasur.com` | Operador | Trabajar la cartera |
| `martin@fibrasur.com` | Supervisor | Solo mirar |

Para probar en Swagger (http://localhost:8000/docs): ejecutá **POST /auth/login**
con uno de esos usuarios. El navegador guarda la cookie de sesión y los demás
endpoints ya la usan. Probá, por ejemplo, **GET /users** con Laura (200) y con
Pablo (403).

Para crear el dueño de la plataforma real (pide la contraseña sin mostrarla):

```bash
docker compose exec backend python -m mavic.cli create-platform-admin --name "Tu nombre" --email tu@email.com
```

## Correr los tests

Los tests usan una base PostgreSQL real (`mavic_test`), que crea el mismo
`docker compose`.

**Windows (PowerShell):**

```powershell
docker compose up -d db          # solo la base, en segundo plano
cd backend
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1       # si da error de permisos, ver nota abajo
pip install -e ".[dev]"
pytest
```

> Si PowerShell no deja activar el entorno, ejecutá una vez
> `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` y volvé a intentar.

**Linux / macOS:**

```bash
docker compose up -d db
cd backend
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

### Verificaciones de calidad (las mismas que corre CI)

```bash
ruff format --check .   # formato
ruff check .            # errores y malas prácticas
mypy                    # tipado estático
lint-imports            # reglas de arquitectura entre capas
alembic check           # los modelos coinciden con las migraciones
pytest --cov=mavic      # tests con cobertura
```

## Estructura

```text
mavic/
├── backend/
│   ├── src/mavic/
│   │   ├── main.py          # arma la app (app factory)
│   │   ├── core/            # configuración, base de datos, errores, logging, reloj
│   │   ├── api/             # piezas HTTP compartidas: errores, middleware, dependencias
│   │   └── modules/         # módulos de negocio, cada uno en capas
│   ├── migrations/          # migraciones de base de datos (Alembic)
│   └── tests/               # unit/ (sin base) y api/ (endpoints)
├── docs/                    # arquitectura y registro de decisiones
├── docker-compose.yml
└── .github/workflows/ci.yml # integración continua
```

Más detalle en [docs/casos-de-uso.md](docs/casos-de-uso.md) (qué hace el
producto), [docs/arquitectura.md](docs/arquitectura.md) (cómo está armado) y
[docs/decisiones.md](docs/decisiones.md) (por qué).

## Hoja de ruta

- [x] **Paso 1 — Base:** estructura por capas, configuración, errores, logging, Docker, tests y CI.
- [x] **Paso 2 — Identidad:** usuarios, empresas, sesión, roles y aislamiento entre empresas.
- [ ] **Paso 3 — Cartera:** importación de facturas y creación de casos.
- [ ] **Paso 4 — Negociación:** reglas, ofertas de pago único y en cuotas.
- [ ] **Paso 5 — Agente de voz:** herramientas del agente de ElevenLabs y registro de resultados.
- [ ] **Paso 6 — Frontend:** aplicación web en Next.js.
