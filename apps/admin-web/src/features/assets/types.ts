export interface Page<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export interface AssetRecord {
  id: string;
  company: string;
  item: string;
  item_code: string;
  item_name: string;
  category_name: string;
  asset_number: string;
  serial_number: string | null;
  status: string;
  condition: string;
  current_custody_type: string;
  current_warehouse: string | null;
  current_warehouse_name: string | null;
  current_branch: string | null;
  current_branch_name: string | null;
  current_employee: string | null;
  current_employee_name: string | null;
  current_site: string | null;
  acquired_on: string | null;
  procurement_receipt_reference: string | null;
  purchase_order_reference: string | null;
  warranty_expires_on: string | null;
  expected_retirement_on: string | null;
  notes: string;
  acquisition_cost?: string | null;
  created_at: string;
}

export interface AssetCategory {
  id: string;
  company: string | null;
  code: string;
  name: string;
  tracking_method: "SERIALIZED" | "QUANTITY";
  is_controlled: boolean;
  is_active: boolean;
}

export interface AssetItem {
  id: string;
  company: string | null;
  category: string;
  item_code: string;
  name: string;
  manufacturer: string;
  model: string;
  unit_of_measure: string;
  is_active: boolean;
}

export interface AssetStore {
  id: string;
  company: string;
  branch: string | null;
  code: string;
  name: string;
  is_active: boolean;
}

export interface AssetMovement {
  id: string;
  asset: string;
  movement_type: string;
  from_custody_type: string | null;
  to_custody_type: string | null;
  moved_at: string;
  reason: string;
}

export interface AssetIssueLine {
  id: string;
  serialized_asset: string | null;
  requested_quantity: string;
  issued_quantity: string | null;
  returned_quantity: string;
}

export interface AssetIssue {
  id: string;
  issue_number: string;
  company: string;
  issue_type: string;
  employee: string | null;
  employee_name: string | null;
  branch: string | null;
  branch_name: string | null;
  expected_return_at: string | null;
  status: string;
  purpose: string;
  notes: string;
  lines: AssetIssueLine[];
}

export interface BranchOption {
  id: string;
  name: string;
  code: string;
}

export interface EmployeeOption {
  id: string;
  employee_number: string;
  full_name: string;
}

export interface RegistrationResult {
  id: string;
  registration_number: string;
  receipt_line: string;
  asset_item: string;
  destination_store: string;
  tracking_method: string;
  registered: string;
  remaining: string;
  results: Array<{ asset: string | null; quantity: string }>;
}
