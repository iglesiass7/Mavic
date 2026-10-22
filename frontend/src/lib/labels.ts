/**
 * Cómo se nombran en pantalla los valores que manda el backend.
 *
 * El backend usa códigos estables en inglés ("pending", "NO_MATCHING_RULE").
 * Las personas leen español claro. Esta es la única traducción: si un nombre
 * cambia, se cambia acá.
 */
import type {
  AgeBucket,
  CallResult,
  CallStatus,
  CaseSort,
  CaseStatus,
  InvoiceStage,
  NoOfferReason,
  UserRole,
} from "./types";

export const CASE_STATUS_LABEL: Record<CaseStatus, string> = {
  pending: "Pendiente",
  contacted: "Contactado",
  agreement: "Acuerdo",
  disputed: "En disputa",
  escalated: "Derivado a una persona",
  closed: "Cerrado",
};

/** Qué significa cada estado, para quien no lo conoce. */
export const CASE_STATUS_HINT: Record<CaseStatus, string> = {
  pending: "Todavía no se contactó al deudor.",
  contacted: "Se habló con el deudor y no hubo acuerdo todavía.",
  agreement: "El deudor aceptó una oferta de pago.",
  disputed: "El deudor no reconoce la deuda.",
  escalated: "El agente lo derivó: lo tiene que atender una persona.",
  closed: "El caso terminó.",
};

export const CASE_SORT_LABEL: Record<CaseSort, string> = {
  oldest_debt: "Más atrasados primero",
  highest_amount: "Mayor deuda primero",
  newest: "Más nuevos primero",
};

export const ROLE_LABEL: Record<UserRole, string> = {
  admin: "Administración",
  operator: "Operación",
  supervisor: "Supervisión",
  platform_admin: "Dueño de la plataforma",
};

/** Qué puede hacer cada rol de empresa (lo decide el backend en identity/domain/roles.py). */
export const ROLE_HINT: Record<Exclude<UserRole, "platform_admin">, string> = {
  admin: "Todo: facturas, casos, reglas y usuarios.",
  operator: "Cargar facturas, generar casos y trabajar la cartera.",
  supervisor: "Ver todo, sin cambiar nada.",
};

export const CALL_RESULT_LABEL: Record<CallResult, string> = {
  CONTACTADO: "Contactado, sin acuerdo",
  DESCONOCIMIENTO: "No reconoce la deuda",
  ACUERDO: "Acuerdo de pago",
  DERIVACION_HUMANA: "Derivado a una persona",
};

export const NO_OFFER_REASON_LABEL: Record<NoOfferReason, string> = {
  NO_MATCHING_RULE:
    "Ninguna regla de negociación activa se aplica a este caso. Si el agente llama, ofrece el monto completo sin descuento.",
  CASE_NOT_NEGOTIABLE:
    "El caso ya tiene un resultado: no se le hacen ofertas nuevas.",
};

/** "PAGO-UNICO" -> "Pago único"; "CUOTAS-3-SIN-INTERES" -> "3 cuotas sin interés". */
export function offerLabel(offerId: string): string {
  if (offerId === "PAGO-UNICO") return "Pago único";
  const match = /^CUOTAS-(\d+)-(SIN|CON)-INTERES$/.exec(offerId);
  if (match) return `${match[1]} cuotas ${match[2] === "SIN" ? "sin" : "con"} interés`;
  return offerId;
}

export const INVOICE_STAGE_LABEL: Record<InvoiceStage, string> = {
  upcoming: "Por vencer",
  due_today: "Vence hoy",
  overdue: "Vencida",
};

/**
 * Las columnas del archivo de facturas. El nombre técnico es el que va en la
 * primera fila del archivo; la descripción es para entender qué poner.
 */
export const IMPORT_COLUMNS: { name: string; label: string }[] = [
  { name: "external_id", label: "Número de factura" },
  { name: "description", label: "Concepto" },
  { name: "debtor_name", label: "Nombre del deudor" },
  { name: "debtor_document", label: "DNI o CUIT" },
  { name: "debtor_phone", label: "Teléfono" },
  { name: "debtor_email", label: "Email" },
  { name: "amount", label: "Monto" },
  { name: "currency", label: "Moneda" },
  { name: "due_date", label: "Vencimiento" },
];

export const AGE_BUCKET_LABEL: Record<AgeBucket, string> = {
  "0_30": "Hasta 30 días",
  "31_60": "31 a 60 días",
  "61_90": "61 a 90 días",
  "91_plus": "Más de 90 días",
};

export const CALL_STATUS_LABEL: Record<CallStatus, string> = {
  INITIATING: "Iniciando la llamada…",
  INITIATED: "Llamada en curso",
  IN_PROGRESS: "Llamada en curso",
  DONE: "Terminada",
  FAILED: "No se pudo llamar",
  NEEDS_REVIEW: "Para revisar",
};

/** Por qué el resultado de una llamada no se aplicó solo (lo revisa una persona). */
export const REVIEW_REASON_LABEL: Record<string, string> = {
  SIN_RESULTADO: "El agente no informó un resultado.",
  RESULTADO_INVALIDO: "El agente informó un resultado que no existe.",
  ACUERDO_SIN_OFERTA: "El agente informó un acuerdo sin decir qué oferta.",
  OFERTA_DESCONOCIDA: "El agente informó un acuerdo con una oferta que no se le dio.",
  ACUERDO_SIN_FOTO:
    "La llamada no se inició desde Mavic: el acuerdo no se puede validar contra las ofertas.",
  CASO_NO_NEGOCIABLE: "El caso ya tenía un resultado de otra llamada.",
};
