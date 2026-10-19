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

// ---------------------------------------------------------------- carga de facturas

/** Un problema en una fila del archivo. `row` es la fila de Excel (1 = encabezado). */
export interface RowError {
  row: number;
  column: string | null;
  code: string;
  message: string;
}

/** Lo que devuelven /imports/preview (qué pasaría) e /imports (qué pasó). */
export interface ImportReport {
  ok: boolean;
  total_rows: number;
  debtors_created: number;
  debtors_updated: number;
  invoices_created: number;
  invoices_updated: number;
  invoices_unchanged: number;
  errors: RowError[];
  import_id: string | null; // null en la vista previa o si hubo errores
}

/** Una carga del historial. */
export interface ImportRecord {
  id: string;
  filename: string;
  user_id: string;
  total_rows: number;
  invoices_created: number;
  invoices_updated: number;
  invoices_unchanged: number;
  created_at: IsoDateTime;
}

export interface GenerationResult {
  cases_created: number;
  cases_updated: number;
  invoices_assigned: number;
}

// ---------------------------------------------------------------- reglas de negociación

/** Una regla tal como la devuelve el backend. Montos y porcentajes en texto. */
export interface Rule {
  id: string;
  name: string;
  description: string;
  min_amount: Money;
  max_amount: Money | null; // null = sin tope
  min_debt_age_days: number;
  max_debt_age_days: number | null;
  min_invoice_count: number;
  max_invoice_count: number | null;
  discount_pct: string;
  payment_days: number;
  max_installments: number; // 1 = solo pago único
  interest_pct: string;
  is_active: boolean;
}

/** Lo que se manda para crear o editar una regla (todo menos el id). */
export type RuleInput = Omit<Rule, "id">;

export type CompanyRole = Exclude<UserRole, "platform_admin">;

export interface CompanyWithAdmin {
  company: Company;
  admin: User;
}
