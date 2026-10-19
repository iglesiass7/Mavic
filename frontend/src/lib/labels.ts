/**
 * Cómo se nombran en pantalla los valores que manda el backend.
 *
 * El backend usa códigos estables en inglés ("pending", "NO_MATCHING_RULE").
 * Las personas leen español claro. Esta es la única traducción: si un nombre
 * cambia, se cambia acá.
 */
import type { CallResult, CaseSort, CaseStatus, NoOfferReason, UserRole } from "./types";

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
