# Conectar el agente de ElevenLabs con Mavic

Hay dos formas de trabajar con el agente, y Mavic acepta las dos a la vez:

| | Agente nuevo "Gestión de Deuda" (ADR-034) | Agente anterior (herramientas) |
| --- | --- | --- |
| Quién inicia la llamada | Mavic, con el botón "Llamar" (`POST /cases/{id}/calls`) | Se prueba desde la consola de ElevenLabs |
| Qué recibe el agente | Todo al empezar: 8 variables dinámicas | Lo pide durante la llamada con 4 herramientas |
| Cómo llega el resultado | En el webhook de fin de llamada | Con la herramienta `registrar_resultado_v2` |
| Lo que hay que configurar | Sección "Agente nuevo" (abajo) | Partes 1 y 2 |

---

## Agente nuevo: llamadas salientes

```text
 Mavic ──① POST /cases/{id}/calls──► ElevenLabs ──② Twilio──► teléfono del deudor
   ▲        (8 variables + rama)          │
   └────────────③ webhook de fin de llamada (transcripción + resultado)
```

### En la PC que corre Mavic (`.env`)

| Variable | Qué es | Secreta |
| --- | --- | --- |
| `ELEVENLABS_API_KEY` | Clave de la API del workspace de ElevenLabs | **Sí** |
| `ELEVENLABS_AGENT_ID` | Id del agente "Gestión de Deuda" | No |
| `ELEVENLABS_PHONE_NUMBER_ID` | Id del número de Twilio vinculado al agente en ElevenLabs | No |
| `ELEVENLABS_BRANCH_ID` | Rama del agente para las pruebas (vacío: la publicada) | No |
| `ELEVENLABS_WEBHOOK_SECRET` | Secreto del webhook de fin de llamada | **Sí** |

Sin las tres primeras, el botón responde **503** `CALLS_DISABLED`. Después de
editar el `.env`, reiniciar Mavic (`docker compose down` y `docker compose up --build`).

### En ElevenLabs (quien configura el agente)

1. **Webhook de fin de llamada** apuntando a `https://<dirección de ngrok>/webhooks/elevenlabs`
   (o `https://<dominio>/api/webhooks/elevenlabs` en AWS), con transcripción.
2. **Datos a recolectar** (Analysis → Data collection) con estos nombres exactos:
   - `resultado`: `CONTACTADO`, `ACUERDO`, `DESCONOCIMIENTO` o `DERIVACION_HUMANA`
   - `oferta_id`: el id de la oferta aceptada (solo si hubo acuerdo)
3. El agente usa las variables `caso_id`, `nombre`, `nombre_acreedor`,
   `cantidad_deudas`, `monto_total`, `moneda_total`, `deudas` y `ofertas`. Mavic
   manda exactamente esas: `deudas` y `ofertas` como texto JSON.

### Probar

1. En Mavic, abrir un caso **pendiente** que tenga una regla (si no, responde
   409 `NO_MATCHING_RULE`) y tocar "Llamar". En Swagger: `POST /cases/{case_id}/calls`.
2. La llamada aparece en el caso con estado **INITIATED**. Cuando termina y llega
   el webhook, pasa a **DONE** y el caso cambia de estado.

### Estados de una llamada

| Estado | Qué significa |
| --- | --- |
| `INITIATING` | Mavic la registró y le está pidiendo la llamada a ElevenLabs |
| `INITIATED` | ElevenLabs la aceptó; falta el webhook |
| `DONE` | Llegó el webhook y se aplicó el resultado |
| `FAILED` | No se pudo iniciar (el motivo se ve en el caso) |
| `NEEDS_REVIEW` | Llegó el webhook pero el resultado no se pudo aplicar solo |

Motivos de `NEEDS_REVIEW` (el caso **no** cambia y no se crea acuerdo):

| Motivo | Qué pasó |
| --- | --- |
| `SIN_RESULTADO` | El análisis no trajo `resultado` |
| `RESULTADO_INVALIDO` | `resultado` no es uno de los cuatro |
| `ACUERDO_SIN_OFERTA` | `ACUERDO` sin `oferta_id` |
| `OFERTA_DESCONOCIDA` | `oferta_id` no es una de las ofertas que Mavic le mandó al agente |
| `ACUERDO_SIN_FOTO` | La llamada no la inició Mavic (por ejemplo, una prueba desde la consola): no hay ofertas con qué validar |
| `CASO_NO_NEGOCIABLE` | El caso ya tenía un resultado de otra llamada |

**Pruebas desde la consola de ElevenLabs:** si se cargan las variables a mano
(con `caso_id` = número de caso), Mavic igual encuentra el caso al llegar el
webhook y guarda la llamada con origen `EXTERNAL`. Los resultados se aplican,
salvo `ACUERDO`, que va a revisión porque no hay foto de ofertas.

---

## Agente anterior: herramientas durante la llamada

Esta parte tiene dos secciones:

1. **Para quien corre Mavic** (en su PC): token, `.env` y ngrok.
2. **Para quien configura el agente** (en ElevenLabs): las 4 herramientas y el webhook.

```text
  ElevenLabs (agente)                         Tu PC
 ┌──────────────────────┐   internet   ┌───────────┐      ┌──────────────────┐
 │ herramientas         │ ───────────► │  ngrok    │ ───► │ Mavic            │
 │ webhook fin llamada  │   (HTTPS)    │  (túnel)  │      │ localhost:8000   │
 └──────────────────────┘              └───────────┘      └──────────────────┘
```

ElevenLabs está en internet y Mavic en tu PC. **ngrok** abre un túnel: le da a
tu PC una dirección pública (`https://algo.ngrok-free.app`) que llega a
`localhost:8000`.

---

## Parte 1 · En la PC que corre Mavic

### 1. Generar el token del agente

Es la "contraseña" que el agente manda en cada herramienta. En PowerShell:

```powershell
py -3.12 -c "import secrets; print(secrets.token_urlsafe(32))"
```

Copiá el resultado. **No lo subas a git ni lo pegues en un chat público.**
Pasáselo a quien configura el agente por un canal privado.

### 2. Crear el archivo `.env`

En la carpeta de Mavic (la que tiene `docker-compose.yml`):

```powershell
Copy-Item .env.example .env
notepad .env
```

Completá la línea del token:

```text
AGENT_TOOLS_TOKEN=el-token-que-generaste
ELEVENLABS_WEBHOOK_SECRET=
```

El segundo valor lo da ElevenLabs al crear el webhook (Parte 2, paso 3). Cuando
lo tengas, completalo también. `.env` está en `.gitignore`: nunca se sube.

Después reiniciá Mavic para que lea el `.env`:

```powershell
docker compose down
docker compose up --build
```

Si el token falta, las herramientas responden **503** con el mensaje
`falta AGENT_TOOLS_TOKEN`.

### 3. Abrir el túnel con ngrok

Una sola vez:

1. Creá una cuenta gratis en [ngrok.com](https://ngrok.com) y copiá tu
   *authtoken* del panel.
2. Instalá ngrok y guardá el authtoken:

   ```powershell
   winget install ngrok -s msstore
   ngrok config add-authtoken "TU_AUTHTOKEN_DE_NGROK"
   ```

Cada vez que quieras probar con el agente (con Mavic ya levantado):

```powershell
ngrok http 8000
```

ngrok muestra una línea `Forwarding https://xxxx.ngrok-free.app -> http://localhost:8000`.
Esa dirección `https://...` es la que va en las herramientas.

> La dirección puede cambiar cada vez que reiniciás ngrok. Si cambia, hay que
> actualizarla en las herramientas del agente.

### 4. Probar el token antes de abrir ngrok

En Swagger (http://localhost:8000/docs):

1. Botón **Authorize** (candado, arriba a la derecha) → en **AgentToken** pegá
   el token, **solo el token, sin "Bearer"** → **Authorize** → **Close**.
2. Abrí **GET /agent/tools/obtener_contexto_del_caso_v2** → **Try it out**.
3. Completá `caso_id` (un número de caso), `conversation_id` (cualquier texto),
   `nombre_consultado` (el nombre del deudor) y `respuesta` (`si`) → **Execute**.

Con `200` y `"identidad_verificada": true`, el token y Mavic andan bien.

> No sirve escribir el token en un campo "authorization" común: Swagger ignora
> a propósito los campos con ese nombre. Hay que usar el botón **Authorize**.

### 5. Elegir el caso para probar

Sin telefonía, el agente se prueba desde ElevenLabs escribiendo el **número de
caso** (`caso_id`). Lo ves en Swagger, en **GET /cases** (campo `number`). Por
ejemplo, `2`. También acepta formatos con prefijo, como `CASO-2`.

El caso tiene que estar en estado `pending` o `contacted`. Si en una prueba
anterior el agente registró un acuerdo, un desconocimiento o una derivación, el
caso ya no se negocia (las ofertas vuelven con `motivo: CASO_NO_NEGOCIABLE`).
Para probarlo otra vez, reabrilo:

```powershell
docker compose exec backend python -m mavic.cli reopen-case --number 1
```

Solo funciona en tu PC (`APP_ENV=local`). Las llamadas y acuerdos anteriores
quedan guardados como historial.

---

## Parte 2 · En ElevenLabs (quien configura el agente)

### 1. Encabezado de autenticación (en las 4 herramientas)

En cada herramienta, en **Headers**:

| Nombre | Tipo | Valor |
| --- | --- | --- |
| `Authorization` | **Secret** | `Bearer <token que te pasaron>` |

Sin este encabezado, Mavic responde **401**.

### 2. Las cuatro herramientas

Para todas:

- **URL:** `https://<dirección de ngrok>/agent/tools/<nombre de la herramienta>`
- **Método:** `POST` con los parámetros en el **body**, o `GET` con los
  parámetros como **query**. Mavic acepta las dos formas.
- `conversation_id`: el id de la conversación de ElevenLabs (la variable de
  sistema `system__conversation_id`). Tiene que ser el mismo en todas las
  herramientas de una llamada: así Mavic sabe que es la misma llamada.

#### `obtener_contexto_del_caso_v2`

URL: `.../agent/tools/obtener_contexto_del_caso_v2`

| Parámetro | Tipo | Qué es |
| --- | --- | --- |
| `caso_id` | texto | Número de caso |
| `conversation_id` | texto | Id de la conversación |
| `nombre_consultado` | texto | Nombre por el que preguntó el agente ("¿hablo con …?") |
| `respuesta` | texto o booleano | Lo que contestó la persona ("sí", "no", `true`…) |

La identidad queda verificada si el nombre consultado coincide con el del
deudor **y** la respuesta es afirmativa. Si no se verifica,
`datos_comunicables` viene en `null`: no se da ningún dato de la deuda.

**Cómo configurar `respuesta` en ElevenLabs:** que lo complete el modelo (LLM
Prompt), con una descripción como *"Enviar solamente `si` si la persona confirmó
que es el titular, o `no` si dijo que no"*. Mavic también entiende frases
completas ("Buenos días, sí, soy Ricardo Pérez") y, por la primera prueba real,
el formato con historial (`x-elevenlabs-history`). Pero si en la frase aparece
un "no", no se verifica: ante la duda, se protegen los datos.

```json
{
  "caso_id": "2",
  "nombre": "Ricardo Pérez",
  "identidad_verificada": true,
  "pago_unico_ofrecido": false,
  "cuotas_ofrecidas": false,
  "ofertas_restantes": 2,
  "datos_comunicables": {
    "nombre_acreedor": "FibraSur",
    "contexto_deuda": "Abono internet agosto, Abono internet septiembre, Abono internet octubre",
    "monto_original": 56900,
    "moneda": "ARS",
    "fecha_vencimiento_original": "2026-08-10"
  }
}
```

#### `obtener_oferta_pago_unico_v2`

URL: `.../agent/tools/obtener_oferta_pago_unico_v2` · Parámetros: `caso_id`, `conversation_id`.

```json
{
  "has_offer": true,
  "pago_unico_ofrecido": true,
  "ofertas_restantes": 1,
  "oferta_id": "PAGO-UNICO",
  "modalidad": "PAGO_UNICO",
  "moneda": "ARS",
  "importe_original": 56900,
  "descuento_porcentaje": 10,
  "descuento": 5690,
  "importe_total": 51210,
  "fecha_limite_pago": "2026-10-22",
  "motivo": null
}
```

#### `obtener_oferta_cuotas_v2`

URL: `.../agent/tools/obtener_oferta_cuotas_v2` · Parámetros: `caso_id`, `conversation_id`.

```json
{
  "has_offer": true,
  "cuotas_ofrecidas": true,
  "ofertas_restantes": 0,
  "oferta_id": "CUOTAS-6-CON-INTERES",
  "modalidad": "CUOTAS",
  "moneda": "ARS",
  "importe_total": 63728,
  "cantidad_cuotas": 6,
  "importe_por_cuota": 10621.33,
  "importe_ultima_cuota": 10621.35,
  "interes_porcentaje": 12,
  "fecha_primera_cuota": "2026-10-22",
  "motivo": null
}
```

La última cuota puede tener unos centavos más, para que la suma dé exacta.

#### `registrar_resultado_v2`

URL: `.../agent/tools/registrar_resultado_v2`

| Parámetro | Tipo | Qué es |
| --- | --- | --- |
| `caso_id` | texto | Número de caso |
| `conversation_id` | texto | Id de la conversación |
| `resultado` | texto | `CONTACTADO`, `DESCONOCIMIENTO`, `ACUERDO` o `DERIVACION_HUMANA` |
| `oferta_id` | texto (opcional) | La oferta aceptada, solo si `resultado` es `ACUERDO` |
| `confirmacion_final` | booleano | `true` si la persona confirmó al final |
| `cantidad_desconocimientos` | número | Cuántas veces dijo no reconocer la deuda (0 si ninguna) |

```json
{ "registrado": true, "resultado": "ACUERDO", "oferta_id": "PAGO-UNICO", "motivo": null }
```

Un **ACUERDO** se registra solo si se cumplen las tres condiciones:

1. la identidad se verificó en esa llamada;
2. `confirmacion_final` es `true`;
3. `oferta_id` es una oferta que el agente pidió **en esa misma llamada**.

Si no se puede registrar, la respuesta trae `"registrado": false` y el `motivo`.

### 3. Webhook de fin de llamada

En la configuración de webhooks del agente (post-call):

- **URL:** `https://<dirección de ngrok>/webhooks/elevenlabs`
- **Evento:** transcripción (`post_call_transcription`)
- Al crearlo, ElevenLabs muestra un **secreto**: va en `ELEVENLABS_WEBHOOK_SECRET`
  del `.env` (Parte 1, paso 2).

Mavic verifica la firma de cada envío (encabezado `ElevenLabs-Signature`) y
guarda la transcripción, el resumen y el análisis en la llamada. Responde
siempre 200, aunque ignore el envío (por ejemplo, si la llamada nunca usó una
herramienta): así ElevenLabs no lo cuenta como falla.

---

## Qué significa cada `motivo`

| `motivo` | En qué herramienta | Qué pasó |
| --- | --- | --- |
| `IDENTIDAD_NO_VERIFICADA` | ofertas, resultado | No se verificó la identidad en esta llamada: no hay datos ni ofertas |
| `SIN_REGLA` | ofertas | Ninguna regla de la empresa se aplica a este caso |
| `SIN_CUOTAS` | cuotas | La regla permite solo pago único |
| `CASO_NO_NEGOCIABLE` | ofertas, resultado | El caso ya tiene un resultado (acuerdo, disputa, derivado o cerrado) |
| `ACUERDO_SIN_CONFIRMAR` | resultado | `confirmacion_final` no vino en `true` |
| `OFERTA_NO_OFRECIDA` | resultado | La oferta aceptada no se le presentó al deudor en esta llamada |
| `YA_REGISTRADO` | resultado | Esta llamada ya tenía otro resultado registrado |

**Cuando no hay oferta** (`has_offer: false`): se devuelve el monto completo,
sin descuento (`descuento: 0`, `importe_total` = deuda), `cantidad_cuotas: 0` y
`ofertas_restantes: 0`. Si no se verificó la identidad, los montos vienen en 0.

## Diferencias con lo que había pasado quien arma el agente

| Qué | Por qué |
| --- | --- |
| Encabezado `Authorization` obligatorio | Con ngrok, Mavic queda en una dirección pública: sin token, cualquiera podría pedir datos de deudores |
| Campos nuevos: `motivo`, `fecha_limite_pago`, `fecha_primera_cuota`, `importe_ultima_cuota`, `interes_porcentaje` | Información útil para el agente. No rompen nada si no se usan |
| Las ofertas también exigen identidad verificada | Extiende la regla del contexto: sin identidad, ningún dato de la deuda |

## Diagnóstico: ¿dónde se corta?

```text
Agente ──① sale?──► ngrok ──② llega?──► Mavic ──③ responde?──► vuelve al agente
```

La herramienta clave es el **inspector de ngrok**: mientras ngrok está abierto,
entrá a http://localhost:4040. Muestra cada pedido que llegó, con sus
parámetros, encabezados y la respuesta de Mavic.

| Lo que ves | Qué pasa | Qué hacer |
| --- | --- | --- |
| No aparece ningún pedido | El agente apunta a otra dirección o no usó la herramienta | Comparar la URL de cada herramienta con la línea `Forwarding` de ngrok |
| `401 AGENT_TOKEN_INVALID` | Falta el encabezado o el token no coincide | Pestaña **Headers** del pedido: ¿llega `Authorization`? ¿Es el token del `.env`? |
| `200` con `identidad_verificada: false` | El nombre no coincide o `respuesta` no es un "sí" | Mirar los **Query Params** / **Body**: ¿qué llegó en `respuesta`? |
| `200` con `has_offer: false` | El `motivo` dice por qué | Ver la tabla de motivos de arriba |
| `404 CASE_NOT_FOUND` | El `caso_id` no existe | Usar el `number` real de **GET /cases** |
| `422` | Falta un parámetro o tiene otro nombre | Comparar con las tablas de la Parte 2 |

## Lo que aprendimos en la primera prueba real

| Problema | Causa | Solución |
| --- | --- | --- |
| 401 al probar en Swagger | Swagger no manda un campo llamado "Authorization" | Usar el botón **Authorize** |
| Al agente no le llegaba nada | Las herramientas apuntaban a otro ngrok (de una prueba anterior) | Corregir las 4 URLs |
| No verificaba la identidad | `respuesta` llegaba con todo el historial de la conversación | Configurar `respuesta` como LLM Prompt (`si`/`no`) y Mavic ahora entiende ese formato |
| No ofrecía descuento ni cuotas | El caso ya tenía un acuerdo de una prueba anterior | Probar otro caso o `reopen-case` |
| `caso_id` llegaba como `DEMO-001` | Valor de ejemplo en las variables del agente | Usar el número real del caso |

## Pendiente

- **Iniciar la llamada desde Mavic:** cuando haya telefonía (Twilio u otro).
  Por ahora se prueba desde ElevenLabs escribiendo el número de caso.
- **Webhook de fin de llamada:** probado simulando a ElevenLabs y a través del
  frontend (`/api/webhooks/elevenlabs`); falta probarlo con el agente real.
- **Llamadas salientes:** probadas con un ElevenLabs simulado; falta la primera
  llamada real (necesita el número de Twilio vinculado al agente).
