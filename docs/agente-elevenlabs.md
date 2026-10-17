# Conectar el agente de ElevenLabs con Mavic

Esta guía tiene dos partes:

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

### 4. Elegir el caso para probar

Sin telefonía, el agente se prueba desde ElevenLabs escribiendo el **número de
caso** (`caso_id`). Lo ves en Swagger, en **GET /cases** (campo `number`). Por
ejemplo, `2`. También acepta formatos con prefijo, como `CASO-2`.

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

## Pendiente

- **Iniciar la llamada desde Mavic:** cuando haya telefonía (Twilio u otro).
  Por ahora se prueba desde ElevenLabs escribiendo el número de caso.
- **Probar con el agente real:** todo lo de arriba está probado simulando al
  agente. La integración no se da por terminada hasta probarla con él.
