# Publicar Mavic en AWS

Guía para quien sube Mavic a una cuenta de AWS. Explica **qué hace falta además
del código**, qué valores configurar y cómo comprobar que quedó andando.

> **Qué está probado y qué no.** Todo lo que dice "probado" se comprobó en una
> PC con la configuración de producción (`APP_ENV=production`, cookie `Secure`,
> Swagger apagado) y con el frontend reenviando al backend, igual que en AWS.
> **Mavic todavía no corrió en AWS.** Por eso conviene empezar por un ambiente
> de prueba (DEV) y pasar a producción recién cuando la lista de la sección 8
> dé todo OK.

---

## 1. Qué se publica

No alcanza con el frontend y el backend: son el programa, pero necesitan una
base de datos, sus secretos, HTTPS y el primer usuario.

```text
                          internet (solo HTTPS)
  Navegador ──────┐
  Agente de       ├──► [ Balanceador + certificado HTTPS ]
  ElevenLabs ─────┘                  │
                                     ▼
                        [ frontend: contenedor Next.js :3000 ]   ← lo único público
                                     │  /api/*  (red interna)
                                     ▼
                        [ backend: contenedor FastAPI :8000 ]    ← privado
                                     │
                                     ▼
                        [ PostgreSQL 16 (RDS) ]                  ← privado

  [ Secrets Manager ] ── contraseñas y tokens ──► backend
```

| Pieza | Qué es | De dónde sale |
| --- | --- | --- |
| frontend | Contenedor de Next.js | `frontend/Dockerfile` |
| backend | Contenedor de FastAPI | `backend/Dockerfile` |
| Base de datos | PostgreSQL 16 | Se crea en RDS (no está en el repo) |
| Secretos | Contraseña de la base y tokens del agente | Se cargan en Secrets Manager (nunca en el repo) |
| Dominio y HTTPS | Dirección pública con certificado | Dominio de la empresa + certificado de ACM |

**Solo el frontend es público.** El navegador y el agente hablan únicamente con
él. Todo lo que empieza con `/api/` lo reenvía al backend por la red interna
(ADR-026). Así el backend y la base quedan sin acceso desde internet.

---

## 2. La base de datos

- **PostgreSQL 16** (la misma versión que en `docker-compose.yml`).
- **Privada:** que solo la alcance el backend.
- Una base vacía alcanza. **Las tablas no se crean a mano:** el backend corre
  las migraciones (`alembic upgrade head`) cada vez que arranca
  (`backend/docker/entrypoint.sh`). Si una migración falla, el backend no
  arranca, a propósito: nunca queda funcionando con tablas a medias.
- No hace falta la base `mavic_test` ni el script de
  `backend/docker/postgres-init/`: son solo para los tests en la PC.
- Activar los backups automáticos de RDS.

---

## 3. Configuración del backend

El backend lee todo de variables de entorno y **revisa la configuración al
arrancar**: si falta algo obligatorio o tiene un formato inválido, no levanta y
lo dice en el log (`backend/src/mavic/core/config.py`).

| Variable | Valor en AWS | Dónde va |
| --- | --- | --- |
| `APP_ENV` | `production` | Variable común |
| `DATABASE_URL` | `postgresql+psycopg://<usuario>:<clave>@<host-de-RDS>:5432/<base>` | **Secrets Manager** |
| `SESSION_COOKIE_SECURE` | `true` | Variable común |
| `DOCS_ENABLED` | `false` | Variable común |
| `AGENT_TOOLS_TOKEN` | Uno **nuevo**, no el que se usó en la PC (mínimo 32 caracteres) | **Secrets Manager** |
| `ELEVENLABS_WEBHOOK_SECRET` | El que muestra ElevenLabs al crear el webhook | **Secrets Manager** |
| `ELEVENLABS_API_KEY` | Clave de la API de ElevenLabs (botón "Llamar") | **Secrets Manager** |
| `ELEVENLABS_AGENT_ID` | Id del agente "Gestión de Deuda" | Variable común |
| `ELEVENLABS_PHONE_NUMBER_ID` | Id del número de Twilio vinculado al agente | Variable común |
| `ELEVENLABS_BRANCH_ID` | Rama del agente (vacío en producción: la publicada) | Variable común |
| `CORS_ALLOWED_ORIGINS` | `https://<dominio>` | Variable común |
| `LOG_LEVEL` | `INFO` | Variable común |

Qué hace cada una en producción (probado):

- `APP_ENV=production` bloquea los comandos de prueba (`seed-demo` y
  `reopen-case` responden "solo se puede usar con APP_ENV=local").
- `SESSION_COOKIE_SECURE=true` hace que la cookie de sesión viaje solo por
  HTTPS. **Sin HTTPS el login no funciona.**
- `DOCS_ENABLED=false` apaga Swagger: `/docs` responde 404.

Para generar el token del agente:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Las variables que no estén en la tabla tienen valores por defecto razonables
(duración de la sesión, freno de intentos de login). Están en
`backend/.env.example`.

---

## 4. Las imágenes

### Backend

```bash
docker build -t mavic-backend ./backend
```

### Frontend: necesita saber dónde está el backend

El servidor de Next reenvía `/api/*` a la dirección de `API_INTERNAL_URL`. Esa
dirección **se fija al construir la imagen**: si cambia, hay que construir la
imagen de nuevo.

```bash
docker build -t mavic-frontend \
  --build-arg API_INTERNAL_URL=http://<dirección-interna-del-backend>:8000 \
  ./frontend
```

`<dirección-interna-del-backend>` es el nombre con el que el frontend encuentra
al backend dentro de la red de AWS. Con ECS, por ejemplo, el nombre que da
Service Connect o Cloud Map, o un balanceador interno. Va sin barra al final y
sin `/api`.

Las dos imágenes se suben a ECR (el registro de imágenes de AWS).

---

## 5. Correr los contenedores (por ejemplo, ECS Fargate)

| | frontend | backend |
| --- | --- | --- |
| Puerto | 3000 | 8000 |
| Público | Sí, detrás del balanceador | No |
| Copias | Las que hagan falta | **1** (ver abajo) |
| Chequeo de salud | `GET /login` → 200 | `GET /health` → 200 (está vivo) · `GET /health/ready` → 200 (además llega a la base) |

**El backend arranca con una sola copia.** Dos motivos:

1. El freno de intentos fallidos de login se guarda en la memoria del proceso.
   Con dos copias, cada una cuenta por su lado. Para tener varias copias, ese
   freno tiene que pasar a un lugar compartido (por ejemplo, Redis). Está
   anotado como pendiente.
2. Cada copia corre las migraciones al arrancar. Con una sola copia no hay dos
   migraciones a la vez.

**Chequeo de salud dentro del contenedor del backend.** La imagen no trae
`curl`. Si ECS lo pide, se puede usar Python:

```bash
python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"
```

Los logs de los dos contenedores salen por la salida estándar: con ECS se
mandan a CloudWatch Logs.

---

## 6. Dominio, HTTPS y balanceador

- Un dominio o subdominio de la empresa, con su certificado de **ACM** (gratis).
- El balanceador escucha en 443 (HTTPS) y manda **todo** al frontend.
- HTTP (80) redirige a HTTPS.
- El backend no necesita reglas en el balanceador: el frontend le llega por la
  red interna.

---

## 7. El primer usuario

En producción no hay usuarios de ejemplo: `seed-demo` está bloqueado. La
primera vez se crea al **dueño de la plataforma**, una sola vez, dentro del
contenedor del backend:

```bash
python -m mavic.cli create-platform-admin --name "<nombre>" --email <email>
```

Pide la contraseña dos veces (mínimo 10 caracteres) y no la muestra en
pantalla, por eso hace falta una consola interactiva. Con ECS se puede usar
**ECS Exec** (`aws ecs execute-command --interactive ...`), que hay que
habilitar en el servicio del backend.

Después, desde la app:

1. Entrar con ese usuario → **Empresas** → crear la empresa con su primera
   persona de administración.
2. Esa persona entra, carga las reglas de negociación y las facturas.

---

## 8. Conectar el agente de ElevenLabs

Las direcciones de ngrok se cambian por el dominio, **con `/api` adelante**:

| Qué | Dirección |
| --- | --- |
| `obtener_contexto_del_caso_v2` | `https://<dominio>/api/agent/tools/obtener_contexto_del_caso_v2` |
| `obtener_oferta_pago_unico_v2` | `https://<dominio>/api/agent/tools/obtener_oferta_pago_unico_v2` |
| `obtener_oferta_cuotas_v2` | `https://<dominio>/api/agent/tools/obtener_oferta_cuotas_v2` |
| `registrar_resultado_v2` | `https://<dominio>/api/agent/tools/registrar_resultado_v2` |
| Webhook de fin de llamada | `https://<dominio>/api/webhooks/elevenlabs` |

- El encabezado `Authorization: Bearer <token>` lleva el `AGENT_TOOLS_TOKEN`
  **nuevo** (sección 3).
- Al crear el webhook en ElevenLabs, el secreto que muestra va en
  `ELEVENLABS_WEBHOOK_SECRET`.

**Probado:** a través del frontend llegan bien el token (sin token: 401; con
token: 200), las 4 herramientas (por POST y por GET) y el webhook con su firma
(firma mala: 401; firma buena: se guardan la transcripción, el resumen y la
duración). El caso cambió de "Pendiente" a "Contactado".

El detalle de cada herramienta está en [agente-elevenlabs.md](agente-elevenlabs.md).

---

## 9. Lista para dar por terminado

Hacerla primero en DEV y después en producción.

- [ ] `https://<dominio>/login` abre la pantalla de ingreso
- [ ] `https://<dominio>/api/health/ready` responde `{"status":"ready"}`
- [ ] `https://<dominio>/api/docs` responde 404 (Swagger apagado)
- [ ] Se puede entrar con el dueño de la plataforma y crear una empresa
- [ ] La administración de la empresa carga facturas y genera casos
- [ ] Una llamada de prueba del agente pasa el caso a "Contactado" (o al resultado que corresponda)
- [ ] En la pantalla del caso aparecen la duración, el resumen y "Ver la conversación"
- [ ] Al reiniciar el backend, vuelve a levantar solo (las migraciones no fallan)

---

## 10. Cuidados

| Tema | Qué hacer |
| --- | --- |
| **El repo es público** | Nunca subir `.env`, claves de AWS ni tokens. Para que GitHub publique en AWS sin guardar claves, usar OIDC (un rol de AWS que GitHub puede asumir) |
| **Tokens de la PC** | No reutilizar en AWS el `AGENT_TOOLS_TOKEN` de las pruebas con ngrok |
| **Cambiar el token** | Se cambia en Secrets Manager, se reinicia el backend y se actualiza en las 4 herramientas del agente |
| **Cambiar la dirección del backend** | Hay que construir de nuevo la imagen del frontend (`API_INTERNAL_URL`) |
| **Costos** | Todavía no están calculados: dependen de los tamaños elegidos y de los minutos de llamada de ElevenLabs. Conviene poner una alarma de costos en la cuenta |

---

## 11. Reutilizar la infraestructura de Rynx

La carpeta `infra/` del repositorio de Rynx tiene en Terraform casi todo esto
(red, RDS, ECR, ECS, balanceador interno, CloudFront, WAF, Secrets Manager,
acceso de GitHub por OIDC, alarmas de costos) y los workflows de deploy. Se
puede usar como base en la cuenta nueva. Diferencias a tener en cuenta:

| En Rynx | En Mavic |
| --- | --- |
| Frontend como sitio estático en S3 + CloudFront | Frontend como **contenedor**, igual que el backend (necesita servidor de Node para reenviar `/api`) |
| Nombres de variables de Rynx (Twilio, mail, etc.) | Las variables de la sección 3 |
| El backend recibía a Twilio y ElevenLabs directamente | El agente entra por el frontend, con `/api` adelante (sección 8) |
