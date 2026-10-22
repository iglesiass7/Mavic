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
| [Docker Desktop](https://docs.docker.com/desktop/) | Levantar la base de datos, el backend y la web |
| [Git](https://git-scm.com/) | Control de versiones |
| [Python 3.12](https://www.python.org/downloads/) | *Opcional:* correr los tests del backend fuera de Docker |
| [Node.js 22](https://nodejs.org/) | *Opcional:* trabajar en el frontend fuera de Docker |

## Levantar la aplicación

```bash
docker compose up --build
```

La primera vez tarda unos minutos (descarga imágenes e instala dependencias).
Cuando veas `Iniciando servidor en el puerto 8000...`:

| URL | Qué es |
| --- | --- |
| **http://localhost:3000** | **La aplicación web** (lo que usa la empresa) |
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

Entrá a **http://localhost:3000** con cualquiera de ellos. **Inicio** es el
tablero: deuda en gestión, cartera por estado y por antigüedad, y cómo terminaron
las llamadas del agente, todo calculado con los datos reales. En **Casos** está la
cartera; al abrir un caso se ve la deuda, las facturas, **lo que el agente
puede ofrecer hoy** (según las reglas) y las llamadas que ya hizo. Los casos
aparecen después de cargar facturas (ver abajo).

Para probar en Swagger (http://localhost:8000/docs): ejecutá **POST /auth/login**
con uno de esos usuarios. El navegador guarda la cookie de sesión y los demás
endpoints ya la usan. Probá, por ejemplo, **GET /users** con Laura (200) y con
Pablo (403).

### Cargar facturas y generar casos

En la carpeta [`samples/`](samples/) hay un archivo de ejemplo en dos formatos
(`facturas-fibrasur.csv` y `facturas-fibrasur.xlsx`): 10 facturas de 5 deudores
ficticios. Los teléfonos son inventados (`+54 9 11 5555-01xx`) y los emails usan
`example.com`, un dominio reservado para ejemplos.

En http://localhost:3000, con **Pablo** (operador) o **Laura** (administradora):

1. **Cargar facturas** → elegí el archivo. Mavic revisa cada fila y te muestra
   qué va a guardar, **sin guardar nada todavía**. Si hay errores, los lista con
   fila y columna, y no deja cargar hasta corregirlos.
2. **Cargar N facturas** → las guarda.
3. **Generar casos** → agrupa las facturas vencidas en un caso por deudor. Si el
   deudor ya tenía un caso pendiente, se suman a ese.
4. **Casos** → la cartera, con lo que el agente puede ofrecer en cada uno.

Volver a subir el mismo archivo no duplica nada. Para armar tu propio archivo,
en la pantalla de carga está **"¿Qué columnas tiene que tener?"** y la plantilla
para descargar. Martín (supervisor) ve las facturas y el historial de cargas,
pero no puede cargar ni generar casos.

> Lo mismo se puede hacer desde Swagger (http://localhost:8000/docs):
> **POST /imports/preview**, **POST /imports** y **POST /cases/generate**.

### Reglas de negociación y ofertas

`seed-demo` también crea las 4 reglas de ejemplo del sistema original
(si ya lo habías corrido en un paso anterior, volvé a correrlo: agrega solo lo
que falta).

1. Con **Laura** (administradora), en **Reglas**: cada regla se lee en palabras
   ("Deuda: hasta $ 500.000 · Atraso: de 15 a 59 días…"). Probá **Nueva regla**
   con un atraso de 10 a 20 días: Mavic no la deja activar porque se pisa con
   otra, ya que a cada caso le tiene que tocar una sola regla.
2. En **Casos**, cada caso muestra qué regla le toca y lo que el agente puede
   ofrecer: pago único con descuento y plan en cuotas.
3. Pablo y Martín pueden ver las reglas, pero no cambiarlas.

Los números se escriben como en Argentina (`500.000`, `12,5`); también se
aceptan `500000` y `12.5`. La regla que le toca a cada caso depende de los días
de atraso, así que cambia según la fecha en que lo pruebes.

### Usuarios y contraseña

- **Usuarios** (solo administración): alta con una contraseña inicial generada
  al azar, cambio de rol y desactivar. Al desactivar a alguien se cierran sus
  sesiones en el momento. Mavic no deja a la empresa sin nadie de administración.
- **Mi cuenta** (todos, abajo en el menú): cambiar la contraseña. Al cambiarla
  se cierra la sesión en las otras computadoras o navegadores.
- **Empresas** (solo `dueno@mavic-demo.com`): dar de alta una empresa nueva con
  su primera persona de administración.

### Agente de voz (ElevenLabs)

Dos formas de trabajar con el agente, que conviven:

- **Agente nuevo "Gestión de Deuda":** el botón **Llamar al deudor** del caso
  (`POST /cases/{id}/calls`) le pide a ElevenLabs que llame por teléfono, con el
  caso, las deudas y las ofertas ya cargados. El resultado llega en el webhook de
  fin de llamada (ADR-034). Necesita `ELEVENLABS_API_KEY`, `ELEVENLABS_AGENT_ID` y
  `ELEVENLABS_PHONE_NUMBER_ID` en el `.env`.
- **Agente anterior:** 4 herramientas que el agente usa durante la llamada.
  Necesita `AGENT_TOOLS_TOKEN`.

En los dos casos, el webhook necesita `ELEVENLABS_WEBHOOK_SECRET` y, en tu PC, un
túnel con ngrok. Los pasos están en [docs/agente-elevenlabs.md](docs/agente-elevenlabs.md).

Para ver qué pasó en una llamada: **GET /cases/{case_id}/conversations**
(identidad, ofertas presentadas, resultado, acuerdo y transcripción). Los casos
derivados a una persona se listan con **GET /cases?status=escalated**.

Para probar las herramientas desde Swagger, usá el botón **Authorize** con el
token del agente. Para volver a probar un caso que ya tuvo resultado:

```bash
docker compose exec backend python -m mavic.cli reopen-case --number 1
```

### Crear el dueño de la plataforma real

Para crear el dueño de la plataforma real (pide la contraseña sin mostrarla):

```bash
docker compose exec backend python -m mavic.cli create-platform-admin --name "Tu nombre" --email tu@email.com
```

### Publicar en AWS

Qué hace falta además del código (base de datos, secretos, HTTPS, primer
usuario y la conexión del agente) en
[docs/despliegue-aws.md](docs/despliegue-aws.md).

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

### Frontend fuera de Docker (opcional)

Para ver los cambios al instante mientras se edita el frontend:

```bash
docker compose up -d db backend   # solo la base y el backend (el puerto 3000 queda libre)
cd frontend
npm ci          # la primera vez
npm run dev     # http://localhost:3000, se actualiza solo al guardar
npm run check   # lint + tipado + tests (lo mismo que CI, menos la compilación)
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
├── frontend/                # aplicación web (Next.js): src/app = pantallas, src/lib = sin React
├── docs/                    # casos de uso, arquitectura, decisiones, agente y despliegue
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
- [x] **Paso 5 — Agente de voz:** herramientas del agente de ElevenLabs y registro de resultados (probado con el agente real de ElevenLabs).
- [x] **Paso 6 — Frontend:** aplicación web en Next.js.
  - [x] 6a — Base, login, menú según el rol, lista y detalle de casos (ofertas y llamadas del agente).
  - [x] 6b — Carga de facturas (con revisión previa), lista de facturas y generación de casos.
  - [x] 6c — Reglas de negociación, usuarios, cambio de contraseña y empresas.
  - [x] 6d — Tablero con números reales (`GET /dashboard`).
- [ ] **Paso 7 — Versión para el equipo:**
  - [x] 7a — Agente nuevo: llamada saliente con variables dinámicas, webhook con resultado y moneda por caso (ADR-034).
  - [ ] 7b — Frontend con el diseño de Rynx.
  - [ ] 7c — Funciones de Rynx: avisos por email y WhatsApp, seguimiento de pagos, auditoría y costos.
