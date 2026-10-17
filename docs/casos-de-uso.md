# Casos de uso

Mavic ayuda a una empresa con facturación recurrente (un proveedor de internet,
un club, una prepaga) a cobrar facturas vencidas. Un **agente de voz con IA**
llama a los deudores, verifica su identidad, informa la deuda y negocia un pago
dentro de **reglas que define la empresa**. Las personas preparan el trabajo,
supervisan y atienden lo que el agente no puede resolver.

## Actores

| Actor | Quién es | Qué hace |
| --- | --- | --- |
| Administrador | Jefe de cobranzas | Usuarios de su empresa y reglas de negociación |
| Operador | Analista de cobranzas | Importa facturas, arma casos, inicia contactos, atiende derivaciones |
| Supervisor | Gerencia | Ve casos y resultados, sin modificar nada |
| Dueño de la plataforma | Quien opera Mavic | Da de alta empresas cliente; no ve datos de deudores |
| Agente de voz | Agente de ElevenLabs | Consulta el caso de la llamada en curso y registra el resultado |

## Ejemplo: una semana en "FibraSur" (empresa ficticia)

1. **Laura** (administradora) da de alta a Pablo (operador) y a Martín
   (supervisor) y define las reglas: descuento máximo por pago único, cantidad
   máxima de cuotas, plazos.
2. **Pablo** (operador) sube un Excel con las facturas impagas. Mavic valida cada
   fila y agrupa las facturas de un mismo cliente en un **caso**.
3. Pablo inicia el contacto. **El agente** llama, verifica que habla con el
   titular, informa la deuda y ofrece pago único o cuotas. Los montos no los
   inventa la IA: los calcula Mavic con las reglas de Laura.
4. El agente registra el resultado: **acuerdo**, **desconocimiento** de la deuda,
   **contactado** sin acuerdo o **derivación a humano**.
5. Pablo atiende los casos derivados, con la transcripción de la llamada.
6. **Martín** (supervisor) mira el tablero de resultados.

## Lista de casos de uso

| # | Caso de uso | Actor | Estado |
| --- | --- | --- | --- |
| CU-01 | Iniciar y cerrar sesión, cambiar la contraseña | Todos | Hecho (Paso 2) |
| CU-02 | Gestionar usuarios de la empresa | Administrador | Hecho (Paso 2) |
| CU-03 | Dar de alta una empresa cliente con su administrador | Dueño de la plataforma | Hecho (Paso 2) |
| CU-04 | Importar facturas desde Excel/CSV | Operador | Hecho (Paso 3) |
| CU-05 | Agrupar facturas en casos | Operador | Hecho (Paso 3) |
| CU-06 | Configurar reglas de negociación | Administrador | Hecho (Paso 4) |
| CU-07 | Calcular ofertas (pago único y cuotas) | Agente de voz | Cálculo hecho (Paso 4); uso desde la llamada en el Paso 5 |
| CU-08 | Iniciar contacto con un caso | Operador | Paso 5 |
| CU-09 | Consultar el contexto del caso durante la llamada | Agente de voz | Paso 5 |
| CU-10 | Registrar el resultado de la llamada | Agente de voz | Paso 5 |
| CU-11 | Atender casos derivados a humano | Operador | Paso 5 |
| CU-12 | Ver el tablero de resultados | Todos los de la empresa | Paso 6 |

## Reglas de la cartera (Paso 3)

**CU-04 · Importar facturas.** El operador sube un CSV o Excel con una fila por
factura.

| Situación | Qué pasa |
| --- | --- |
| Alguna fila tiene un error (teléfono inválido, monto negativo, fecha vacía…) | No se carga **nada**. Se devuelven todos los errores con fila y columna |
| La factura no existía | Se crea (y el deudor, si tampoco existía) |
| La factura ya existía y todavía no está en un caso | Se actualiza con los datos nuevos |
| La factura ya está en un caso y viene igual | Se ignora (cuenta como “sin cambios”) |
| La factura ya está en un caso y viene distinta | Error `INVOICE_IN_CASE`: no se cambia una deuda que ya se está gestionando |
| El mismo DNI en dos empresas | Son dos deudores distintos; ninguna empresa ve ni pisa los datos de la otra |

Solo se aceptan pesos (`ARS`). El monto admite `18500.50` o `18.500,50`.

**CU-05 · Generar casos.** Un caso agrupa las facturas **vencidas** de un
deudor. Al generar:

- Si el deudor no tiene un caso **pendiente** (todavía sin contactar), se crea uno.
- Si ya tiene uno pendiente, las facturas nuevas se suman a ese caso.
- Si su caso ya fue contactado, las facturas nuevas van a un caso nuevo (no se
  cambia lo que se está negociando).
- Las facturas que todavía no vencieron quedan sin caso.
- Generar dos veces seguidas no crea nada la segunda vez.

## Reglas de negociación y ofertas (Paso 4)

**CU-06 · Configurar reglas.** Cada regla dice a qué casos se aplica y qué se
puede ofrecer:

| Parte | Campos | Ejemplo ("Mora alta con plan extendido") |
| --- | --- | --- |
| A qué casos | Monto total, días de atraso, cantidad de facturas (mínimo y máximo; máximo vacío = sin tope) | 0 a 500.000 · 60 días o más · 1 a 12 facturas |
| Qué ofrecer | % de descuento por pago único, días de plazo, máximo de cuotas, % de interés | 10 % · 5 días · 6 cuotas · 12 % |

- Solo el administrador crea o cambia reglas; el resto de la empresa las ve.
- Dos reglas **activas** no pueden pisarse: si existe un caso al que se le
  aplicarían las dos, se rechaza (`RULE_OVERLAP`).
- No se borran: se desactivan.

**CU-07 · Calcular ofertas.** Para un caso pendiente o contactado, Mavic busca
la regla activa que le corresponde y calcula:

| Oferta | Cálculo | Ejemplo con 120.000 |
| --- | --- | --- |
| `PAGO-UNICO` | deuda − descuento, a pagar dentro del plazo | 10 % → 108.000 |
| `CUOTAS-N-SIN-INTERES` / `CUOTAS-N-CON-INTERES` | deuda + interés, en N cuotas mensuales; la primera vence al terminar el plazo | 3 sin interés → 3 × 40.000 |

Si no hay oferta, se informa el motivo: `NO_MATCHING_RULE` (ninguna regla
activa aplica) o `CASE_NOT_NEGOTIABLE` (el caso ya tiene un resultado).
