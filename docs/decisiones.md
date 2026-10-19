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

## ADR-017 · El backend decide la oferta: una sola regla por caso

- **Contexto:** en el original, el backend devolvía todas las reglas que se
  aplicaban a un caso y el agente de voz elegía. Quien arma el agente pidió lo
  contrario: que el backend le dé la oferta ya calculada.
- **Decisión:** a cada caso le corresponde como máximo una regla activa. Al
  crear, cambiar o activar una regla, se rechaza si sus tres rangos (monto, días
  de atraso, cantidad de facturas) se pisan con los de otra regla activa
  (`RULE_OVERLAP`). La validación corre con un bloqueo por empresa, así dos
  administradores no pueden colarse a la vez.
- **Alternativas:** prioridades entre reglas (descartado: nadie lo pidió, y
  "¿por qué le tocó esta?" se vuelve difícil de explicar); una restricción
  `EXCLUDE` de PostgreSQL con rangos (más robusta, pero exige columnas de tipo
  rango y la extensión `btree_gist`: más complejo de lo que el proyecto necesita hoy).
- **Consecuencias:** puede haber casos sin regla (huecos entre rangos). No es un
  error: el caso queda sin oferta (`NO_MATCHING_RULE`) y, en el Paso 5, el agente
  lo deriva a una persona.

## ADR-018 · Cómo se calculan las ofertas

- **Decisión:**
  - Pago único: deuda − descuento de la regla, a pagar dentro de `payment_days`.
  - Cuotas: deuda + interés de la regla (sin descuento: el descuento es el premio
    por pagar todo junto), en la cantidad máxima de cuotas que permite la regla,
    mensuales, la primera al terminar el plazo.
  - Redondeo "half up" a centavos. Las cuotas se redondean para abajo y la
    última se lleva los centavos que sobran, así la suma da exacto el total.
  - Identificadores con el formato que usa el agente: `PAGO-UNICO`,
    `CUOTAS-3-SIN-INTERES`.
- **Fuente:** los porcentajes, cuotas y plazos son los campos de las reglas del
  original. Que el descuento sea para el pago único y el interés para las
  cuotas surge de las descripciones de sus reglas de ejemplo y de los ejemplos
  del agente (`CUOTAS-3-SIN-INTERES`: 120.000 en 3 × 40.000).
- **Consecuencias:** una regla con `max_installments = 1` ofrece solo pago
  único. En el Paso 5 hay que traducir estos campos a los nombres que espera el
  agente (`importe_original`, `descuento_porcentaje`, `importe_por_cuota`...).

## ADR-019 · Un módulo usa a otro por sus casos de uso

- **Decisión:** la negociación lee los casos llamando a
  `portfolio.application.cases.get_case`, no a sus repositorios ni a sus
  tablas. La cartera no importa nada de la negociación. Dos contratos de
  `import-linter` lo verifican.
- **Por qué:** si la negociación leyera las tablas de la cartera, cualquier
  cambio en esas tablas la rompería, y habría que repetir en dos lugares las
  reglas de permisos y de empresa.
- **Consecuencias:** se trae un poco más de información de la necesaria (las
  facturas del caso). Si algún día pesa, la cartera puede exponer un caso de uso
  más liviano.

## ADR-020 · El agente se autentica con un token; no es un usuario

- **Contexto:** el agente de ElevenLabs llama a Mavic desde internet (a través
  de ngrok). No tiene cookie de sesión ni rol. Quien arma el agente no usaba
  autenticación porque eran pruebas.
- **Decisión:** las herramientas exigen `Authorization: Bearer <token>`
  (`AGENT_TOOLS_TOKEN`, de 32 caracteres o más). ElevenLabs lo guarda como
  "Secret". El token solo abre las herramientas, no el resto de la API. Si no
  está configurado, responden 503 en vez de quedar abiertas.
- **Por qué:** con ngrok, Mavic queda en una dirección pública y los números de
  caso son correlativos: sin token, cualquiera podría pedir datos de deudores
  probando números.
- **Consecuencias:** el agente usa casos de uso "internos" que reciben la
  empresa explícitamente (la del caso), en lugar de los que verifican permisos
  de una persona.

## ADR-021 · Las ofertas de una llamada quedan fijas y solo se acepta lo ofrecido

- **Decisión:** la primera vez que una llamada necesita las ofertas, se
  calculan y se guardan en la conversación (JSON). Se registra si cada oferta
  se presentó. Un `ACUERDO` solo se acepta con identidad verificada,
  `confirmacion_final = true` y una oferta presentada en esa llamada. El acuerdo
  guarda montos y cronograma tal como se ofrecieron.
- **Por qué:** un modelo de lenguaje puede inventar o mezclar datos. El backend
  es la fuente de verdad: lo que no salió de él no se registra como acuerdo. Y
  si una regla cambia a mitad de la llamada, el acuerdo respeta lo que escuchó
  el deudor.
- **Consecuencias:** si el registro se rechaza, el agente recibe
  `registrado: false` y un `motivo`, en vez de un error HTTP que lo haga
  reintentar.

## ADR-022 · Webhook firmado y siempre con 200

- **Decisión:** el webhook verifica la firma HMAC-SHA256 de ElevenLabs
  (`ElevenLabs-Signature: t=…,v0=…`, sobre `"<t>.<cuerpo>"`) y rechaza firmas
  de más de 30 minutos. Con firma válida responde 200 siempre, aunque ignore el
  evento (por ejemplo, una llamada que nunca usó una herramienta).
- **Por qué:** sin firma, cualquiera podría cargar transcripciones falsas. El
  límite de tiempo evita que se reenvíe un mensaje viejo capturado. ElevenLabs
  cuenta como falla toda respuesta que no sea 200 y desactiva el webhook tras
  muchas fallas seguidas.
- **Fuente:** la documentación de post-call webhooks de ElevenLabs.

## ADR-023 · Para el agente, los montos van como número JSON

- **Contexto:** en el resto de la API, los montos viajan como texto (ADR-016).
  Los ejemplos del agente usan números (`"importe_total": 108000`).
- **Decisión:** solo en las respuestas de las herramientas, los montos se
  serializan como número (`120000` o `53325.45`). Adentro de Mavic siguen
  siendo `Decimal`.
- **Por qué:** el contrato lo define el agente. Son montos de 2 decimales que
  el agente solo lee en voz alta, así que el riesgo de redondeo de JavaScript
  no aplica.

## ADR-024 · Las herramientas aceptan GET y POST

- **Decisión:** cada herramienta acepta los parámetros como query string (GET)
  o como JSON en el cuerpo (POST).
- **Por qué:** en ElevenLabs se pueden configurar de las dos formas, y no
  estaba claro cuál usaba el agente. Aceptar ambas evita una falla difícil de
  diagnosticar en la primera prueba. El código es el mismo: solo cambia de
  dónde se leen los parámetros.

## ADR-025 · Confirmación de identidad tolerante, pero "ante la duda, no"

- **Contexto:** en la primera prueba con el agente real, `respuesta` llegó con
  todo el historial de la conversación, y la frase de la persona era "Buenos
  días. Sí, sí, soy Ricardo Pérez". Mavic solo aceptaba respuestas que
  empezaran con "sí", así que no verificaba la identidad.
- **Decisión:** si `respuesta` trae el formato de historial de ElevenLabs, se
  usa el `respuesta` del último pedido a la herramienta. Un "sí" (o "correcto",
  "soy yo", "él habla"…) en cualquier parte de la frase verifica, **salvo** que
  también aparezca un "no". Las palabras que solo valen como respuesta completa
  (`true`, `1`, `s`) no cuentan dentro de una frase: el historial trae
  `"x-elevenlabs-history": true` y eso no puede valer como "sí".
- **Por qué:** un falso "sí" le cuenta la deuda a quien no es el titular. Un
  falso "no" solo hace que el agente no dé datos. El segundo error es mucho más
  barato que el primero.
- **Consecuencias:** se recomienda igual que el agente mande solo `si`/`no`.
  Los tests usan el pedido exacto que llegó en la prueba real.

## ADR-026 · El navegador habla solo con el frontend

- **Contexto:** en Rynx cada archivo del frontend llamaba directo al backend con
  `NEXT_PUBLIC_API_URL` (la misma línea repetida en muchos archivos). Eso obliga
  a configurar CORS y a que la cookie de sesión viaje entre dos direcciones
  distintas.
- **Decisión:** el navegador solo habla con `localhost:3000`. Lo que empieza con
  `/api/` lo reenvía el servidor de Next al backend (`rewrites` en
  `next.config.ts`). La dirección del backend está en un solo lugar.
- **Alternativas:** llamar al backend directo, como el original (más
  configuración y más formas de equivocarse con la cookie); un servidor
  intermedio propio (más código sin beneficio para esta app).
- **Consecuencias:** la cookie es "de la misma página" y no hace falta CORS. La
  dirección del backend se fija al compilar: en Docker es `http://backend:8000`
  y si cambia hay que reconstruir la imagen. El freno de intentos de login
  cuenta por email, no por IP, así que el reenvío no lo afecta.

## ADR-027 · La sesión vive solo en la cookie

- **Contexto:** Rynx ya usaba una cookie HttpOnly, pero además guardaba los
  datos del usuario en `localStorage` (`rynx_user`). Esa copia puede quedar
  vieja (rol cambiado, usuario desactivado) y queda en la PC después de cerrar
  el navegador.
- **Decisión:** nada de la sesión se guarda en el navegador. Quién es el
  usuario, su empresa y sus permisos se piden a `GET /auth/me` y quedan solo en
  la memoria de la pestaña. Al cerrar sesión se borra todo lo cargado.
- **Consecuencias:** un pedido más al abrir la app (se reutiliza durante 5
  minutos). Si el backend desactiva a alguien, en el próximo pedido recibe 401 y
  vuelve al login.

## ADR-028 · Los montos se muestran como texto, sin convertirlos a número

- **Contexto:** el backend manda los montos como texto con 2 decimales exactos
  (`"21330.18"`). JavaScript guarda los números con decimales de forma
  aproximada; Rynx los convertía con `Number(...)`.
- **Decisión:** el frontend nunca hace cuentas con plata. `formatMoney` solo
  agrega separadores al texto (`"$ 21.330,18"`), con un espacio que no corta
  para que el signo no quede en un renglón y el número en otro. Las fechas sin
  hora (`"2026-10-24"`) tampoco pasan por `Date`, que las correría un día según
  la zona horaria.
- **Consecuencias:** si alguna pantalla necesita un total, lo calcula el
  backend. Es la misma regla que con el agente: los montos los decide Mavic,
  nadie más.

## ADR-029 · Las pantallas muestran solo datos reales

- **Contexto:** es tentador llenar un panel con números de ejemplo mientras no
  existe el dato verdadero.
- **Decisión:** cada pantalla muestra solo lo que devuelve el backend. Si un
  dato todavía no existe (por ejemplo, los totales del tablero), primero se
  agrega el endpoint y después la pantalla. Cuando no hay nada, se dice qué
  falta y cómo conseguirlo ("Todavía no hubo llamadas…").
- **Consecuencias:** el tablero con números (Paso 6d) espera a su endpoint de
  resumen. Nadie toma decisiones mirando datos inventados.

## ADR-030 · Cargar facturas: primero se revisa, después se guarda

- **Contexto:** en Rynx la carga ya tenía tres pasos (subir, validar, cargar) y
  revisaba en el navegador el tamaño (10 MB) y la extensión (`.csv`, `.xls`,
  `.xlsx`). Al generar casos mostraba una barra de progreso que avanzaba sola
  con un temporizador, sin relación con lo que hacía el servidor.
- **Decisión:**
  - Al elegir el archivo se llama a `POST /imports/preview`, que **no guarda
    nada**, y se muestra qué pasaría: facturas nuevas, actualizadas y sin
    cambios, o los errores con fila y columna. Recién con "Cargar" se llama a
    `POST /imports`, que vuelve a revisar todo.
  - El navegador solo hace una revisión rápida (extensión y 5 MB, los mismos
    límites que el backend) para no subir algo que va a ser rechazado. `.xls`
    no se acepta porque el backend no lo lee.
  - "Generar casos" muestra el botón cargando mientras espera y después el
    resultado real ("Se agruparon 8 facturas en 4 casos nuevos"). No hay
    barras de progreso inventadas.
- **Alternativas:** cargar directo y mostrar los errores después (con un solo
  error no se guarda nada, pero la persona no sabe de antemano qué iba a
  cambiar).
- **Consecuencias:** el archivo viaja dos veces (revisión y carga). Con el
  límite de 5 MB no importa. El historial de cargas no muestra quién subió cada
  archivo: el módulo de cartera no puede leer los usuarios (regla de
  dependencias entre módulos); si hace falta, se agrega a la respuesta del
  backend en un paso propio.
