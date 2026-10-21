export interface Page<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export interface RequisitionLine {
  id: string;
  description: string;
  quantity: string;
  estimated_unit_price: string;
  estimated_total: string;
  expense_account: string;
  expense_account_code: string;
  expense_account_name: string;
}

export interface PurchaseRequisition {
  id: string;
  company: string;
  requisition_number: string;
  required_date: string;
  purpose: string;
  status: string;
  branch: string | null;
  branch_name: string | null;
  department: string | null;
  department_name: string | null;
  cost_center: string | null;
  cost_center_name: string | null;
  created_by_name: string;
  approved_by_name: string | null;
  estimated_total: string;
  lines: RequisitionLine[];
  created_at: string;
}

export interface OrderLine {
  id: string;
  requisition_line: string;
  requisition_line_description: string;
  description: string;
  quantity: string;
  unit_price: string;
  tax_amount: string;
  line_total: string;
  received_quantity: string;
}

export interface PurchaseOrder {
  id: string;
  company: string;
  requisition: string;
  requisition_number: string;
  vendor: string;
  vendor_code: string;
  vendor_name: string;
  order_number: string;
  order_date: string;
  status: string;
  created_by_name: string;
  approved_by_name: string | null;
  total_amount: string;
  lines: OrderLine[];
  created_at: string;
}

export interface ReceiptLine {
  id: string;
  purchase_order_line: string;
  description: string;
  ordered_quantity: string;
  quantity: string;
  accepted_quantity: string;
  notes: string;
}

export interface PurchaseReceipt {
  id: string;
  company: string;
  purchase_order: string;
  purchase_order_number: string;
  vendor: string;
  vendor_name: string;
  receipt_number: string;
  receipt_date: string;
  receipt_type: "GOODS" | "SERVICE";
  status: string;
  received_by_name: string;
  lines: ReceiptLine[];
  created_at: string;
}

export interface ExpenseAccount {
  id: string;
  code: string;
  name: string;
  account_type: string;
}

export interface VendorOption {
  id: string;
  code: string;
  name: string;
  is_active: boolean;
}
