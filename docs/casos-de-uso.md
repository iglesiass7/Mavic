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
| CU-04 | Importar facturas desde Excel/CSV | Operador | Paso 3 |
| CU-05 | Agrupar facturas en casos | Operador | Paso 3 |
| CU-06 | Configurar reglas de negociación | Administrador | Paso 4 |
| CU-07 | Calcular ofertas (pago único y cuotas) | Agente de voz | Pasos 4 y 5 |
| CU-08 | Iniciar contacto con un caso | Operador | Paso 5 |
| CU-09 | Consultar el contexto del caso durante la llamada | Agente de voz | Paso 5 |
| CU-10 | Registrar el resultado de la llamada | Agente de voz | Paso 5 |
| CU-11 | Atender casos derivados a humano | Operador | Paso 5 |
| CU-12 | Ver el tablero de resultados | Todos los de la empresa | Paso 6 |
