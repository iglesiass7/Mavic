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

## ADR-031 · Reglas: en palabras y con los números como se escriben acá

- **Contexto:** en Rynx las reglas se mostraban en una tabla con prioridad y un
  resumen abreviado ("Desc. max 10% · Interés max 12% · 6 cuotas · 5 días
  promesa"). En Mavic las reglas activas no se pueden pisar (ADR-017), así que a
  cada caso le toca una sola y la prioridad no hace falta.
- **Decisión:**
  - Cada regla se muestra como dos frases: a qué casos se aplica ("Deuda: hasta
    $ 500.000 · Atraso: de 15 a 59 días") y qué puede ofrecer el agente ("10 %
    de descuento, a pagar en 5 días · 3 cuotas con 8 % de interés total").
  - El editor muestra esas mismas frases mientras se completa, antes de guardar.
  - Los campos aceptan `500.000`, `1.250,50` y `12,5`, además de `500000` y
    `12.5`. Se convierten a texto con punto decimal (`lib/numbers.ts`), sin pasar
    por `Number` (ADR-028).
  - El formulario valida lo mismo que el backend (rangos, 1 a 36 cuotas, 1 a 90
    días, descuento menor a 100 %) para marcar el error en su campo. Si dos
    reglas activas se pisan, lo dice el backend (`RULE_OVERLAP`) con el nombre
    de la otra regla.
- **Consecuencias:** si cambian los límites del backend, hay que cambiarlos
  también en `features/rules.ts` (están juntos y comentados). El backend sigue
  siendo el que decide: el formulario solo avisa antes.

## ADR-032 · Usuarios: contraseña inicial al azar y nadie se desactiva a sí mismo

- **Contexto:** Rynx tenía, en la configuración, una ventana para invitar miembros. En
  Mavic no hay envío de emails (la única integración externa es el agente de
  voz), así que no hay invitación por correo.
- **Decisión:**
  - Al dar de alta un usuario (o una empresa con su primera persona de
    administración), el navegador propone una contraseña al azar de 12
    caracteres sin letras que se confunden ("Hk7m-p2Qa-9xTe"), generada con
    `crypto.getRandomValues`. Se muestra una sola vez, con un botón para
    copiarla, y se pasa por un medio privado. Después cada persona la cambia
    desde **Mi cuenta**.
  - En la lista de usuarios no se ofrece cambiarse el rol ni desactivarse a uno
    mismo: cerraría la sesión en el momento. Que la empresa no se quede sin
    administración lo controla el backend (`LAST_ACTIVE_ADMIN`).
- **Consecuencias:** quien da de alta conoce la contraseña inicial hasta que la
  persona la cambia. Si más adelante se agregan emails, se reemplaza por un link
  de invitación.

## ADR-033 · El tablero se calcula en el backend, en un módulo propio

- **Contexto:** el tablero de Rynx tenía los números escritos en el código del
  frontend (por ejemplo, `{ name: "Pendiente", value: 32 }`): no pedía nada al
  backend y mostraba lo mismo para cualquier empresa. Además, el frontend de
  Mavic no hace cuentas con plata (ADR-028).
- **Decisión:**
  - `GET /dashboard` devuelve todo calculado: casos y deuda por estado (los 6,
    con 0 si no hay), deuda en gestión por tramo de atraso (0-30, 31-60, 61-90,
    más de 90 días), facturas sin caso vencidas y por vencer, llamadas por
    resultado, identidad verificada y acuerdos con sus montos.
  - "En gestión" usa la misma regla que el agente para saber qué se puede
    negociar (`NEGOTIABLE_STATUSES`: pendiente y contactado). "Vencidas sin
    caso" usa la misma condición que "Generar casos".
  - Las cuentas se hacen en la base (`GROUP BY`, `SUM ... FILTER`) dentro de cada
    módulo. Un módulo nuevo, `reporting`, solo las junta y no lee tablas: lo
    controla import-linter.
  - Los acuerdos son lo que el deudor **se comprometió** a pagar, no plata
    cobrada: la pantalla lo aclara, porque Mavic todavía no registra pagos.
  - Gráficos: la barra de antigüedad usa un solo color (es una cantidad); la de
    estados usa los colores de estado, en un orden validado con el script de la
    guía de gráficos para que verde y rojo no queden pegados (con daltonismo
    rojo-verde se confunden). El gris de "Cerrado" no pasa el control de
    saturación a propósito: es el estado neutro, y siempre va con su nombre en
    la leyenda, que además es una tabla con los números.
  - El navegador usa `Number` solo para el largo de las barras; el texto que se
    lee es el monto exacto del backend.
- **Consecuencias:** como solo hay pesos (`ARS`), las sumas son correctas. Si se
  agrega otra moneda, el resumen tiene que separar por moneda. Con muchísimos
  casos, el reparto por tramos (que hoy se hace en Python) puede pasar a SQL.

## ADR-034 · Llamadas salientes: el agente recibe todo al empezar

- **Contexto:** quien arma el agente publicó una versión nueva, "Gestión de
  Deuda", y escribió su contrato de integración (PDF del 22/10/2026). El agente
  nuevo **no usa herramientas** durante la llamada: recibe el caso, las deudas y
  las ofertas antes de empezar, y el resultado llega en el análisis del webhook.
  Con el diseño anterior, la fila de la llamada nacía cuando el agente usaba una
  herramienta; sin herramientas, el webhook terminaba en
  `CONVERSACION_DESCONOCIDA` y se perdía todo.
- **Decisión:**
  - `POST /cases/{id}/calls` (botón "Llamar", permiso de operar la cartera)
    inicia la llamada con el SDK oficial de ElevenLabs por Twilio. El SDK queda
    encerrado en `voice/infrastructure/elevenlabs_calls.py` detrás de una
    interfaz (`domain/call_gateway.py`): los tests usan una falsa.
  - Orden: se bloquea el caso, se arma la foto y se guarda la conversación
    `INITIATING` **antes** de llamar; después `INITIATED` con `conversation_id` y
    `callSid`, o `FAILED` con el motivo. Una llamada en curso bloquea otra al
    mismo caso durante 30 minutos (si el webhook no llega, se asume perdida).
  - Las 8 variables con los nombres exactos del contrato; `deudas` y `ofertas`
    como texto JSON en UTF-8; montos convertidos a número recién en el borde,
    verificando que no se pierda un centavo.
  - Ofertas: una lista ordenada (posición 0 primero) con ids estables
    (`PAGO-UNICO`, `CUOTAS-6-CON-INTERES`). Sin fechas: el agente no pacta fechas
    de pago. **Cuotas iguales:** el importe se redondea al centavo y el total del
    plan es cuotas × importe. Antes, la última cuota se llevaba los centavos
    sobrantes; el contrato nuevo tiene un solo importe por cuota y no permite
    esconder esa diferencia. Ejemplo: 310.000 al 12 % en 6 cuotas eran
    5 × 57.866,66 + 57.866,70; ahora son 6 × 57.866,67 = 347.200,02.
  - La foto (`initiation_payload`, `schema_version = 2`) es la fuente de verdad:
    un `ACUERDO` se registra solo si `oferta_id` está en la foto, y los montos se
    copian de ella, no del texto de la llamada ni de las reglas de hoy.
  - Webhook: primero se guarda el envío tal como llegó (`webhook_events`, con su
    hash para reconocer repeticiones), después se procesa en otra transacción.
    Si falla la base, responde 500 y el reintento de ElevenLabs lo procesa. La
    llamada se busca por `conversation_id` y, si no está, por el `caso_id` de las
    variables. Una llamada que no inició Mavic se registra con origen `EXTERNAL`.
  - Lo dudoso no se aplica solo: resultado vacío o desconocido, `ACUERDO` sin
    oferta o con una que no se mandó, o el caso que ya tenía resultado →
    `NEEDS_REVIEW`, sin cambiar el caso ni crear acuerdos.
  - Moneda: el caso tiene moneda y se agrupa por deudor + moneda. La base lo
    garantiza: la factura apunta a (caso, deudor, moneda).
- **Consecuencias:** conviven los dos flujos (etapa 1 del contrato): las
  herramientas `/agent/tools/*_v2` siguen andando para el agente anterior.
  Cuando nadie las use (etapa 2), se borran junto con `AGENT_TOOLS_TOKEN` y las
  columnas del progreso por oferta. `identity_verified` solo tiene sentido en el
  flujo anterior: en el nuevo la pantalla no lo muestra. Faltan pantallas para
  resolver las llamadas `NEEDS_REVIEW` (hoy se ven en el caso, con su motivo).

## ADR-035 · El frontend con el diseño de Rynx, sin funciones de mentira

- **Contexto:** el equipo pidió que Mavic se vea igual que Rynx para que el
  cambio no se note en el uso diario. Rynx tiene pantallas y botones que Mavic
  todavía no respalda (preferencias, autenticación en dos pasos, "Recuérdame",
  "¿Olvidaste tu contraseña?", horario de reintentos, auditoría, costos).
- **Decisión:**
  - Se copia el diseño (colores, letras, menú, tarjetas, tablas, pasos, panel
    lateral) y la organización de las pantallas, con los datos y las reglas de
    Mavic. Las piezas comunes están en `components/` (`DataTable`, `Stepper`,
    `Sheet`, `AmountRange`, `ui.tsx`) para que todas las pantallas se vean igual.
  - **No se muestra nada que no funcione.** Un botón que no hace nada confunde
    más que su ausencia. Lo que Rynx tiene y Mavic no, se suma cuando exista el
    backend (paso 7c), no antes.
  - Conversaciones: en Rynx cada tarjeta es un caso; en Mavic, una **llamada**,
    así se filtra por cómo terminó cada una (acuerdo, no reconoce, para revisar…).
  - Configuración junta "Mi cuenta" y "Usuarios" en pestañas, como Rynx. Las
    direcciones viejas (`/account`, `/users`) responden 308 hacia las nuevas
    (en `next.config.ts`), así no se rompen links guardados.
  - Los filtros y lo elegido viven en la dirección (`?estado=acuerdo&llamada=…`),
    con nombres en castellano: se puede volver atrás o compartir el link.
  - Las tablas chicas (reglas, usuarios, empresas) se filtran y ordenan en el
    navegador; las grandes (casos, facturas, llamadas) las pagina el backend.
- **Consecuencias:** el logo y los colores son los de Rynx (`public/brand/`). Si
  el producto cambia de nombre, se cambian ahí y en `Brand.tsx`. Las pantallas
  que faltan de Rynx (Auditoría, Medidor de costos, las pestañas Preventivo y
  Corriente de reglas) llegan con el paso 7c.

## ADR-036 · Auditoría: un evento por cambio, en la misma transacción, que no se borra

- **Contexto:** la pantalla de Auditoría de Rynx mostraba cuatro eventos escritos
  a mano en el código. El equipo necesita saber de verdad quién cambió una regla,
  quién registró un pago o qué hizo el agente.
- **Decisión:**
  - Módulo `audit` con una tabla `audit_events`. Los otros módulos le avisan con
    `audit.record(...)` **antes** de su `commit`: el cambio y su evento se guardan
    juntos o no se guarda ninguno. La auditoría no conoce a los otros módulos
    (recibe todo armado), así no hay dependencias en círculo (lo verifica
    `import-linter`).
  - Cada evento guarda quién (persona, agente o sistema, con el nombre de ese
    día), qué (`action`), sobre qué (`subject`), un resumen en castellano y el
    detalle (para los cambios, el antes y el después de cada campo).
  - **Solo se agrega:** un trigger de PostgreSQL rechaza `UPDATE` y `DELETE`,
    también para quien entre a la base a mano.
  - La hora la pone la base (`now()` de la transacción): es la hora real.
  - La ven administración y supervisión (`VIEW_AUDIT`). Guardar sin cambios no
    deja un evento vacío.
- **Consecuencias:** la tabla crece para siempre. Con mucho volumen se puede
  particionar por mes. Hoy registra cambios de configuración, cargas, casos,
  llamadas, acuerdos, pagos y avisos; los ingresos al sistema (login) no.

## ADR-037 · Seguimiento de pagos: cuotas con fecha y registro manual

- **Contexto:** un acuerdo de la llamada es una promesa, no plata. Rynx tenía
  el estado del acuerdo en la base pero ninguna forma de cargar un pago. El
  agente nuevo no pacta fechas (ADR-034).
- **Decisión:**
  - Al crearse un acuerdo, Mavic arma sus cuotas (`agreement_installments`): la
    primera vence a los días de plazo de la regla con la que se llamó (está en
    la foto de la llamada) y las demás cada mes. El pago único es una cuota.
  - Una persona de la empresa registra cada pago ("Registrar pago", con el día
    en que pagó y una nota). Equivocarse se arregla con "Anular", que pide un
    motivo (queda en la auditoría).
  - El estado **se calcula, no se guarda**: todas pagas = cumplido; alguna
    vencida sin pagar = atrasado; si no, al día. Así nunca queda viejo.
  - Cuando se paga la última cuota, el caso pasa a "cerrado"; si se anula ese
    pago, vuelve a "acuerdo de pago".
  - La migración arma las cuotas de los acuerdos que ya existían.
- **Consecuencias:** no hay pagos parciales de una cuota ni conciliación
  automática con el banco: se puede sumar una carga de pagos por planilla.

## ADR-038 · Avisos por email y WhatsApp: una vez por factura, a mano o solos

- **Contexto:** Rynx tenía las pestañas Preventivo y Corriente, pero la
  configuración no se guardaba, el botón de WhatsApp no mandaba nada y la
  contraseña de Gmail estaba escrita en el código.
- **Decisión:**
  - Dos momentos: **preventivo** (facturas sin caso que vencen entre mañana y
    dentro de N días) y **día de vencimiento**. Cada empresa elige canal, hora,
    días de anticipación, texto con marcadores (`{nombre}`, `{monto}`…) y "cómo
    pagar". Los marcadores mal escritos se rechazan antes de guardar.
  - Se mandan con el botón de Facturas (grupos 1 y 2, con vista previa del
    primer aviso) y, si está prendido, solos todos los días a la hora elegida.
    Lo automático lo hace un proceso aparte (`python -m mavic.worker`, servicio
    `worker` de docker compose) que revisa cada minuto.
  - **Una vez por factura y momento, garantizado por la base:** un índice único
    parcial sobre `notice_deliveries` deja un solo "mandando/mandado". Antes de
    mandar se anota "mandando" y se confirma; si el botón y el worker coinciden,
    el segundo choca y no manda. Un "mandando" colgado más de 15 minutos se da
    por fallido y se reintenta. Los fallidos se pueden reintentar.
  - Email por **SMTP genérico** (Gmail, AWS SES o Mailpit en la PC, cambiando
    solo el `.env`); WhatsApp por la API de **Twilio** (texto libre, o plantilla
    aprobada por Meta con variables numeradas). Los proveedores quedan detrás
    de una interfaz; los tests usan unos falsos.
  - Las claves solo en el `.env` / Secrets Manager; nunca en el código ni en un
    error.
- **Consecuencias:** para escribirle primero a un deudor por WhatsApp hace falta
  una plantilla aprobada por Meta (trámite de la empresa en Twilio). El aviso es
  por factura: un deudor con tres facturas que vencen juntas recibe tres.

## ADR-039 · Medidor de costos: uso real por tarifas de la empresa

- **Contexto:** el medidor de Rynx mostraba montos inventados.
- **Decisión:** el costo es **uso real × tarifa**. El uso sale de las tablas de
  Mavic: minutos de llamada (la duración que trae el webhook, al segundo) y
  avisos mandados por canal. Las tarifas las carga administración
  (`MANAGE_COSTS`), con hasta 4 decimales y un tope mensual opcional; la
  supervisión las ve. La proyección es lo gastado al mismo ritmo hasta fin de
  mes. Cambiar tarifas queda en la auditoría.
- **Consecuencias:** es una estimación tan buena como las tarifas cargadas: no
  lee las facturas de ElevenLabs, Twilio ni AWS. Si un proveedor cambia de
  precio, hay que actualizar la tarifa.
