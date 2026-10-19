/**
 * Forma de las respuestas del backend (las mismas que muestra Swagger en /docs).
 *
 * Montos y porcentajes son `string` a propósito: el backend los manda como texto
 * exacto. Para mostrarlos se usan las funciones de format.ts; nunca se pasan a
 * número para hacer cuentas en el navegador.
 */

export type Money = string;
export type IsoDate = string; // "2026-09-10"
export type IsoDateTime = string; // "2026-10-19T16:49:25Z"

export type Permission =
  | "view_portfolio"
  | "operate_portfolio"
  | "manage_rules"
  | "manage_users"
  | "manage_companies";

export type UserRole = "admin" | "operator" | "supervisor" | "platform_admin";

export interface User {
  id: string;
  company_id: string | null;
  name: string;
  email: string;
  role: UserRole;
  is_active: boolean;
  last_login_at: IsoDateTime | null;
  created_at: IsoDateTime;
}

export interface Company {
  id: string;
  name: string;
  is_active: boolean;
  created_at: IsoDateTime;
}

export interface Me {
  user: User;
  company: Company | null;
  permissions: Permission[];
}

export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export type CaseStatus =
  | "pending"
  | "contacted"
  | "agreement"
  | "disputed"
  | "escalated"
  | "closed";

export type CaseSort = "oldest_debt" | "highest_amount" | "newest";

export interface Debtor {
  id: string;
  name: string;
  document_number: string;
  phone: string;
  email: string;
}

export interface CaseSummary {
  id: string;
  number: number;
  status: CaseStatus;
  debtor: Debtor;
  invoice_count: number;
  total_amount: Money;
  oldest_due_date: IsoDate;
  debt_age_days: number;
}

export type InvoiceStage = "upcoming" | "due_today" | "overdue";

export interface Invoice {
  id: string;
  external_id: string;
  description: string;
  amount: Money;
  currency: string;
  due_date: IsoDate;
  stage: InvoiceStage;
  debtor_id: string;
  debtor_name: string;
  case_id: string | null;
  case_number: number | null;
}

export interface CaseDetail extends CaseSummary {
  invoices: Invoice[];
}

export interface SinglePaymentOffer {
  offer_id: string;
  original_amount: Money;
  discount_pct: string;
  discount_amount: Money;
  total_amount: Money;
  pay_by: IsoDate;
}

export interface Installment {
  number: number;
  due_date: IsoDate;
  amount: Money;
}

export interface InstallmentsOffer {
  offer_id: string;
  original_amount: Money;
  interest_pct: string;
  interest_amount: Money;
  total_amount: Money;
  installment_count: number;
  installment_amount: Money;
  schedule: Installment[];
}

export type NoOfferReason = "NO_MATCHING_RULE" | "CASE_NOT_NEGOTIABLE";

export interface CaseOffers {
  case_id: string;
  case_number: number;
  case_status: CaseStatus;
  currency: string;
  total_amount: Money;
  debt_age_days: number;
  invoice_count: number;
  rule: { id: string; name: string } | null;
  has_offer: boolean;
  reason: NoOfferReason | null;
  single_payment: SinglePaymentOffer | null;
  installments: InstallmentsOffer | null;
}

export type CallResult = "CONTACTADO" | "DESCONOCIMIENTO" | "ACUERDO" | "DERIVACION_HUMANA";

export interface TranscriptTurn {
  role: "agent" | "user" | string;
  message: string | null;
  time_in_call_secs: number | null;
}

export interface Agreement {
  offer_id: string;
  modality: "PAGO_UNICO" | "CUOTAS";
  currency: string;
  original_amount: Money;
  total_amount: Money;
  installment_count: number;
  schedule: Installment[];
  created_at: IsoDateTime;
}

export interface Conversation {
  id: string;
  provider_conversation_id: string;
  started_at: IsoDateTime;
  identity_verified: boolean;
  offered: string[];
  result: CallResult | null;
  unknown_count: number | null;
  agreement: Agreement | null;
  summary: string | null;
  call_duration_secs: number | null;
  transcript: TranscriptTurn[] | null;
}
