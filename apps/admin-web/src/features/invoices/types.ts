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
