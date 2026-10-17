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

### Cargar facturas y generar casos

En la carpeta [`samples/`](samples/) hay un archivo de ejemplo en dos formatos
(`facturas-fibrasur.csv` y `facturas-fibrasur.xlsx`): 10 facturas de 5 deudores
ficticios. Los teléfonos son inventados (`+54 9 11 5555-01xx`) y los emails usan
`example.com`, un dominio reservado para ejemplos.

En Swagger, con la sesión de **Pablo** (operador):

1. **POST /imports/preview** → subí el archivo. Te dice qué haría, sin guardar nada.
2. **POST /imports** → lo carga. Si hay un solo error, no carga nada y devuelve
   la lista de errores con fila y columna.
3. **POST /cases/generate** → agrupa las facturas vencidas en un caso por deudor.
4. **GET /cases** y **GET /cases/{case_id}** → la cartera de casos.

Volver a subir el mismo archivo no duplica nada. Para armar tu propio archivo,
descargá la plantilla con **GET /imports/template**.

### Reglas de negociación y ofertas

`seed-demo` también crea las 4 reglas de ejemplo del sistema original
(si ya lo habías corrido en un paso anterior, volvé a correrlo: agrega solo lo
que falta).

1. Con **Laura** (administradora): **GET /negotiation-rules** lista las reglas.
   Probá crear una que se pise con otra (**POST /negotiation-rules**): responde
   409 `RULE_OVERLAP`, porque a cada caso le tiene que tocar una sola regla.
2. Con **Pablo** (operador), después de importar y generar casos:
   **GET /cases/{case_id}/offers** muestra qué regla le toca al caso y las dos
   ofertas: pago único con descuento y plan en cuotas.
3. Pablo y Martín pueden ver las reglas, pero no cambiarlas (403).

La regla que le toca a cada caso depende de los días de atraso, así que cambia
según la fecha en que lo pruebes.

### Agente de voz (ElevenLabs)

Mavic expone las 4 herramientas que usa el agente durante la llamada y el
webhook de fin de llamada. Para conectarlo hacen falta un token en el `.env` y
un túnel con ngrok: los pasos están en
[docs/agente-elevenlabs.md](docs/agente-elevenlabs.md).

Para ver qué pasó en una llamada: **GET /cases/{case_id}/conversations**
(identidad, ofertas presentadas, resultado, acuerdo y transcripción). Los casos
derivados a una persona se listan con **GET /cases?status=escalated**.

### Crear el dueño de la plataforma real

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
pytest --cov=mavic      # tests con cobertura (incluye los ejemplos ">>>" de los docstrings)
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
│   └── tests/               # unit/ (sin base), api/ (endpoints), integration/ (base y concurrencia)
├── docs/                    # casos de uso, arquitectura y registro de decisiones
├── samples/                 # archivos de ejemplo para importar
├── docker-compose.yml
└── .github/workflows/ci.yml # integración continua
```

Más detalle en [docs/casos-de-uso.md](docs/casos-de-uso.md) (qué hace el
producto), [docs/arquitectura.md](docs/arquitectura.md) (cómo está armado) y
[docs/decisiones.md](docs/decisiones.md) (por qué).

## Hoja de ruta

- [x] **Paso 1 — Base:** estructura por capas, configuración, errores, logging, Docker, tests y CI.
- [x] **Paso 2 — Identidad:** usuarios, empresas, sesión, roles y aislamiento entre empresas.
- [x] **Paso 3 — Cartera:** importación de facturas y creación de casos.
- [x] **Paso 4 — Negociación:** reglas, ofertas de pago único y en cuotas.
- [x] **Paso 5 — Agente de voz:** herramientas del agente de ElevenLabs y registro de resultados (probado simulando al agente; falta la prueba con el agente real).
- [ ] **Paso 6 — Frontend:** aplicación web en Next.js.
