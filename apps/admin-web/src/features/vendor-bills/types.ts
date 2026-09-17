export type VendorBillStatus =
  | "DRAFT"
  | "SUBMITTED"
  | "APPROVED"
  | "REJECTED"
  | "POSTED"
  | "PARTIALLY_PAID"
  | "PAID"
  | "CLOSED"
  | "CANCELLED";

export interface VendorBillLine {
  id: string;
  purchase_order_line: string | null;
  receipt_line: string | null;
  description: string;
  quantity: string;
  unit_price: string;
  tax_amount: string;
  line_total: string;
  expense_account: string;
  expense_account_code: string;
  expense_account_name: string;
}

export interface VendorBill {
  id: string;
  bill_number: string;
  vendor_invoice_number: string;
  vendor: string;
  vendor_code: string;
  vendor_name: string;
  bill_date: string;
  due_date: string;
  status: VendorBillStatus;
  total_amount: string;
  paid_amount: string;
  outstanding_amount: string;
  purchase_order?: string | null;
  match_type?: "TWO_WAY" | "THREE_WAY";
  subtotal?: string;
  tax_amount?: string;
  match_exception?: string;
  lines?: VendorBillLine[];
}

export interface VendorBillPage {
  count: number;
  next: string | null;
  previous: string | null;
  results: VendorBill[];
}

export interface VendorBillAttachment {
  id: string;
  filename: string;
  content_type: string;
  size: number;
  created_at: string;
}

export interface VendorOption {
  id: string;
  code: string;
  name: string;
  is_active: boolean;
}
export interface AccountOption {
  id: string;
  code: string;
  name: string;
  account_type: string;
}

export const VENDOR_BILL_HEADER_FIELDS = [
  "vendor",
  "purchase_order",
  "vendor_invoice_number",
  "bill_number",
  "bill_date",
  "due_date",
  "match_type",
] as const;
export const VENDOR_BILL_LINE_FIELDS = [
  "description",
  "quantity",
  "unit_price",
  "tax_amount",
  "expense_account",
  "purchase_order_line",
  "receipt_line",
] as const;
