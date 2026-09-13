export type InvoiceStatus =
  | "DRAFT"
  | "UNDER_REVIEW"
  | "APPROVED"
  | "ISSUED"
  | "PARTIALLY_PAID"
  | "PAID"
  | "VOIDED"
  | "CANCELLED";

export interface InvoiceLine {
  id: string;
  line_number: number;
  contract_service: string | null;
  site: string | null;
  billing_rule: string | null;
  description: string;
  quantity: string;
  unit: string;
  unit_price: string;
  gross_amount: string;
  discount_amount: string;
  taxable_amount: string;
  tax_amount: string;
  line_total: string;
  revenue_account: string;
  cost_center: string | null;
  created_at: string;
}

export interface InvoiceDetail {
  id: string;
  invoice_number: string;
  company: string;
  client: string;
  contract: string | null;
  invoice_type: string;
  currency: string;
  invoice_date: string;
  service_period_start: string | null;
  service_period_end: string | null;
  due_date: string;
  client_po_reference: string;
  client_reference: string;
  source_billing_schedule: string | null;
  subtotal: string;
  discount_total: string;
  tax_total: string;
  adjustment_total: string;
  total_amount: string;
  amount_paid: string;
  balance_due: string;
  status: InvoiceStatus;
  generated_by: string;
  reviewed_by: string | null;
  reviewed_at: string | null;
  approved_by: string | null;
  approved_at: string | null;
  issued_by: string | null;
  issued_at: string | null;
  voided_by: string | null;
  voided_at: string | null;
  void_reason: string;
  billing_name_snapshot: string;
  billing_address_snapshot: string;
  tax_registration_snapshot: string;
  payment_terms_snapshot: number;
  payment_instructions_snapshot: string;
  notes_snapshot: string;
  posted_at: string | null;
  created_at: string;
  updated_at: string;
  is_overdue: boolean;
  pdf_available: boolean;
  lines: InvoiceLine[];
  receipt_allocations?: InvoiceReceiptAllocation[];
}

export interface InvoiceReceiptAllocation {
  id: string;
  receipt: string;
  receipt_number: string;
  receipt_date: string;
  payment_method: string;
  reference: string;
  amount: string;
  allocated_at: string;
}

export type InvoiceSummary = InvoiceDetail;

export interface PaginatedResponse<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export type InvoiceQuery = {
  [key: string]: string | number | boolean | null | undefined;
  company?: string;
  client?: string;
  contract?: string;
  status?: string;
  invoice_type?: string;
  search?: string;
  ordering?: string;
  page?: string | number;
};

export const INVOICE_TYPE_OPTIONS: [string, string][] = [
  ["STANDARD", "Standard"],
  ["RECURRING", "Recurring"],
  ["ADJUSTMENT", "Adjustment"],
  ["FINAL", "Final"],
  ["OTHER", "Other"],
];

export interface BillingProfile {
  id: string;
  client: string;
  company: string;
  billing_name: string;
  billing_address: string;
  billing_email: string;
  billing_phone: string;
  tax_registration_number: string;
  payment_terms_days: number;
  currency: string;
  default_billing_frequency: string;
  default_revenue_account: string | null;
  default_receivable_account: string;
  default_tax_account: string | null;
  default_discount_account: string | null;
  default_payment_instructions: string;
  invoice_notes: string;
  is_active: boolean;
}

export interface Contract {
  id: string;
  company: string;
  client: string;
  contract_number: string;
  contract_type: string;
  title: string;
  status: string;
  currency: string;
  start_date: string;
  end_date: string | null;
}

export interface ContractServiceOption {
  id: string;
  contract: string;
  service_type: string;
  name: string;
}

export interface SiteOption {
  id: string;
  contract: string;
  client: string;
  company: string;
  site_code: string;
  name: string;
}

export interface BillingRuleOption {
  id: string;
  contract_service: string | null;
  site: string | null;
  description: string;
}

export interface AccountOption {
  id: string;
  company: string;
  code: string;
  name: string;
  account_type: string;
}

export const INVOICE_CREATE_FIELDS = [
  "billing_profile",
  "invoice_date",
  "invoice_type",
  "contract",
  "service_period_start",
  "service_period_end",
  "client_po_reference",
  "client_reference",
] as const;

export const INVOICE_DRAFT_UPDATE_FIELDS = [
  "contract",
  "invoice_date",
  "service_period_start",
  "service_period_end",
  "client_po_reference",
  "client_reference",
] as const;

export const INVOICE_LINE_WRITE_FIELDS = [
  "description",
  "quantity",
  "unit",
  "unit_price",
  "discount_amount",
  "tax_rate",
  "revenue_account",
  "cost_center",
  "contract_service",
  "site",
  "billing_rule",
] as const;

export interface InvoiceCreateInput {
  billing_profile: string;
  invoice_date: string;
  invoice_type: string;
  contract?: string | null;
  service_period_start?: string | null;
  service_period_end?: string | null;
  client_po_reference?: string;
  client_reference?: string;
}

export interface InvoiceDraftUpdateInput {
  contract?: string | null;
  invoice_date?: string;
  service_period_start?: string | null;
  service_period_end?: string | null;
  client_po_reference?: string;
  client_reference?: string;
}

export interface InvoiceLineWriteInput {
  description: string;
  quantity: string;
  unit?: string;
  unit_price: string;
  discount_amount?: string;
  tax_rate?: string;
  revenue_account: string;
  cost_center?: string | null;
  contract_service?: string | null;
  site?: string | null;
  billing_rule?: string | null;
}
